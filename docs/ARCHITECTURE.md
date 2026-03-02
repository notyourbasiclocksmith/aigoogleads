# Ignite Ads AI — System Architecture

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (Next.js 14)                 │
│  App Router │ shadcn/ui │ Tailwind │ TypeScript          │
│  Auth UI │ Tenant Switching │ RBAC │ Dashboard           │
└──────────────────────┬──────────────────────────────────┘
                       │ REST API (JWT)
┌──────────────────────▼──────────────────────────────────┐
│                   BACKEND (FastAPI)                       │
│                                                          │
│  ┌──────────┐ ┌───────────┐ ┌────────────────┐          │
│  │ API Layer│ │ Services  │ │ Repositories   │          │
│  │ (Routes) │→│ (Logic)   │→│ (Data Access)  │          │
│  └──────────┘ └───────────┘ └───────┬────────┘          │
│                                      │                   │
│  ┌──────────────┐  ┌────────────────┐│                   │
│  │ Integrations │  │ Background Jobs││                   │
│  │ - Google Ads  │  │ - Celery       ││                   │
│  │ - seopix.ai   │  │ - Sync         ││                   │
│  │ - Crawler     │  │ - Diagnostics  ││                   │
│  │ - SERP        │  │ - Reports      ││                   │
│  └──────────────┘  └────────────────┘│                   │
│                                      │                   │
│  ┌─────────────────┐  ┌─────────────▼───────┐           │
│  │ Core            │  │ Models (SQLAlchemy) │           │
│  │ - Auth/JWT      │  └─────────────────────┘           │
│  │ - RBAC          │                                     │
│  │ - Guardrails    │                                     │
│  │ - Encryption    │                                     │
│  └─────────────────┘                                     │
└──────────────────────┬──────────────────────────────────┘
                       │
         ┌─────────────┼──────────────┐
         ▼             ▼              ▼
   ┌──────────┐  ┌──────────┐  ┌──────────┐
   │PostgreSQL│  │  Redis   │  │ S3/Disk  │
   │  (Data)  │  │(Cache/Q) │  │ (Assets) │
   └──────────┘  └──────────┘  └──────────┘
```

## Multi-Tenancy Model
- Every table has `tenant_id` column
- All queries filter by `tenant_id` via repository layer
- Tokens encrypted per-tenant using Fernet
- Session carries `current_tenant_id` from JWT
- Cross-tenant data only in anonymized `learnings` and `playbooks` tables

## Data Flow: Prompt-to-Campaign
```
User Prompt → Intent Parser → Business Profile Lookup
    → Existing Account Check → Playbook Selection
    → Campaign Draft Generator → Preview & Edit
    → Approval → Google Ads API Changeset → Verify → Log
```

## Data Flow: Diagnostic Engine
```
Cron (daily) → Pull Performance Data → Run Diagnostic Rules
    → Generate DiagnosticReport → Create Recommendations
    → Apply Auto-Changes (if autonomy allows) → Log + Alert
```

## Data Flow: Competitive Intelligence
```
Cron (weekly) → SERP Keyword Scan → Extract Ad Copy/Domains
    → Pull Auction Insights from Google Ads API
    → Fetch Competitor Landing Pages → Extract Themes
    → Build Market Messaging Summary → Store
```

## Security Architecture
- JWT tokens with tenant_id + user_id + role
- Refresh tokens stored encrypted in DB
- Google Ads tokens encrypted with Fernet at rest
- Per-tenant isolation enforced at repository layer
- RBAC middleware checks role before route execution
- All mutations logged to change_logs with rollback tokens
- Rate limiting on API + Google Ads API calls

## Background Job Schedule
| Job | Frequency | Description |
|-----|-----------|-------------|
| ads_sync_hourly | Every hour | Spend pacing, budget alerts |
| ads_sync_daily | Daily 2am | Full campaign/performance sync |
| diagnostic_run | Daily 6am | Run all diagnostic checks |
| recommendation_gen | Daily 7am | Generate optimization recommendations |
| serp_scan | Weekly Mon | SERP keyword scans for competitors |
| website_crawl | Weekly Sun | Re-crawl tenant websites |
| report_weekly | Weekly Fri | Generate weekly PDF reports |
| report_monthly | Monthly 1st | Generate monthly growth reviews |
| learning_aggregate | Weekly Sat | Aggregate anonymized cross-tenant patterns |
| autopilot_apply | Daily 8am | Apply auto-approved changes (if enabled) |
