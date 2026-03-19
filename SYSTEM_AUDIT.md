# IgniteAds.ai — Full System Audit

**Date:** March 19, 2026  
**Scope:** Frontend, Backend, Integrations, User Flows, Wiring Status

---

## 1. Architecture Overview

| Layer | Tech | Location |
|---|---|---|
| **Frontend** | Next.js 14, React, TailwindCSS, Radix UI, Recharts, Lucide icons | `frontend/` |
| **Backend** | FastAPI, SQLAlchemy (async), Pydantic, structlog | `backend/` |
| **Database** | PostgreSQL 15 (async via asyncpg) | Docker / Render |
| **Cache/Queue** | Redis 7 (Celery broker + result backend) | Docker / Render |
| **Background Jobs** | Celery (worker + beat) | `backend/app/jobs/` |
| **Auth** | JWT (access + refresh), Fernet encryption for tokens | `backend/app/core/security.py` |
| **Multi-tenancy** | Every request scoped to `(user_id, tenant_id, role)` via DB-verified middleware | `backend/app/core/deps.py` |
| **API Proxy** | Next.js rewrites `/api/*` → `http://localhost:8000/api/*` | `frontend/next.config.js` |

### Infrastructure (Docker Compose)
- `postgres` — PostgreSQL 15 Alpine
- `redis` — Redis 7 Alpine
- `backend` — FastAPI (runs migrations + seed on startup)
- `celery-worker` — 4 concurrent workers
- `celery-beat` — periodic task scheduler
- `frontend` — Next.js standalone

---

## 2. Database Models (78 tables)

### Core Models (v1)
| Model | Purpose |
|---|---|
| `User` | User accounts (email, hashed password) |
| `Tenant` | Workspace/business (name, industry, autonomy_mode) |
| `TenantUser` | Many-to-many user↔tenant with role (owner/admin/analyst/viewer) |
| `TenantSettings` | Per-tenant config |
| `BusinessProfile` | Business details (phone, website, services, locations, brand voice, etc.) |
| `SocialProfile` | Social media links per tenant |
| `CrawledPage` | Website pages crawled during onboarding scan |
| `IntegrationGoogleAds` | Google Ads OAuth connection (encrypted refresh token, customer ID) |
| `AdsAccountCache` | Cached account-level data |
| `Campaign` | Synced Google Ads campaigns |
| `AdGroup` | Synced ad groups |
| `Ad` | Synced individual ads |
| `Keyword` | Synced keywords |
| `Negative` | Negative keywords |
| `Asset` | Ad assets (images, etc.) |
| `Conversion` | Conversion actions |
| `PerformanceDaily` | Daily performance metrics (campaign level) |
| `AdPerformanceDaily` | Daily ad-level metrics |
| `AdGroupPerformanceDaily` | Daily ad group metrics |
| `KeywordPerformanceDaily` | Daily keyword metrics |
| `SearchTermPerformance` | Search term report data |
| `LandingPagePerformance` | Landing page metrics |
| `AuctionInsight` | Auction insight data |
| `SerpScan` | SERP scanning results |
| `CompetitorProfile` | Competitor intelligence |
| `Recommendation` | AI-generated recommendations |
| `GoogleRecommendation` | Native Google Ads recommendations |
| `ChangeLog` | All changes made (audit trail) |
| `Approval` | Approval workflow for changes |
| `Experiment` | A/B test experiments |
| `Playbook` | Optimization playbooks |
| `Learning` | AI learnings from past actions |
| `Alert` | System alerts and notifications |
| `UserSession` | Session tracking |
| `Invitation` | Tenant invitations |
| `AuditEvent` | Audit log events |
| `LandingPage` / `LandingPageVariant` / `LandingPageEvent` | AI-generated landing pages |
| `ExpansionRecommendation` | Service expansion suggestions |
| `AIGenerationLog` | Log of AI content generation |
| `LSALead` / `LSAConversation` | Local Services Ads leads |
| `GBPConnection` / `GBPLocation` / `GBPPost` / `GBPReview` | Google Business Profile |

