import uuid
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import auth
from database import SessionLocal, Profile

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None, success: str = None):
    user = auth.get_current_user(request)
    if user and user.get("email_confirmed"):
        return RedirectResponse("/admin" if user["role"] == "admin" else "/student", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": error,
        "success": success,
    })


@router.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
):
    # --- DEV MODE FAKE REGISTER ---
    if auth.SKIP_EMAIL_VERIFICATION and not auth.SUPABASE_SERVICE_ROLE_KEY:
        import uuid
        fake_id = str(uuid.uuid4())
        
        # Check if email exists in DB first
        db = auth.SessionLocal()
        try:
            existing = db.query(auth.Profile).filter(auth.Profile.email == email).first()
            if existing:
                return RedirectResponse("/login?error=This+email+is+already+registered.+Try+signing+in.", status_code=302)
        finally:
            db.close()

        profile = auth.get_or_create_profile(fake_id, email, full_name)
        request.session["access_token"] = "fake_dev_token"
        request.session["role"] = profile.role
        request.session["user_id"] = str(profile.id)
        return RedirectResponse("/admin" if profile.role == "admin" else "/student", status_code=302)
    # ------------------------------

    if auth.SKIP_EMAIL_VERIFICATION and auth.SUPABASE_SERVICE_ROLE_KEY:
        result = auth.supabase_admin_create_user(email, password, full_name)
        err = result.get("error") or result.get("msg") or result.get("message")
        if result.get("_status_code") == 422 or (err and "already" in str(err).lower()):
            return RedirectResponse("/login?error=This+email+is+already+registered.+Try+signing+in.", status_code=302)
    else:
        result = auth.supabase_sign_up(email, password, full_name)

    # Handle errors from Supabase
    err = result.get("error") or result.get("msg")
    if err:
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        # "User already registered" — direct them to sign in instead
        if "already registered" in msg.lower() or "already been registered" in msg.lower():
            return RedirectResponse(
                "/login?error=This+email+is+already+registered.+Try+signing+in.",
                status_code=302,
            )
        return RedirectResponse(f"/login?error={msg}", status_code=302)

    user_data = result.get("user") or result
    user_id = user_data.get("id")
    user_email = user_data.get("email", email)

    if user_id:
        auth.get_or_create_profile(user_id, user_email, full_name)

    # Dev mode: auto-confirm the user via service role key, then sign in
    if auth.SKIP_EMAIL_VERIFICATION:
        # Step 1: if service role key is available, force-confirm their email on Supabase
        if user_id and auth.SUPABASE_SERVICE_ROLE_KEY:
            auth.supabase_admin_confirm_user(user_id)

        # Step 2: now try to sign in (will work if confirmed, or if Supabase has confirm disabled)
        sign_in_result = auth.supabase_sign_in(email, password)
        access_token = sign_in_result.get("access_token")

        if access_token:
            user_obj = sign_in_result.get("user", {})
            payload = auth.verify_supabase_jwt(access_token)
            resolved_id = (payload or {}).get("sub") or user_obj.get("id") or user_id
            resolved_email = (payload or {}).get("email") or user_obj.get("email", email)

            if resolved_id:
                profile = auth.get_or_create_profile(resolved_id, resolved_email, full_name)
                request.session["access_token"] = access_token
                request.session["role"] = profile.role
                request.session["user_id"] = str(resolved_id)
                return RedirectResponse(
                    "/admin" if profile.role == "admin" else "/student", status_code=302
                )

        # Sign-in still blocked (email not confirmed on Supabase, no service key)
        request.session["pending_email"] = user_email
        return RedirectResponse("/verify-pending", status_code=302)

    # Normal flow: ask user to verify email
    request.session["pending_email"] = user_email
    return RedirectResponse("/verify-pending", status_code=302)


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    # --- DEV MODE FAKE LOGIN ---
    if auth.SKIP_EMAIL_VERIFICATION and not auth.SUPABASE_SERVICE_ROLE_KEY:
        db = auth.SessionLocal()
        try:
            profile = db.query(auth.Profile).filter(auth.Profile.email == email).first()
            if profile:
                request.session["access_token"] = "fake_dev_token"
                request.session["role"] = profile.role
                request.session["user_id"] = str(profile.id)
                return RedirectResponse("/admin" if profile.role == "admin" else "/student", status_code=302)
            return RedirectResponse("/login?error=Invalid+login+credentials", status_code=302)
        finally:
            db.close()
    # ---------------------------

    result = auth.supabase_sign_in(email, password)

    err = result.get("error_description") or result.get("error") or result.get("msg")
    if err:
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)

        # If "email not confirmed" and we're in dev mode, try to confirm via service role
        if "email not confirmed" in msg.lower() and auth.SKIP_EMAIL_VERIFICATION:
            # Look up user by email and force-confirm them
            user_info = auth.supabase_admin_get_user_by_email(email)
            if user_info and auth.supabase_admin_confirm_user(user_info["id"]):
                # Retry sign-in now that user is confirmed
                result = auth.supabase_sign_in(email, password)
                err = result.get("error_description") or result.get("error")
                if err:
                    return RedirectResponse(f"/login?error=Auto-confirm+failed:+{err}", status_code=302)
            else:
                # No service role key — guide user to Supabase dashboard
                request.session["pending_email"] = email
                return RedirectResponse("/verify-pending", status_code=302)

        elif "email not confirmed" in msg.lower():
            request.session["pending_email"] = email
            return RedirectResponse("/verify-pending?error=Please+verify+your+email+first.", status_code=302)

        elif err:
            return RedirectResponse(f"/login?error={msg}", status_code=302)

    access_token = result.get("access_token")
    if not access_token:
        return RedirectResponse("/login?error=Login+failed.+Please+try+again.", status_code=302)

    payload = auth.verify_supabase_jwt(access_token)
    user_obj = result.get("user", {})

    # Use JWT payload if valid, otherwise fall back to sign-in response user object
    user_id = (payload or {}).get("sub") or user_obj.get("id")
    user_email = (payload or {}).get("email") or user_obj.get("email", email)
    email_confirmed = (payload or {}).get("email_confirmed_at")

    if not user_id:
        return RedirectResponse("/login?error=Session+error.+Please+try+again.", status_code=302)

    profile = auth.get_or_create_profile(user_id, user_email)
    request.session["access_token"] = access_token
    request.session["role"] = profile.role
    request.session["user_id"] = str(user_id)

    # Require verification unless bypass is on
    if not email_confirmed and not auth.SKIP_EMAIL_VERIFICATION:
        request.session["pending_email"] = user_email
        return RedirectResponse(
            "/verify-pending?error=Please+click+the+link+in+your+email+to+continue.",
            status_code=302,
        )
    return RedirectResponse("/admin" if profile.role == "admin" else "/student", status_code=302)




