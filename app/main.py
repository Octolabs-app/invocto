"""
main.py — FastAPI application entry point.

Startup tasks:
  1. Create all database tables (SQLAlchemy creates them if they don't exist).
  2. Mount static files at /static.
  3. Register all route routers.
  4. Add a middleware that redirects unauthenticated requests to /login
     (except for /login, /register, /static, and /api paths).

Run with:
    uvicorn app.main:app --reload
"""
import os
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

# Load .env first so all os.getenv() calls elsewhere work
load_dotenv()

from .database import engine, Base
from . import models  # noqa: F401 — ensures models are registered with Base
from .auth import router as auth_router, get_current_user, COOKIE_NAME
from .routes.dashboard import router as dashboard_router
from .routes.clients   import router as clients_router
from .routes.invoices  import router as invoices_router
from .routes.expenses  import router as expenses_router
from .routes.reports   import router as reports_router

# ── Create tables on startup (idempotent — won't overwrite existing data) ────
Base.metadata.create_all(bind=engine)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Tax-Ready Invoice",
    description="Invoice management for creative freelancers",
    version="1.0.0",
    docs_url=None,   # disable Swagger UI in production (optional)
    redoc_url=None,
)

# ── Static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(clients_router)
app.include_router(invoices_router)
app.include_router(expenses_router)
app.include_router(reports_router)

# ── Auth middleware ───────────────────────────────────────────────────────────
# Public paths that don't require a logged-in user
_PUBLIC_PREFIXES = ("/login", "/register", "/static")

@app.middleware("http")
async def require_login_middleware(request: Request, call_next):
    """
    Redirect any unauthenticated request to /login,
    unless the path is a public route or the /api/* endpoints
    (those return 401 JSON themselves).
    """
    path = request.url.path

    # Always allow public routes
    if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
        return await call_next(request)

    # API endpoints return JSON 401, not a redirect
    if path.startswith("/api/"):
        return await call_next(request)

    # Check cookie — if missing or invalid, redirect to login
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return RedirectResponse(url="/login", status_code=302)

    return await call_next(request)
