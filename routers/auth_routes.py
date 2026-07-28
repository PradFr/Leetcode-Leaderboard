import os
from pathlib import Path
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import auth

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None, success: str = None):
    user = auth.get_current_user(request)
    if user:
        return RedirectResponse("/admin", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": error,
        "success": success,
    })


@router.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    result = auth.supabase_sign_in(email, password)
    
    if result.get("error") or result.get("msg"):
        err = result.get("error_description") or result.get("msg") or result.get("message")
        return RedirectResponse(f"/login?error={err}", status_code=302)

    access_token = result.get("access_token")
    user_data = result.get("user")

    if access_token and user_data:
        user_id = user_data.get("id")
        user_email = user_data.get("email", email)
        full_name = user_data.get("user_metadata", {}).get("full_name")
        
        # Ensure profile exists, role will automatically be 'admin'
        profile = auth.get_or_create_profile(user_id, user_email, full_name)
        
        request.session["access_token"] = access_token
        request.session["role"] = profile.role
        request.session["user_id"] = str(user_id)
        
        return RedirectResponse("/admin", status_code=302)

    return RedirectResponse("/login?error=Unknown error occurred", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login?success=Logged out successfully", status_code=302)
