"""
main.py — FastAPI application entry point.
"""
import os
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

from .database import engine, Base
from . import models  # noqa: F401
from .auth import router as auth_router, COOKIE_NAME
from .routes.dashboard import router as dashboard_router
from .routes.clients   import router as clients_router
from .routes.invoices  import router as invoices_router
from .routes.expenses  import router as expenses_router
from .routes.reports   import router as reports_router

# ── Create tables (safe: skips existing, wrapped so a DB hiccup won't crash startup)
try:
    Base.metadata.create_all(bind=engine)
    print("INFO:     Database tables verified.")
except Exception as e:
    print(f"WARNING:  Could not verify DB tables at startup: {e}")
    print("WARNING:  App will still start — tables may already exist.")

app = FastAPI(title="Tax-Ready Invoice", version="1.0.0", docs_url=None, redoc_url=None)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(clients_router)
app.include_router(invoices_router)
app.include_router(expenses_router)
app.include_router(reports_router)

_PUBLIC_PREFIXES = ("/login", "/register", "/static")

@app.middleware("http")
async def require_login_middleware(request: Request, call_next):
    path = request.url.path
    if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
        return await call_next(request)
    if path.startswith("/api/"):
        return await call_next(request)
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return RedirectResponse(url="/login", status_code=302)
    return await call_next(request)
