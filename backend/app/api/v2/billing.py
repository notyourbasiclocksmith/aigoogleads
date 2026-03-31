"""Module 9 — Billing, Metering & Limits API Routes (Stripe)"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.v2.billing_service import (
    get_or_create_billing, create_stripe_customer, create_checkout_session,
    create_portal_session, handle_webhook_event,
    get_current_usage, check_limit, PLAN_LIMITS,
)

router = APIRouter()


class CreateCustomerRequest(BaseModel):
    tenant_id: str
    email: str
    name: str


class CheckoutRequest(BaseModel):
    tenant_id: str
    plan: str
    success_url: str = "http://localhost:3000/billing?success=true"
    cancel_url: str = "http://localhost:3000/billing?canceled=true"


class PortalRequest(BaseModel):
    tenant_id: str
    return_url: str = "http://localhost:3000/billing"


@router.get("/status")
async def billing_status(tenant_id: str, db: AsyncSession = Depends(get_db)):
    billing = await get_or_create_billing(db, tenant_id)
    return {
        "tenant_id": tenant_id,
        "plan": billing.plan,
        "status": billing.status,
        "stripe_customer_id": billing.stripe_customer_id or None,
        "stripe_subscription_id": billing.stripe_subscription_id or None,
        "current_period_end": billing.current_period_end.isoformat() if billing.current_period_end else None,
    }


@router.post("/create-customer")
async def create_customer(req: CreateCustomerRequest, db: AsyncSession = Depends(get_db)):
    return await create_stripe_customer(db, req.tenant_id, req.email, req.name)


@router.post("/checkout")
async def checkout(req: CheckoutRequest, db: AsyncSession = Depends(get_db)):
    if req.plan not in PLAN_LIMITS:
        raise HTTPException(400, f"Invalid plan: {req.plan}")
    return await create_checkout_session(db, req.tenant_id, req.plan, req.success_url, req.cancel_url)


@router.post("/portal")
async def portal(req: PortalRequest, db: AsyncSession = Depends(get_db)):
    return await create_portal_session(db, req.tenant_id, req.return_url)


@router.get("/usage")
async def usage(tenant_id: str, db: AsyncSession = Depends(get_db)):
    billing = await get_or_create_billing(db, tenant_id)
    current = await get_current_usage(db, tenant_id)
    limits = PLAN_LIMITS.get(billing.plan or "starter", PLAN_LIMITS["starter"])
    return {
        "plan": billing.plan,
        "usage": current,
        "limits": limits,
        "usage_pct": {
            k: round(current.get(k, 0) / v * 100, 1) if v > 0 else 0
            for k, v in limits.items()
        },
    }


@router.get("/check-limit")
async def check_limit_endpoint(tenant_id: str, metric: str, db: AsyncSession = Depends(get_db)):
    return await check_limit(db, tenant_id, metric)


@router.get("/plans")
async def list_plans():
    return {
        "plans": [
            {"name": "starter", "label": "Starter", "limits": PLAN_LIMITS["starter"], "price": "$97/mo", "price_cents": 9700},
            {"name": "pro", "label": "Pro", "limits": PLAN_LIMITS["pro"], "price": "$197/mo", "price_cents": 19700},
            {"name": "elite", "label": "Elite", "limits": PLAN_LIMITS["elite"], "price": "$397/mo", "price_cents": 39700},
        ]
    }


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Stripe webhook events."""
    import stripe
    from app.core.config import settings

    body = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(500, "Webhook secret not configured")

    try:
        event = stripe.Webhook.construct_event(
            body, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid webhook signature")
    except Exception:
        raise HTTPException(400, "Invalid payload")

    event_type = event["type"]
    data = event["data"]
    result = await handle_webhook_event(db, event_type, data)
    return result