### V2 Models (34 additional tables)
| Model | Purpose |
|---|---|
| `GoogleAdsAccessibleAccount` / `TenantGoogleAdsBinding` | MCC account management |
| `IntegrationGA4` / `TrackingHealthReport` | GA4 integration |
| `OfflineConversion` / `OfflineConversionUpload` | Offline conversion imports |
| `ChangeSet` / `ChangeSetItem` / `FreezeWindow` / `RollbackPolicy` | Change management |
| `Connector` / `ConnectorEvent` | Third-party connectors |
| `PolicyRule` / `TenantPolicyOverride` / `PolicyScanResult` | Policy compliance |
| `BillingCustomer` / `UsageCounter` / `CreditLedgerEntry` | Billing & usage |
| `NotificationChannel` / `NotificationRule` / `NotificationSent` | Notifications |
| `OperatorScan` / `OperatorRecommendation` / `OperatorChangeSet` / `OperatorMutation` | AI Operator |
| `OptimizationCycle` / `OptimizationLearning` | Optimization tracking |
| `CreativeAudit` | Creative quality audits |
| `ExtractedSnippet` | Website content extraction |
| `RecommendationOutcome` / `PlaybookStat` | Outcome tracking |
| `CompetitorCreative` / `CompetitorAlert` | Competitor monitoring |

---

## 3. Backend API Routes (31 routers)

### V1 Routes
| Prefix | Router File | Endpoints | Status |
|---|---|---|---|
| `/api/auth` | `auth.py` | register, login, refresh, me, tenants, select-tenant | ✅ **Wired & Functional** |
| `/api/tenants` | `tenants.py` | CRUD tenants | ✅ **Wired** |
| `/api/onboarding` | `onboarding.py` | step1-5, status, data | ✅ **Wired & Functional** |
| `/api/dashboard` | `dashboard.py` | kpis, alerts, campaigns, daily-trend, top-keywords, search-terms-preview, recommendations | ✅ **Wired** (needs synced data) |
| `/api/ads/accounts` | `ads_accounts.py` | OAuth callback, list, connect, disconnect, reconnect, accessible-customers, select-customer, sync | ✅ **Wired & Functional** |
| `/api/ads/audit` | `ads_audit.py` | Campaign audit, account audit | ✅ **Wired** |
| `/api/ads/prompt` | `ads_prompt.py` | AI campaign builder (prompt→campaign) | ✅ **Wired** (needs OpenAI key) |
| `/api/ads` | `ads_data.py` | Keywords, search-terms, ads, ad-groups, landing-pages, recommendations, keyword-research, negatives | ✅ **Wired** (largest data API — 48KB) |
| `/api/campaigns` | `campaigns.py` | List, detail, pause/enable, budget update | ✅ **Wired** |
| `/api/creative` | `creative.py` | AI ad copy generation, headline/description writing | ✅ **Wired** (needs OpenAI) |
| `/api/intel/competitors` | `competitors.py` | Competitor analysis | ✅ **Wired** |
| `/api/optimizations` | `optimizations.py` | Optimization suggestions | ✅ **Wired** |
| `/api/experiments` | `experiments.py` | A/B test management | ✅ **Wired** |
| `/api/reports` | `reports.py` | Report generation | ⚠️ **Minimal** (2.6KB — likely stub) |
| `/api/settings` | `admin_settings.py` | Profile, guardrails, notifications, team management | ✅ **Wired** (18KB — full implementation) |
| `/api/lsa` | `lsa.py` | Local Services Ads leads, conversations, analytics | ✅ **Wired** |
| `/api/bridge` | `bridge.py` | CallFlux ↔ IgniteAds integration (call tracking) | ✅ **Wired** |
| `/api/gbp` | `gbp.py` | Google Business Profile (OAuth, posts, reviews, images) | ✅ **Wired** |
| `/api` (workspace) | `workspace.py` | Workspace management, invitations, audit log | ✅ **Wired** |

