import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

import database
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

# Run schema migrations on startup (optional if deploying to Vercel/serverless)
@app.on_event("startup")
def on_startup():
    try:
        database.ensure_tables()
    except Exception as e:
        print(f"Migration warning: {e}")

app.include_router(auth_routes.router)
app.include_router(admin_routes.router)
app.include_router(public_routes.router)


@app.get("/")
async def root(request: Request):
    token = request.session.get("access_token")
    if token:
        # If logged in, you can go to admin dashboard
        return RedirectResponse("/admin", status_code=302)
    # If not logged in, show the public leaderboard for students
    return RedirectResponse("/leaderboard", status_code=302)
