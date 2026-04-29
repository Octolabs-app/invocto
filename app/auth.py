"""
auth.py — Authentication logic and routes.

Uses:
  - passlib[bcrypt] for password hashing
  - python-jose for JWT token creation/verification
  - httpOnly cookies to store the token (not accessible via JS → XSS protection)
"""
import os
from datetime import datetime, timedelta

import bcrypt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# ── Constants ────────────────────────────────────────────────────────────────
SECRET_KEY  = os.getenv("SECRET_KEY", "CHANGE-ME-USE-A-RANDOM-SECRET-IN-PRODUCTION")
ALGORITHM   = "HS256"
COOKIE_NAME = "access_token"
TOKEN_EXPIRE_DAYS = 7

# ── Password hashing (using bcrypt directly for Python 3.12 compatibility) ───
def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def hash_password(plain: str) -> str:
    """Hash a plain-text password with bcrypt and return as string."""
    hashed = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


# ── JWT helpers ───────────────────────────────────────────────────────────────
def create_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> int | None:
    """Return user_id from token, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        return None


# ── Current user helpers ──────────────────────────────────────────────────────
def get_current_user(request: Request, db: Session) -> User | None:
    """Read JWT from cookie and return the User object, or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    user_id = decode_token(token)
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency that redirects to /login if not authenticated."""
    user = get_current_user(request, db)
    if not user:
        # Raise a redirect — caller must handle RedirectResponse
        raise _AuthRedirect()
    return user


class _AuthRedirect(Exception):
    """Sentinel to signal an unauthenticated request."""


# ── Routes ────────────────────────────────────────────────────────────────────
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    email    = form.get("email", "").strip().lower()
    password = form.get("password", "")

    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid email or password."},
        )

    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        COOKIE_NAME, create_token(user.id),
        httponly=True, max_age=TOKEN_EXPIRE_DAYS * 86_400, samesite="lax"
    )
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@router.post("/register", response_class=HTMLResponse)
async def register_submit(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    email    = form.get("email", "").strip().lower()
    password = form.get("password", "")
    confirm  = form.get("confirm_password", "")

    # Basic validation
    if len(email) < 3 or "@" not in email:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "Please enter a valid email."}
        )
    if len(password) < 8:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "Password must be at least 8 characters."}
        )
    if password != confirm:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "Passwords do not match."}
        )
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "That email is already registered."}
        )

    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        COOKIE_NAME, create_token(user.id),
        httponly=True, max_age=TOKEN_EXPIRE_DAYS * 86_400, samesite="lax"
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response