### V2 Routes
| Prefix | Router File | Endpoints | Status |
|---|---|---|---|
| `/api/v2/mcc` | `mcc.py` | MCC/Agency multi-account management | ✅ **Wired** |
| `/api/v2/conversions` | `conversions.py` | Conversion tracking, offline uploads, truth table | ✅ **Wired** |
| `/api/v2/changes` | `change_mgmt.py` | Change sets, freeze windows, rollback | ✅ **Wired** |
| `/api/v2/connectors` | `connectors.py` | Third-party connector framework | ✅ **Wired** |
| `/api/v2/policy` | `policy.py` | Policy compliance scanning | ✅ **Wired** |
| `/api/v2/billing` | `billing.py` | Stripe billing, checkout, usage | ⚠️ **Wired but requires Stripe keys** |
| `/api/v2/notifications` | `notifications.py` | Notification channels, rules, test email | ✅ **Wired** |
| `/api/v2/evaluation` | `evaluation.py` | AI quality evaluation | ⚠️ **Minimal** (1.6KB) |
| `/api/v2/operator` | `operator.py` | AI Operator — full account scan, recommendations, execution | ✅ **Wired** (28KB — heavy implementation) |
| `/api/v2/growth` | `growth.py` | Search mining, service expansion, bulk campaign gen | ✅ **Wired** |
| `/api/v2/strategist` | `strategist.py` | AI Strategist chat, auto-build with streaming | ✅ **Wired** (41KB — largest API file) |

---

## 4. Backend Services (Business Logic)

| Service | File Size | Purpose | Status |
|---|---|---|---|
| `campaign_generator.py` | **159KB** | AI campaign generation (the core engine) | ✅ Heavy implementation |
| `strategist_orchestrator.py` | **90KB** | AI strategist chat orchestration | ✅ Heavy implementation |
| `campaign_compliance.py` | **46KB** | Campaign policy compliance checking | ✅ Full |
| `report_service.py` | **29KB** | PDF/email report generation | ✅ Full |
| `landing_page_generator.py` | **23KB** | AI landing page generation | ✅ Full |
| `diagnostic_engine.py` | **20KB** | Account diagnostic analysis | ✅ Full |
| `creative_service.py` | **17KB** | AI ad copy/creative generation | ✅ Full |
| `social_analyzer.py` | **17KB** | Social media analysis | ✅ Full |
| `gbp_service.py` | **15KB** | GBP management | ✅ Full |
| `search_term_miner.py` | **14KB** | Search term analysis/mining | ✅ Full |
| `gbp_review_service.py` | **11KB** | Review management & AI reply drafts | ✅ Full |
| `gbp_post_service.py` | **11KB** | GBP post creation & scheduling | ✅ Full |
| `business_scanner.py` | **9KB** | Website scanning during onboarding | ✅ Full |
| `competitor_intel_service.py` | **9KB** | Competitor intelligence | ✅ Full |
| `guardrails.py` | **8KB** | AI guardrails enforcement | ✅ Full |
| `campaign_auditor.py` | **8KB** | Campaign audit engine | ✅ Full |
| `optimization_engine.py` | **7KB** | Optimization suggestions | ✅ Full |
| `expansion_scorer.py` | **7KB** | Service expansion scoring | ✅ Full |
| `service_expander.py` | **7KB** | Service expansion engine | ✅ Full |
| `email_service.py` | **8KB** | Email notifications | ✅ Full |
| `landing_page_auditor.py` | **6KB** | Landing page quality audit | ✅ Full |
| `gbp_oauth_service.py` | **5KB** | GBP OAuth flow | ✅ Full |
| `audit_service.py` | **1KB** | Audit logging | ⚠️ Minimal |

