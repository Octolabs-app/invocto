"""
main.py — FastAPI application entry point v3.0
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

from .database import engine, Base
from . import models  # noqa
from .auth import router as auth_router, COOKIE_NAME, decode_token
from .routes.dashboard    import router as dashboard_router
from .routes.clients      import router as clients_router
from .routes.invoices     import router as invoices_router
from .routes.expenses     import router as expenses_router
from .routes.reports      import router as reports_router
from .routes.profile      import router as profile_router
from .routes.billing      import router as billing_router
from .routes.items        import router as items_router
from .routes.estimates    import router as estimates_router
from .routes.time_tracker import router as time_router
from .routes.recurring    import router as recurring_router
from .routes.public       import router as public_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        Base.metadata.create_all(bind=engine)
        print("INFO:     Database tables verified.")
    except Exception as e:
        print(f"WARNING:  DB table check failed (tables may already exist): {e}")

    # Start scheduler only if APScheduler installed + email configured
    scheduler_started = False
    try:
        from .scheduler import start_scheduler
        start_scheduler()
        scheduler_started = True
        print("INFO:     Scheduler started.")
    except ImportError:
        print("INFO:     APScheduler not installed — scheduler disabled.")
    except Exception as e:
        print(f"WARNING:  Scheduler failed to start: {e}")

    yield

    # Shutdown
    if scheduler_started:
        from .scheduler import stop_scheduler
        stop_scheduler()


app = FastAPI(
    title="Tax-Ready Invoice",
    version="3.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_router)
app.include_router(public_router)      # must be before auth middleware check
app.include_router(dashboard_router)
app.include_router(clients_router)
app.include_router(invoices_router)
app.include_router(expenses_router)
app.include_router(reports_router)
app.include_router(profile_router)
app.include_router(billing_router)
app.include_router(items_router)
app.include_router(estimates_router)
app.include_router(time_router)
app.include_router(recurring_router)

_PUBLIC = ("/login", "/register", "/start", "/static", "/billing/webhook", "/invoice/")

@app.middleware("http")
async def require_login_middleware(request: Request, call_next):
    path = request.url.path
    if any(path.startswith(p) for p in _PUBLIC):
        return await call_next(request)
    if path.startswith("/api/") or path.startswith("/items/api/"):
        return await call_next(request)
    # Validate the JWT itself (not just the cookie's presence) so an expired or
    # forged token is rejected at the gate rather than leaking past it.
    token = request.cookies.get(COOKIE_NAME)
    if not token or decode_token(token) is None:
        # No valid session → hand them an instant guest workspace (no sign-up).
        resp = RedirectResponse(url="/start", status_code=302)
        if token:
            resp.delete_cookie(COOKIE_NAME)
        return resp
    return await call_next(request)
