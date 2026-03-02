# Ignite Ads AI — V2 Upgrade Path & Feature Flags

## Overview
V2 modules are additive — they **do not break** any V1 functionality. All V2 tables, API routes, services, and frontend pages are isolated under `v2/` namespaces. V1 tenants continue to operate exactly as before.

## Deployment Steps

### 1. Database Migration
```bash
# Run the V2 migration to add all new tables + columns
alembic upgrade v2_001
```
This adds:
- 3 new columns on `tenants` (feature_flags_json, is_agency, allow_shared_accounts)
- 3 new columns on `integrations_google_ads` (manager_customer_id, is_manager, accessible_accounts_synced_at)
- 5 new columns on `business_profiles` (profit model fields)
- 20+ new tables for all V2 modules

**Zero-downtime**: All new columns have defaults; no existing data is modified.

### 2. Environment Variables
Add these to your `.env` (all optional — V2 features degrade gracefully when keys are empty):

```env
# Stripe Billing
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_STARTER=price_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_ELITE=price_...

# SERP Provider (optional — falls back to mock)
SERP_PROVIDER_KEY=

# Email (SendGrid)
EMAIL_PROVIDER_KEY=
EMAIL_FROM=noreply@yourdomain.com

# Slack
SLACK_DEFAULT_WEBHOOK=

# GA4 OAuth
GA4_CLIENT_ID=
GA4_CLIENT_SECRET=
GA4_REDIRECT_URI=http://localhost:3000/api/auth/ga4/callback
```

### 3. Backend Deployment
No changes needed to existing V1 routes. V2 routes are registered at `/api/v2/*` prefixes:

| Module | Prefix | Tag |
|--------|--------|-----|
| MCC/Agency | `/api/v2/mcc` | V2 MCC/Agency |
| Conversion Truth | `/api/v2/conversions` | V2 Conversion Truth |
| Change Management | `/api/v2/changes` | V2 Change Management |
| Connectors | `/api/v2/connectors` | V2 Connectors |
| Policy Compliance | `/api/v2/policy` | V2 Policy Compliance |
| Billing | `/api/v2/billing` | V2 Billing |
| Notifications | `/api/v2/notifications` | V2 Notifications |
| Evaluation | `/api/v2/evaluation` | V2 Evaluation |

### 4. Celery Beat Schedule
V2 adds 4 periodic tasks (auto-registered):
- `v2-apply-scheduled-changes` — every 5 min
- `v2-rollback-trigger-check` — hourly
- `v2-recommendation-outcomes` — daily at 5:30 UTC
- `v2-evaluation-regression` — weekly (Monday 6:30 UTC)

### 5. Frontend Deployment
V2 pages are at `/v2/*` routes. Sidebar automatically shows V2 navigation section.

---

## Feature Flags

Feature flags are stored per-tenant in `tenants.feature_flags_json` (JSONB column). Default: `{}` (all V2 features hidden).

### Enabling V2 for a Tenant
```sql
UPDATE tenants
SET feature_flags_json = '{
  "mcc_enabled": true,
  "conversion_truth_enabled": true,
  "change_management_enabled": true,
  "connectors_enabled": true,
  "policy_compliance_enabled": true,
  "evaluation_enabled": true,
  "competitor_intel_v2_enabled": true,
  "billing_enabled": true,
  "alerting_v2_enabled": true
}'
WHERE id = '<tenant_id>';
```

### Plan-Based Enablement
| Feature | Starter | Pro | Elite |
|---------|---------|-----|-------|
| MCC/Agency | — | — | Yes |
| Conversion Truth | GA4 only | Full | Full |
| Change Management | Basic | Full | Full |
| Connectors | 1 | 3 | Unlimited |
| Policy Compliance | Basic | Strict | Custom |
| Evaluation | View only | Full | Full |
| Competitor Intel V2 | — | Yes | Yes |
| Billing | Self-serve | Self-serve | Custom |
| Alerting V2 | Email only | Slack+Email | All |

### Checking Flags in Code
```python
# Backend — check feature flag
tenant = await db.get(Tenant, tenant_id)
flags = tenant.feature_flags_json or {}
if not flags.get("mcc_enabled"):
    raise HTTPException(403, "MCC feature not enabled for your plan")
```

```typescript
// Frontend — conditional rendering
{tenant.feature_flags_json?.mcc_enabled && (
  <Link href="/v2/mcc">MCC / Agency</Link>
)}
```

---

## Rollback Plan

If V2 causes issues:

1. **Disable V2 routes**: Comment out V2 router registrations in `main.py`
2. **Disable Celery tasks**: Remove V2 entries from `celery_app.conf.beat_schedule`
3. **Hide frontend**: Remove V2 nav items from sidebar
4. **Database**: V2 tables can remain — they don't affect V1 queries

**No data migration rollback needed** — the `downgrade()` in the Alembic migration drops V2 tables cleanly if required.

---

## Module Dependencies

```
Module 1 (MCC) ←── standalone
Module 2 (Conversions) ←── standalone
Module 3 (Change Mgmt) ←── depends on change_logs (V1)
Module 4 (Connectors) ←── standalone
Module 5 (Policy) ←── standalone
Module 6 (Sanitization) ←── used by creative/prompt services
Module 7 (Evaluation) ←── depends on recommendations (V1)
Module 8 (Competitor V2) ←── depends on serp_scans (V1)
Module 9 (Billing) ←── standalone, enforces limits on other modules
Module 10 (Alerting) ←── depends on connectors (Module 4)
```

## New Dependencies (pip)

```
stripe>=7.0.0      # Module 9 (optional — stub mode without it)
httpx>=0.25.0       # Modules 4, 8, 10 (async HTTP for webhooks/SERP)
cryptography>=41.0  # Module 4 (Fernet encryption for connector credentials)
```

Add to `requirements.txt` and rebuild.
