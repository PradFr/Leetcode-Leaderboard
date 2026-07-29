from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db, Class, Invite, Student, Category
from utils import fetch_leetcode_stats

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


import auth

@router.get("/leaderboard", response_class=HTMLResponse)
async def public_index(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request)
    categories = db.query(Category).order_by(Category.name).all()
    # Eager load classes if not configured, or just fetch all
    classes = db.query(Class).order_by(Class.created_at.desc()).all()
    
    # Group classes by category ID for easy template rendering
    grouped = {cat.id: {"cat": cat, "classes": []} for cat in categories}
    ungrouped = []
    
    for cls in classes:
        if cls.category_id and cls.category_id in grouped:
            grouped[cls.category_id]["classes"].append(cls)
        else:
            ungrouped.append(cls)
            
    return templates.TemplateResponse("public_views/index.html", {
        "request": request,
        "user": user,
        "grouped": grouped.values(),
        "ungrouped": ungrouped,
    })


@router.get("/leaderboard/{class_id}", response_class=HTMLResponse)
async def public_leaderboard(request: Request, class_id: str, db: Session = Depends(get_db)):
    user = auth.get_current_user(request)
    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        return HTMLResponse("Class not found", status_code=404)

    members = db.query(Student).filter(Student.class_id == class_id).all()
    leaderboard = sorted(members, key=lambda s: s.points or 0, reverse=True)
    
    for i, s in enumerate(leaderboard):
        s._rank = i + 1

    return templates.TemplateResponse("public_views/leaderboard.html", {
        "request": request,
        "user": user,
        "cls": cls,
        "leaderboard": leaderboard,
        "total_in_class": len(leaderboard),
    })


@router.get("/join/{token}", response_class=HTMLResponse)
async def join_class_page(request: Request, token: str, db: Session = Depends(get_db)):
    invite = db.query(Invite).filter(Invite.token == token, Invite.is_active == True).first()
    if not invite:
        return templates.TemplateResponse("join.html", {
            "request": request, "error": "Invalid or expired invite link.", "cls": None, "token": token
        })

    cls = db.query(Class).filter(Class.id == invite.class_id).first()
    return templates.TemplateResponse("join.html", {
        "request": request, "cls": cls, "token": token, "error": None
    })

@router.post("/join/{token}")
async def join_class(
    request: Request, 
    token: str, 
    leetcode_username: str = Form(...),
    display_name: Optional[str] = Form(None),
    register_number: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    invite = db.query(Invite).filter(Invite.token == token, Invite.is_active == True).first()
    if not invite:
        return RedirectResponse(f"/join/{token}?error=Invalid+or+expired+invite+link", status_code=302)

    username = leetcode_username.strip()
    name = (display_name or username).strip()
    reg_num = register_number.strip() if register_number else None
    
    if not username:
        return RedirectResponse(f"/join/{token}?error=LeetCode+username+required", status_code=302)

    existing = db.query(Student).filter(Student.class_id == invite.class_id, Student.leetcode_username == username).first()
    if existing:
        return RedirectResponse(f"/join/{token}?error=You+are+already+in+this+class", status_code=302)

    stats = fetch_leetcode_stats(username)
    if not stats:
        return RedirectResponse(f"/join/{token}?error=Could+not+fetch+stats.+Please+check+your+username.", status_code=302)

    new_student = Student(
        class_id=invite.class_id,
        leetcode_username=username,
        display_name=name,
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

    # Get class so we can redirect to its leaderboard
    cls = db.query(Class).filter(Class.id == invite.class_id).first()
    return RedirectResponse(f"/leaderboard/{cls.id}?success=Joined+successfully", status_code=302)
