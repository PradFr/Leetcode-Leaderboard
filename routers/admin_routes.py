import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import uuid

import auth
from database import get_db, Profile, Class, Invite, Student, Category
from utils import fetch_leetcode_stats

router = APIRouter(prefix="/admin")
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _get_admin(request: Request):
    user = auth.get_current_user(request)
    if not user or user.get("role") not in ("admin", "superadmin"):
        return None
    return user


# ─── Dashboard ────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    total_classes = db.query(Class).count()
    total_students = db.query(Student).count()
    total_admins = db.query(Profile).count()
    total_solved = sum((s.solved_total or 0) for s in db.query(Student).all())
    
    classes = db.query(Class).order_by(Class.created_at.desc()).limit(5).all()
    class_data = []
    for cls in classes:
        count = db.query(Student).filter(Student.class_id == cls.id).count()
        class_data.append({"cls": cls, "student_count": count})

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "user": user,
        "total_classes": total_classes,
        "total_students": total_students,
        "total_solved": total_solved,
        "total_admins": total_admins,
        "recent_classes": class_data,
    })


# ─── Manage Staff/Admins ──────────────────────────────────────────────────────

@router.get("/staff", response_class=HTMLResponse)
async def manage_staff(request: Request, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    profiles = db.query(Profile).all()
    return templates.TemplateResponse("admin/staff.html", {
        "request": request,
        "user": user,
        "profiles": profiles
    })

@router.post("/staff/add")
async def add_staff(request: Request, email: str = Form(...), password: str = Form(...), full_name: str = Form(...), db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    # Check if they exist in our DB already
    existing = db.query(Profile).filter(Profile.email == email).first()
    if existing:
        return RedirectResponse("/admin/staff?error=Email+already+exists", status_code=302)

    res = auth.supabase_admin_create_user(email, password, full_name)
    if res.get("error"):
        err = res.get("message", "Could not create user in Supabase")
        return RedirectResponse(f"/admin/staff?error={err}", status_code=302)
    
    user_id = res.get("id")
    if user_id:
        new_profile = Profile(
            id=uuid.UUID(user_id),
            email=email,
            full_name=full_name,
            role="admin"
        )
        db.add(new_profile)
        db.commit()

    return RedirectResponse("/admin/staff?success=Staff+member+added", status_code=302)


@router.post("/staff/delete/{admin_id}")
async def delete_staff(request: Request, admin_id: str, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    if user.get("id") == admin_id:
        return RedirectResponse("/admin/staff?error=You+cannot+delete+your+own+account", status_code=302)

    try:
        uid = uuid.UUID(admin_id)
        profile = db.query(Profile).filter(Profile.id == uid).first()
        if profile:
            if profile.role == "superadmin":
                return RedirectResponse("/admin/staff?error=Super+Admin+accounts+cannot+be+deleted", status_code=302)
            db.delete(profile)
            db.commit()
    except Exception as e:
        return RedirectResponse(f"/admin/staff?error=Invalid+user+id", status_code=302)

    return RedirectResponse("/admin/staff?success=Staff+member+removed", status_code=302)


# ─── Classes ──────────────────────────────────────────────────────────────────

@router.get("/classes", response_class=HTMLResponse)
async def admin_classes(request: Request, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    categories = db.query(Category).order_by(Category.name).all()
    classes = db.query(Class).order_by(Class.created_at.desc()).all()
    class_data = []
    for cls in classes:
        members = db.query(Student).filter(Student.class_id == cls.id).all()
        top_user = max(members, key=lambda s: s.points or 0) if members else None
        invite = db.query(Invite).filter(Invite.class_id == cls.id, Invite.is_active == True).first()
        class_data.append({"cls": cls, "student_count": len(members), "top_user": top_user, "invite": invite})

    return templates.TemplateResponse("admin/classes.html", {
        "request": request, "user": user, "classes": class_data, "categories": categories
    })


@router.post("/categories")
async def create_category(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    new_cat = Category(name=name.strip())
    db.add(new_cat)
    db.commit()
    return RedirectResponse("/admin/classes", status_code=302)


@router.post("/classes")
async def create_class(request: Request, name: str = Form(...), description: str = Form(""), category_id: str = Form(...), db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    new_class = Class(name=name, description=description, category_id=category_id, created_by=user["id"])
    db.add(new_class)
    db.flush()

    # Auto-generate an invite
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    invite = Invite(class_id=new_class.id, token=secrets.token_urlsafe(16), is_active=True, expires_at=expires)
    db.add(invite)
    db.commit()
    return RedirectResponse("/admin/classes", status_code=302)


@router.get("/classes/{class_id}", response_class=HTMLResponse)
async def class_detail(request: Request, class_id: str, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        return RedirectResponse("/admin/classes", status_code=302)

    members = db.query(Student).filter(Student.class_id == class_id).all()
    leaderboard = sorted(members, key=lambda s: s.points or 0, reverse=True)
    for i, s in enumerate(leaderboard):
        s._rank = i + 1

    invite = db.query(Invite).filter(Invite.class_id == class_id, Invite.is_active == True).first()
    base_url = str(request.base_url).rstrip("/")
    invite_link = f"{base_url}/join/{invite.token}" if invite else None

    return templates.TemplateResponse("admin/class_detail.html", {
        "request": request, "user": user, "cls": cls, "leaderboard": leaderboard, "invite_link": invite_link
    })


@router.post("/classes/{class_id}/add-student-manual")
async def add_student_manual(request: Request, class_id: str, leetcode_username: str = Form(...), display_name: Optional[str] = Form(None), register_number: Optional[str] = Form(None), db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    is_ajax = "application/json" in request.headers.get("accept", "")

    username = leetcode_username.strip()
    dname = (display_name or username).strip()
    reg_num = register_number.strip() if register_number else None
    
    if not username:
        if is_ajax: return JSONResponse({"success": False, "error": "LeetCode username required"})
        return RedirectResponse(f"/admin/classes/{class_id}?error=LeetCode+username+required", status_code=302)

    existing = db.query(Student).filter(Student.class_id == class_id, Student.leetcode_username == username).first()
    if existing:
        if is_ajax: return JSONResponse({"success": False, "error": "Student already in class"})
        return RedirectResponse(f"/admin/classes/{class_id}?error=Student+already+in+class", status_code=302)

    stats = fetch_leetcode_stats(username)
    if not stats:
        if is_ajax: return JSONResponse({"success": False, "error": f"Could not fetch stats for {username}"})
        return RedirectResponse(f"/admin/classes/{class_id}?error=Could+not+fetch+stats+for+{username}", status_code=302)

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
        ranking=stats["ranking"]
    )
    db.add(new_student)
    db.commit()
    
    if is_ajax: return JSONResponse({"success": True, "message": "Student added successfully"})
    return RedirectResponse(f"/admin/classes/{class_id}?success=Student+added", status_code=302)


@router.post("/classes/{class_id}/generate-invite")
async def generate_invite(request: Request, class_id: str, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    db.query(Invite).filter(Invite.class_id == class_id).update({"is_active": False})
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    invite = Invite(class_id=class_id, token=secrets.token_urlsafe(16), is_active=True, expires_at=expires)
    db.add(invite)
    db.commit()
    return RedirectResponse(f"/admin/classes/{class_id}", status_code=302)


@router.post("/classes/{class_id}/edit")
async def edit_class(request: Request, class_id: str, name: str = Form(...), description: str = Form(""), db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        return RedirectResponse("/admin/classes?error=Class+not+found", status_code=302)

    cname = name.strip()
    if not cname:
        return RedirectResponse(f"/admin/classes/{class_id}?error=Class+name+cannot+be+empty", status_code=302)

    existing = db.query(Class).filter(Class.name == cname, Class.id != class_id).first()
    if existing:
        return RedirectResponse(f"/admin/classes/{class_id}?error=Class+name+already+exists", status_code=302)

    cls.name = cname
    cls.description = description.strip()
    db.commit()

    return RedirectResponse(f"/admin/classes/{class_id}?success=Class+updated", status_code=302)


@router.post("/classes/{class_id}/remove-student/{student_id}")
async def remove_student(request: Request, class_id: str, student_id: str, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    student = db.query(Student).filter(Student.class_id == class_id, Student.id == student_id).first()
    if student:
        db.delete(student)
        db.commit()
    return RedirectResponse(f"/admin/classes/{class_id}", status_code=302)


@router.post("/classes/{class_id}/delete")
async def delete_class(request: Request, class_id: str, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    cls = db.query(Class).filter(Class.id == class_id).first()
    if cls:
        db.delete(cls)
        db.commit()
    return RedirectResponse("/admin/classes", status_code=302)


@router.post("/refresh-stats/{class_id}")
async def refresh_class_stats(request: Request, class_id: str, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    members = db.query(Student).filter(Student.class_id == class_id).all()
    refreshed = 0
    for s in members:
        if s.leetcode_username:
            stats = fetch_leetcode_stats(s.leetcode_username)
            if stats:
                s.solved_easy = stats["easy"]
                s.solved_medium = stats["medium"]
                s.solved_hard = stats["hard"]
                s.solved_total = stats["total"]
                s.ranking = stats["ranking"]
                s.points = stats["easy"] * 1 + stats["medium"] * 3 + stats["hard"] * 5
                refreshed += 1
    db.commit()
    return JSONResponse({"refreshed": refreshed})