### Operator Services (AI Brain)
| Service | Size | Purpose |
|---|---|---|
| `recommendation_engine.py` | **61KB** | AI recommendation generation |
| `execution_engine.py` | **27KB** | Execute approved changes in Google Ads |
| `account_scan_service.py` | **25KB** | Deep account scanning |
| `autonomous_optimizer.py` | **18KB** | Autonomous optimization cycles |
| `creative_intelligence_service.py` | **15KB** | Creative analysis & suggestions |
| `operator_orchestrator.py` | **14KB** | Orchestrate scan → recommend → execute |
| `feedback_loop.py` | **12KB** | Learn from past actions |
| `schemas.py` | **11KB** | Data schemas for operator |
| `projection_engine.py` | **7KB** | Performance projections |
| `narrative_generator.py` | **6KB** | Human-readable explanations |

### Background Jobs (Celery)
| Task File | Size | Key Tasks |
|---|---|---|
| `tasks.py` | **98KB** | `sync_ads_account_task`, `scan_business_task`, daily sync, keyword sync, search term sync, landing page sync, competitor monitoring, report generation |
| `operator_tasks.py` | **9KB** | `run_operator_scan`, `execute_approved_changes`, `run_autonomous_cycle` |
| `v2_tasks.py` | **10KB** | Conversion uploads, policy scans, connector syncs |

---

## 5. Frontend Pages (45 pages)

### Auth & Onboarding Flow
| Page | Route | Backend API | Status |
|---|---|---|---|
| Root | `/` | — | ✅ Redirects to `/dashboard` or `/marketing` |
| Marketing/Landing | `/marketing` | — | ✅ Static landing page |
| Pricing | `/pricing` | — | ✅ Plan selection → register |
| Register | `/register` | `/api/auth/register`, `/api/auth/login`, `/api/auth/select-tenant`, `/api/v2/billing/*` | ✅ **Wired** (Stripe optional) |
| Login | `/login` | `/api/auth/login`, `/api/auth/tenants`, `/api/auth/select-tenant` | ✅ **Wired** |
| Onboarding (5 steps) | `/onboarding` | `/api/onboarding/step1-5`, `/api/onboarding/status`, `/api/onboarding/data`, `/api/onboarding/google-ads-url`, `/api/ads/accounts/*` | ✅ **Wired** |
| Tenant Select | `/tenant/select` | `/api/auth/tenants`, `/api/auth/select-tenant` | ✅ **Wired** |
| Tenant Create | `/tenant/create` | `/api/tenants` | ✅ **Wired** |

### Core Dashboard
| Page | Route | Backend API | Status |
|---|---|---|---|
| Dashboard | `/dashboard` | `/api/dashboard/kpis`, `/api/dashboard/alerts`, `/api/dashboard/campaigns`, `/api/dashboard/daily-trend` | ✅ **Wired** — shows KPIs, charts, alerts, campaigns |
| Get Customers (wizard) | `/get-customers` | `/api/v2/strategist/auto-build/stream` (SSE streaming) | ✅ **Wired** — 5-step wizard → AI builds campaign |

### AI Intelligence
| Page | Route | Backend API | Status |
|---|---|---|---|
| AI Operator (Strategist Chat) | `/strategist` | `/api/v2/strategist/chat` (streaming), `/api/v2/strategist/auto-build/stream` | ✅ **Wired** — full chat UI with rich responses |
| Fix My Ads (Operator) | `/operator` | `/api/v2/operator/scan`, `/api/v2/operator/scans/{id}`, `/api/v2/operator/scans/{id}/recommendations`, `/api/v2/operator/apply` | ✅ **Wired** — scan account, review & approve recommendations |
| Operator Live | `/operator/live` | `/api/v2/operator/*` | ✅ **Wired** — real-time operator view |