@router.get("/verify-pending", response_class=HTMLResponse)
async def verify_pending(request: Request, error: str = None, success: str = None):
    # If verification is skipped globally, just redirect home
    if auth.SKIP_EMAIL_VERIFICATION:
        user = auth.get_current_user(request)
        if user:
            return RedirectResponse(
                "/admin" if user["role"] == "admin" else "/student", status_code=302
            )
    email = request.session.get("pending_email", "your email")
    return templates.TemplateResponse("verify_pending.html", {
        "request": request,
        "email": email,
        "error": error,
        "success": success,
        "skip_verification": auth.SKIP_EMAIL_VERIFICATION,
    })


@router.post("/resend-verification")
async def resend_verification(request: Request):
    email = request.session.get("pending_email")
    if not email:
        return RedirectResponse(
            "/verify-pending?error=Session+expired.+Please+try+signing+in+again.",
            status_code=302,
        )

    success, message = auth.supabase_resend_confirmation(email)
    param = "success" if success else "error"
    # URL-encode the message
    from urllib.parse import quote
    return RedirectResponse(
        f"/verify-pending?{param}={quote(message)}", status_code=302
    )


@router.get("/auth/callback", response_class=HTMLResponse)
async def auth_callback(request: Request):
    """Landing page after clicking the Supabase email verification link."""
    return templates.TemplateResponse("auth_callback.html", {"request": request})


@router.post("/auth/set-session")
async def set_session(request: Request):
    """Called by auth_callback.html after extracting token from URL hash."""
    body = await request.json()
    access_token = body.get("access_token")
    error = body.get("error")

    if error:
        return JSONResponse({"error": error, "error_description": body.get("error_description")}, status_code=400)

    if not access_token:
        return JSONResponse({"error": "No token"}, status_code=400)

    payload = auth.verify_supabase_jwt(access_token)

    if not payload:
        # Trust Supabase response even if our JWT secret is wrong
        user_info = body.get("user") or {}
        user_id = user_info.get("id")
        user_email = user_info.get("email", "")
        if not user_id:
            return JSONResponse({"error": "Could not parse token"}, status_code=400)
        profile = auth.get_or_create_profile(user_id, user_email)
        request.session["access_token"] = access_token
        request.session["role"] = profile.role
        request.session["user_id"] = str(user_id)
        request.session.pop("pending_email", None)
        return JSONResponse({"ok": True})

    user_id = payload.get("sub")
    user_email = payload.get("email", "")
    profile = auth.get_or_create_profile(user_id, user_email)

    request.session["access_token"] = access_token
    request.session["role"] = profile.role
    request.session["user_id"] = str(user_id)
    request.session.pop("pending_email", None)

    return JSONResponse({"ok": True})


@router.get("/check-verified")
async def check_verified(request: Request):
    """Polled by verify-pending page to detect when user is confirmed."""
    if auth.SKIP_EMAIL_VERIFICATION:
        user = auth.get_current_user(request)
        if user:
            return JSONResponse({"verified": True, "redirect": "/admin" if user["role"] == "admin" else "/student"})

    user = auth.get_current_user(request)
    if user and user.get("email_confirmed"):
        return JSONResponse({"verified": True, "redirect": "/admin" if user["role"] == "admin" else "/student"})

    return JSONResponse({"verified": False})


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login?success=You+have+been+logged+out.", status_code=302)
