"""
billing.py — Stripe subscription billing ($9/month Pro plan).
Set STRIPE_SECRET_KEY and STRIPE_PRICE_ID in your .env.
"""
import os
import stripe
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import UserProfile
from ..auth import get_current_user
from ..routes.profile import get_or_create_profile

router = APIRouter(prefix="/billing")
templates = Jinja2Templates(directory="app/templates")

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID    = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
APP_URL = os.getenv("APP_URL", "https://tax-ready-invoice.onrender.com")


@router.get("/upgrade", response_class=HTMLResponse)
async def upgrade_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    profile = get_or_create_profile(db, user.id)
    return templates.TemplateResponse("billing.html", {
        "request": request,
        "user":    user,
        "profile": profile,
        "stripe_key": os.getenv("STRIPE_PUBLISHABLE_KEY", ""),
    })


@router.post("/create-checkout")
async def create_checkout(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    if not stripe.api_key or not STRIPE_PRICE_ID:
        return RedirectResponse("/profile/?error=stripe_not_configured", status_code=302)

    profile = get_or_create_profile(db, user.id)

    # Reuse existing Stripe customer or create new one
    customer_id = profile.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(email=user.email, metadata={"user_id": user.id})
        customer_id = customer.id
        profile.stripe_customer_id = customer_id
        db.commit()

    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        mode="subscription",
        success_url=f"{APP_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{APP_URL}/billing/upgrade",
        allow_promotion_codes=True,
    )
    return RedirectResponse(session.url, status_code=302)


@router.get("/success")
async def billing_success(request: Request, session_id: str = "", db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    # Activate pro (webhook will also do this, but this gives instant feedback).
    # Verify the checkout session actually belongs to this user's Stripe customer
    # so a paid session_id can't be replayed to upgrade a different account.
    if session_id and stripe.api_key:
        try:
            profile = get_or_create_profile(db, user.id)
            session = stripe.checkout.Session.retrieve(session_id)
            if (session.payment_status == "paid"
                    and session.customer
                    and session.customer == profile.stripe_customer_id):
                profile.plan = "pro"
                profile.stripe_subscription_id = session.subscription
                db.commit()
        except Exception:
            pass

    return RedirectResponse("/profile/?success=upgraded", status_code=302)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Stripe sends events here — keep subscription status in sync."""
    payload   = await request.body()
    sig       = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception:
        return JSONResponse({"error": "Invalid signature"}, status_code=400)

    etype = event["type"]
    data  = event["data"]["object"]

    if etype in ("customer.subscription.created", "customer.subscription.updated"):
        customer_id = data.get("customer")
        status      = data.get("status")
        profile = db.query(UserProfile).filter(UserProfile.stripe_customer_id == customer_id).first()
        if profile:
            profile.plan = "pro" if status == "active" else "free"
            profile.stripe_subscription_id = data.get("id")
            db.commit()

    elif etype == "customer.subscription.deleted":
        customer_id = data.get("customer")
        profile = db.query(UserProfile).filter(UserProfile.stripe_customer_id == customer_id).first()
        if profile:
            profile.plan = "free"
            db.commit()

    return JSONResponse({"received": True})


@router.post("/cancel")
async def cancel_subscription(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    profile = get_or_create_profile(db, user.id)
    if profile.stripe_subscription_id and stripe.api_key:
        try:
            stripe.Subscription.modify(
                profile.stripe_subscription_id,
                cancel_at_period_end=True
            )
        except Exception:
            pass

    return RedirectResponse("/profile/?success=cancelled", status_code=302)
