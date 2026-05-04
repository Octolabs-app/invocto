"""
public.py — Unauthenticated routes: public invoice view, payment confirmation.
Routes here are whitelisted in middleware.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Invoice
from ..email import send_invoice_email
from ..auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/invoice/{token}", response_class=HTMLResponse)
async def public_invoice(token: str, request: Request, db: Session = Depends(get_db)):
    """Public invoice view — no auth required. Accessible via emailed link."""
    invoice = db.query(Invoice).filter(Invoice.view_token == token).first()
    if not invoice:
        return HTMLResponse("<h2>Invoice not found or link has expired.</h2>", status_code=404)
    return templates.TemplateResponse("invoice_public.html", {
        "request": request, "invoice": invoice,
        "paid": request.query_params.get("paid"),
    })


@router.post("/invoices/{invoice_id}/send-email")
async def send_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    """Send invoice by email to the client."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if not invoice:
        return RedirectResponse("/invoices/", status_code=302)

    # Generate view_token if missing
    if not invoice.view_token:
        import uuid
        invoice.view_token = str(uuid.uuid4())
        db.commit()

    ok = send_invoice_email(invoice, user.email)

    if ok:
        from datetime import datetime
        invoice.last_sent_at = datetime.utcnow()
        db.commit()

    return RedirectResponse(f"/invoices/?sent={'ok' if ok else 'fail'}", status_code=302)
