# Ignite Ads AI — AI CMO Platform

## Overview
Ignite Ads AI is a multi-tenant, multi-workspace AI CMO platform for Google Ads. It scans business assets, audits campaigns, generates ready-to-approve campaigns (including creatives), tracks performance, diagnoses issues, applies safe optimizations, and learns across tenants. V2 adds agency mode, conversion truth layer, change management, connectors, policy compliance, billing, notifications, and AI quality evaluation.

## Architecture
- **Frontend**: Next.js 14+ (App Router), TypeScript, Tailwind CSS, shadcn/ui
- **Backend**: FastAPI (Python 3.11+), SQLAlchemy, Alembic
- **Database**: PostgreSQL 15+
- **Cache/Queue**: Redis + Celery
- **Storage**: S3-compatible object storage

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 20+
- Python 3.11+
- PostgreSQL 15+
- Redis 7+

### Development (Docker)
```bash
docker-compose up --build
```

### Manual Development
```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
alembic upgrade head
python -m app.seed  # seed demo data
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

### Environment Variables
Copy `.env.example` to `.env` and fill in:
- `DATABASE_URL` — Postgres connection string
- `REDIS_URL` — Redis connection string
- `GOOGLE_ADS_DEVELOPER_TOKEN` — Google Ads API developer token
- `GOOGLE_ADS_CLIENT_ID` — OAuth client ID
- `GOOGLE_ADS_CLIENT_SECRET` — OAuth client secret
- `SEOPIX_API_KEY` — seopix.ai API key
- `JWT_SECRET` — JWT signing secret
- `ENCRYPTION_KEY` — Fernet key for token encryption
- `STRIPE_SECRET_KEY` — Stripe billing (V2)
- `STRIPE_WEBHOOK_SECRET` — Stripe webhook verification (V2)
- `SERP_PROVIDER_KEY` — SERP API key (V2, optional)
- `GA4_CLIENT_ID` / `GA4_CLIENT_SECRET` — GA4 OAuth (V2)

## Project Structure
```
ignite-ads-ai/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── tenant/          # Workspace selection & creation
│   │   │   │   ├── select/
│   │   │   │   └── create/
│   │   │   ├── workspace/[tenantId]/  # Tenant-scoped routes (layout guard)
│   │   │   │   ├── dashboard/
│   │   │   │   ├── settings/team/
│   │   │   │   ├── settings/security/
│   │   │   │   └── v2/...
│   │   │   ├── agency/dashboard/ # Multi-tenant rollup view
│   │   │   ├── v2/              # V2 module pages (legacy routes)
│   │   │   └── ...
│   │   ├── components/
│   │   │   ├── layout/sidebar.tsx
│   │   │   └── workspace-switcher.tsx
│   │   └── lib/
│   └── ...
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── workspace.py     # Multi-workspace endpoints
│   │   │   ├── auth.py
│   │   │   └── v2/              # V2 module routes
│   │   ├── services/
│   │   │   ├── audit_service.py # Audit event logging
│   │   │   └── v2/              # V2 services
│   │   ├── models/
│   │   │   ├── user_session.py
│   │   │   ├── invitation.py
│   │   │   ├── audit_event.py
│   │   │   ├── tenant_settings.py
│   │   │   └── v2/              # V2 models
│   │   ├── core/
│   │   │   ├── deps.py          # Hardened tenant isolation deps
│   │   │   ├── permissions.py   # RBAC permission map
│   │   │   └── security.py
│   │   └── jobs/
│   │       ├── tasks.py
│   │       └── v2_tasks.py
│   ├── alembic/
│   ├── tests/
│   │   └── test_tenant_isolation.py
│   └── ...
├── docs/
│   ├── V2_PRD.md
│   └── V2_UPGRADE_PATH.md
└── docker-compose.yml
```

## Monetization Tiers
- **Starter**: 1 Google Ads account, Suggest mode, 1 report/month
- **Pro**: Semi-auto, weekly reports, competitor SERP scans, creative studio
- **Elite**: Full autopilot, experiments, multi-location playbooks, advanced intel

## Multi-Workspace Architecture

### How It Works
- One global user account can access multiple tenant workspaces
- JWT tokens are scoped to `(user_id, tenant_id, role)`
- Every API request is validated: auth → tenant membership (DB lookup) → RBAC permission
- Resources are always filtered by `tenant_id` — cross-tenant access returns 404

### URL Routing
- **Workspace routes**: `/workspace/[tenantId]/dashboard`, `/workspace/[tenantId]/settings/team`
- **Tenant management**: `/tenant/select`, `/tenant/create`
- **Agency overview**: `/agency/dashboard` (multi-tenant rollup)
- **Future-ready**: `tenant.slug` column supports subdomain routing when enabled via feature flag

### RBAC Roles
| Role | Campaigns | Autopilot | Members | Billing | Approve Changes |
|------|-----------|-----------|---------|---------|----------------|
| Owner | Full | Enable | Manage | Full | Yes |
| Admin | Full | Enable | Manage | Read | Yes |
| Analyst | Write | — | — | — | — |
| Viewer | Read | — | — | — | — |

### Security
- `require_tenant` dependency validates membership via DB on every request
- `require_permission("perm")` enforces RBAC from `permissions.py`
- `verify_resource_tenant()` blocks cross-tenant entity access (returns 404)
- Audit events logged for: tenant switches, invites, role changes, permission denials
- Invitation tokens are single-use, time-limited (7 days), and revocable

### Migrations
```bash
# Run all migrations including multi-workspace tables
alembic upgrade head
```

### Tests
```bash
pytest tests/test_tenant_isolation.py -v
```

## License
Proprietary — All rights reserved.
