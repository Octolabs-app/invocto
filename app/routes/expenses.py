"""
expenses.py — Expense tracking routes.

Users can add, edit, and delete business expenses with a date, description,
amount, and category (same categories as invoices).
"""
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Expense
from ..auth import get_current_user
from ..utils import safe_float, safe_date

router = APIRouter(prefix="/expenses")
templates = Jinja2Templates(directory="app/templates")

CATEGORIES = ["Design", "Writing", "Video", "Social Media", "Consulting", "Other"]


# ── List ──────────────────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def list_expenses(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    expenses = (
        db.query(Expense)
        .filter(Expense.user_id == user.id)
        .order_by(Expense.date.desc())
        .all()
    )
    total = sum(e.amount for e in expenses)

    return templates.TemplateResponse("expenses.html", {
        "request":     request,
        "user":        user,
        "expenses":    expenses,
        "categories":  CATEGORIES,
        "total":       total,
        "today":       date.today().isoformat(),
        "edit_expense": None,
    })


# ── Add ───────────────────────────────────────────────────────────────────────
@router.post("/add")
async def add_expense(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    exp_date = safe_date(form.get("date"))
    if exp_date is None:
        return RedirectResponse("/expenses/?error=date", status_code=302)
    expense = Expense(
        user_id     = user.id,
        date        = exp_date,
        description = form.get("description", "").strip(),
        amount      = safe_float(form.get("amount"), 0.0),
        category    = form.get("category", "Other"),
    )
    db.add(expense)
    db.commit()
    return RedirectResponse("/expenses/", status_code=302)


# ── Edit — page ───────────────────────────────────────────────────────────────
@router.get("/{expense_id}/edit", response_class=HTMLResponse)
async def edit_expense_page(expense_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == user.id).first()
    if not expense:
        return RedirectResponse("/expenses/", status_code=302)

    expenses = db.query(Expense).filter(Expense.user_id == user.id).order_by(Expense.date.desc()).all()
    total = sum(e.amount for e in expenses)

    return templates.TemplateResponse("expenses.html", {
        "request":      request,
        "user":         user,
        "expenses":     expenses,
        "categories":   CATEGORIES,
        "total":        total,
        "today":        date.today().isoformat(),
        "edit_expense": expense,
    })


# ── Edit — submit ─────────────────────────────────────────────────────────────
@router.post("/{expense_id}/edit")
async def edit_expense(expense_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == user.id).first()
    if expense:
        form = await request.form()
        expense.date        = safe_date(form.get("date"), expense.date)
        expense.description = form.get("description", "").strip()
        expense.amount      = safe_float(form.get("amount"), 0.0)
        expense.category    = form.get("category", "Other")
        db.commit()
    return RedirectResponse("/expenses/", status_code=302)


# ── Delete ────────────────────────────────────────────────────────────────────
@router.post("/{expense_id}/delete")
async def delete_expense(expense_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == user.id).first()
    if expense:
        db.delete(expense)
        db.commit()
    return RedirectResponse("/expenses/", status_code=302)
