"""
Module 9 — Billing, Metering & Plan Enforcement (Stripe)
"""
import uuid
from datetime import datetime, timezone, date
from typing import Optional, Dict, Any
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.config import settings
from app.models.v2.billing_customer import BillingCustomer
from app.models.v2.usage_counter import UsageCounter
from app.models.v2.credit_ledger_entry import CreditLedgerEntry

logger = structlog.get_logger()

# ── Plan definitions ──
PLAN_LIMITS: Dict[str, Dict[str, int]] = {
    "starter": {
        "prompts": 50,
        "serp_scans": 20,
        "seopix_credits": 10,
        "accounts_connected": 1,
        "autopilot_actions": 100,
        "ad_spend_limit": 5000,
    },
    "pro": {
        "prompts": 500,
        "serp_scans": 200,
        "seopix_credits": 100,
        "accounts_connected": 5,
        "autopilot_actions": 1000,
        "ad_spend_limit": 25000,
    },
    "elite": {
        "prompts": -1,  # unlimited
        "serp_scans": -1,
        "seopix_credits": 500,
        "accounts_connected": -1,
        "autopilot_actions": -1,
        "ad_spend_limit": -1,
    },
}

PLAN_PRICES: Dict[str, int] = {
    "starter": 9700,   # $97/mo
    "pro": 19700,      # $197/mo
    "elite": 39700,    # $397/mo
}

# Stripe price IDs → plan name mapping (set via env or hardcoded for live)
STRIPE_PRICE_TO_PLAN: Dict[str, str] = {}


def _build_price_to_plan_map() -> Dict[str, str]:
    """Build reverse map from Stripe price IDs to plan names."""
    mapping = {}
    if settings.STRIPE_PRICE_STARTER:
        mapping[settings.STRIPE_PRICE_STARTER] = "starter"
    if settings.STRIPE_PRICE_PRO:
        mapping[settings.STRIPE_PRICE_PRO] = "pro"
    if settings.STRIPE_PRICE_ELITE:
        mapping[settings.STRIPE_PRICE_ELITE] = "elite"
    return mapping


async def get_or_create_billing(db: AsyncSession, tenant_id: str) -> BillingCustomer:
    stmt = select(BillingCustomer).where(BillingCustomer.tenant_id == tenant_id)
    result = await db.execute(stmt)
    billing = result.scalars().first()
    if billing:
        return billing

    # Create stub billing record (Stripe customer creation happens via API)
    billing = BillingCustomer(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        stripe_customer_id="",
        plan="starter",
        status="active",
    )
    db.add(billing)
    return billing


async def create_stripe_customer(db: AsyncSession, tenant_id: str, email: str, name: str) -> Dict[str, Any]:
    """Create Stripe customer and store reference. Requires stripe library."""
    try:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        customer = stripe.Customer.create(email=email, name=name, metadata={"tenant_id": tenant_id})
        billing = await get_or_create_billing(db, tenant_id)
        billing.stripe_customer_id = customer.id
        return {"stripe_customer_id": customer.id}
    except ImportError:
        logger.warning("Stripe library not installed, using stub")
        billing = await get_or_create_billing(db, tenant_id)
        billing.stripe_customer_id = f"cus_stub_{tenant_id[:8]}"
        return {"stripe_customer_id": billing.stripe_customer_id, "stub": True}
    except Exception as e:
        logger.error("Stripe customer creation failed", error=str(e))
        raise


