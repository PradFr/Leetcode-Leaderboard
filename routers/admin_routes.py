import secrets
import httpx
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import auth
from database import get_db, Profile, Class, Invite, Student

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")


def _get_admin(request: Request):
    user = auth.get_current_user(request)
    if not user or user["role"] != "admin":
        return None
    return user


def _fetch_leetcode_stats(username: str) -> dict | None:
    query = """
    query userProfile($username: String!) {
      matchedUser(username: $username) {
        profile { ranking }
        submitStats {
          acSubmissionNum { difficulty count }
        }
      }
    }
    """
    try:
        r = httpx.post(
            "https://leetcode.com/graphql",
            json={"query": query, "variables": {"username": username}},
            headers={"Content-Type": "application/json", "Referer": "https://leetcode.com"},
            timeout=10,
        )
        data = r.json()
        user = data.get("data", {}).get("matchedUser")
        if not user:
            return None
        ranking = user.get("profile", {}).get("ranking", 0)
        counts = {item["difficulty"]: item["count"]
                  for item in user.get("submitStats", {}).get("acSubmissionNum", [])}
        return {
            "easy": counts.get("Easy", 0),
            "medium": counts.get("Medium", 0),
            "hard": counts.get("Hard", 0),
            "total": counts.get("All", 0),
            "ranking": ranking or 0,
        }
    except Exception:
        return None


# ─── Dashboard ────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    total_classes = db.query(Class).count()
    total_students = db.query(Student).count()
    total_solved = sum(
        (s.solved_total or 0) for s in db.query(Student).all()
    )
    unassigned = db.query(Student).filter(Student.class_id == None).count()

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
        "unassigned_students": unassigned,
        "recent_classes": class_data,
    })


# ─── Classes ──────────────────────────────────────────────────────────────────

@router.get("/classes", response_class=HTMLResponse)
async def admin_classes(request: Request, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    classes = db.query(Class).order_by(Class.created_at.desc()).all()
    class_data = []
    for cls in classes:
        members = db.query(Student).filter(Student.class_id == cls.id).all()
        top_user = max(members, key=lambda s: s.solved_total or 0) if members else None

        # Get active invite token
        invite = db.query(Invite).filter(
            Invite.class_id == cls.id, Invite.is_active == True
        ).first()

        class_data.append({
            "cls": cls,
            "student_count": len(members),
            "top_user": top_user,
            "invite": invite,
        })

    return templates.TemplateResponse("admin/classes.html", {
        "request": request,
        "user": user,
        "classes": class_data,
    })


@router.post("/classes")
async def create_class(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db)
):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    new_class = Class(name=name, description=description, created_by=user["id"])
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
    # Sort leaderboard by points
    leaderboard = sorted(members, key=lambda s: s.points or 0, reverse=True)
    for i, s in enumerate(leaderboard):
        s._rank = i + 1

    invite = db.query(Invite).filter(
        Invite.class_id == class_id, Invite.is_active == True
    ).first()
    base_url = str(request.base_url).rstrip("/")
    invite_link = f"{base_url}/join/{invite.token}" if invite else None

    return templates.TemplateResponse("admin/class_detail.html", {
        "request": request,
        "user": user,
        "cls": cls,
        "leaderboard": leaderboard,
        "invite_link": invite_link,
    })


import uuid

@router.post("/classes/{class_id}/add-student-manual")
async def add_student_manual(
    request: Request, class_id: str, leetcode_username: str = Form(...), db: Session = Depends(get_db)
):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    username = leetcode_username.strip()
    if not username:
        return RedirectResponse(f"/admin/classes/{class_id}?error=Username+cannot+be+empty", status_code=302)

    # Check if student already exists in this class
    existing = db.query(Student).filter(
        Student.class_id == class_id, 
        Student.leetcode_username == username
    ).first()
    if existing:
        return RedirectResponse(f"/admin/classes/{class_id}?error=Student+already+in+class", status_code=302)

    # Fetch initial stats
    stats = _fetch_leetcode_stats(username)
    if not stats:
        return RedirectResponse(f"/admin/classes/{class_id}?error=Could+not+fetch+stats+for+{username}", status_code=302)

    new_student = Student(
        class_id=class_id,
        user_id=f"manual_{uuid.uuid4().hex}",
        leetcode_username=username,
        display_name=username,
        solved_easy=stats["easy"],
        solved_medium=stats["medium"],
        solved_hard=stats["hard"],
        solved_total=stats["total"],
        points=stats["easy"] * 1 + stats["medium"] * 3 + stats["hard"] * 5,
        ranking=stats["ranking"]
    )
    db.add(new_student)
    db.commit()
    
    return RedirectResponse(f"/admin/classes/{class_id}?success=Student+added", status_code=302)


@router.post("/classes/{class_id}/generate-invite")
async def generate_invite(request: Request, class_id: str, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    # Deactivate old invites
    db.query(Invite).filter(Invite.class_id == class_id).update({"is_active": False})
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    invite = Invite(class_id=class_id, token=secrets.token_urlsafe(16), is_active=True, expires_at=expires)
    db.add(invite)
    db.commit()
    return RedirectResponse(f"/admin/classes/{class_id}", status_code=302)


@router.post("/classes/{class_id}/remove-student/{student_user_id}")
async def remove_student(
    request: Request, class_id: str, student_user_id: str, db: Session = Depends(get_db)
):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    student = db.query(Student).filter(
        Student.class_id == class_id, Student.user_id == student_user_id
    ).first()
    if student:
        if student.user_id.startswith("manual_"):
            db.delete(student)
        else:
            student.class_id = None
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


# ─── Students ─────────────────────────────────────────────────────────────────

@router.get("/students", response_class=HTMLResponse)
async def admin_students(request: Request, filter: str = "all", db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    query = db.query(Student)
    if filter == "unassigned":
        query = query.filter(Student.class_id == None)

    students = query.order_by(Student.joined_at.desc()).all()
    student_data = []
    for s in students:
        cls = db.query(Class).filter(Class.id == s.class_id).first() if s.class_id else None
        student_data.append({"student": s, "class": cls})

    return templates.TemplateResponse("admin/students.html", {
        "request": request,
        "user": user,
        "students": student_data,
        "filter": filter,
    })


# ─── Refresh stats ────────────────────────────────────────────────────────────

@router.post("/refresh-stats/{class_id}")
async def refresh_class_stats(request: Request, class_id: str, db: Session = Depends(get_db)):
    user = _get_admin(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    members = db.query(Student).filter(Student.class_id == class_id).all()
    refreshed = 0
    for s in members:
        if s.leetcode_username:
            stats = _fetch_leetcode_stats(s.leetcode_username)
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
