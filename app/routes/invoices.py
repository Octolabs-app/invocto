"""
invoices.py — Invoice CRUD + live preview data + AI category + template support.
"""
import os
from datetime import date
from typing import Optional
import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Client, Invoice, LineItem, UserProfile
from ..auth import get_current_user
from ..utils import safe_float, safe_int, safe_date, next_sequence_number
from ..einvoice import invoice_to_ubl

router = APIRouter(prefix="/invoices")
templates = Jinja2Templates(directory="app/templates")

CATEGORIES = ["Design", "Writing", "Video", "Social Media", "Consulting", "Other"]
CURRENCIES  = ["USD", "EUR", "GBP", "MUR"]


async def suggest_category(descriptions: list) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or not descriptions:
        return "Other"
    prompt = (
        "You are a bookkeeping assistant. Based on these freelance service descriptions, "
        "choose ONE category: Design, Writing, Video, Social Media, Consulting, Other.\n"
        f"Descriptions: {', '.join(descriptions)}\nReply with ONLY the category name."
    )
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-1.5-flash:generateContent?key={api_key}")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            for cat in CATEGORIES:
                if cat.lower() in text.lower():
                    return cat
    except Exception:
        pass
    return "Other"


def next_invoice_number(db: Session, user_id: int) -> str:
    # Derive from the highest existing number (not a row count) so deleting an
    # invoice can never cause the next one to reuse an existing number.
    nums = [n for (n,) in db.query(Invoice.invoice_number)
            .filter(Invoice.user_id == user_id, Invoice.is_template == False).all()]
    return next_sequence_number(nums, "INV")


def _parse_line_items(form) -> list:
    items = []
    for desc, qty, price in zip(form.getlist("description[]"), form.getlist("quantity[]"), form.getlist("unit_price[]")):
        desc = desc.strip()
        if desc:
            items.append({"description": desc,
                          "quantity": safe_float(qty, 1.0),
                          "unit_price": safe_float(price, 0.0)})
    return items


def _owned_client_id(db: Session, user_id: int, raw) -> Optional[int]:
    """Return the client id only if it is a valid int owned by this user."""
    cid = safe_int(raw)
    if cid is None:
        return None
    exists = db.query(Client.id).filter(Client.id == cid, Client.user_id == user_id).first()
    return cid if exists else None


def _save_line_items(db, invoice_id, items):
    for item in items:
        db.add(LineItem(invoice_id=invoice_id, **item))


def _get_profile(db: Session, user_id: int) -> Optional[UserProfile]:
    return db.query(UserProfile).filter(UserProfile.user_id == user_id).first()


# ── List ──────────────────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def list_invoices(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    invoices = (db.query(Invoice)
                .filter(Invoice.user_id == user.id, Invoice.is_template == False)
                .order_by(Invoice.created_at.desc()).all())
    templates_list = (db.query(Invoice)
                      .filter(Invoice.user_id == user.id, Invoice.is_template == True).all())
    return templates.TemplateResponse("invoice_list.html", {
        "request": request, "user": user,
        "invoices": invoices, "templates_list": templates_list,
        "today": date.today(),
    })


