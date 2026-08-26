import os
import time
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

import database
from utils import fetch_leetcode_stats
from routers import auth_routes, admin_routes, public_routes

load_dotenv(override=True)

SECRET_KEY = os.getenv("SUPABASE_JWT_SECRET", "changeme-secret-key")
REFRESH_INTERVAL_HOURS = int(os.getenv("REFRESH_INTERVAL_HOURS", "24"))  # Defaults to once daily

app = FastAPI(title="KAHE - Placement Cell", docs_url=None, redoc_url=None)

class VercelPathMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path.startswith("/api/index.py"):
                scope["path"] = path.replace("/api/index.py", "", 1) or "/"
            elif path.startswith("/api/index"):
                scope["path"] = path.replace("/api/index", "", 1) or "/"
        await self.app(scope, receive, send)

app.add_middleware(VercelPathMiddleware)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=86400 * 7)

# Make sure Vercel or local app can find static files correctly
BASE_DIR = Path(__file__).resolve().parent
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

async def execute_refresh_job(triggered_by: str = "scheduled") -> dict:
    """
    Executes a staggered, rate-limited refresh of all student LeetCode statistics.
    Records run status, success/failure counts, and error details in refresh_logs.
    """
    start_time = datetime.now(timezone.utc)
    db = database.SessionLocal()
    errors = []
    success_count = 0
    failure_count = 0
    total_students = 0

    try:
        students = db.query(database.Student).all()
        total_students = len(students)

        for s in students:
            if not s.leetcode_username:
                continue

            # Stagger requests by 0.4s to respect LeetCode rate limits
            await asyncio.sleep(0.4)

            try:
                stats = fetch_leetcode_stats(s.leetcode_username, retries=3, retry_delay=0.5)
                if stats:
                    new_easy = stats["easy"]
                    new_med = stats["medium"]
                    new_hard = stats["hard"]
                    new_total = stats["total"]
                    new_rank = stats["ranking"]
                    new_points = new_easy * 1 + new_med * 3 + new_hard * 5
                    now_utc = datetime.now(timezone.utc)

                    # Update last_active if a newer submission timestamp was returned
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
                    success_count += 1
                else:
                    failure_count += 1
                    errors.append({
                        "username": s.leetcode_username,
                        "display_name": s.display_name,
                        "error": "Failed to fetch stats from LeetCode API after retries"
                    })
            except Exception as item_err:
                failure_count += 1
                errors.append({
                    "username": s.leetcode_username,
                    "display_name": s.display_name,
                    "error": str(item_err)
                })

        db.commit()

        duration = int((datetime.now(timezone.utc) - start_time).total_seconds())
        status = "completed" if failure_count == 0 else ("partial" if success_count > 0 else "failed")

        # Save to refresh_logs table
        log_entry = database.RefreshLog(
            timestamp=start_time,
            status=status,
            total_students=total_students,
            success_count=success_count,
            failure_count=failure_count,
            duration_seconds=duration,
            error_details=errors if errors else None,
            triggered_by=triggered_by
        )
        db.add(log_entry)
        db.commit()

        return {
            "success": True,
            "status": status,
            "total": total_students,
            "success_count": success_count,
            "failure_count": failure_count,
            "duration_seconds": duration,
            "timestamp": start_time.isoformat()
        }
    except Exception as e:
        db.rollback()
        print(f"[Refresh Job Error] {e}")
        return {
            "success": False,
            "error": str(e),
            "total": total_students,
            "success_count": success_count,
            "failure_count": failure_count
        }
    finally:
        db.close()

async def periodic_stats_refresh():
    """Background scheduled worker running once daily (or configured interval)."""
    # Wait 30 seconds after server boot before first check
    await asyncio.sleep(30)
    interval_seconds = max(300, REFRESH_INTERVAL_HOURS * 3600)
    
    while True:
        try:
            res = await execute_refresh_job(triggered_by="scheduled")
            print(f"[Daily Auto-Sync] Status: {res.get('status')}, Refreshed: {res.get('success_count')}, Failed: {res.get('failure_count')}")
        except Exception as e:
            print(f"[Daily Auto-Sync Error] {e}")
        await asyncio.sleep(interval_seconds)

# Run schema migrations on startup
@app.on_event("startup")
async def on_startup():
    if os.getenv("VERCEL"):
        print("Running on Vercel: skipping startup database migration.")
        return
    try:
        database.ensure_tables()
    except Exception as e:
        print(f"Migration warning: {e}")
    
    # Start background task for scheduled stat updates on persistent servers
    asyncio.create_task(periodic_stats_refresh())

app.include_router(auth_routes.router)
app.include_router(admin_routes.router)
app.include_router(public_routes.router)

@app.api_route("/api/cron/refresh", methods=["GET", "POST"])
async def cron_refresh_stats():
    res = await execute_refresh_job(triggered_by="cron_api")
    return JSONResponse(res)

@app.get("/")
async def root(request: Request):
    token = request.session.get("access_token")
    if token:
        return RedirectResponse("/admin", status_code=302)
    return RedirectResponse("/leaderboard", status_code=302)
