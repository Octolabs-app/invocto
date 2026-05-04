"""
time_tracker.py — Log billable hours, convert to invoice line items.
"""
from datetime import date
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Client, TimeLog, Invoice, LineItem
from ..auth import get_current_user
from ..routes.invoices import next_invoice_number

router = APIRouter(prefix="/time")
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def list_time(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    logs    = db.query(TimeLog).filter(TimeLog.user_id == user.id).order_by(TimeLog.log_date.desc()).all()
    clients = db.query(Client).filter(Client.user_id == user.id).order_by(Client.name).all()
    unbilled = [l for l in logs if not l.invoiced]
    total_unbilled = sum(l.amount for l in unbilled)
    return templates.TemplateResponse("time_tracker.html", {
        "request": request, "user": user, "logs": logs,
        "clients": clients, "unbilled": unbilled,
        "total_unbilled": total_unbilled,
        "today": date.today().isoformat(),
        "success": request.query_params.get("success"),
    })


@router.post("/add")
async def add_time(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    form = await request.form()
    log = TimeLog(
        user_id     = user.id,
        client_id   = int(form.get("client_id")) if form.get("client_id") else None,
        description = form.get("description", "").strip(),
        hours       = float(form.get("hours", 0)),
        rate        = float(form.get("rate", 0)),
        log_date    = date.fromisoformat(form.get("log_date", date.today().isoformat())),
    )
    db.add(log); db.commit()
    return RedirectResponse("/time/?success=added", status_code=302)


@router.post("/{log_id}/delete")
async def delete_time(log_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    log = db.query(TimeLog).filter(TimeLog.id == log_id, TimeLog.user_id == user.id).first()
    if log:
        db.delete(log); db.commit()
    return RedirectResponse("/time/", status_code=302)


@router.post("/convert-to-invoice")
async def convert_to_invoice(request: Request, db: Session = Depends(get_db)):
    """Convert selected unbilled time entries to a new invoice."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    form    = await request.form()
    log_ids = [int(i) for i in form.get("log_ids", "").split(",") if i.strip().isdigit()]
    if not log_ids:
        return RedirectResponse("/time/", status_code=302)

    logs = db.query(TimeLog).filter(
        TimeLog.id.in_(log_ids), TimeLog.user_id == user.id, TimeLog.invoiced == False
    ).all()
    if not logs:
        return RedirectResponse("/time/", status_code=302)

    # Group by client — use the first log's client
    client_id = logs[0].client_id
    due       = date.fromisoformat(form.get("due_date", date.today().isoformat()))

    inv = Invoice(
        user_id=user.id, client_id=client_id,
        invoice_number=next_invoice_number(db, user.id),
        due_date=due, currency="USD", category="Consulting",
        status="unpaid", is_template=False,
    )
    db.add(inv); db.flush()

    for log in logs:
        db.add(LineItem(
            invoice_id  = inv.id,
            description = f"{log.description} ({log.hours}h @ {log.rate}/h)",
            quantity    = 1,
            unit_price  = log.amount,
        ))
        log.invoiced   = True
        log.invoice_id = inv.id

    db.commit()
    return RedirectResponse(f"/invoices/{inv.id}/edit", status_code=302)
