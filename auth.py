import os
import httpx
import uuid
from typing import Optional
from jose import jwt, JWTError
from dotenv import load_dotenv
from fastapi import Request
from database import Profile, SessionLocal

load_dotenv(override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")

def _anon_headers() -> dict:
    return {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}

def _service_headers() -> dict:
    """Headers using the service role key — bypasses RLS and auth checks."""
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }

def supabase_sign_in(email: str, password: str) -> dict:
    try:
        r = httpx.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            json={"email": email, "password": password},
            headers=_anon_headers(), timeout=15,
        )
        data = r.json()
        data["_status_code"] = r.status_code
        return data
    except Exception as e:
        return {"error": "Connection error", "msg": f"Failed to connect to Supabase: {str(e)}"}

def supabase_admin_create_user(email: str, password: str, full_name: str) -> dict:
    """Create an admin user directly via Admin API to bypass rate limits and auto-confirm email."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {"error": "Missing SUPABASE_SERVICE_ROLE_KEY"}
    try:
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
    except Exception as e:
        return {"error": "Connection error", "msg": f"Failed to connect to Supabase Admin API: {str(e)}"}

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

def get_or_create_profile(user_id: str, email: str, full_name: str = None) -> Profile:
    db = SessionLocal()
    try:
        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        profile = db.query(Profile).filter(Profile.id == uid).first()
        if not profile:
            profile = Profile(
                id=uid,
                email=email,
                full_name=full_name or email.split("@")[0],
                role="admin", # Everyone who successfully logs in is an admin
            )
            db.add(profile)
            db.commit()
            db.refresh(profile)
        return profile
    finally:
        db.close()

def get_current_user(request: Request) -> Optional[dict]:
    token = request.session.get("access_token")
    if not token:
        return None

    payload = verify_supabase_jwt(token)
    user_id = (payload or {}).get("sub") or request.session.get("user_id")
    email = (payload or {}).get("email", "")

    if not user_id:
        return None

    db = SessionLocal()
    try:
        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        profile = db.query(Profile).filter(Profile.id == uid).first()
    except Exception:
        profile = None
    finally:
        db.close()

    if not profile:
        return None

    return {
        "id": str(user_id),
        "email": email or profile.email,
        "full_name": profile.full_name,
        "role": profile.role,
    }
