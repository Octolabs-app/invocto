"""
profile.py — User business profile: name, logo, reg number, payment details, plan.
"""
import base64
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import UserProfile
from ..auth import get_current_user

router = APIRouter(prefix="/profile")
templates = Jinja2Templates(directory="app/templates")

INVOICE_TEMPLATES = [
    {"id": "minimal",  "name": "Minimal",  "desc": "Clean white, simple lines"},
    {"id": "bold",     "name": "Bold",     "desc": "Dark navy header, gold accents"},
    {"id": "creative", "name": "Creative", "desc": "Indigo gradient, modern layout"},
]

MAX_LOGO_BYTES = 500_000  # 500 KB


def get_or_create_profile(db: Session, user_id: int) -> UserProfile:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


@router.get("/", response_class=HTMLResponse)
async def profile_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    profile = get_or_create_profile(db, user.id)
    return templates.TemplateResponse("profile.html", {
        "request":            request,
        "user":               user,
        "profile":            profile,
        "invoice_templates":  INVOICE_TEMPLATES,
        "success":            request.query_params.get("success"),
    })


@router.post("/save")
async def save_profile(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    profile = get_or_create_profile(db, user.id)

    profile.business_name        = form.get("business_name", "").strip() or None
    profile.business_reg_number  = form.get("business_reg_number", "").strip() or None
    profile.business_address     = form.get("business_address", "").strip() or None
    profile.business_email       = form.get("business_email", "").strip() or None
    profile.business_phone       = form.get("business_phone", "").strip() or None
    profile.business_website     = form.get("business_website", "").strip() or None
    profile.invoice_template     = form.get("invoice_template", "minimal")
    profile.payment_instructions = form.get("payment_instructions", "").strip() or None
    profile.bank_details         = form.get("bank_details", "").strip() or None
    profile.paypal_email         = form.get("paypal_email", "").strip() or None

    # Logo upload — convert to base64
    logo_file = form.get("logo")
    if logo_file and hasattr(logo_file, "read"):
        data = await logo_file.read()
        if data and len(data) <= MAX_LOGO_BYTES:
            ct = logo_file.content_type or "image/png"
            profile.logo_base64 = f"data:{ct};base64,{base64.b64encode(data).decode()}"
        elif data:
            # Too large — keep old logo, could show error
            pass

    # Remove logo if requested
    if form.get("remove_logo"):
        profile.logo_base64 = None

    db.commit()
    return RedirectResponse("/profile/?success=1", status_code=302)