async def create_checkout_session(db: AsyncSession, tenant_id: str, plan: str, success_url: str, cancel_url: str) -> Dict[str, Any]:
    """Create Stripe checkout session for plan subscription."""
    billing = await get_or_create_billing(db, tenant_id)
    try:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        price_map = {
            "starter": settings.STRIPE_PRICE_STARTER if hasattr(settings, "STRIPE_PRICE_STARTER") else "",
            "pro": settings.STRIPE_PRICE_PRO if hasattr(settings, "STRIPE_PRICE_PRO") else "",
            "elite": settings.STRIPE_PRICE_ELITE if hasattr(settings, "STRIPE_PRICE_ELITE") else "",
        }
        session = stripe.checkout.Session.create(
            customer=billing.stripe_customer_id,
            mode="subscription",
            line_items=[{"price": price_map.get(plan, ""), "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"tenant_id": tenant_id, "plan": plan},
        )
        return {"checkout_url": session.url, "session_id": session.id}
    except ImportError:
        return {"checkout_url": f"/billing/stub-checkout?plan={plan}", "stub": True}
    except Exception as e:
        logger.error("Stripe checkout creation failed", error=str(e))
        raise


async def create_portal_session(db: AsyncSession, tenant_id: str, return_url: str) -> Dict[str, Any]:
    """Create Stripe billing portal session."""
    billing = await get_or_create_billing(db, tenant_id)
    try:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        session = stripe.billing_portal.Session.create(
            customer=billing.stripe_customer_id,
            return_url=return_url,
        )
        return {"portal_url": session.url}
    except ImportError:
        return {"portal_url": "/billing/stub-portal", "stub": True}
    except Exception as e:
        logger.error("Stripe portal creation failed", error=str(e))
        raise


async def handle_webhook_event(db: AsyncSession, event_type: str, data: dict) -> Dict[str, Any]:
    """Handle Stripe webhook events for subscription changes."""
    price_to_plan = _build_price_to_plan_map()

    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        sub = data.get("object", {})
        customer_id = sub.get("customer", "")
        stmt = select(BillingCustomer).where(BillingCustomer.stripe_customer_id == customer_id)
        result = await db.execute(stmt)
        billing = result.scalars().first()
        if billing:
            billing.status = sub.get("status", billing.status)
            billing.stripe_subscription_id = sub.get("id", billing.stripe_subscription_id)
            # Resolve plan from price ID
            items_data = sub.get("items", {}).get("data", [])
            if items_data:
                price_id = items_data[0].get("price", {}).get("id", "")
                resolved_plan = price_to_plan.get(price_id)
                if resolved_plan:
                    billing.plan = resolved_plan
                    logger.info("Plan resolved from Stripe price", plan=resolved_plan, price_id=price_id)
            if sub.get("current_period_end"):
                billing.current_period_end = datetime.fromtimestamp(sub["current_period_end"], tz=timezone.utc)
            return {"updated": True, "plan": billing.plan}

    elif event_type == "checkout.session.completed":
        session = data.get("object", {})
        customer_id = session.get("customer", "")
        metadata = session.get("metadata", {})
        plan = metadata.get("plan", "")
        stmt = select(BillingCustomer).where(BillingCustomer.stripe_customer_id == customer_id)
        result = await db.execute(stmt)
        billing = result.scalars().first()
        if billing and plan:
            billing.plan = plan
            billing.status = "active"
            sub_id = session.get("subscription", "")
            if sub_id:
                billing.stripe_subscription_id = sub_id
            logger.info("Checkout completed, plan set", plan=plan, customer_id=customer_id)
            return {"checkout_completed": True, "plan": plan}

    elif event_type == "customer.subscription.deleted":
        sub = data.get("object", {})
        customer_id = sub.get("customer", "")
        stmt = select(BillingCustomer).where(BillingCustomer.stripe_customer_id == customer_id)
        result = await db.execute(stmt)
        billing = result.scalars().first()
        if billing:
            billing.status = "canceled"
            return {"canceled": True}

    return {"handled": False}


# ── Usage metering ──
async def get_current_usage(db: AsyncSession, tenant_id: str) -> Dict[str, int]:
    today = date.today()
    period_start = today.replace(day=1)
    if today.month == 12:
        period_end = today.replace(year=today.year + 1, month=1, day=1)
    else:
        period_end = today.replace(month=today.month + 1, day=1)

    stmt = select(UsageCounter).where(
        and_(
            UsageCounter.tenant_id == tenant_id,
            UsageCounter.period_start == period_start,
        )
    )
    result = await db.execute(stmt)
    counter = result.scalars().first()
    if counter:
        return counter.counters_json
    return {"prompts": 0, "serp_scans": 0, "seopix_credits": 0, "accounts_connected": 0, "autopilot_actions": 0}


async def increment_usage(db: AsyncSession, tenant_id: str, metric: str, amount: int = 1) -> Dict[str, Any]:
    today = date.today()
    period_start = today.replace(day=1)
    if today.month == 12:
        period_end = today.replace(year=today.year + 1, month=1, day=1)
    else:
        period_end = today.replace(month=today.month + 1, day=1)

    stmt = select(UsageCounter).where(
        and_(
            UsageCounter.tenant_id == tenant_id,
            UsageCounter.period_start == period_start,
        )
    )
    result = await db.execute(stmt)
    counter = result.scalars().first()
    if not counter:
        counter = UsageCounter(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            counters_json={"prompts": 0, "serp_scans": 0, "seopix_credits": 0, "accounts_connected": 0, "autopilot_actions": 0},
        )
        db.add(counter)

    counters = counter.counters_json or {}
    counters[metric] = counters.get(metric, 0) + amount
    counter.counters_json = counters
    return counters


async def check_limit(db: AsyncSession, tenant_id: str, metric: str) -> Dict[str, Any]:
    """Check if tenant is within plan limits for a specific metric."""
    billing = await get_or_create_billing(db, tenant_id)
    plan = billing.plan or "starter"
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["starter"])
    limit_val = limits.get(metric, 0)

    if limit_val == -1:
        return {"allowed": True, "limit": -1, "used": 0}

    usage = await get_current_usage(db, tenant_id)
    used = usage.get(metric, 0)

    return {
        "allowed": used < limit_val,
        "limit": limit_val,
        "used": used,
        "plan": plan,
        "remaining": max(0, limit_val - used),
    }


async def add_credit(db: AsyncSession, tenant_id: str, credit_type: str, amount: int, reason: str):
    entry = CreditLedgerEntry(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        type=credit_type,
        amount=amount,
        reason=reason,
    )
    db.add(entry)
