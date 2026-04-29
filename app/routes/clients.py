"""
clients.py — CRUD routes for managing clients.

All routes require an authenticated user. Users can only see/edit their own clients.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Client
from ..auth import get_current_user

router = APIRouter(prefix="/clients")
templates = Jinja2Templates(directory="app/templates")


def _auth(request: Request, db: Session):
    """Helper: return user or redirect."""
    user = get_current_user(request, db)
    if not user:
        raise _Redirect("/login")
    return user


class _Redirect(Exception):
    def __init__(self, url: str):
        self.url = url


# ── List ─────────────────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def list_clients(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    clients = (
        db.query(Client)
        .filter(Client.user_id == user.id)
        .order_by(Client.name)
        .all()
    )
    return templates.TemplateResponse("clients.html", {
        "request": request,
        "user": user,
        "clients": clients,
        "edit_client": None,
        "success": request.query_params.get("success"),
    })


# ── Add ───────────────────────────────────────────────────────────────────────
@router.post("/add")
async def add_client(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    client = Client(
        user_id = user.id,
        name    = form.get("name", "").strip(),
        email   = form.get("email", "").strip() or None,
        address = form.get("address", "").strip() or None,
        phone   = form.get("phone", "").strip() or None,
    )
    db.add(client)
    db.commit()
    return RedirectResponse("/clients/?success=added", status_code=302)


# ── Edit page ─────────────────────────────────────────────────────────────────
@router.get("/{client_id}/edit", response_class=HTMLResponse)
async def edit_client_page(client_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    client = db.query(Client).filter(Client.id == client_id, Client.user_id == user.id).first()
    if not client:
        return RedirectResponse("/clients/", status_code=302)

    clients = db.query(Client).filter(Client.user_id == user.id).order_by(Client.name).all()
    return templates.TemplateResponse("clients.html", {
        "request": request,
        "user": user,
        "clients": clients,
        "edit_client": client,
    })


# ── Edit submit ───────────────────────────────────────────────────────────────
@router.post("/{client_id}/edit")
async def edit_client(client_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    client = db.query(Client).filter(Client.id == client_id, Client.user_id == user.id).first()
    if client:
        form = await request.form()
        client.name    = form.get("name", "").strip()
        client.email   = form.get("email", "").strip() or None
        client.address = form.get("address", "").strip() or None
        client.phone   = form.get("phone", "").strip() or None
        db.commit()
    return RedirectResponse("/clients/?success=updated", status_code=302)


# ── Delete ────────────────────────────────────────────────────────────────────
@router.post("/{client_id}/delete")
async def delete_client(client_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    client = db.query(Client).filter(Client.id == client_id, Client.user_id == user.id).first()
    if client:
        db.delete(client)
        db.commit()
    return RedirectResponse("/clients/", status_code=302)
