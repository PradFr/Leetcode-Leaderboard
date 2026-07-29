import os
import asyncio
from datetime import datetime, timezone
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

app = FastAPI(title="LeetCode Leaderboard", docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=86400 * 7)

from pathlib import Path

# Make sure Vercel or local app can find static files correctly
BASE_DIR = Path(__file__).resolve().parent
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

def refresh_all_students_stats_sync():
    db = database.SessionLocal()
    try:
        students = db.query(database.Student).all()
        refreshed = 0
        for s in students:
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
        return refreshed
    except Exception as e:
        db.rollback()
        print(f"Error refreshing student stats: {e}")
        return 0
    finally:
        db.close()

async def periodic_stats_refresh():
    while True:
        await asyncio.sleep(3600)  # 1 hour interval
        try:
            refreshed = refresh_all_students_stats_sync()
            print(f"[Hourly Auto-Sync] Refreshed stats for {refreshed} student(s).")
        except Exception as e:
            print(f"[Hourly Auto-Sync Error] {e}")

# Run schema migrations on startup (optional if deploying to Vercel/serverless)
@app.on_event("startup")
async def on_startup():
    if os.getenv("VERCEL"):
        print("Running on Vercel: skipping startup database migration.")
        return
    try:
        database.ensure_tables()
    except Exception as e:
        print(f"Migration warning: {e}")
    
    # Start background task for hourly stat updates on persistent servers
    asyncio.create_task(periodic_stats_refresh())

app.include_router(auth_routes.router)
app.include_router(admin_routes.router)
app.include_router(public_routes.router)

@app.api_route("/api/cron/refresh", methods=["GET", "POST"])
async def cron_refresh_stats():
    refreshed = refresh_all_students_stats_sync()
    return JSONResponse({
        "success": True,
        "refreshed": refreshed,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

@app.get("/")
async def root(request: Request):
    token = request.session.get("access_token")
    if token:
        # If logged in, you can go to admin dashboard
        return RedirectResponse("/admin", status_code=302)
    # If not logged in, show the public leaderboard for students
    return RedirectResponse("/leaderboard", status_code=302)

