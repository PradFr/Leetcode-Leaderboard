import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List
import uuid
import io
import json
import pandas as pd
from fastapi import APIRouter, Request, Form, Depends, UploadFile, File, Query
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func

import auth
from database import (
    get_db, Profile, Class, Invite, Student, Category,
    TestResult, StaffAssignment, AuditLog, RefreshLog
)
from utils import (
    fetch_leetcode_stats, format_relative_time,
    get_inactivity_status, get_inactivity_days
)

router = APIRouter(prefix="/admin")
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Register custom Jinja template filters
templates.env.filters["relative_time"] = format_relative_time
templates.env.filters["inactivity_status"] = get_inactivity_status
templates.env.filters["inactivity_days"] = get_inactivity_days


def _get_admin(request: Request):
    user = auth.get_current_user(request)
    if not user or user.get("role") not in ("admin", "superadmin", "staff"):
        return None
    return user


def _render_403(request: Request, message: str = "You do not have permission to access this resource."):
    return HTMLResponse(
        f"""
        <!DOCTYPE html>
        <html>
        <head><title>403 Forbidden</title><link rel="stylesheet" href="/static/css/main.css"></head>
        <body style="display:flex;align-items:center;justify-content:center;min-height:100vh;background:var(--bg-canvas);">
          <div class="card" style="max-width:440px;text-align:center;padding:32px;">
            <div style="font-size:3rem;margin-bottom:12px;">🚫</div>
            <h2 style="margin-bottom:8px;color:var(--red);">403 Forbidden</h2>
            <p style="color:var(--text-secondary);margin-bottom:20px;">{message}</p>
            <a href="/admin" class="btn btn-primary">Return to Dashboard</a>
          </div>
        </body>
        </html>
        """,
        status_code=403
    )


# ─── Dashboard ────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    is_super = auth.is_superadmin(user)
    latest_refresh = db.query(RefreshLog).order_by(RefreshLog.timestamp.desc()).first()
    last_refreshed_str = format_relative_time(latest_refresh.timestamp) if latest_refresh else "Never"

    if is_super:
        total_classes = db.query(Class).count()
        total_students = db.query(Student).count()
        total_admins = db.query(Profile).count()
        total_solved = sum((s.solved_total or 0) for s in db.query(Student).all())
        classes = db.query(Class).order_by(Class.created_at.desc()).limit(6).all()
    else:
        assigned_ids = auth.get_user_assigned_class_ids(db, user["id"])
        total_classes = len(assigned_ids)
        total_students = db.query(Student).filter(Student.class_id.in_(assigned_ids)).count() if assigned_ids else 0
        total_admins = db.query(Profile).count()
        assigned_students = db.query(Student).filter(Student.class_id.in_(assigned_ids)).all() if assigned_ids else []
        total_solved = sum((s.solved_total or 0) for s in assigned_students)
        classes = db.query(Class).filter(Class.id.in_(assigned_ids)).order_by(Class.created_at.desc()).limit(6).all() if assigned_ids else []

    class_data = []
    for cls in classes:
        count = db.query(Student).filter(Student.class_id == cls.id).count()
        class_data.append({"cls": cls, "student_count": count})

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "user": user,
        "is_superadmin": is_super,
        "total_classes": total_classes,
        "total_students": total_students,
        "total_solved": total_solved,
        "total_admins": total_admins,
        "recent_classes": class_data,
        "latest_refresh": latest_refresh,
        "last_refreshed_str": last_refreshed_str,
    })


# ─── Manage Staff/Admins (Superadmin Only) ───────────────────────────────────

