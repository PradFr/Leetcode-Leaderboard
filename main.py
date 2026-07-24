import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
import database
from routers import auth_routes, admin_routes, student_routes

load_dotenv()

SECRET_KEY = os.getenv("SUPABASE_JWT_SECRET", "changeme-secret-key")

app = FastAPI(title="LeetCode Leaderboard", docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=86400 * 7)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Run schema migrations on startup
@app.on_event("startup")
def on_startup():
    try:
        database.ensure_tables()
    except Exception as e:
        print(f"Migration warning: {e}")

app.include_router(auth_routes.router)
app.include_router(admin_routes.router)
app.include_router(student_routes.router)


@app.get("/")
async def root(request: Request):
    token = request.session.get("access_token")
    if token:
        role = request.session.get("role", "student")
        if role == "admin":
            return RedirectResponse("/admin", status_code=302)
        return RedirectResponse("/student", status_code=302)
    return RedirectResponse("/login", status_code=302)