# ── New invoice ───────────────────────────────────────────────────────────────
@router.get("/new", response_class=HTMLResponse)
async def new_invoice_page(request: Request, from_template: int = 0, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    clients = db.query(Client).filter(Client.user_id == user.id).order_by(Client.name).all()
    if not clients:
        return RedirectResponse("/clients/?need_client=1", status_code=302)
    profile = _get_profile(db, user.id)
    tmpl_invoice = None
    if from_template:
        tmpl_invoice = db.query(Invoice).filter(Invoice.id == from_template, Invoice.user_id == user.id).first()
    return templates.TemplateResponse("invoice_form.html", {
        "request": request, "user": user, "clients": clients,
        "categories": CATEGORIES, "currencies": CURRENCIES,
        "invoice": None, "tmpl_invoice": tmpl_invoice,
        "next_number": next_invoice_number(db, user.id),
        "today": date.today().isoformat(), "profile": profile,
    })


@router.post("/new")
async def create_invoice(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    form = await request.form()

    client_id = _owned_client_id(db, user.id, form.get("client_id"))
    if client_id is None:
        return RedirectResponse("/invoices/new?error=client", status_code=302)
    due_date = safe_date(form.get("due_date"))
    if due_date is None:
        return RedirectResponse("/invoices/new?error=due_date", status_code=302)

    items = _parse_line_items(form)
    category = await suggest_category([i["description"] for i in items])
    is_template = bool(form.get("save_as_template"))
    invoice = Invoice(
        user_id=user.id,
        client_id=client_id,
        invoice_number=form.get("invoice_number", "").strip() or next_invoice_number(db, user.id),
        due_date=due_date,
        currency=form.get("currency", "USD"),
        category=category,
        notes=form.get("notes", "").strip(),
        template=form.get("template", "minimal"),
        payment_note=form.get("payment_note", "").strip(),
        discount_pct=safe_float(form.get("discount_pct"), 0.0),
        tax_rate=safe_float(form.get("tax_rate"), 0.0),
        late_fee_amount=safe_float(form.get("late_fee_amount"), 0.0),
        is_template=is_template,
        template_name=form.get("template_name", "").strip() if is_template else None,
        status="unpaid",
    )
    db.add(invoice)
    db.flush()
    _save_line_items(db, invoice.id, items)
    db.commit()
    return RedirectResponse("/invoices/?created=1", status_code=302)


# ── Edit ──────────────────────────────────────────────────────────────────────
@router.get("/{invoice_id}/edit", response_class=HTMLResponse)
async def edit_invoice_page(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if not invoice:
        return RedirectResponse("/invoices/", status_code=302)
    clients = db.query(Client).filter(Client.user_id == user.id).order_by(Client.name).all()
    profile = _get_profile(db, user.id)
    return templates.TemplateResponse("invoice_form.html", {
        "request": request, "user": user, "clients": clients,
        "categories": CATEGORIES, "currencies": CURRENCIES,
        "invoice": invoice, "tmpl_invoice": None,
        "today": date.today().isoformat(), "profile": profile,
    })


@router.post("/{invoice_id}/edit")
async def edit_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if not invoice:
        return RedirectResponse("/invoices/", status_code=302)
    form = await request.form()
    client_id = _owned_client_id(db, user.id, form.get("client_id"))
    if client_id is None:
        return RedirectResponse(f"/invoices/{invoice_id}/edit?error=client", status_code=302)
    due_date = safe_date(form.get("due_date"))
    if due_date is None:
        return RedirectResponse(f"/invoices/{invoice_id}/edit?error=due_date", status_code=302)
    invoice.client_id    = client_id
    invoice.due_date     = due_date
    invoice.currency     = form.get("currency", "USD")
    invoice.category     = form.get("category", "Other")
    invoice.notes        = form.get("notes", "").strip()
    invoice.template     = form.get("template", "minimal")
    invoice.payment_note = form.get("payment_note", "").strip()
    invoice.discount_pct    = safe_float(form.get("discount_pct"), 0.0)
    invoice.tax_rate        = safe_float(form.get("tax_rate"), 0.0)
    invoice.late_fee_amount = safe_float(form.get("late_fee_amount"), 0.0)
    invoice.is_template  = bool(form.get("save_as_template"))
    invoice.template_name= form.get("template_name", "").strip() if invoice.is_template else None
    for old in invoice.line_items:
        db.delete(old)
    db.flush()
    _save_line_items(db, invoice.id, _parse_line_items(form))
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


# ── Mark paid/unpaid ──────────────────────────────────────────────────────────
@router.post("/{invoice_id}/mark-paid")
async def mark_paid(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    inv = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if inv:
        inv.status = "paid"; inv.payment_date = date.today(); db.commit()
    return RedirectResponse("/invoices/", status_code=302)


@router.post("/{invoice_id}/mark-unpaid")
async def mark_unpaid(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    inv = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if inv:
        inv.status = "unpaid"; inv.payment_date = None; db.commit()
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
            user_id=user.id, client_id=src.client_id,
            invoice_number=next_invoice_number(db, user.id),
            due_date=src.due_date, currency=src.currency, category=src.category,
            notes=src.notes, template=src.template, payment_note=src.payment_note,
            discount_pct=src.discount_pct, tax_rate=src.tax_rate,
            status="unpaid", is_template=False,
        )
        db.add(new_inv); db.flush()
        for item in src.line_items:
            db.add(LineItem(invoice_id=new_inv.id, description=item.description,
                            quantity=item.quantity, unit_price=item.unit_price))
        db.commit()
    return RedirectResponse("/invoices/", status_code=302)


# ── Print ─────────────────────────────────────────────────────────────────────
@router.get("/{invoice_id}/print", response_class=HTMLResponse)
async def print_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if not invoice:
        return RedirectResponse("/invoices/", status_code=302)
    profile = _get_profile(db, user.id)
    return templates.TemplateResponse("invoice_print.html", {
        "request": request, "invoice": invoice, "user": user, "profile": profile,
    })


# ── E-invoice (UBL / EN 16931 XML) ────────────────────────────────────────────
@router.get("/{invoice_id}/einvoice.xml")
async def invoice_einvoice(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if not invoice:
        return RedirectResponse("/invoices/", status_code=302)
    profile = _get_profile(db, user.id)
    xml = invoice_to_ubl(invoice, profile, user.email)
    return Response(content=xml, media_type="application/xml", headers={
        "Content-Disposition": f'attachment; filename="einvoice_{invoice.invoice_number}.xml"'
    })


# ── Bulk mark paid ────────────────────────────────────────────────────────────
@router.post("/bulk-paid")
async def bulk_mark_paid(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    form = await request.form()
    ids_raw = form.get("ids", "")
    ids = [int(i) for i in ids_raw.split(",") if i.strip().isdigit()]
    if ids:
        invoices = db.query(Invoice).filter(
            Invoice.id.in_(ids),
            Invoice.user_id == user.id,
            Invoice.status == "unpaid"
        ).all()
        for inv in invoices:
            inv.status = "paid"
            inv.payment_date = date.today()
        db.commit()
    return RedirectResponse("/invoices/", status_code=302)
