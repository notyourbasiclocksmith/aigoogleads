# IgniteAds.ai — Engineering Implementation Plan
## Incomplete Systems: Gap Analysis & Build Blueprint

**Date:** 2026-03-13
**Author:** Staff Engineer Audit
**Scope:** 8 incomplete/stubbed systems identified in full software audit

---

## TABLE OF CONTENTS

1. [Executive Summary](#1-executive-summary)
2. [System-by-System Gap Analysis](#2-gap-analysis)
3. [Prioritization & Build Order](#3-build-order)
4. [Implementation Blueprints (Top 5)](#4-blueprints)
5. [Bug Fix: Recommendation.updated_at](#5-bug-fix)
6. [Env Var Requirements](#6-env-vars)
7. [Migration Requirements](#7-migrations)

---

## 1. EXECUTIVE SUMMARY

### Systems Audited

| # | System | Severity | Current State |
|---|--------|----------|---------------|
| 1 | Rollback trigger metrics | **CRITICAL** | Hardcoded `{"conversions": 10, "cpa": 45}` — safety system is non-functional |
| 2 | Recommendation outcome metrics | **CRITICAL** | Hardcoded `{"conversions_delta": 2}` — AI learning loop broken |
| 3 | Recommendation.updated_at bug | **CRITICAL** | Column doesn't exist but `v2_tasks.py:118` queries it — runtime crash |
| 4 | Stripe webhook signature | **HIGH** | No signature verification — anyone can forge billing events |
| 5 | Offline conversion upload | **HIGH** | Marks as "uploaded" without calling Google Ads API |
| 6 | MCC account discovery | **MEDIUM** | Stub logs only — multi-account users can't discover sub-accounts |
| 7 | Learning aggregation | **MEDIUM** | Stub logs only — cross-tenant AI learning disabled |
| 8 | SERP scanning | **LOW** | Requires external API key ($$) — mock provider works for dev |

### Latent Runtime Bug (Immediate Fix)

`v2_tasks.py:118` filters on `Recommendation.updated_at` but `recommendation.py` has NO `updated_at` column. Only `created_at` and `applied_at` exist. This will crash every time `record_recommendation_outcomes` runs (daily at 5:30 AM UTC).

**Fix:** Use `Recommendation.applied_at` instead (semantically correct — we want recs applied N days ago).

---

## 2. SYSTEM-BY-SYSTEM GAP ANALYSIS

### 2.1 Rollback Trigger Metrics (CRITICAL)

**File:** `backend/app/jobs/v2_tasks.py` lines 62-64
**Current code:**
```python
# Stub: in production, fetch actual current vs baseline metrics
current_metrics = {"conversions": 10, "cpa": 45, "spend": 500}
baseline_metrics = {"conversions": 12, "cpa": 40, "spend": 450}
```

**Impact:** The rollback trigger system exists to auto-detect degradation after optimization changes. With hardcoded metrics, it NEVER detects real problems — meaning bad optimizations won't trigger rollbacks.

**What's needed:**
- Query `PerformanceDaily` for the last 3 days (current) vs the 7 days before the most recent change (baseline)
- Scope to campaigns affected by the most recent `ChangeLog` entries for this tenant
- Compute: total conversions, avg CPA (cost/conversions), total spend
- Pass real numbers to `evaluate_rollback_triggers()`

**Dependencies:** `PerformanceDaily` model (exists), `ChangeLog` model (exists), `RollbackPolicy` model (exists)

---

### 2.2 Recommendation Outcome Metrics (CRITICAL)

**File:** `backend/app/jobs/v2_tasks.py` lines 138-143
**Current code:**
```python
# Stub: in production, compute actual metrics delta
actual_metrics = {
    "conversions_delta": 2,
    "cpa_delta": -3,
    "roas_delta": 0.15,
}
```

**Impact:** The evaluation system records whether recommendations helped or hurt. With hardcoded deltas, every recommendation looks equally good — the AI learning loop can't distinguish good recommendations from bad ones.

**What's needed:**
- For each applied recommendation, read its `action_diff_json` to determine which entity was changed (campaign_id, ad_group_id, keyword_id)
- Query `PerformanceDaily` for `window_days` BEFORE and AFTER `applied_at`
- Compute delta: conversions change, CPA change, ROAS change
- Handle edge cases: entity might have been paused (0 data), newly created (no baseline), or budget-changed (normalize by spend)

**Dependencies:** `Recommendation.applied_at` (exists), `PerformanceDaily` (exists), `action_diff_json` contains entity refs

---

### 2.3 Recommendation.updated_at Bug (CRITICAL)

**File:** `backend/app/jobs/v2_tasks.py` line 118
**References:** `Recommendation.updated_at` — column does NOT exist on model

**Current model columns:** `id, tenant_id, category, severity, title, rationale, expected_impact_json, risk_level, action_diff_json, status, created_at, applied_at`

**Fix options:**
- **Option A (minimal):** Change `Recommendation.updated_at` → `Recommendation.applied_at` in the query. Semantically correct — we want recommendations applied N days ago.
- **Option B (schema change):** Add `updated_at` column via Alembic migration. More correct long-term but requires migration.

**Recommendation:** Option A (one-line fix, no migration, semantically right)

---

### 2.4 Stripe Webhook Signature Verification (HIGH)

**File:** `backend/app/api/v2/billing.py` lines 97-111
**Current code:**
```python
body = await request.body()
event = json.loads(body)  # No signature verification!
# Comment says: "In production, verify webhook signature"
```

**Impact:** Anyone who knows the webhook URL can forge subscription events (e.g., fake `checkout.session.completed` to grant free access, or `customer.subscription.deleted` to cancel someone's plan).

**What's needed:**
```python
import stripe
stripe.api_key = settings.STRIPE_SECRET_KEY
event = stripe.Webhook.construct_event(
    body, request.headers.get("stripe-signature"), settings.STRIPE_WEBHOOK_SECRET
)
```

**Dependencies:** `STRIPE_WEBHOOK_SECRET` env var (already set on Render: `whsec_wFlVBGlCymBzthy9hrIBxqLcYD7JAuzA`), `stripe` Python package (already in requirements)

---

### 2.5 Offline Conversion Upload (HIGH)

**File:** `backend/app/jobs/v2_tasks.py` lines 201-224
**Current code:**
```python
# Stub: would call Google Ads ConversionUploadService
for conv in conversions:
    conv.status = "uploaded"  # Lies — nothing was uploaded
```

**Impact:** Users who submit offline conversions (phone calls → closed deals) think they're being uploaded to Google Ads for Smart Bidding optimization. They're not. Google's ML models are optimizing on incomplete data.

**What's needed:**
- Use `google.ads.googleads.client` to call `ConversionUploadService.upload_click_conversions`
- Build `ClickConversion` objects from `OfflineConversion` rows: gclid, conversion_action, conversion_date_time, conversion_value, currency_code
- Handle partial failures (some conversions may have invalid gclids)
- Mark successful ones as `"uploaded"`, failed ones as `"failed"` with error details
- Need a method `upload_offline_conversions()` on `GoogleAdsClient`

**Dependencies:** `OfflineConversion` model (exists with gclid, conversion_name, conversion_time, value, currency, status), `IntegrationGoogleAds` (for auth), `Conversion` model (to resolve conversion_name → conversion_action_resource_name)

---

### 2.6 MCC Account Discovery (MEDIUM)

**File:** `backend/app/jobs/v2_tasks.py` lines 187-190
**Current code:**
```python
logger.info("MCC account sync triggered (stub)", tenant_id=tenant_id)
# In production: call Google Ads API to list accessible customers
```

**Impact:** Multi-account (MCC) users can't discover sub-accounts from the platform. They must manually know customer IDs.

**What's needed:**
- Use `GoogleAdsClient._get_client()` to call `CustomerService.list_accessible_customers()`
- For each accessible customer, query `customer` resource for name/currency/timezone/status
- Upsert into `GoogleAdsAccessibleAccount` table (exists with all needed columns)
- Set `last_seen_at` on found accounts, detect removed accounts

**Dependencies:** `GoogleAdsAccessibleAccount` model (exists), `IntegrationGoogleAds` (for auth), Google Ads API `CustomerService`

---

### 2.7 Learning Aggregation (MEDIUM)

**File:** `backend/app/jobs/tasks.py` line 1476-1478
**Current code:**
```python
def aggregate_learnings():
    logger.info("Learning aggregation task started")
```

**Impact:** The `Learning` model stores cross-tenant patterns (headline themes, match types, offer types, negative keywords by industry). The campaign generator reads these via `_synthesize_strategy_ai()`. With no aggregation, the learnings table stays empty — every campaign generation starts from scratch.

**What's needed:**
- Query `AdPerformanceDaily` + `Ad` (headlines/descriptions) across all tenants in same industry
- Identify high-performing headline patterns (CTR > industry avg, conversions > 0)
- Query `KeywordPerformanceDaily` to find match type patterns (which match types convert best)
- Query `Negative` to build industry-standard negative keyword lists
- Upsert results into `Learning` table with confidence scores

**Model:** `Learning(industry, pattern_type, pattern_json, evidence_json, confidence)`

**Dependencies:** `AdPerformanceDaily`, `Ad`, `KeywordPerformanceDaily`, `Negative`, `BusinessProfile` (for industry), `Learning` model — all exist

---

### 2.8 SERP Scanning (LOW priority — requires paid API)

**File:** `backend/app/jobs/tasks.py` lines 1116-1118
**Current code:**
```python
def run_serp_scan_task(tenant_id, keywords, geo, device):
    logger.info("SERP scan task started", ...)
    # Does nothing
```

**Infrastructure exists:**
- `serp_provider.py` — full abstraction with `BaseSerpProvider`, `MockSerpProvider`, `SerpApiProvider`, `cached_serp_search()`
- `SerpScan` model — stores keyword, geo, device, results_json, ads_json
- `SERP_PROVIDER_KEY` in config
- `SerpApiProvider.search()` — has httpx call structure but points to `serpapi.example.com`

**What's needed:**
- Pick a SERP API provider (ValueSERP at $50/mo for 5000 searches is best value; SerpAPI at $50/mo for 5000; DataForSEO at ~$0.002/search)
- Update `SerpApiProvider.search()` with real API URL and response parsing
- Wire `run_serp_scan_task` to call `cached_serp_search()` for each keyword
- Store results via existing `SerpScan` model
- Feed results to `competitor_intel_service.py` (already consumes SERP data)

**Blocked on:** Commercial decision — which provider + budget allocation. Mock provider works for development.

---

## 3. PRIORITIZATION & BUILD ORDER

### Tier 1: Critical Fixes (< 1 hour total, fixes safety + correctness)

| Order | Item | Effort | Risk if Skipped |
|-------|------|--------|-----------------|
| 1 | `Recommendation.updated_at` bug fix | 1 line | **Runtime crash** daily at 5:30 AM |
| 2 | Stripe webhook signature verification | 5 lines | **Security vulnerability** — forged billing events |
| 3 | Rollback trigger real metrics | ~40 lines | Safety system non-functional |
| 4 | Recommendation outcome real metrics | ~50 lines | AI learning loop broken |

### Tier 2: Feature Completions (2-4 hours total)

| Order | Item | Effort | Impact |
|-------|------|--------|--------|
| 5 | Offline conversion upload | ~60 lines (new client method + task rewrite) | Smart Bidding optimization accuracy |
| 6 | MCC account discovery | ~50 lines (new client method + task rewrite) | Multi-account user experience |

### Tier 3: Enhancement (4+ hours)

| Order | Item | Effort | Impact |
|-------|------|--------|--------|
| 7 | Learning aggregation | ~120 lines | Cross-tenant AI intelligence |
| 8 | SERP scanning | ~30 lines code + API subscription | Competitor intelligence depth |

---

## 4. IMPLEMENTATION BLUEPRINTS

### Blueprint 1: Fix `Recommendation.updated_at` → `applied_at`

**File:** `backend/app/jobs/v2_tasks.py`
**Line 118:** Change `Recommendation.updated_at` → `Recommendation.applied_at`
**Line 119:** Change `Recommendation.updated_at` → `Recommendation.applied_at`

One-line semantic fix. `applied_at` is set when a recommendation is executed, which is exactly what we want — "recommendations applied N days ago."

---

### Blueprint 2: Stripe Webhook Signature Verification

**File:** `backend/app/api/v2/billing.py` lines 97-111

Replace the raw JSON parse with Stripe's signature verification:

```python
@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    import stripe
    stripe.api_key = settings.STRIPE_SECRET_KEY
    body = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    
    if not settings.STRIPE_WEBHOOK_SECRET:
        # Fallback for dev — parse without verification
        import json
        event = json.loads(body)
    else:
        try:
            event = stripe.Webhook.construct_event(body, sig_header, settings.STRIPE_WEBHOOK_SECRET)
        except stripe.error.SignatureVerificationError:
            raise HTTPException(400, "Invalid signature")
        except Exception:
            raise HTTPException(400, "Invalid payload")
    
    event_type = event.get("type", "") if isinstance(event, dict) else event["type"]
    data = event.get("data", {}) if isinstance(event, dict) else event["data"]
    result = await handle_webhook_event(db, event_type, data)
    return result
```

---

### Blueprint 3: Rollback Trigger Real Metrics

**File:** `backend/app/jobs/v2_tasks.py` — replace lines 62-64

**Logic:**
1. Find the most recent `ChangeLog` for this tenant (last applied change)
2. Query `PerformanceDaily` for 3 days after the change (current period)
3. Query `PerformanceDaily` for 7 days before the change (baseline period)
4. Aggregate: sum conversions, sum cost, compute CPA = cost/conversions, sum spend
5. Pass to `evaluate_rollback_triggers()`

```python
async def _get_real_metrics(db, tenant_id, period_days, end_date=None):
    """Get aggregate performance metrics for a tenant over a period."""
    from app.models.performance_daily import PerformanceDaily
    from datetime import datetime, timezone, timedelta
    
    end = end_date or datetime.now(timezone.utc)
    start = end - timedelta(days=period_days)
    
    stmt = select(
        func.sum(PerformanceDaily.conversions).label("conversions"),
        func.sum(PerformanceDaily.cost_micros).label("cost_micros"),
        func.sum(PerformanceDaily.clicks).label("clicks"),
    ).where(
        and_(
            PerformanceDaily.tenant_id == tenant_id,
            PerformanceDaily.entity_type == "campaign",
            PerformanceDaily.date >= start.date(),
            PerformanceDaily.date <= end.date(),
        )
    )
    result = await db.execute(stmt)
    row = result.first()
    
    conversions = float(row.conversions or 0)
    cost = float(row.cost_micros or 0) / 1_000_000
    spend = cost
    cpa = cost / conversions if conversions > 0 else 999
    
    return {"conversions": conversions, "cpa": round(cpa, 2), "spend": round(spend, 2)}
```

Then in the policy loop:
```python
for policy in policies:
    from app.models.change_log import ChangeLog
    # Find most recent change for baseline reference
    change_stmt = select(ChangeLog).where(
        ChangeLog.tenant_id == policy.tenant_id
    ).order_by(ChangeLog.created_at.desc()).limit(1)
    change_result = await db.execute(change_stmt)
    last_change = change_result.scalars().first()
    
    if last_change:
        baseline_end = last_change.created_at
    else:
        baseline_end = datetime.now(timezone.utc) - timedelta(days=3)
    
    current_metrics = await _get_real_metrics(db, policy.tenant_id, period_days=3)
    baseline_metrics = await _get_real_metrics(db, policy.tenant_id, period_days=7, end_date=baseline_end)
    
    eval_result = await evaluate_rollback_triggers(
        db, policy.tenant_id, current_metrics, baseline_metrics
    )
```

---

### Blueprint 4: Recommendation Outcome Real Metrics

**File:** `backend/app/jobs/v2_tasks.py` — replace lines 138-143

**Logic:**
1. Read `rec.action_diff_json` to find the entity (campaign_id, keyword_id, etc.)
2. Read `rec.applied_at` as the change date
3. Query `PerformanceDaily` for `window_days` BEFORE `applied_at` (baseline)
4. Query `PerformanceDaily` for `window_days` AFTER `applied_at` (post-change)
5. Compute deltas: conversions_delta, cpa_delta, roas_delta

```python
async def _compute_recommendation_metrics(db, rec, window_days):
    """Compute actual before/after metrics for a recommendation."""
    from app.models.performance_daily import PerformanceDaily
    from datetime import timedelta
    from sqlalchemy import func
    
    # Extract entity from action_diff
    diff = rec.action_diff_json or {}
    entity_type = diff.get("entity_type", "campaign")
    entity_id = diff.get("entity_id") or diff.get("campaign_id")
    
    if not entity_id:
        return None
    
    applied = rec.applied_at
    if not applied:
        return None
    
    # Before period
    before_start = (applied - timedelta(days=window_days)).date()
    before_end = applied.date()
    
    # After period
    after_start = applied.date()
    after_end = (applied + timedelta(days=window_days)).date()
    
    async def _agg(start_date, end_date):
        stmt = select(
            func.sum(PerformanceDaily.conversions).label("conv"),
            func.sum(PerformanceDaily.cost_micros).label("cost"),
            func.sum(PerformanceDaily.conversion_value_micros).label("value"),
        ).where(
            and_(
                PerformanceDaily.tenant_id == rec.tenant_id,
                PerformanceDaily.entity_id == entity_id,
                PerformanceDaily.date >= start_date,
                PerformanceDaily.date <= end_date,
            )
        )
        r = await db.execute(stmt)
        row = r.first()
        conv = float(row.conv or 0)
        cost = float(row.cost or 0) / 1_000_000
        value = float(row.value or 0) / 1_000_000
        cpa = cost / conv if conv > 0 else 0
        roas = value / cost if cost > 0 else 0
        return {"conversions": conv, "cpa": cpa, "roas": roas, "cost": cost}
    
    before = await _agg(before_start, before_end)
    after = await _agg(after_start, after_end)
    
    return {
        "conversions_delta": round(after["conversions"] - before["conversions"], 1),
        "cpa_delta": round(after["cpa"] - before["cpa"], 2),
        "roas_delta": round(after["roas"] - before["roas"], 3),
        "before": before,
        "after": after,
    }
```

Then in the main loop, replace the hardcoded metrics:
```python
for rec in recs:
    # ... existing dedup check ...
    actual_metrics = await _compute_recommendation_metrics(db, rec, window_days)
    if actual_metrics is None:
        continue
    await record_outcome(db, rec.id, window_days, actual_metrics)
```

---

### Blueprint 5: Offline Conversion Upload

**Step 1:** Add `upload_offline_conversions()` to `GoogleAdsClient`

```python
async def upload_offline_conversions(self, conversions: list) -> dict:
    """Upload click conversions to Google Ads."""
    await self._ensure_token()
    client = self._get_client()
    
    conversion_upload_service = client.get_service("ConversionUploadService")
    conversion_action_service = client.get_service("ConversionActionService")
    
    click_conversions = []
    for conv in conversions:
        click_conversion = client.get_type("ClickConversion")
        click_conversion.gclid = conv["gclid"]
        click_conversion.conversion_action = f"customers/{self.customer_id}/conversionActions/{conv['conversion_action_id']}"
        click_conversion.conversion_date_time = conv["conversion_time"].strftime("%Y-%m-%d %H:%M:%S%z")
        if conv.get("value"):
            click_conversion.conversion_value = float(conv["value"])
            click_conversion.currency_code = conv.get("currency", "USD")
        click_conversions.append(click_conversion)
    
    request = client.get_type("UploadClickConversionsRequest")
    request.customer_id = self.customer_id
    request.conversions = click_conversions
    request.partial_failure = True
    
    response = conversion_upload_service.upload_click_conversions(request=request)
    
    results = {"uploaded": 0, "failed": 0, "errors": []}
    if response.partial_failure_error:
        for error in response.partial_failure_error.details:
            results["errors"].append(str(error))
            results["failed"] += 1
    results["uploaded"] = len(click_conversions) - results["failed"]
    
    return results
```

**Step 2:** Rewrite `_push_offline_conversions_async` in `v2_tasks.py`

```python
async def _push_offline_conversions_async(tenant_id, upload_id):
    from app.core.database import async_session_factory
    from app.models.v2.offline_conversion import OfflineConversion
    from app.models.integration_google_ads import IntegrationGoogleAds
    from app.models.conversion import Conversion
    from app.integrations.google_ads.client import GoogleAdsClient
    
    async with async_session_factory() as db:
        # Get pending conversions
        stmt = select(OfflineConversion).where(and_(
            OfflineConversion.tenant_id == tenant_id,
            OfflineConversion.upload_id == upload_id,
            OfflineConversion.status == "pending",
        ))
        result = await db.execute(stmt)
        conversions = result.scalars().all()
        
        if not conversions:
            return
        
        # Get integration for auth
        customer_id = conversions[0].google_customer_id
        integ = await db.execute(select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.customer_id == customer_id,
            IntegrationGoogleAds.is_active == True,
        ))
        integration = integ.scalar_one_or_none()
        if not integration:
            logger.error("No integration for offline conv upload", customer_id=customer_id)
            return
        
        # Resolve conversion_name → conversion_action_id
        conv_actions = {}
        for conv in conversions:
            if conv.conversion_name not in conv_actions:
                ca = await db.execute(select(Conversion).where(and_(
                    Conversion.tenant_id == tenant_id,
                    Conversion.name == conv.conversion_name,
                )))
                action = ca.scalars().first()
                conv_actions[conv.conversion_name] = action.action_id if action else None
        
        # Build upload payload
        client = GoogleAdsClient(
            customer_id=integration.customer_id,
            refresh_token_encrypted=integration.refresh_token_encrypted,
            login_customer_id=integration.login_customer_id,
        )
        
        upload_data = []
        skipped = []
        for conv in conversions:
            action_id = conv_actions.get(conv.conversion_name)
            if not action_id:
                conv.status = "failed"
                skipped.append(conv.id)
                continue
            upload_data.append({
                "gclid": conv.gclid,
                "conversion_action_id": action_id,
                "conversion_time": conv.conversion_time,
                "value": conv.value,
                "currency": conv.currency,
            })
        
        if upload_data:
            result = await client.upload_offline_conversions(upload_data)
            # Mark successful
            for i, conv in enumerate(c for c in conversions if c.id not in skipped):
                if i < result["uploaded"]:
                    conv.status = "uploaded"
                else:
                    conv.status = "failed"
        
        await db.commit()
        logger.info("Offline conversions uploaded", 
                     uploaded=result.get("uploaded", 0),
                     failed=result.get("failed", 0) + len(skipped))
```

---

### Blueprint 6: MCC Account Discovery

**Step 1:** Add `list_accessible_customers()` to `GoogleAdsClient`

```python
async def list_accessible_customers(self) -> list:
    """List all customer accounts accessible via this manager account."""
    await self._ensure_token()
    client = self._get_client()
    
    customer_service = client.get_service("CustomerService")
    response = customer_service.list_accessible_customers()
    
    accounts = []
    ga_service = client.get_service("GoogleAdsService")
    for resource_name in response.resource_names:
        customer_id = resource_name.split("/")[-1]
        try:
            query = f'''
                SELECT customer.id, customer.descriptive_name,
                       customer.currency_code, customer.time_zone,
                       customer.status
                FROM customer
                WHERE customer.id = {customer_id}
            '''
            rows = ga_service.search(customer_id=customer_id, query=query)
            for row in rows:
                accounts.append({
                    "customer_id": str(row.customer.id),
                    "descriptive_name": row.customer.descriptive_name,
                    "currency": row.customer.currency_code,
                    "timezone": row.customer.time_zone,
                    "status": row.customer.status.name,
                })
        except Exception as e:
            accounts.append({"customer_id": customer_id, "error": str(e)})
    
    return accounts
```

**Step 2:** Rewrite `_sync_mcc_accounts_async` in `v2_tasks.py`

```python
async def _sync_mcc_accounts_async(tenant_id):
    from app.core.database import async_session_factory
    from app.models.integration_google_ads import IntegrationGoogleAds
    from app.models.v2.google_ads_accessible_account import GoogleAdsAccessibleAccount
    from app.integrations.google_ads.client import GoogleAdsClient
    
    async with async_session_factory() as db:
        integ = await db.execute(select(IntegrationGoogleAds).where(and_(
            IntegrationGoogleAds.tenant_id == tenant_id,
            IntegrationGoogleAds.is_active == True,
        )))
        integration = integ.scalars().first()
        if not integration:
            return
        
        client = GoogleAdsClient(
            customer_id=integration.customer_id,
            refresh_token_encrypted=integration.refresh_token_encrypted,
            login_customer_id=integration.login_customer_id,
        )
        
        accounts = await client.list_accessible_customers()
        now = datetime.now(timezone.utc)
        
        for acct in accounts:
            if "error" in acct:
                continue
            existing = await db.execute(select(GoogleAdsAccessibleAccount).where(and_(
                GoogleAdsAccessibleAccount.tenant_id == tenant_id,
                GoogleAdsAccessibleAccount.customer_id == acct["customer_id"],
            )))
            row = existing.scalars().first()
            if row:
                row.descriptive_name = acct.get("descriptive_name")
                row.currency = acct.get("currency")
                row.timezone = acct.get("timezone")
                row.status = acct.get("status")
                row.last_seen_at = now
            else:
                db.add(GoogleAdsAccessibleAccount(
                    tenant_id=tenant_id,
                    manager_customer_id=integration.login_customer_id or integration.customer_id,
                    customer_id=acct["customer_id"],
                    descriptive_name=acct.get("descriptive_name"),
                    currency=acct.get("currency"),
                    timezone=acct.get("timezone"),
                    status=acct.get("status"),
                    last_seen_at=now,
                ))
        
        await db.commit()
        logger.info("MCC accounts synced", tenant_id=tenant_id, count=len(accounts))
```

---

## 5. BUG FIX: Recommendation.updated_at

**File:** `backend/app/jobs/v2_tasks.py`
**Line 118:** `Recommendation.updated_at >= window_start,`
**Line 119:** `Recommendation.updated_at <= window_end,`

**Fix:** Replace both with `Recommendation.applied_at`

This is semantically correct because:
- The task finds recommendations applied N days ago to evaluate their outcomes
- `applied_at` is set when a recommendation is executed (line exists in model)
- `updated_at` does not exist on the model — this is a latent crash

---

## 6. ENV VAR REQUIREMENTS

| Variable | Service | Status | Needed For |
|----------|---------|--------|------------|
| `STRIPE_WEBHOOK_SECRET` | API | ✅ Already set (`whsec_wFlV...`) | Webhook signature verification |
| `OPENAI_API_KEY` | API + Worker | ✅ Already set | AI features |
| `SERP_PROVIDER_KEY` | API | ❌ Not set | SERP scanning (Tier 3) |
| All others | Both | ✅ Verified | Existing features |

No new env vars needed for Tier 1 and Tier 2 fixes.

---

## 7. MIGRATION REQUIREMENTS

**No Alembic migrations needed** for Tier 1 or Tier 2 fixes.

All models and columns already exist:
- `PerformanceDaily` — has `tenant_id, entity_type, entity_id, date, conversions, cost_micros, conversion_value_micros`
- `ChangeLog` — has `tenant_id, created_at`
- `Recommendation` — has `applied_at, action_diff_json, tenant_id`
- `OfflineConversion` — has `gclid, conversion_name, conversion_time, value, currency, status`
- `GoogleAdsAccessibleAccount` — has all needed columns
- `Learning` — has `industry, pattern_type, pattern_json, evidence_json, confidence`

**Optional future migration:** Add `updated_at` to `Recommendation` model for general use (not blocking).

---

## IMPLEMENTATION SEQUENCE

```
Day 1 (1-2 hours):
  ✅ Fix 1: Recommendation.updated_at → applied_at (1 line)
  ✅ Fix 2: Stripe webhook signature verification (5 lines)
  ✅ Fix 3: Rollback trigger real metrics (~40 lines)
  ✅ Fix 4: Recommendation outcome real metrics (~50 lines)
  → Commit + deploy backend

Day 2 (2-3 hours):
  ✅ Fix 5: Offline conversion upload (new client method + task rewrite)
  ✅ Fix 6: MCC account discovery (new client method + task rewrite)
  → Commit + deploy backend + worker

Day 3 (3-4 hours):
  ✅ Fix 7: Learning aggregation implementation
  → Commit + deploy worker

Future (when budget approved):
  ✅ Fix 8: SERP scanning (pick provider, set API key, update URL)
```
