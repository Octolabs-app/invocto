"""
estimates.py — Estimates/quotes that can be converted to invoices in 1 click.
"""
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Client, Estimate, EstimateLineItem, Invoice, LineItem, UserProfile
from ..auth import get_current_user
from ..routes.invoices import next_invoice_number, _parse_line_items

router = APIRouter(prefix="/estimates")
templates = Jinja2Templates(directory="app/templates")

CATEGORIES = ["Design", "Writing", "Video", "Social Media", "Consulting", "Other"]
CURRENCIES  = ["USD", "EUR", "GBP", "MUR"]
STATUSES    = ["draft", "sent", "accepted", "declined"]


def next_estimate_number(db: Session, user_id: int) -> str:
    count = db.query(Estimate).filter(Estimate.user_id == user_id).count()
    return f"EST-{count + 1:04d}"


def _save_est_items(db, estimate_id, items):
    for item in items:
        db.add(EstimateLineItem(estimate_id=estimate_id, **item))


def _get_profile(db, user_id) -> Optional[UserProfile]:
    return db.query(UserProfile).filter(UserProfile.user_id == user_id).first()


@router.get("/", response_class=HTMLResponse)
async def list_estimates(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    estimates = (db.query(Estimate).filter(Estimate.user_id == user.id)
                 .order_by(Estimate.created_at.desc()).all())
    return templates.TemplateResponse("estimate_list.html", {
        "request": request, "user": user, "estimates": estimates, "today": date.today(),
    })


@router.get("/new", response_class=HTMLResponse)
async def new_estimate_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    clients = db.query(Client).filter(Client.user_id == user.id).order_by(Client.name).all()
    if not clients:
        return RedirectResponse("/clients/?need_client=1", status_code=302)
    profile = _get_profile(db, user.id)
    return templates.TemplateResponse("estimate_form.html", {
        "request": request, "user": user, "clients": clients,
        "categories": CATEGORIES, "currencies": CURRENCIES,
        "estimate": None, "profile": profile,
        "next_number": next_estimate_number(db, user.id),
        "today": date.today().isoformat(),
    })


@router.post("/new")
async def create_estimate(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    form = await request.form()
    expiry = form.get("expiry_date", "")
    est = Estimate(
        user_id=user.id,
        client_id=int(form.get("client_id")),
        estimate_number=form.get("estimate_number") or next_estimate_number(db, user.id),
        expiry_date=date.fromisoformat(expiry) if expiry else None,
        currency=form.get("currency", "USD"),
        category=form.get("category", "Other"),
        notes=form.get("notes", "").strip(),
        payment_note=form.get("payment_note", "").strip(),
        template=form.get("template", "minimal"),
        status="draft",
    )
    db.add(est); db.flush()
    _save_est_items(db, est.id, _parse_line_items(form))
    db.commit()
    return RedirectResponse("/estimates/?created=1", status_code=302)


@router.get("/{est_id}/edit", response_class=HTMLResponse)
async def edit_estimate_page(est_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    est = db.query(Estimate).filter(Estimate.id == est_id, Estimate.user_id == user.id).first()
    if not est:
        return RedirectResponse("/estimates/", status_code=302)
    clients = db.query(Client).filter(Client.user_id == user.id).order_by(Client.name).all()
    profile = _get_profile(db, user.id)
    return templates.TemplateResponse("estimate_form.html", {
        "request": request, "user": user, "clients": clients,
        "categories": CATEGORIES, "currencies": CURRENCIES,
        "estimate": est, "profile": profile,
        "today": date.today().isoformat(),
    })


@router.post("/{est_id}/edit")
async def edit_estimate(est_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    est = db.query(Estimate).filter(Estimate.id == est_id, Estimate.user_id == user.id).first()
    if est:
        form = await request.form()
        expiry = form.get("expiry_date", "")
        est.client_id    = int(form.get("client_id"))
        est.expiry_date  = date.fromisoformat(expiry) if expiry else None
        est.currency     = form.get("currency", "USD")
        est.category     = form.get("category", "Other")
        est.notes        = form.get("notes", "").strip()
        est.payment_note = form.get("payment_note", "").strip()
        est.template     = form.get("template", "minimal")
        est.status       = form.get("status", "draft")
        for old in est.line_items: db.delete(old)
        db.flush()
        _save_est_items(db, est.id, _parse_line_items(form))
        db.commit()
    return RedirectResponse("/estimates/", status_code=302)


@router.post("/{est_id}/convert")
async def convert_to_invoice(est_id: int, request: Request, db: Session = Depends(get_db)):
    """Convert accepted estimate to invoice in 1 click."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    est = db.query(Estimate).filter(Estimate.id == est_id, Estimate.user_id == user.id).first()
    if not est:
        return RedirectResponse("/estimates/", status_code=302)

    inv = Invoice(
        user_id=user.id, client_id=est.client_id,
        invoice_number=next_invoice_number(db, user.id),
        due_date=date.today(), currency=est.currency,
        category=est.category, notes=est.notes,
        payment_note=est.payment_note, template=est.template,
        status="unpaid", is_template=False,
    )
    db.add(inv); db.flush()
    for item in est.line_items:
        db.add(LineItem(invoice_id=inv.id, description=item.description,
                        quantity=item.quantity, unit_price=item.unit_price))
    est.status = "accepted"
    est.converted_to_invoice_id = inv.id
    db.commit()
    return RedirectResponse(f"/invoices/{inv.id}/edit", status_code=302)


@router.post("/{est_id}/delete")
async def delete_estimate(est_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    est = db.query(Estimate).filter(Estimate.id == est_id, Estimate.user_id == user.id).first()
    if est:
        db.delete(est); db.commit()
    return RedirectResponse("/estimates/", status_code=302)