### Manage Ads
| Page | Route | Backend API | Status |
|---|---|---|---|
| Campaigns | `/ads/campaigns` | `/api/campaigns`, `/api/campaigns/{id}/pause`, `/api/campaigns/{id}/enable` | ✅ **Wired** — list, pause/enable, sort, CSV export |
| Campaign Detail | `/ads/campaigns/[id]` | `/api/campaigns/{id}` | ✅ **Wired** — drill-down with ad groups, keywords, ads |
| Ads | `/ads/ads` | `/api/ads/ads`, `/api/ads/audit/ad/{id}` | ✅ **Wired** — ad performance, AI audit per ad |
| Keywords | `/ads/keywords` | `/api/ads/keywords`, `/api/ads/keywords/{id}/pause`, `/api/ads/keywords/{id}/enable` | ✅ **Wired** — keyword management with actions |
| Search Terms | `/ads/search-terms` | `/api/ads/search-terms`, `/api/ads/search-terms/waste`, `/api/ads/negatives` | ✅ **Wired** — waste detection, add negatives |
| Landing Pages | `/ads/landing-pages` | `/api/ads/landing-pages`, `/api/ads/landing-pages/{url}/audit` | ✅ **Wired** — PageSpeed, AI audit |

### Advanced (admin/owner only)
| Page | Route | Backend API | Status |
|---|---|---|---|
| Campaign Builder | `/ads/prompt` | `/api/ads/prompt/build` (streaming) | ✅ **Wired** — AI prompt → full campaign generation |
| Landing Page Studio | `/ads/landing-page-studio` | `/api/ads/landing-pages/generate`, `/api/ads/landing-pages/variants` | ✅ **Wired** — AI landing page builder |
| Search Mining | `/growth/search-mining` | `/api/v2/growth/search-mining/*` | ✅ **Wired** |
| Expand Services | `/growth/expand` | `/api/v2/growth/expand/*` | ✅ **Wired** |
| Bulk Campaigns | `/growth/bulk-generate` | `/api/v2/growth/bulk-generate` | ✅ **Wired** |
| Recommendations | `/ads/recommendations` | `/api/ads/recommendations` | ✅ **Wired** |
| Audit | `/audit` | `/api/ads/audit/account` | ✅ **Wired** |
| Competitors | `/intel/competitors` | `/api/intel/competitors/*` | ✅ **Wired** |
| Keyword Research | `/ads/keyword-research` | `/api/ads/keyword-research` | ✅ **Wired** |
| Reports | `/reports` | `/api/reports/*` | ⚠️ **Wired but backend is minimal** |
| Experiments | `/experiments` | `/api/experiments/*` | ✅ **Wired** |

### Leads & Local
| Page | Route | Backend API | Status |
|---|---|---|---|
| Calls & Leads | `/calls` | `/api/bridge/calls`, `/api/bridge/stats` | ✅ **Wired** — CallFlux integration |
| GBP Manager | `/gbp` | `/api/gbp/posts`, `/api/gbp/reviews`, `/api/gbp/images`, `/api/gbp/posts/generate` | ✅ **Wired** — posts, reviews, AI replies |
| LSA Leads | `/lsa` | `/api/lsa/leads`, `/api/lsa/conversations`, `/api/lsa/analytics` | ✅ **Wired** |

### V2 Pages
| Page | Route | Backend API | Status |
|---|---|---|---|
| Billing | `/v2/billing` | `/api/v2/billing/*` | ⚠️ **Wired but needs Stripe keys** |
| MCC / Agency | `/v2/mcc` | `/api/v2/mcc/*` | ✅ **Wired** |
| Conversions | `/v2/conversions` | `/api/v2/conversions/*` | ✅ **Wired** |
| Change History | `/v2/changes` | `/api/v2/changes/*` | ✅ **Wired** |
| Connectors | `/v2/connectors` | `/api/v2/connectors/*` | ✅ **Wired** |
| Policy | `/v2/policy` | `/api/v2/policy/*` | ✅ **Wired** |
| AI Quality | `/v2/evaluation` | `/api/v2/evaluation/*` | ⚠️ **Wired but backend is minimal** |
| Notifications | `/v2/notifications` | `/api/v2/notifications/*` | ✅ **Wired** |