@router.get("/staff", response_class=HTMLResponse)
async def manage_staff(request: Request, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not auth.can_manage_staff(user):
        return _render_403(request, "Only authorized admins can manage staff accounts and permissions.")

    profiles = db.query(Profile).order_by(Profile.created_at.desc()).all()
    all_classes = db.query(Class).order_by(Class.name).all()
    all_categories = db.query(Category).order_by(Category.name).all()

    # Preload staff assignments for each profile
    staff_data = []
    for p in profiles:
        assignments = db.query(StaffAssignment).filter(StaffAssignment.profile_id == p.id).all()
        assigned_class_ids = [a.class_id for a in assignments if a.class_id]
        assigned_cat_ids = [a.category_id for a in assignments if a.category_id]
        
        assigned_classes = [c for c in all_classes if c.id in assigned_class_ids]
        assigned_categories = [cat for cat in all_categories if cat.id in assigned_cat_ids]
        
        staff_data.append({
            "profile": p,
            "is_super": auth.is_superadmin({"email": p.email, "role": p.role}),
            "assigned_classes": assigned_classes,
            "assigned_categories": assigned_categories,
            "assigned_class_ids": assigned_class_ids,
            "assigned_cat_ids": assigned_cat_ids,
        })

    return templates.TemplateResponse("admin/staff.html", {
        "request": request,
        "user": user,
        "is_superadmin": auth.is_superadmin(user),
        "staff_data": staff_data,
        "all_classes": all_classes,
        "all_categories": all_categories,
    })


@router.post("/staff/add")
async def add_staff(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    role: str = Form("staff"),
    db: Session = Depends(get_db)
):
    user = _get_admin(request)
    if not user or not auth.can_manage_staff(user):
        return _render_403(request, "Only authorized admins can add staff.")

    is_super = auth.is_superadmin(user)

    # Security Rule: Only Super Admins can create another Super Admin account.
    if role == "superadmin" and not is_super:
        return _render_403(request, "Only Super Administrators can create Super Admin accounts.")

    actual_role = "superadmin" if (role == "superadmin" and is_super) else "staff"

    email_clean = email.strip().lower()
    existing = db.query(Profile).filter(func.lower(Profile.email) == email_clean).first()
    if existing:
        return RedirectResponse("/admin/staff?error=Email+already+exists", status_code=302)

    res = auth.supabase_admin_create_user(email_clean, password, full_name.strip())
    if res.get("error"):
        err = res.get("message") or res.get("msg") or "Could not create user in Supabase"
        return RedirectResponse(f"/admin/staff?error={err}", status_code=302)

    user_id = res.get("id")
    if user_id:
        new_profile = Profile(
            id=uuid.UUID(user_id),
            email=email_clean,
            full_name=full_name.strip(),
            role=actual_role
        )
        db.add(new_profile)
        db.commit()

        auth.log_audit_event(
            db, request, user,
            action_type="staff_created",
            target_type="staff",
            target_id=str(user_id),
            description=f"Created {actual_role} account for '{full_name.strip()}' ({email_clean})"
        )

    return RedirectResponse("/admin/staff?success=Staff+member+added+successfully", status_code=302)


@router.post("/staff/delete/{admin_id}")
async def delete_staff(request: Request, admin_id: str, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user or not auth.can_manage_staff(user):
        return _render_403(request, "Only authorized admins can remove staff.")

    is_super = auth.is_superadmin(user)

    if user.get("id") == admin_id:
        return RedirectResponse("/admin/staff?error=You+cannot+delete+your+own+account", status_code=302)

    try:
        uid = uuid.UUID(admin_id)
        profile = db.query(Profile).filter(Profile.id == uid).first()
        if profile:
            if profile.role == "superadmin":
                if not is_super:
                    return _render_403(request, "Only Super Administrators can remove Super Admin accounts.")
                if profile.email.lower() in auth.ADMIN_EMAILS:
                    return RedirectResponse("/admin/staff?error=Primary+Super+Admin+accounts+cannot+be+deleted", status_code=302)
            
            p_name = profile.full_name or profile.email
            p_email = profile.email
            db.delete(profile)
            db.commit()

            auth.log_audit_event(
                db, request, user,
                action_type="staff_deleted",
                target_type="staff",
                target_id=admin_id,
                description=f"Deleted staff member '{p_name}' ({p_email})"
            )
    except Exception as e:
        return RedirectResponse(f"/admin/staff?error=Invalid+user+id", status_code=302)

    return RedirectResponse("/admin/staff?success=Staff+member+removed", status_code=302)


@router.post("/staff/{admin_id}/assignments")
async def update_staff_assignments(
    request: Request,
    admin_id: str,
    db: Session = Depends(get_db)
):
    user = _get_admin(request)
    if not user or not auth.can_manage_staff(user):
        return _render_403(request, "Only authorized admins can update staff assignments.")

    try:
        uid = uuid.UUID(admin_id)
        profile = db.query(Profile).filter(Profile.id == uid).first()
        if not profile:
            return RedirectResponse("/admin/staff?error=Profile+not+found", status_code=302)

        form_data = await request.form()
        class_ids = form_data.getlist("class_ids")
        category_ids = form_data.getlist("category_ids")

        # Clear existing assignments
        db.query(StaffAssignment).filter(StaffAssignment.profile_id == uid).delete()

        # Add new assignments
        for cid in class_ids:
            if cid.strip():
                db.add(StaffAssignment(profile_id=uid, class_id=cid.strip()))
        for cat_id in category_ids:
            if cat_id.strip():
                db.add(StaffAssignment(profile_id=uid, category_id=cat_id.strip()))

        db.commit()

        auth.log_audit_event(
            db, request, user,
            action_type="staff_permissions_changed",
            target_type="staff",
            target_id=admin_id,
            description=f"Updated access permissions for '{profile.full_name or profile.email}': {len(class_ids)} class(es), {len(category_ids)} category(ies)"
        )

        return RedirectResponse("/admin/staff?success=Staff+assignments+updated+successfully", status_code=302)
    except Exception as e:
        return RedirectResponse(f"/admin/staff?error=Could+not+update+assignments:+{str(e)}", status_code=302)


@router.post("/staff/{admin_id}/role")
async def update_staff_role(
    request: Request,
    admin_id: str,
    role: str = Form(...),
    db: Session = Depends(get_db)
):
    user = _get_admin(request)
    if not user or not auth.can_manage_staff(user):
        return _render_403(request, "Only authorized admins can change staff roles.")

    is_super = auth.is_superadmin(user)
    if role == "superadmin" and not is_super:
        return _render_403(request, "Only Super Administrators can assign the Super Admin role.")

    try:
        uid = uuid.UUID(admin_id)
        profile = db.query(Profile).filter(Profile.id == uid).first()
        if not profile:
            return RedirectResponse("/admin/staff?error=Profile+not+found", status_code=302)

        if profile.role == "superadmin" and not is_super:
            return _render_403(request, "Only Super Administrators can modify Super Admin accounts.")

        new_role = "superadmin" if (role == "superadmin" and is_super) else "staff"
        old_role = profile.role
        profile.role = new_role
        db.commit()

        auth.log_audit_event(
            db, request, user,
            action_type="staff_role_changed",
            target_type="staff",
            target_id=admin_id,
            description=f"Changed role of '{profile.full_name or profile.email}' from '{old_role}' to '{new_role}'"
        )

        return RedirectResponse("/admin/staff?success=Role+updated+successfully", status_code=302)
    except Exception as e:
        return RedirectResponse(f"/admin/staff?error=Could+not+update+role", status_code=302)


# ─── Classes & Categories ─────────────────────────────────────────────────────

@router.get("/classes", response_class=HTMLResponse)
async def admin_classes(request: Request, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    is_super = auth.is_superadmin(user)
    latest_refresh = db.query(RefreshLog).order_by(RefreshLog.timestamp.desc()).first()
    last_refreshed_str = format_relative_time(latest_refresh.timestamp) if latest_refresh else "Never"

    if is_super:
        categories = db.query(Category).order_by(Category.name).all()
        classes = db.query(Class).order_by(Class.created_at.desc()).all()
    else:
        assigned_ids = auth.get_user_assigned_class_ids(db, user["id"])
        classes = db.query(Class).filter(Class.id.in_(assigned_ids)).order_by(Class.created_at.desc()).all() if assigned_ids else []
        cat_ids = {c.category_id for c in classes if c.category_id}
        categories = db.query(Category).filter(Category.id.in_(cat_ids)).order_by(Category.name).all() if cat_ids else []

    class_data = []
    for cls in classes:
        members = db.query(Student).filter(Student.class_id == cls.id).all()
        top_user = max(members, key=lambda s: s.points or 0) if members else None
        invite = db.query(Invite).filter(Invite.class_id == cls.id, Invite.is_active == True).first()
        class_data.append({"cls": cls, "student_count": len(members), "top_user": top_user, "invite": invite})

    category_data = []
    for cat in categories:
        cls_count = sum(1 for c in classes if c.category_id == cat.id)
        category_data.append({"cat": cat, "class_count": cls_count})

    return templates.TemplateResponse("admin/classes.html", {
        "request": request,
        "user": user,
        "is_superadmin": is_super,
        "classes": class_data,
        "categories": categories,
        "category_data": category_data,
        "latest_refresh": latest_refresh,
        "last_refreshed_str": last_refreshed_str,
    })


@router.post("/categories")
async def create_category(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not auth.is_superadmin(user):
        return _render_403(request, "Only Superadmins can create categories.")

    cname = name.strip()
    if not cname:
        return RedirectResponse("/admin/classes?error=Category+name+cannot+be+empty", status_code=302)

    existing = db.query(Category).filter(Category.name == cname).first()
    if existing:
        return RedirectResponse("/admin/classes?error=Category+already+exists", status_code=302)

    new_cat = Category(name=cname)
    db.add(new_cat)
    db.commit()

    auth.log_audit_event(
        db, request, user,
        action_type="category_created",
        target_type="category",
        target_id=new_cat.id,
        description=f"Created category '{new_cat.name}'"
    )

    return RedirectResponse("/admin/classes?success=Category+created", status_code=302)


@router.post("/categories/{category_id}/edit")
async def edit_category(request: Request, category_id: str, name: str = Form(...), db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not auth.is_superadmin(user):
        return _render_403(request, "Only Superadmins can edit categories.")

    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        return RedirectResponse("/admin/classes?error=Category+not+found", status_code=302)

    cname = name.strip()
    if not cname:
        return RedirectResponse("/admin/classes?error=Category+name+cannot+be+empty", status_code=302)

    existing = db.query(Category).filter(Category.name == cname, Category.id != category_id).first()
    if existing:
        return RedirectResponse("/admin/classes?error=Category+name+already+exists", status_code=302)

    old_name = cat.name
    cat.name = cname
    db.commit()

    auth.log_audit_event(
        db, request, user,
        action_type="category_edited",
        target_type="category",
        target_id=category_id,
        description=f"Renamed category '{old_name}' to '{cname}'"
    )

    return RedirectResponse("/admin/classes?success=Category+updated", status_code=302)


@router.post("/categories/{category_id}/delete")
async def delete_category(request: Request, category_id: str, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not auth.is_superadmin(user):
        return _render_403(request, "Only Superadmins can delete categories.")

    cat = db.query(Category).filter(Category.id == category_id).first()
    if cat:
        has_classes = db.query(Class).filter(Class.category_id == category_id).count()
        if has_classes > 0:
            return RedirectResponse(f"/admin/classes?error=Cannot+delete+category+with+{has_classes}+class(es).+Please+reassign+or+delete+the+classes+first.", status_code=302)
        cat_name = cat.name
        db.delete(cat)
        db.commit()

        auth.log_audit_event(
            db, request, user,
            action_type="category_deleted",
            target_type="category",
            target_id=category_id,
            description=f"Deleted category '{cat_name}'"
        )
    return RedirectResponse("/admin/classes?success=Category+deleted", status_code=302)


@router.post("/classes")
async def create_class(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    category_id: str = Form(...),
    db: Session = Depends(get_db)
):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    new_class = Class(name=name.strip(), description=description.strip(), category_id=category_id, created_by=user["id"])
    db.add(new_class)
    db.flush()

    # If the creator is a non-superadmin staff, automatically assign them access to this class
    if not auth.is_superadmin(user):
        uid = uuid.UUID(user["id"]) if isinstance(user["id"], str) else user["id"]
        assignment = StaffAssignment(profile_id=uid, class_id=new_class.id)
        db.add(assignment)

    # Auto-generate an invite
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    invite = Invite(class_id=new_class.id, token=secrets.token_urlsafe(16), is_active=True, expires_at=expires)
    db.add(invite)
    db.commit()

    auth.log_audit_event(
        db, request, user,
        action_type="class_created",
        target_type="class",
        target_id=new_class.id,
        description=f"Created class '{new_class.name}'"
    )

    return RedirectResponse("/admin/classes", status_code=302)


@router.get("/classes/{class_id}", response_class=HTMLResponse)
async def class_detail(request: Request, class_id: str, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    if not auth.can_access_class(db, user, class_id):
        return _render_403(request, "You are not assigned to manage this class.")

    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        return RedirectResponse("/admin/classes", status_code=302)

    categories = db.query(Category).order_by(Category.name).all()
    members = db.query(Student).filter(Student.class_id == class_id).all()
    leaderboard = sorted(members, key=lambda s: s.points or 0, reverse=True)
    is_super = auth.is_superadmin(user)

    inactive_count = 0
    for i, s in enumerate(leaderboard):
        s._rank = i + 1
        if is_super:
            s._inactivity = get_inactivity_status(s.last_active, is_superadmin=True)
            s._last_active_str = s._inactivity["relative"]
            s._days_inactive = s._inactivity["days"]
            if s._inactivity.get("is_inactive"):
                inactive_count += 1
        else:
            s._inactivity = None
            s._last_active_str = None
            s._days_inactive = None

    invite = db.query(Invite).filter(Invite.class_id == class_id, Invite.is_active == True).first()
    base_url = str(request.base_url).rstrip("/")
    invite_link = f"{base_url}/join/{invite.token}" if invite else None

    tests = db.query(TestResult).filter(TestResult.class_id == class_id).order_by(TestResult.upload_date.desc()).all()
    latest_refresh = db.query(RefreshLog).order_by(RefreshLog.timestamp.desc()).first()
    last_refreshed_str = format_relative_time(latest_refresh.timestamp) if latest_refresh else "Never"

    return templates.TemplateResponse("admin/class_detail.html", {
        "request": request,
        "user": user,
        "is_superadmin": auth.is_superadmin(user),
        "cls": cls,
        "categories": categories,
        "leaderboard": leaderboard,
        "invite_link": invite_link,
        "tests": tests,
        "latest_refresh": latest_refresh,
        "last_refreshed_str": last_refreshed_str,
        "inactive_count": inactive_count,
    })


@router.post("/classes/{class_id}/add-student-manual")
async def add_student_manual(
    request: Request,
    class_id: str,
    leetcode_username: str = Form(...),
    display_name: Optional[str] = Form(None),
    register_number: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    if not auth.can_access_class(db, user, class_id):
        return _render_403(request, "You do not have access to this class.")

    is_ajax = "application/json" in request.headers.get("accept", "")
    username = leetcode_username.strip()
    dname = (display_name or username).strip()
    reg_num = register_number.strip().upper() if register_number and register_number.strip() else None

    if not username:
        if is_ajax: return JSONResponse({"success": False, "error": "LeetCode username required"})
        return RedirectResponse(f"/admin/classes/{class_id}?error=LeetCode+username+required", status_code=302)

    existing = db.query(Student).filter(Student.class_id == class_id, Student.leetcode_username == username).first()
    if existing:
        if is_ajax: return JSONResponse({"success": False, "error": "Student already in class"})
        return RedirectResponse(f"/admin/classes/{class_id}?error=Student+already+in+class", status_code=302)

    stats = fetch_leetcode_stats(username, retries=3, retry_delay=0.5)
    if not stats:
        if is_ajax: return JSONResponse({"success": False, "error": f"Could not fetch stats for {username}"})
        return RedirectResponse(f"/admin/classes/{class_id}?error=Could+not+fetch+stats+for+{username}", status_code=302)

    now_utc = datetime.now(timezone.utc)
    last_act = stats.get("last_submission_time") or now_utc

    new_student = Student(
        class_id=class_id,
        leetcode_username=username,
        display_name=dname,
        register_number=reg_num,
        solved_easy=stats["easy"],
        solved_medium=stats["medium"],
        solved_hard=stats["hard"],
        solved_total=stats["total"],
        points=stats["easy"] * 1 + stats["medium"] * 3 + stats["hard"] * 5,
        ranking=stats["ranking"],
        last_active=last_act,
        last_updated=now_utc
    )
    db.add(new_student)
    db.commit()

    cls = db.query(Class).filter(Class.id == class_id).first()
    cls_name = cls.name if cls else class_id
    auth.log_audit_event(
        db, request, user,
        action_type="student_added",
        target_type="student",
        target_id=new_student.id,
        description=f"Added student '{dname}' (@{username}) to class '{cls_name}'"
    )

    if is_ajax: return JSONResponse({"success": True, "message": "Student added successfully"})
    return RedirectResponse(f"/admin/classes/{class_id}?success=Student+added", status_code=302)


@router.post("/classes/{class_id}/generate-invite")
async def generate_invite(request: Request, class_id: str, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    if not auth.can_access_class(db, user, class_id):
        return _render_403(request, "You do not have access to this class.")

    db.query(Invite).filter(Invite.class_id == class_id).update({"is_active": False})
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    invite = Invite(class_id=class_id, token=secrets.token_urlsafe(16), is_active=True, expires_at=expires)
    db.add(invite)
    db.commit()

    cls = db.query(Class).filter(Class.id == class_id).first()
    cls_name = cls.name if cls else class_id
    auth.log_audit_event(
        db, request, user,
        action_type="invite_regenerated",
        target_type="invite",
        target_id=class_id,
        description=f"Regenerated invite token for class '{cls_name}'"
    )

    return RedirectResponse(f"/admin/classes/{class_id}", status_code=302)


@router.post("/classes/{class_id}/edit")
async def edit_class(
    request: Request,
    class_id: str,
    name: str = Form(...),
    description: str = Form(""),
    category_id: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    if not auth.can_access_class(db, user, class_id):
        return _render_403(request, "You do not have access to this class.")

    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        return RedirectResponse("/admin/classes?error=Class+not+found", status_code=302)

    cname = name.strip()
    if not cname:
        return RedirectResponse(f"/admin/classes/{class_id}?error=Class+name+cannot+be+empty", status_code=302)

    existing = db.query(Class).filter(Class.name == cname, Class.id != class_id).first()
    if existing:
        return RedirectResponse(f"/admin/classes/{class_id}?error=Class+name+already+exists", status_code=302)

    old_name = cls.name
    cls.name = cname
    cls.description = description.strip()
    if category_id is not None:
        cls.category_id = category_id if category_id != "" else None
    db.commit()

    auth.log_audit_event(
        db, request, user,
        action_type="class_edited",
        target_type="class",
        target_id=class_id,
        description=f"Updated class '{old_name}' (renamed to '{cname}')"
    )

    return RedirectResponse(f"/admin/classes/{class_id}?success=Class+updated", status_code=302)


@router.post("/classes/{class_id}/remove-student/{student_id}")
async def remove_student(request: Request, class_id: str, student_id: str, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    if not auth.can_access_class(db, user, class_id):
        return _render_403(request, "You do not have access to this class.")

    student = db.query(Student).filter(Student.class_id == class_id, Student.id == student_id).first()
    if student:
        s_name = student.display_name
        s_user = student.leetcode_username
        cls = db.query(Class).filter(Class.id == class_id).first()
        cls_name = cls.name if cls else class_id
        db.delete(student)
        db.commit()

        auth.log_audit_event(
            db, request, user,
            action_type="student_removed",
            target_type="student",
            target_id=student_id,
            description=f"Removed student '{s_name}' (@{s_user}) from class '{cls_name}'"
        )
    return RedirectResponse(f"/admin/classes/{class_id}", status_code=302)


@router.post("/classes/{class_id}/delete")
async def delete_class(request: Request, class_id: str, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    if not auth.can_access_class(db, user, class_id):
        return _render_403(request, "You do not have access to this class.")

    cls = db.query(Class).filter(Class.id == class_id).first()
    if cls:
        cls_name = cls.name
        db.delete(cls)
        db.commit()

        auth.log_audit_event(
            db, request, user,
            action_type="class_deleted",
            target_type="class",
            target_id=class_id,
            description=f"Deleted class '{cls_name}'"
        )
    return RedirectResponse("/admin/classes", status_code=302)


@router.post("/classes/{class_id}/tests/upload")
async def upload_test(
    request: Request,
    class_id: str,
    test_name: str = Form(...),
    duration: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    if not auth.can_access_class(db, user, class_id):
        return _render_403(request, "You do not have access to this class.")

    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        return RedirectResponse(f"/admin/classes/{class_id}?error=Invalid+file+format", status_code=302)

    try:
        contents = await file.read()
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))

        df = df.fillna("")

        for col in df.columns:
            try:
                if pd.api.types.is_float_dtype(df[col]):
                    df[col] = df[col].round(2)
            except Exception:
                pass

        data = json.loads(df.to_json(orient="records", date_format="iso"))
        columns = [str(c) for c in df.columns]

        expires_at = None
        now = datetime.now(timezone.utc)
        if duration == "24h":
            expires_at = now + timedelta(hours=24)
        elif duration == "48h":
            expires_at = now + timedelta(hours=48)
        elif duration == "1w":
            expires_at = now + timedelta(weeks=1)
        elif duration == "1m":
            expires_at = now + timedelta(days=30)

        new_test = TestResult(
            class_id=class_id,
            test_name=test_name,
            columns=columns,
            data=data,
            uploaded_by=user["id"],
            expires_at=expires_at
        )
        db.add(new_test)
        db.commit()

        cls = db.query(Class).filter(Class.id == class_id).first()
        cls_name = cls.name if cls else class_id
        auth.log_audit_event(
            db, request, user,
            action_type="test_uploaded",
            target_type="test",
            target_id=str(new_test.id),
            description=f"Uploaded test results '{test_name}' ({len(data)} rows) for class '{cls_name}'"
        )

        return RedirectResponse(f"/admin/classes/{class_id}?success=Test+uploaded", status_code=302)

    except Exception as e:
        print(f"Error parsing file: {e}")
        return RedirectResponse(f"/admin/classes/{class_id}?error=Could+not+parse+file", status_code=302)


@router.post("/classes/{class_id}/tests/{test_id}/delete")
async def delete_test(request: Request, class_id: str, test_id: str, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    if not auth.can_access_class(db, user, class_id):
        return _render_403(request, "You do not have access to this class.")

    test = db.query(TestResult).filter(TestResult.id == test_id, TestResult.class_id == class_id).first()
    if test:
        t_name = test.test_name
        cls = db.query(Class).filter(Class.id == class_id).first()
        cls_name = cls.name if cls else class_id
        db.delete(test)
        db.commit()

        auth.log_audit_event(
            db, request, user,
            action_type="test_deleted",
            target_type="test",
            target_id=test_id,
            description=f"Deleted test '{t_name}' from class '{cls_name}'"
        )
    return RedirectResponse(f"/admin/classes/{class_id}?success=Test+deleted", status_code=302)


# ─── Refresh Stats (Class-Level & System-Wide) ────────────────────────────────

@router.post("/refresh-stats/{class_id}")
async def refresh_class_stats(request: Request, class_id: str, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    if not auth.can_access_class(db, user, class_id):
        return JSONResponse({"error": "Forbidden: You do not have access to this class"}, status_code=403)

    members = db.query(Student).filter(Student.class_id == class_id).all()
    refreshed = 0
    failed = 0
    now_utc = datetime.now(timezone.utc)

    for s in members:
        if s.leetcode_username:
            stats = fetch_leetcode_stats(s.leetcode_username, retries=3, retry_delay=0.4)
            if stats:
                new_easy = stats["easy"]
                new_med = stats["medium"]
                new_hard = stats["hard"]
                new_total = stats["total"]
                new_rank = stats["ranking"]
                new_points = new_easy * 1 + new_med * 3 + new_hard * 5

                if stats.get("last_submission_time"):
                    s.last_active = stats["last_submission_time"]
                elif (s.solved_total != new_total or s.points != new_points) or not s.last_active:
                    s.last_active = now_utc

                s.solved_easy = new_easy
                s.solved_medium = new_med
                s.solved_hard = new_hard
                s.solved_total = new_total
                s.ranking = new_rank
                s.points = new_points
                s.last_updated = now_utc
                refreshed += 1
            else:
                failed += 1

    db.commit()

    cls = db.query(Class).filter(Class.id == class_id).first()
    cls_name = cls.name if cls else class_id
    auth.log_audit_event(
        db, request, user,
        action_type="class_stats_refreshed",
        target_type="class",
        target_id=class_id,
        description=f"Refreshed stats for class '{cls_name}': {refreshed} succeeded, {failed} failed"
    )

    return JSONResponse({"success": True, "refreshed": refreshed, "failed": failed})


@router.post("/refresh-all")
async def refresh_all_stats(request: Request, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    from main import execute_refresh_job
    result = await execute_refresh_job(triggered_by=f"manual: {user.get('email')}")

    auth.log_audit_event(
        db, request, user,
        action_type="all_stats_refreshed",
        target_type="system",
        description=f"Manual batch refresh: {result.get('success_count')} succeeded, {result.get('failure_count')} failed"
    )

    return JSONResponse(result)


# ─── Activity Log / Audit Log (Superadmin Only) ───────────────────────────────

@router.get("/activity", response_class=HTMLResponse)
async def activity_log(
    request: Request,
    actor: Optional[str] = Query(None),
    action_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=10, le=100),
    db: Session = Depends(get_db)
):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not auth.is_superadmin(user):
        return _render_403(request, "Only Superadmins can view activity logs.")

    query = db.query(AuditLog)

    if actor and actor.strip():
        search = f"%{actor.strip().lower()}%"
        query = query.filter(or_(
            func.lower(AuditLog.actor_email).like(search),
            func.lower(AuditLog.actor_name).like(search)
        ))

    if action_type and action_type.strip() and action_type != "all":
        query = query.filter(AuditLog.action_type.startswith(action_type.strip()))

    if date_from and date_from.strip():
        try:
            df = datetime.fromisoformat(date_from.strip()).replace(tzinfo=timezone.utc)
            query = query.filter(AuditLog.created_at >= df)
        except Exception:
            pass

    if date_to and date_to.strip():
        try:
            dt = datetime.fromisoformat(date_to.strip()).replace(tzinfo=timezone.utc) + timedelta(days=1)
            query = query.filter(AuditLog.created_at <= dt)
        except Exception:
            pass

    total_logs = query.count()
    total_pages = max(1, (total_logs + page_size - 1) // page_size)
    offset = (page - 1) * page_size
    logs = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size).all()

    # Pre-format relative times
    for l in logs:
        l._time_str = format_relative_time(l.created_at)

    # Fetch recent refresh execution logs (last 5 runs)
    refresh_logs = db.query(RefreshLog).order_by(RefreshLog.timestamp.desc()).limit(5).all()
    for rl in refresh_logs:
        rl._time_str = format_relative_time(rl.timestamp)

    return templates.TemplateResponse("admin/activity.html", {
        "request": request,
        "user": user,
        "is_superadmin": True,
        "logs": logs,
        "refresh_logs": refresh_logs,
        "total_logs": total_logs,
        "page": page,
        "total_pages": total_pages,
        "page_size": page_size,
        "filters": {
            "actor": actor or "",
            "action_type": action_type or "all",
            "date_from": date_from or "",
            "date_to": date_to or ""
        }
    })
