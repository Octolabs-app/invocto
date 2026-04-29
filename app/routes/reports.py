"""
reports.py — Tax report generation routes.

Features:
  - Annual summary: income by quarter, total income, total expenses, net income,
    estimated tax (25% of net income)
  - CSV download: one row per paid invoice for the selected year
  - Print view: a clean HTML page the user can Ctrl+P → Save as PDF
"""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Expense, Invoice
from ..auth import get_current_user

router = APIRouter(prefix="/reports")
templates = Jinja2Templates(directory="app/templates")

TAX_RATE = 0.25  # 25% estimated self-employment tax


def _get_quarter(d: date) -> int:
    """Return quarter (1–4) for a given date."""
    return (d.month - 1) // 3 + 1


def _build_report(db: Session, user_id: int, year: int) -> dict:
    """Compute all report figures for the given year."""
    start = date(year, 1, 1)
    end   = date(year, 12, 31)

    # Paid invoices in this year (payment date determines income year)
    paid_invoices = (
        db.query(Invoice)
        .filter(
            Invoice.user_id    == user_id,
            Invoice.status     == "paid",
            Invoice.payment_date >= start,
            Invoice.payment_date <= end,
        )
        .order_by(Invoice.payment_date)
        .all()
    )

    # Income by quarter
    quarterly = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
    for inv in paid_invoices:
        quarterly[_get_quarter(inv.payment_date)] += inv.total

    total_income = sum(quarterly.values())

    # Expenses for the year
    expenses = (
        db.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.date    >= start,
            Expense.date    <= end,
        )
        .all()
    )
    total_expenses = sum(e.amount for e in expenses)

    net_income    = total_income - total_expenses
    estimated_tax = max(0.0, net_income * TAX_RATE)

    return {
        "year":           year,
        "quarterly":      quarterly,
        "total_income":   total_income,
        "total_expenses": total_expenses,
        "net_income":     net_income,
        "estimated_tax":  estimated_tax,
        "paid_invoices":  paid_invoices,
        "expenses":       expenses,
    }


# ── Report page ───────────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def reports_page(request: Request, year: int = None, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    current_year = date.today().year
    year = year or current_year

    report = _build_report(db, user.id, year)

    # Offer last 5 years in the selector
    year_range = list(range(current_year, current_year - 6, -1))

    return templates.TemplateResponse("reports.html", {
        "request":    request,
        "user":       user,
        "year_range": year_range,
        **report,
    })


# ── CSV download ──────────────────────────────────────────────────────────────
@router.get("/download-csv")
async def download_csv(request: Request, year: int = None, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    current_year = date.today().year
    year = year or current_year

    report = _build_report(db, user.id, year)

    buf = io.StringIO()
    writer = csv.writer(buf)

    # Header
    writer.writerow(["Section", "Date", "Client", "Invoice #", "Amount", "Currency", "Category", "Paid?"])

    # Income rows
    for inv in report["paid_invoices"]:
        writer.writerow([
            "Income",
            inv.payment_date.isoformat() if inv.payment_date else "",
            inv.client.name,
            inv.invoice_number,
            f"{inv.total:.2f}",
            inv.currency,
            inv.category,
            "Yes",
        ])

    # Expense rows
    for exp in report["expenses"]:
        writer.writerow([
            "Expense",
            exp.date.isoformat(),
            "",
            "",
            f"{exp.amount:.2f}",
            "USD",
            exp.category,
            "",
        ])

    # Summary rows
    writer.writerow([])
    writer.writerow(["SUMMARY"])
    writer.writerow(["Total Income (USD)", f"{report['total_income']:.2f}"])
    writer.writerow(["Total Expenses (USD)", f"{report['total_expenses']:.2f}"])
    writer.writerow(["Net Income", f"{report['net_income']:.2f}"])
    writer.writerow([f"Estimated Tax ({int(TAX_RATE*100)}%)", f"{report['estimated_tax']:.2f}"])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=tax_report_{year}.csv"},
    )


# ── Print / PDF page ──────────────────────────────────────────────────────────
@router.get("/print", response_class=HTMLResponse)
async def print_report(request: Request, year: int = None, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    current_year = date.today().year
    year = year or current_year

    report = _build_report(db, user.id, year)

    return templates.TemplateResponse("report_print.html", {
        "request":     request,
        "user":        user,
        "today":       date.today(),
        "tax_rate_pct": int(TAX_RATE * 100),
        **report,
    })
