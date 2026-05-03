"""
items.py — Item/service library. Saved items appear as autocomplete in invoice line items.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Item
from ..auth import get_current_user

router = APIRouter(prefix="/items")
templates = Jinja2Templates(directory="app/templates")

UNITS = ["service", "hour", "day", "word", "page", "unit", "project", "month"]
CATEGORIES = ["Design", "Writing", "Video", "Social Media", "Consulting", "Other"]


@router.get("/", response_class=HTMLResponse)
async def list_items(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    items = db.query(Item).filter(Item.user_id == user.id).order_by(Item.name).all()
    return templates.TemplateResponse("items.html", {
        "request": request, "user": user, "items": items,
        "units": UNITS, "categories": CATEGORIES,
        "edit_item": None,
        "success": request.query_params.get("success"),
    })


@router.get("/api/search")
async def search_items(request: Request, q: str = "", db: Session = Depends(get_db)):
    """Autocomplete endpoint — returns matching items as JSON."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse([], status_code=401)
    items = (db.query(Item)
             .filter(Item.user_id == user.id,
                     Item.name.ilike(f"%{q}%"))
             .order_by(Item.name).limit(10).all())
    return JSONResponse([{
        "id": i.id, "name": i.name,
        "description": i.description or i.name,
        "unit_price": i.unit_price,
        "unit": i.unit, "category": i.category,
    } for i in items])


@router.post("/add")
async def add_item(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    form = await request.form()
    item = Item(
        user_id=user.id,
        name=form.get("name", "").strip(),
        description=form.get("description", "").strip() or None,
        unit_price=float(form.get("unit_price", 0)),
        unit=form.get("unit", "service"),
        category=form.get("category", "Other"),
    )
    db.add(item); db.commit()
    return RedirectResponse("/items/?success=added", status_code=302)


@router.get("/{item_id}/edit", response_class=HTMLResponse)
async def edit_item_page(item_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    item = db.query(Item).filter(Item.id == item_id, Item.user_id == user.id).first()
    if not item:
        return RedirectResponse("/items/", status_code=302)
    items = db.query(Item).filter(Item.user_id == user.id).order_by(Item.name).all()
    return templates.TemplateResponse("items.html", {
        "request": request, "user": user, "items": items,
        "units": UNITS, "categories": CATEGORIES, "edit_item": item,
    })


@router.post("/{item_id}/edit")
async def edit_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    item = db.query(Item).filter(Item.id == item_id, Item.user_id == user.id).first()
    if item:
        form = await request.form()
        item.name        = form.get("name", "").strip()
        item.description = form.get("description", "").strip() or None
        item.unit_price  = float(form.get("unit_price", 0))
        item.unit        = form.get("unit", "service")
        item.category    = form.get("category", "Other")
        db.commit()
    return RedirectResponse("/items/?success=updated", status_code=302)


@router.post("/{item_id}/delete")
async def delete_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    item = db.query(Item).filter(Item.id == item_id, Item.user_id == user.id).first()
    if item:
        db.delete(item); db.commit()
    return RedirectResponse("/items/", status_code=302)
