"""
reports.py — Tax reports with country-specific rates, quarterly breakdown, CSV/PDF.
"""
import csv, io
from datetime import date
from collections import defaultdict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Expense, Invoice, UserProfile
from ..auth import get_current_user
from ..tax_data import get_country, country_choices, COUNTRIES

router = APIRouter(prefix="/reports")
templates = Jinja2Templates(directory="app/templates")


def _get_tax_rate(profile: UserProfile | None) -> float:
    if not profile:
        return 25.0
    country = get_country(profile.country or "OTHER")
    # Use custom_tax_rate if manually set AND country is OTHER
    if (profile.country or "OTHER") == "OTHER":
        return profile.custom_tax_rate or 25.0
    return country["rate"]


def _get_quarter(d: date) -> int:
    return (d.month - 1) // 3 + 1


def _build_report(db: Session, user_id: int, year: int, profile) -> dict:
    start, end = date(year, 1, 1), date(year, 12, 31)

    all_paid = (
        db.query(Invoice)
        .filter(Invoice.user_id == user_id, Invoice.status == "paid",
                Invoice.is_template == False,
                Invoice.payment_date >= start, Invoice.payment_date <= end)
        .order_by(Invoice.payment_date).all()
    )

    usd_invoices   = [i for i in all_paid if i.currency == "USD"]
    other_invoices = [i for i in all_paid if i.currency != "USD"]

    quarterly = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
    for inv in usd_invoices:
        quarterly[_get_quarter(inv.payment_date)] += inv.total

    total_income = sum(quarterly.values())

    other_by_currency = defaultdict(float)
    for inv in other_invoices:
        other_by_currency[inv.currency] += inv.total

    expenses = (db.query(Expense)
                .filter(Expense.user_id == user_id,
                        Expense.date >= start, Expense.date <= end).all())
    total_expenses = sum(e.amount for e in expenses)
    net_income     = total_income - total_expenses

    tax_rate      = _get_tax_rate(profile)
    estimated_tax = max(0.0, net_income * tax_rate / 100)

    # Quarter labels from country data
    country_code = (profile.country or "OTHER") if profile else "OTHER"
    country_info = get_country(country_code)

    return {
        "year":             year,
        "quarterly":        quarterly,
        "quarter_labels":   country_info["quarters"],
        "total_income":     total_income,
        "total_expenses":   total_expenses,
        "net_income":       net_income,
        "estimated_tax":    estimated_tax,
        "tax_rate":         tax_rate,
        "usd_invoices":     usd_invoices,
        "other_invoices":   other_invoices,
        "other_by_currency": dict(other_by_currency),
        "expenses":         expenses,
        "country_info":     country_info,
        "country_code":     country_code,
    }


@router.get("/", response_class=HTMLResponse)
async def reports_page(request: Request, year: int = None, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    current_year = date.today().year
    year    = year or current_year
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    report  = _build_report(db, user.id, year, profile)
    # Pass country rates for JS (used to auto-update rate display on country change)
    country_rates = {k: v["rate"] for k, v in COUNTRIES.items()}
    return templates.TemplateResponse("reports.html", {
        "request": request, "user": user,
        "year_range": list(range(current_year, current_year - 6, -1)),
        "profile": profile,
        "country_choices": country_choices(),
        "country_rates": country_rates,
        **report,
    })


@router.post("/set-country")
async def set_country(request: Request, db: Session = Depends(get_db)):
    """Save country + optional custom tax rate from the reports page."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    form    = await request.form()
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if not profile:
        from ..models import UserProfile as UP
        profile = UP(user_id=user.id)
        db.add(profile)

    profile.country         = form.get("country", "OTHER")
    profile.custom_tax_rate = float(form.get("custom_tax_rate") or 25.0)
    db.commit()
    return RedirectResponse(f"/reports/?year={form.get('year', date.today().year)}", status_code=302)


@router.get("/download-csv")
async def download_csv(request: Request, year: int = None, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    year    = year or date.today().year
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    report  = _build_report(db, user.id, year, profile)

    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(["Section", "Date", "Client", "Invoice #", "Amount", "Currency", "Category", "Paid?"])
    for inv in report["usd_invoices"]:
        w.writerow(["Income (USD)", inv.payment_date.isoformat(),
                    inv.client.name, inv.invoice_number,
                    f"{inv.total:.2f}", "USD", inv.category, "Yes"])
    for inv in report["other_invoices"]:
        w.writerow([f"Income ({inv.currency}) — convert manually",
                    inv.payment_date.isoformat(), inv.client.name,
                    inv.invoice_number, f"{inv.total:.2f}", inv.currency, inv.category, "Yes"])
    for exp in report["expenses"]:
        w.writerow(["Expense", exp.date.isoformat(), "", "", f"{exp.amount:.2f}", "USD", exp.category, ""])
    w.writerow([])
    w.writerow(["SUMMARY"])
    w.writerow(["Total Income (USD)",   f"{report['total_income']:.2f}"])
    w.writerow(["Total Expenses",       f"{report['total_expenses']:.2f}"])
    w.writerow(["Net Income",           f"{report['net_income']:.2f}"])
    w.writerow([f"Est. Tax ({report['tax_rate']}% — {report['country_info']['name']})",
                f"{report['estimated_tax']:.2f}"])

    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=tax_report_{year}.csv"})


@router.get("/print", response_class=HTMLResponse)
async def print_report(request: Request, year: int = None, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    year    = year or date.today().year
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    report  = _build_report(db, user.id, year, profile)
    return templates.TemplateResponse("report_print.html", {
        "request": request, "user": user,
        "today": date.today(),
        **report,
    })
