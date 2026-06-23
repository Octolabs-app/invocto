"""
recurring.py — Recurring invoice management UI.
The scheduler (scheduler.py) auto-generates these invoices daily.
"""
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Client, RecurringInvoice, RecurringLineItem
from ..auth import get_current_user
from ..utils import safe_float, safe_date
from ..routes.invoices import _owned_client_id

router = APIRouter(prefix="/recurring")
templates = Jinja2Templates(directory="app/templates")

FREQUENCIES = ["weekly", "monthly", "quarterly", "yearly"]
CURRENCIES  = ["USD", "EUR", "GBP", "MUR"]


def _parse_line_items(form):
    items = []
    for desc, qty, price in zip(
        form.getlist("description[]"),
        form.getlist("quantity[]"),
        form.getlist("unit_price[]")
    ):
        desc = desc.strip()
        if desc:
            items.append({"description": desc,
                          "quantity": safe_float(qty, 1.0),
                          "unit_price": safe_float(price, 0.0)})
    return items


@router.get("/", response_class=HTMLResponse)
async def list_recurring(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    recurrings = (db.query(RecurringInvoice)
                  .filter(RecurringInvoice.user_id == user.id)
                  .order_by(RecurringInvoice.next_date).all())
    return templates.TemplateResponse("recurring_list.html", {
        "request": request, "user": user,
        "recurrings": recurrings, "today": date.today(),
        "success": request.query_params.get("success"),
    })


@router.get("/new", response_class=HTMLResponse)
async def new_recurring_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    clients = db.query(Client).filter(Client.user_id == user.id).order_by(Client.name).all()
    if not clients:
        return RedirectResponse("/clients/?need_client=1", status_code=302)
    return templates.TemplateResponse("recurring_form.html", {
        "request": request, "user": user,
        "clients": clients, "frequencies": FREQUENCIES,
        "currencies": CURRENCIES, "recurring": None,
        "today": date.today().isoformat(),
    })


@router.post("/new")
async def create_recurring(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    form = await request.form()
    client_id = _owned_client_id(db, user.id, form.get("client_id"))
    if client_id is None:
        return RedirectResponse("/recurring/new?error=client", status_code=302)
    next_date = safe_date(form.get("next_date"))
    if next_date is None:
        return RedirectResponse("/recurring/new?error=next_date", status_code=302)
    rec = RecurringInvoice(
        user_id=user.id,
        client_id=client_id,
        frequency=form.get("frequency", "monthly"),
        next_date=next_date,
        end_date=safe_date(form.get("end_date")),
        currency=form.get("currency", "USD"),
        category=form.get("category", "Other"),
        notes=form.get("notes", "").strip(),
        payment_note=form.get("payment_note", "").strip(),
        template=form.get("template", "minimal"),
        active=True,
    )
    db.add(rec); db.flush()
    for item in _parse_line_items(form):
        db.add(RecurringLineItem(recurring_invoice_id=rec.id, **item))
    db.commit()
    return RedirectResponse("/recurring/?success=created", status_code=302)


@router.post("/{rec_id}/toggle")
async def toggle_recurring(rec_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    rec = db.query(RecurringInvoice).filter(RecurringInvoice.id == rec_id, RecurringInvoice.user_id == user.id).first()
    if rec:
        rec.active = not rec.active; db.commit()
    return RedirectResponse("/recurring/", status_code=302)


@router.post("/{rec_id}/delete")
async def delete_recurring(rec_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    rec = db.query(RecurringInvoice).filter(RecurringInvoice.id == rec_id, RecurringInvoice.user_id == user.id).first()
    if rec:
        db.delete(rec); db.commit()
    return RedirectResponse("/recurring/", status_code=302)