### Settings
| Page | Route | Backend API | Status |
|---|---|---|---|
| Settings | `/settings` | `/api/settings/profile`, `/api/settings/guardrails`, `/api/ads/accounts`, `/api/gbp/*` | ✅ **Wired** — profile, guardrails, Google Ads connect/disconnect/reconnect, GBP connect |

---

## 6. User Flow — How The Software Works

### Flow 1: Registration → Onboarding
```
/marketing (landing page)
  → /pricing (select plan: starter/growth/pro)
    → /register?plan=growth (register form)
      → POST /api/auth/register (create user)
      → POST /api/auth/login (get JWT)
      → POST /api/auth/select-tenant (scope JWT to tenant)
      → [Optional] POST /api/v2/billing/checkout (Stripe — skipped if not configured)
      → Redirect to /onboarding

/onboarding (5-step wizard)
  Step 1: Business Info → POST /api/onboarding/step1
    - Business name, industry, phone, service area
    - Creates Tenant + BusinessProfile
    - Returns tenant-scoped JWT

  Step 2: Online Presence → POST /api/onboarding/step2
    - Website URL, description, social links, GBP link
    - Triggers background scan_business_task (crawls website)

  Step 3: Google Ads → GET /api/onboarding/google-ads-url
    - Opens Google OAuth consent screen
    - Callback saves refresh token encrypted
    - User picks which account to manage
    - OR user clicks "Skip for Now"

  Step 4: Budget & Goals → POST /api/onboarding/step4
    - Monthly budget, conversion goal (calls/forms/bookings)

  Step 5: AI Preferences → POST /api/onboarding/step5
    - Autonomy mode: full_auto / semi_auto / manual
    - Shows completion animation → redirects to /dashboard
```

### Flow 2: Dashboard (Daily Use)
```
/dashboard
  → GET /api/dashboard/kpis (impressions, clicks, cost, conversions, ROAS)
  → GET /api/dashboard/daily-trend (chart data)
  → GET /api/dashboard/alerts (issues/opportunities)
  → GET /api/dashboard/campaigns (top campaigns)
  → Links to detailed views
```

### Flow 3: "Get Customers" Wizard (Primary CTA)
```
/get-customers (5-step wizard)
  Step 1: Select business type (locksmith, plumber, etc.)
  Step 2: Enter location
  Step 3: Set budget
  Step 4: Choose goal (calls/leads/both)
  Step 5: AI builds campaign via SSE streaming
    → POST /api/v2/strategist/auto-build/stream
    → Real-time progress: keyword research → strategy → campaign creation → compliance check
    → Shows result: campaign name, budget, # ad groups, # keywords, # ads, compliance grade
```

### Flow 4: AI Operator — "Fix My Ads"
```
/operator
  → Click "Scan Account"
  → POST /api/v2/operator/scan (deep account analysis)
  → Shows: wasted spend, missed opportunities, projected improvements
  → Lists recommendations grouped by type:
    - Budget reallocation
    - Keyword pauses/additions
    - Bid adjustments
    - Negative keyword additions
    - Ad copy improvements
  → User reviews each recommendation (approve/reject)
  → Click "Apply Approved"
  → POST /api/v2/operator/apply (executes changes in Google Ads)
```

### Flow 5: AI Strategist Chat
```
/strategist
  → Chat interface — type natural language requests
  → POST /api/v2/strategist/chat (streaming response)
  → AI can:
    - Build campaigns from description
    - Audit existing campaigns
    - Generate landing pages
    - Research keywords
    - Analyze competitors
    - Suggest expansions
  → Rich responses with inline campaign drafts, audit results, quick actions
```

