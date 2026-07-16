import os
import httpx
import uuid
from typing import Optional
from jose import jwt, JWTError
from dotenv import load_dotenv
from fastapi import Request
from database import Profile, SessionLocal

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
ADMIN_EMAILS = [e.strip() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()]

# When True: skip our own email-verified check.
# But Supabase itself still blocks sign-in unless:
#   (a) you disable "Confirm email" in Supabase Dashboard > Auth > Settings, OR
#   (b) SUPABASE_SERVICE_ROLE_KEY is set (we'll auto-confirm users on registration)
SKIP_EMAIL_VERIFICATION = os.getenv("SKIP_EMAIL_VERIFICATION", "false").lower() == "true"


def _anon_headers() -> dict:
    return {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}


def _service_headers() -> dict:
    """Headers using the service role key — bypasses RLS and auth checks."""
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


# ─── Supabase Auth REST helpers ───────────────────────────────────────────────

def supabase_sign_up(email: str, password: str, full_name: str) -> dict:
    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/signup",
        json={"email": email, "password": password, "data": {"full_name": full_name}},
        headers=_anon_headers(), timeout=15,
    )
    return r.json()


def supabase_sign_in(email: str, password: str) -> dict:
    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        json={"email": email, "password": password},
        headers=_anon_headers(), timeout=15,
    )
    data = r.json()
    data["_status_code"] = r.status_code
    return data


def supabase_admin_create_user(email: str, password: str, full_name: str) -> dict:
    """Create a user directly via Admin API to bypass rate limits and auto-confirm email."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {}
    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"full_name": full_name}
        },
        headers=_service_headers(), timeout=15,
    )
    data = r.json()
    data["_status_code"] = r.status_code
    return data


def supabase_admin_confirm_user(user_id: str) -> bool:
    """
    Force-confirm a user's email using the Service Role key.
    Requires SUPABASE_SERVICE_ROLE_KEY to be set.
    """
    if not SUPABASE_SERVICE_ROLE_KEY:
        return False
    r = httpx.put(
        f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
        json={"email_confirm": True},
        headers=_service_headers(), timeout=10,
    )
    return r.status_code == 200


def supabase_admin_get_user_by_email(email: str) -> Optional[dict]:
    """Look up a Supabase auth user by email using the admin API."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        return None
    r = httpx.get(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        params={"email": email},
        headers=_service_headers(), timeout=10,
    )
    if r.status_code != 200:
        return None
    data = r.json()
    users = data.get("users", [])
    for u in users:
        if u.get("email", "").lower() == email.lower():
            return u
    return None


def supabase_resend_confirmation(email: str) -> tuple[bool, str]:
    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/resend",
        json={"type": "signup", "email": email},
        headers=_anon_headers(), timeout=15,
    )
    data = r.json()

    # 200 or empty body = success
    if r.status_code in (200, 204) or data == {}:
        return True, "Verification email sent! Check your inbox (and spam folder)."

    err = data.get("error_description") or data.get("message") or data.get("msg") or str(data)
    if "rate limit" in str(err).lower() or r.status_code == 429:
        return False, "Too many emails sent — Supabase limits to ~2–3 per hour on free plan. Wait a bit and try again."
    if "already confirmed" in str(err).lower():
        return False, "This email is already verified! Try signing in directly."

    return False, f"Could not send email: {err}"


def verify_supabase_jwt(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(
            token, SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        return payload
    except JWTError:
        return None


# ─── Profile helpers ──────────────────────────────────────────────────────────

def get_or_create_profile(user_id: str, email: str, full_name: str = None) -> Profile:
    db = SessionLocal()
    try:
        uid = uuid.UUID(user_id)
        profile = db.query(Profile).filter(Profile.id == uid).first()
        if not profile:
            role = "admin" if email in ADMIN_EMAILS else "student"
            profile = Profile(
                id=uid,
                email=email,
                full_name=full_name or email.split("@")[0],
                role=role,
            )
            db.add(profile)
            db.commit()
            db.refresh(profile)
        else:
            if email in ADMIN_EMAILS and profile.role != "admin":
                profile.role = "admin"
                db.commit()
                db.refresh(profile)
        return profile
    finally:
        db.close()


# ─── Request-level current user ───────────────────────────────────────────────

def get_current_user(request: Request) -> Optional[dict]:
    token = request.session.get("access_token")
    if not token:
        return None

    payload = verify_supabase_jwt(token)

    # If JWT secret doesn't match, fall back to stored session data
    user_id = (payload or {}).get("sub") or request.session.get("user_id")
    email = (payload or {}).get("email", "")
    email_confirmed = (payload or {}).get("email_confirmed_at")

    if not user_id:
        return None

    db = SessionLocal()
    try:
        uid = uuid.UUID(user_id)
        profile = db.query(Profile).filter(Profile.id == uid).first()
    finally:
        db.close()

    if not profile:
        return None

    is_confirmed = bool(email_confirmed) or SKIP_EMAIL_VERIFICATION

    return {
        "id": str(user_id),
        "email": email or profile.email,
        "full_name": profile.full_name,
        "role": profile.role,
        "leetcode_username": profile.leetcode_username,
        "email_confirmed": is_confirmed,
    }
