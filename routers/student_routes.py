import httpx
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

import auth
from database import get_db, Profile, Class, Invite, Student

router = APIRouter()
templates = Jinja2Templates(directory="templates")


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
        matched = data.get("data", {}).get("matchedUser")
        if not matched:
            return None
        ranking = matched.get("profile", {}).get("ranking", 0)
        counts = {item["difficulty"]: item["count"]
                  for item in matched.get("submitStats", {}).get("acSubmissionNum", [])}
        return {
            "easy": counts.get("Easy", 0),
            "medium": counts.get("Medium", 0),
            "hard": counts.get("Hard", 0),
            "total": counts.get("All", 0),
            "ranking": ranking or 0,
        }
    except Exception:
        return None


def _upsert_stats(db: Session, user_id: str, username: str, display_name: str, class_id=None):
    """Fetch LeetCode stats and save/update the student row."""
    stats = _fetch_leetcode_stats(username)
    student = db.query(Student).filter(Student.user_id == user_id).first()
    if not student:
        student = Student(user_id=user_id, display_name=display_name, class_id=class_id)
        db.add(student)
    student.leetcode_username = username
    student.display_name = display_name
    if class_id is not None:
        student.class_id = class_id
    if stats:
        student.solved_easy = stats["easy"]
        student.solved_medium = stats["medium"]
        student.solved_hard = stats["hard"]
        student.solved_total = stats["total"]
        student.ranking = stats["ranking"]
        student.points = stats["easy"] * 1 + stats["medium"] * 3 + stats["hard"] * 5
    db.commit()
    db.refresh(student)
    return student, stats


# ─── Student Dashboard ────────────────────────────────────────────────────────

@router.get("/student", response_class=HTMLResponse)
async def student_dashboard(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not user.get("email_confirmed"):
        return RedirectResponse("/verify-pending", status_code=302)

    me = db.query(Student).filter(Student.user_id == user["id"]).first()

    leaderboard = []
    cls = None
    my_rank = None

    if me and me.class_id:
        cls = db.query(Class).filter(Class.id == me.class_id).first()
        members = db.query(Student).filter(Student.class_id == me.class_id).all()
        leaderboard = sorted(members, key=lambda s: s.solved_total or 0, reverse=True)
        for i, s in enumerate(leaderboard):
            s._rank = i + 1
            if s.user_id == user["id"]:
                my_rank = i + 1

    # If student row doesn't exist yet, create a placeholder
    if not me:
        me = Student(
            user_id=user["id"],
            display_name=user.get("full_name") or user["email"].split("@")[0],
        )
        db.add(me)
        db.commit()
        db.refresh(me)

    # Check pending join token
    pending_token = request.session.pop("pending_join_token", None)
    if pending_token and not me.class_id:
        return RedirectResponse(f"/join/{pending_token}", status_code=302)

    return templates.TemplateResponse("student/dashboard.html", {
        "request": request,
        "user": user,
        "me": me,
        "cls": cls,
        "leaderboard": leaderboard,
        "my_rank": my_rank,
        "total_in_class": len(leaderboard),
    })


# ─── Join class via invite link ───────────────────────────────────────────────

@router.get("/join/{token}", response_class=HTMLResponse)
async def join_class(request: Request, token: str, db: Session = Depends(get_db)):
    user = auth.get_current_user(request)
    if not user:
        request.session["pending_join_token"] = token
        return RedirectResponse("/login?success=Please+log+in+to+join+the+class.", status_code=302)
    if not user.get("email_confirmed"):
        request.session["pending_join_token"] = token
        return RedirectResponse("/verify-pending", status_code=302)

    invite = db.query(Invite).filter(Invite.token == token, Invite.is_active == True).first()
    if not invite:
        return templates.TemplateResponse("join.html", {
            "request": request, "user": user,
            "error": "Invalid or expired invite link.", "cls": None, "token": token,
            "already_member": False, "current_class": None,
        })

    cls = db.query(Class).filter(Class.id == invite.class_id).first()
    me = db.query(Student).filter(Student.user_id == user["id"]).first()
    already_member = me and me.class_id is not None
    current_class = db.query(Class).filter(Class.id == me.class_id).first() if already_member else None

    return templates.TemplateResponse("join.html", {
        "request": request, "user": user,
        "cls": cls, "token": token, "error": None,
        "already_member": already_member,
        "current_class": current_class,
    })


@router.post("/join/{token}")
async def join_class_confirm(request: Request, token: str, db: Session = Depends(get_db)):
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    invite = db.query(Invite).filter(Invite.token == token, Invite.is_active == True).first()
    if not invite:
        return RedirectResponse("/student?error=Invalid+invite+link.", status_code=302)

    me = db.query(Student).filter(Student.user_id == user["id"]).first()
    if me and me.class_id:
        return RedirectResponse("/student?error=You+are+already+in+a+class.", status_code=302)

    if not me:
        me = Student(
            user_id=user["id"],
            display_name=user.get("full_name") or user["email"].split("@")[0],
        )
        db.add(me)

    me.class_id = invite.class_id
    me.display_name = user.get("full_name") or user["email"].split("@")[0]
    db.commit()

    request.session.pop("pending_join_token", None)
    return RedirectResponse("/student?success=Welcome+to+the+class!", status_code=302)


# ─── Set LeetCode username ────────────────────────────────────────────────────

@router.post("/student/set-username")
async def set_username(
    request: Request,
    leetcode_username: str = Form(...),
    db: Session = Depends(get_db)
):
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    username = leetcode_username.strip()
    display = user.get("full_name") or user["email"].split("@")[0]

    me = db.query(Student).filter(Student.user_id == user["id"]).first()
    class_id = me.class_id if me else None

    _upsert_stats(db, user["id"], username, display, class_id)
    return RedirectResponse("/student?success=LeetCode+username+updated+and+stats+fetched!", status_code=302)


# ─── Refresh own stats ────────────────────────────────────────────────────────

@router.post("/student/refresh")
async def refresh_stats(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    me = db.query(Student).filter(Student.user_id == user["id"]).first()
    if not me or not me.leetcode_username:
        return JSONResponse({"error": "No LeetCode username set."}, status_code=400)

    stats = _fetch_leetcode_stats(me.leetcode_username)
    if not stats:
        return JSONResponse({"error": "Could not fetch LeetCode stats. Check username."}, status_code=400)

    me.solved_easy = stats["easy"]
    me.solved_medium = stats["medium"]
    me.solved_hard = stats["hard"]
    me.solved_total = stats["total"]
    me.ranking = stats["ranking"]
    me.points = stats["easy"] * 1 + stats["medium"] * 3 + stats["hard"] * 5
    db.commit()

    return JSONResponse({"success": True, "stats": stats})