### Flow 6: Campaign Management
```
/ads/campaigns → list all campaigns with performance metrics
  → Click campaign → /ads/campaigns/[id] (detail: ad groups, keywords, ads)
  → Pause/enable campaigns
  → View metrics: impressions, clicks, CTR, conversions, CPA, ROAS

/ads/keywords → all keywords with quality scores, bids, performance
  → Pause/enable keywords
  → Sort/filter, CSV export

/ads/ads → all ads with performance
  → AI audit per ad (click "Audit" → gets improvement suggestions)

/ads/search-terms → search term report
  → Waste detection (irrelevant terms eating budget)
  → One-click add as negative keyword
```

### Flow 7: GBP Manager
```
/gbp (tabs: Posts | Reviews | Images)
  Posts:
    → List all posts, create new, AI-generate
    → POST /api/gbp/posts/generate (AI writes GBP post)
    → Schedule posts, view engagement (views, clicks)
  Reviews:
    → List reviews with ratings
    → AI drafts reply to each review
    → One-click publish reply
  Images:
    → Manage GBP photos
```

### Flow 8: Settings
```
/settings
  Business Profile: name, industry, phone, website, description, service area, budget, radius
  Location & Address: street, city, state, zip (auto-populated from GBP if connected)
  Social Links: Facebook, Instagram, TikTok, GBP URL
  GBP Connection: connect/disconnect/sync Google Business Profile
  Google Ads Connection: connected account info, Sync Now, Reconnect, Disconnect
  AI Guardrails: autonomy mode, max daily budget, max CPC, max budget increase %, min ROAS
  Notifications: email settings, test email
```

---

## 7. Integration Points

| Integration | Backend | Frontend | Status |
|---|---|---|---|
| **Google Ads API** | `integrations/google_ads/client.py` (496 lines), `oauth.py` | Onboarding Step 3, Settings, all ads pages | ✅ **Wired** — read & write (campaigns, keywords, ads, conversions, auction insights) |
| **Google Business Profile** | `services/gbp_service.py`, `gbp_oauth_service.py`, `gbp_post_service.py`, `gbp_review_service.py` | `/gbp`, `/settings` | ✅ **Wired** — OAuth, posts, reviews, images |
| **OpenAI** | Used in `campaign_generator.py`, `creative_service.py`, `strategist_orchestrator.py`, `landing_page_generator.py`, `recommendation_engine.py` | Strategist, Campaign Builder, Creative, Operator | ⚠️ **Wired but needs OPENAI_API_KEY** |
| **Stripe** | `services/v2/billing_service.py` | `/register`, `/v2/billing` | ⚠️ **Wired but needs Stripe keys** — graceful fallback exists |
| **CallFlux** | `api/bridge.py` | `/calls` | ✅ **Wired** — call tracking integration |
| **SEOpix Image Generator** | `integrations/image_generator/`, `integrations/seopix/` | Creative pages | ⚠️ **Wired but needs API key** |
| **S3 Storage** | Config present | Asset storage | ⚠️ **Wired but needs S3 credentials** |

---

## 8. Security & Auth

- **JWT** — access tokens (60 min) + refresh tokens (30 days)
- **Fernet encryption** — Google Ads refresh tokens encrypted at rest
- **Multi-tenant isolation** — every API endpoint validates user membership in tenant via DB (not just JWT)
- **RBAC roles** — owner, admin, analyst, viewer with permission checks
- **Onboarding guard** — `useOnboardingGuard()` hook redirects users to onboarding if not complete
- **Resource tenant verification** — `verify_resource_tenant()` prevents cross-tenant data access
- **CORS** — configurable origins

---

## 9. What's Fully Functional vs Needs Work

