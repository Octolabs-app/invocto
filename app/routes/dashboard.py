"""
dashboard.py — Main dashboard and /api/monthly-income JSON endpoint.
"""
from datetime import date
from collections import defaultdict
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Invoice, Expense
from ..auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    today        = date.today()
    current_year = today.year

    invoices = db.query(Invoice).filter(
        Invoice.user_id == user.id,
        Invoice.is_template == False
    ).all()

    # Totals grouped by currency
    paid_totals    = defaultdict(float)
    pending_totals = defaultdict(float)
    overdue_totals = defaultdict(float)

    for inv in invoices:
        t = inv.total
        c = inv.currency
        if inv.status == "paid":
            paid_totals[c] += t
        else:
            pending_totals[c] += t
            if inv.due_date < today:
                overdue_totals[c] += t

    # Expenses this year
    expenses = db.query(Expense).filter(
        Expense.user_id == user.id,
        Expense.date    >= date(current_year, 1, 1),
        Expense.date    <= date(current_year, 12, 31),
    ).all()
    total_expenses = sum(e.amount for e in expenses)

    recent = sorted(invoices, key=lambda i: i.created_at, reverse=True)[:5]

    return templates.TemplateResponse("dashboard.html", {
        "request":        request,
        "user":           user,
        "today":          today,
        "paid_totals":    dict(paid_totals),
        "pending_totals": dict(pending_totals),
        "overdue_totals": dict(overdue_totals),
        "total_expenses": total_expenses,
        "recent_invoices": recent,
        "current_year":   current_year,
    })


@router.get("/api/monthly-income")
async def monthly_income(request: Request, db: Session = Depends(get_db)):
    """Monthly USD income for Chart.js bar chart."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    current_year = date.today().year
    monthly = [0.0] * 12

    invoices = db.query(Invoice).filter(
        Invoice.user_id    == user.id,
        Invoice.status     == "paid",
        Invoice.currency   == "USD",
        Invoice.is_template == False,
    ).all()

    for inv in invoices:
        if inv.payment_date and inv.payment_date.year == current_year:
            monthly[inv.payment_date.month - 1] += inv.total

    return JSONResponse({"months": monthly, "year": current_year})
