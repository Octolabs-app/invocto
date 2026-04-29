"""
invoices.py — Invoice CRUD routes with AI-powered category suggestion via Gemini.

Key behaviours:
  - Invoice numbers auto-generated per-user as INV-0001, INV-0002, …
  - On creation, Gemini API is called asynchronously to suggest a category.
    If the call fails (no API key, network error, bad response) we silently
    default to "Other" — the app never crashes due to Gemini unavailability.
  - On edit, the user can manually change the category.
  - Marking paid records today's date as payment_date.
  - Duplicate creates a new invoice copying all fields + line items.
"""
import os
from datetime import date

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Client, Invoice, LineItem
from ..auth import get_current_user

router = APIRouter(prefix="/invoices")
templates = Jinja2Templates(directory="app/templates")

CATEGORIES = ["Design", "Writing", "Video", "Social Media", "Consulting", "Other"]
CURRENCIES = ["USD", "EUR", "GBP", "MUR"]


# ── AI Categorization ─────────────────────────────────────────────────────────
async def suggest_category(descriptions: list[str]) -> str:
    """
    Call Google Gemini API to guess the best service category.
    Returns one of: Design, Writing, Video, Social Media, Consulting, Other.
    Defaults to "Other" on any error.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or not descriptions:
        return "Other"

    prompt = (
        "You are a bookkeeping assistant. Based on the following freelance service "
        "descriptions, choose ONE category from this list: "
        "Design, Writing, Video, Social Media, Consulting, Other.\n\n"
        f"Descriptions: {', '.join(descriptions)}\n\n"
        "Reply with ONLY the category name — nothing else."
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-1.5-flash:generateContent?key={api_key}"
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Validate against known categories
            for cat in CATEGORIES:
                if cat.lower() in text.lower():
                    return cat
    except Exception:
        pass  # Any error → fall through to default

    return "Other"


# ── Helpers ───────────────────────────────────────────────────────────────────
def next_invoice_number(db: Session, user_id: int) -> str:
    """Generate the next sequential invoice number for this user."""
    count = db.query(Invoice).filter(Invoice.user_id == user_id).count()
    return f"INV-{count + 1:04d}"


def _parse_line_items(form) -> list[dict]:
    """Extract and validate line item arrays from form data."""
    descriptions = form.getlist("description[]")
    quantities   = form.getlist("quantity[]")
    unit_prices  = form.getlist("unit_price[]")

    items = []
    for desc, qty, price in zip(descriptions, quantities, unit_prices):
        desc = desc.strip()
        if desc:
            items.append({
                "description": desc,
                "quantity":    float(qty)   if qty   else 1.0,
                "unit_price":  float(price) if price else 0.0,
            })
    return items


def _save_line_items(db: Session, invoice_id: int, items: list[dict]):
    for item in items:
        db.add(LineItem(invoice_id=invoice_id, **item))


# ── List ──────────────────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def list_invoices(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    invoices = (
        db.query(Invoice)
        .filter(Invoice.user_id == user.id)
        .order_by(Invoice.created_at.desc())
        .all()
    )
    return templates.TemplateResponse("invoice_list.html", {
        "request":  request,
        "user":     user,
        "invoices": invoices,
        "today":    date.today(),
    })


# ── New invoice — form ────────────────────────────────────────────────────────
@router.get("/new", response_class=HTMLResponse)
async def new_invoice_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    clients = db.query(Client).filter(Client.user_id == user.id).order_by(Client.name).all()
    if not clients:
        # Redirect to clients page first so user can add a client
        return RedirectResponse("/clients/?need_client=1", status_code=302)

    return templates.TemplateResponse("invoice_form.html", {
        "request":      request,
        "user":         user,
        "clients":      clients,
        "categories":   CATEGORIES,
        "currencies":   CURRENCIES,
        "invoice":      None,
        "next_number":  next_invoice_number(db, user.id),
        "today":        date.today().isoformat(),
    })


# ── New invoice — submit ──────────────────────────────────────────────────────
@router.post("/new")
async def create_invoice(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()

    client_id      = int(form.get("client_id"))
    due_date       = date.fromisoformat(form.get("due_date"))
    currency       = form.get("currency", "USD")
    notes          = form.get("notes", "").strip()
    invoice_number = form.get("invoice_number", "").strip() or next_invoice_number(db, user.id)

    items = _parse_line_items(form)
    # AI category suggestion (async, fails silently)
    category = await suggest_category([i["description"] for i in items])

    invoice = Invoice(
        user_id        = user.id,
        client_id      = client_id,
        invoice_number = invoice_number,
        due_date       = due_date,
        currency       = currency,
        category       = category,
        notes          = notes,
        status         = "unpaid",
    )
    db.add(invoice)
    db.flush()  # get invoice.id without committing
    _save_line_items(db, invoice.id, items)
    db.commit()

    return RedirectResponse("/invoices/?created=1", status_code=302)


# ── Edit — form ───────────────────────────────────────────────────────────────
@router.get("/{invoice_id}/edit", response_class=HTMLResponse)
async def edit_invoice_page(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if not invoice:
        return RedirectResponse("/invoices/", status_code=302)

    clients = db.query(Client).filter(Client.user_id == user.id).order_by(Client.name).all()
    return templates.TemplateResponse("invoice_form.html", {
        "request":    request,
        "user":       user,
        "clients":    clients,
        "categories": CATEGORIES,
        "currencies": CURRENCIES,
        "invoice":    invoice,
        "today":      date.today().isoformat(),
    })


# ── Edit — submit ─────────────────────────────────────────────────────────────
@router.post("/{invoice_id}/edit")
async def edit_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if not invoice:
        return RedirectResponse("/invoices/", status_code=302)

    form = await request.form()
    invoice.client_id = int(form.get("client_id"))
    invoice.due_date  = date.fromisoformat(form.get("due_date"))
    invoice.currency  = form.get("currency", "USD")
    invoice.category  = form.get("category", "Other")
    invoice.notes     = form.get("notes", "").strip()

    # Replace all line items
    for old in invoice.line_items:
        db.delete(old)
    db.flush()

    items = _parse_line_items(form)
    _save_line_items(db, invoice.id, items)
    db.commit()

    return RedirectResponse("/invoices/", status_code=302)


# ── Delete ────────────────────────────────────────────────────────────────────
@router.post("/{invoice_id}/delete")
async def delete_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if invoice:
        db.delete(invoice)
        db.commit()
    return RedirectResponse("/invoices/", status_code=302)


# ── Mark paid ─────────────────────────────────────────────────────────────────
@router.post("/{invoice_id}/mark-paid")
async def mark_paid(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if invoice:
        invoice.status       = "paid"
        invoice.payment_date = date.today()
        db.commit()
    return RedirectResponse("/invoices/", status_code=302)


# ── Mark unpaid ───────────────────────────────────────────────────────────────
@router.post("/{invoice_id}/mark-unpaid")
async def mark_unpaid(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if invoice:
        invoice.status       = "unpaid"
        invoice.payment_date = None
        db.commit()
    return RedirectResponse("/invoices/", status_code=302)


# ── Duplicate ─────────────────────────────────────────────────────────────────
@router.post("/{invoice_id}/duplicate")
async def duplicate_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    src = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if src:
        new_inv = Invoice(
            user_id        = user.id,
            client_id      = src.client_id,
            invoice_number = next_invoice_number(db, user.id),
            due_date       = src.due_date,
            currency       = src.currency,
            category       = src.category,
            notes          = src.notes,
            status         = "unpaid",
        )
        db.add(new_inv)
        db.flush()
        for item in src.line_items:
            db.add(LineItem(
                invoice_id  = new_inv.id,
                description = item.description,
                quantity    = item.quantity,
                unit_price  = item.unit_price,
            ))
        db.commit()

    return RedirectResponse("/invoices/", status_code=302)


# ── Print / PDF ───────────────────────────────────────────────────────────────
@router.get("/{invoice_id}/print", response_class=HTMLResponse)
async def print_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if not invoice:
        return RedirectResponse("/invoices/", status_code=302)

    return templates.TemplateResponse("invoice_print.html", {
        "request": request,
        "invoice": invoice,
        "user":    user,
    })
