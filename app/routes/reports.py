"""
reports.py — Tax reports: quarterly income (USD only), expenses, net, estimated tax.
Non-USD invoices are listed separately — user converts manually.
"""
import csv
import io
from datetime import date
from collections import defaultdict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Expense, Invoice
from ..auth import get_current_user

router = APIRouter(prefix="/reports")
templates = Jinja2Templates(directory="app/templates")
TAX_RATE = 0.25


def _get_quarter(d: date) -> int:
    return (d.month - 1) // 3 + 1


def _build_report(db: Session, user_id: int, year: int) -> dict:
    start, end = date(year, 1, 1), date(year, 12, 31)

    all_paid = (
        db.query(Invoice)
        .filter(
            Invoice.user_id == user_id,
            Invoice.status == "paid",
            Invoice.is_template == False,
            Invoice.payment_date >= start,
            Invoice.payment_date <= end,
        )
        .order_by(Invoice.payment_date)
        .all()
    )

    # Split USD (counted in report) vs other currencies (shown but not summed)
    usd_invoices   = [i for i in all_paid if i.currency == "USD"]
    other_invoices = [i for i in all_paid if i.currency != "USD"]

    # Quarterly totals — USD only
    quarterly = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
    for inv in usd_invoices:
        quarterly[_get_quarter(inv.payment_date)] += inv.total

    total_income = sum(quarterly.values())

    # Group non-USD invoices by currency for display
    other_by_currency = defaultdict(float)
    for inv in other_invoices:
        other_by_currency[inv.currency] += inv.total

    # Expenses for the year
    expenses = (
        db.query(Expense)
        .filter(Expense.user_id == user_id,
                Expense.date >= start, Expense.date <= end)
        .all()
    )
    total_expenses = sum(e.amount for e in expenses)
    net_income     = total_income - total_expenses
    estimated_tax  = max(0.0, net_income * TAX_RATE)

    return {
        "year":            year,
        "quarterly":       quarterly,
        "total_income":    total_income,
        "total_expenses":  total_expenses,
        "net_income":      net_income,
        "estimated_tax":   estimated_tax,
        "usd_invoices":    usd_invoices,
        "other_invoices":  other_invoices,
        "other_by_currency": dict(other_by_currency),
        "expenses":        expenses,
    }


@router.get("/", response_class=HTMLResponse)
async def reports_page(request: Request, year: int = None, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    current_year = date.today().year
    year = year or current_year
    report = _build_report(db, user.id, year)
    return templates.TemplateResponse("reports.html", {
        "request": request, "user": user,
        "year_range": list(range(current_year, current_year - 6, -1)),
        **report,
    })


@router.get("/download-csv")
async def download_csv(request: Request, year: int = None, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    year = year or date.today().year
    report = _build_report(db, user.id, year)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Section", "Date", "Client", "Invoice #", "Amount", "Currency", "Category", "Paid?"])
    for inv in report["usd_invoices"]:
        w.writerow(["Income (USD)", inv.payment_date.isoformat(), inv.client.name,
                    inv.invoice_number, f"{inv.total:.2f}", "USD", inv.category, "Yes"])
    for inv in report["other_invoices"]:
        w.writerow([f"Income ({inv.currency}) — convert manually",
                    inv.payment_date.isoformat(), inv.client.name,
                    inv.invoice_number, f"{inv.total:.2f}", inv.currency, inv.category, "Yes"])
    for exp in report["expenses"]:
        w.writerow(["Expense", exp.date.isoformat(), "", "", f"{exp.amount:.2f}", "USD", exp.category, ""])
    w.writerow([])
    w.writerow(["SUMMARY (USD only)"])
    w.writerow(["Total Income (USD)",    f"{report['total_income']:.2f}"])
    w.writerow(["Total Expenses (USD)",  f"{report['total_expenses']:.2f}"])
    w.writerow(["Net Income",            f"{report['net_income']:.2f}"])
    w.writerow([f"Est. Tax ({int(TAX_RATE*100)}%)", f"{report['estimated_tax']:.2f}"])

    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=tax_report_{year}.csv"})


@router.get("/print", response_class=HTMLResponse)
async def print_report(request: Request, year: int = None, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    year = year or date.today().year
    report = _build_report(db, user.id, year)
    return templates.TemplateResponse("report_print.html", {
        "request": request, "user": user,
        "today": date.today(), "tax_rate_pct": int(TAX_RATE * 100),
        **report,
    })