### ✅ Fully Wired (Frontend ↔ Backend Connected)
- Auth flow (register, login, tenant selection)
- Onboarding (all 5 steps)
- Google Ads OAuth connection & account selection
- Dashboard (KPIs, charts, alerts)
- Campaign management (list, detail, pause/enable)
- Keyword management
- Ad performance & AI audit
- Search term analysis & negative keyword management
- Landing page analysis & audit
- AI Campaign Builder (prompt → campaign)
- AI Strategist chat
- AI Operator (scan → recommend → apply)
- Get Customers wizard
- Settings (profile, guardrails, connections)
- GBP Manager (posts, reviews, images)
- Calls & Leads (CallFlux bridge)
- LSA Leads
- All V2 pages (MCC, conversions, changes, connectors, policy, notifications)

### ⚠️ Wired But Needs External Config
| Feature | What's Needed |
|---|---|
| AI features (Strategist, Operator, Campaign Builder, Creative) | `OPENAI_API_KEY` in .env |
| Stripe billing | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` |
| Image generation | `IMAGE_GENERATOR_API_KEY` |
| S3 asset storage | `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` |
| Email notifications | SMTP/email service config |

### ⚠️ Functional But Minimal Implementation
| Feature | Details |
|---|---|
| Reports (`/reports`) | Backend is only 2.6KB — likely returns basic data, no PDF generation hooked up |
| AI Quality/Evaluation (`/v2/evaluation`) | Backend is 1.6KB — minimal endpoints |
| Audit service | Only 1KB — basic logging |

### 🔴 Not Working Without Infrastructure
| Requirement | Impact |
|---|---|
| **PostgreSQL** | ALL API calls fail — no database |
| **Redis** | Background jobs don't run — no sync, no scans |
| **Celery worker** | No background processing — Google Ads sync, business scan, reports |
| **Google Ads API (Basic Access)** | Can't read/write real campaign data with test token |

---

## 10. Data Flow — How Syncing Works

```
1. User connects Google Ads (OAuth) → refresh token stored encrypted
2. sync_ads_account_task triggered (Celery)
   → Fetches: campaigns, ad groups, ads, keywords, conversions, performance data
   → Stores everything in PostgreSQL (Campaign, AdGroup, Ad, Keyword, PerformanceDaily, etc.)
3. Daily sync (Celery Beat) refreshes data
4. Frontend reads from PostgreSQL (not directly from Google Ads API for reads)
5. Writes (pause/enable, budget changes, new campaigns) go directly to Google Ads API + update local DB
```

---

## 11. File Size Summary (Effort Indicator)

| Area | Total Size | Assessment |
|---|---|---|
| Backend API routes | ~300KB | Heavy — most endpoints are fully implemented |
| Backend services | ~600KB+ | Very heavy — especially campaign_generator (159KB), strategist (90KB), operator services (200KB+) |
| Backend models | ~100KB | Complete — 78 tables |
| Backend jobs | ~117KB | Full — sync, scan, operator, reports |
| Frontend pages | 45 pages | All wired to backend APIs |
| Frontend components | 6 UI components + sidebar layout | Minimal component library (uses Radix/shadcn) |

---

## 12. Summary

**This is a substantially complete AI-powered Google Ads management platform.** The codebase has:

- **45 frontend pages** all wired to backend APIs
- **31 backend API routers** with real business logic
- **78 database models** covering the full domain
- **600KB+ of service layer code** with deep AI integration
- **Full background job system** for syncing and automation

**To get it running locally, you need:**
1. Docker Desktop → `docker compose up -d postgres redis`
2. Run migrations → `alembic upgrade head`
3. Backend `.env` with Google Ads credentials ✅ (done)
4. `OPENAI_API_KEY` for AI features
5. Start backend + frontend + celery worker

**The biggest gaps are:**
- No `OPENAI_API_KEY` configured → all AI features return errors
- Reports backend is minimal
- No automated tests (test directory is empty)
- Seed data (`seed.py` — 18KB) exists but hasn't been run
