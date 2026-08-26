import os
import httpx
import uuid
from typing import Optional, Set
from jose import jwt, JWTError
from dotenv import load_dotenv
from fastapi import Request
from sqlalchemy.orm import Session
from database import Profile, SessionLocal, StaffAssignment, Class, AuditLog

load_dotenv(override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
ADMIN_EMAILS = [e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()]

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

def is_superadmin(user: Optional[dict]) -> bool:
    """Returns True if the user is a superadmin or in ADMIN_EMAILS environment list."""
    if not user:
        return False
    email = (user.get("email") or "").lower().strip()
    role = (user.get("role") or "").lower().strip()
    if role == "superadmin":
        return True
    if email and email in ADMIN_EMAILS:
        return True
    return False

def can_manage_staff(user: Optional[dict]) -> bool:
    """Returns True if user has permission to manage staff accounts and class assignments."""
    if not user:
        return False
    if is_superadmin(user):
        return True
    email = (user.get("email") or "").lower().strip()
    if email == "technicaltrainer1@kahedu.edu.in":
        return True
    if user.get("role") in ["superadmin", "admin"]:
        return True
    return False

def can_view_activity_log(user: Optional[dict]) -> bool:
    """Returns True ONLY for Superadmin accounts. Strictly restricted from regular trainers/admins."""
    return is_superadmin(user)

def get_user_assigned_class_ids(db: Session, user_id: str) -> Set[str]:
    """Returns set of all class IDs accessible by a staff member (both direct and category-level)."""
    try:
        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
    except Exception:
        return set()

    assignments = db.query(StaffAssignment).filter(StaffAssignment.profile_id == uid).all()
    if not assignments:
        # If no specific scoped restrictions are set, grant default access to all classes
        all_cls = db.query(Class.id).all()
        return {cid for (cid,) in all_cls}

    class_ids = set()
    for a in assignments:
        if a.class_id:
            class_ids.add(a.class_id)
        if a.category_id:
            # Add all classes belonging to this category
            cat_classes = db.query(Class.id).filter(Class.category_id == a.category_id).all()
            for (cid,) in cat_classes:
                class_ids.add(cid)

    return class_ids

def can_access_class(db: Session, user: Optional[dict], class_id: str) -> bool:
    """Check whether a user has permission to view or manage a class."""
    if not user:
        return False
    if is_superadmin(user):
        return True
    assigned_ids = get_user_assigned_class_ids(db, user["id"])
    return str(class_id) in assigned_ids

def can_access_category(db: Session, user: Optional[dict], category_id: str) -> bool:
    """Check whether a user has permission for a category."""
    if not user:
        return False
    if is_superadmin(user):
        return True
    try:
        uid = uuid.UUID(user["id"]) if isinstance(user["id"], str) else user["id"]
    except Exception:
        return False

    assignments = db.query(StaffAssignment).filter(StaffAssignment.profile_id == uid).all()
    if not assignments:
        return True

    # Check direct assignment to category or any class in this category
    direct = db.query(StaffAssignment).filter(
        StaffAssignment.profile_id == uid,
        StaffAssignment.category_id == category_id
    ).first()
    if direct:
        return True
    assigned_ids = get_user_assigned_class_ids(db, user["id"])
    cat_class_count = db.query(Class).filter(
        Class.category_id == category_id,
        Class.id.in_(assigned_ids)
    ).count()
    return cat_class_count > 0

def log_audit_event(
    db: Session,
    request: Optional[Request],
    user: Optional[dict],
    action_type: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    description: str = ""
) -> None:
    """Records a mutation audit log entry in the audit_logs table."""
    try:
        ip_addr = None
        if request:
            ip_addr = request.headers.get("x-forwarded-for") or (request.client.host if request.client else None)
            if ip_addr and "," in ip_addr:
                ip_addr = ip_addr.split(",")[0].strip()

        actor_id = user.get("id") if user else None
        actor_email = user.get("email") if user else "system"
        actor_name = user.get("full_name") if user else "System"

        log_entry = AuditLog(
            actor_id=str(actor_id) if actor_id else None,
            actor_email=actor_email,
            actor_name=actor_name,
            action_type=action_type,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            description=description,
            ip_address=ip_addr,
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        print(f"[Audit Log Error] {e}")
        try:
            db.rollback()
        except Exception:
            pass

def get_or_create_profile(user_id: str, email: str, full_name: str = None) -> Profile:
    db = SessionLocal()
    try:
        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        profile = db.query(Profile).filter(Profile.id == uid).first()
        is_super = email.lower().strip() in ADMIN_EMAILS
        default_role = "superadmin" if is_super else "staff"
        
        if not profile:
            profile = Profile(
                id=uid,
                email=email,
                full_name=full_name or email.split("@")[0],
                role=default_role,
            )
            db.add(profile)
            db.commit()
            db.refresh(profile)
        elif is_super and profile.role != "superadmin":
            profile.role = "superadmin"
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

    user_dict = {
        "id": str(user_id),
        "email": email or profile.email,
        "full_name": profile.full_name,
        "role": profile.role,
    }
    user_dict["is_superadmin"] = is_superadmin(user_dict)
    user_dict["can_manage_staff"] = can_manage_staff(user_dict)
    user_dict["can_view_activity_log"] = can_view_activity_log(user_dict)
    return user_dict
