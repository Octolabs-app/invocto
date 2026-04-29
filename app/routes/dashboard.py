"""
dashboard.py — Main dashboard view and the /api/monthly-income JSON endpoint
used by Chart.js to render the bar chart.
"""
from datetime import date
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

    # ── Load all user invoices ───────────────────────────────────────────────
    invoices = db.query(Invoice).filter(Invoice.user_id == user.id).all()

    # Build per-currency totals for paid, pending, overdue
    paid_totals    = {}   # currency → float
    pending_totals = {}
    overdue_totals = {}

    for inv in invoices:
        t = inv.total
        c = inv.currency
        if inv.status == "paid":
            paid_totals[c] = paid_totals.get(c, 0.0) + t
        else:
            pending_totals[c] = pending_totals.get(c, 0.0) + t
            if inv.due_date < today:
                overdue_totals[c] = overdue_totals.get(c, 0.0) + t

    # ── Expenses for current year ────────────────────────────────────────────
    year_start = date(current_year, 1, 1)
    year_end   = date(current_year, 12, 31)
    expenses   = db.query(Expense).filter(
        Expense.user_id == user.id,
        Expense.date    >= year_start,
        Expense.date    <= year_end,
    ).all()
    total_expenses = sum(e.amount for e in expenses)

    # ── Recent invoices (last 5 by creation date) ────────────────────────────
    recent = sorted(invoices, key=lambda i: i.created_at, reverse=True)[:5]

    return templates.TemplateResponse("dashboard.html", {
        "request":        request,
        "user":           user,
        "today":          today,
        "paid_totals":    paid_totals,
        "pending_totals": pending_totals,
        "overdue_totals": overdue_totals,
        "total_expenses": total_expenses,
        "recent_invoices": recent,
        "current_year":   current_year,
    })


@router.get("/api/monthly-income")
async def monthly_income(request: Request, db: Session = Depends(get_db)):
    """
    Returns monthly income totals for the current year (paid invoices only).
    Used by Chart.js on the dashboard.

    Response: { "months": [jan, feb, ..., dec] }  (12 floats, USD only)
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    current_year = date.today().year
    monthly = [0.0] * 12

    invoices = db.query(Invoice).filter(
        Invoice.user_id == user.id,
        Invoice.status  == "paid",
    ).all()

    for inv in invoices:
        # Only count USD invoices in the chart for clarity
        if inv.payment_date and inv.payment_date.year == current_year and inv.currency == "USD":
            monthly[inv.payment_date.month - 1] += inv.total

    return JSONResponse({"months": monthly, "year": current_year})
