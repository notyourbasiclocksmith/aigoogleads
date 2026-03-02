# Ignite Ads AI — V2 PRD (Product Requirements Document)

## Overview
V2 upgrades Ignite Ads AI from "AI Google Ads Worker" to "AI CMO" — a full-spectrum campaign intelligence platform with agency support, conversion truth, change governance, billing, policy compliance, and extensible connectors.

## Feature Flags
All V2 modules are gated behind feature flags stored on the Tenant model (`feature_flags_json` JSONB column). This allows per-plan and per-tenant enablement without breaking V1 tenants.

Flag keys:
- `mcc_enabled` — Module 1
- `conversion_truth_enabled` — Module 2
- `change_management_enabled` — Module 3
- `connectors_enabled` — Module 4
- `policy_compliance_enabled` — Module 5
- `evaluation_enabled` — Module 7
- `competitor_intel_v2_enabled` — Module 8
- `billing_enabled` — Module 9
- `alerting_v2_enabled` — Module 10

---

## MODULE 1 — MCC / Agency Mode

### User Stories
- US-1.1: As an agency, I connect my MCC and the system discovers all child accounts.
- US-1.2: As an agency, I bind specific child accounts to a tenant for management.
- US-1.3: As a multi-location brand, I view rollup KPIs across all bound accounts.
- US-1.4: As an admin, I prevent a customer_id from being bound to multiple tenants (unless enterprise).

### Acceptance Criteria
- OAuth flow stores manager_customer_id and triggers account discovery job.
- Discovery job populates google_ads_accessible_accounts within 60s of OAuth.
- Binding UI shows checkboxes; save persists tenant_google_ads_bindings.
- Rollup endpoints aggregate metrics across all bound accounts with correct currency handling.
- Tenant isolation enforced: unique constraint on (google_customer_id) in bindings unless allow_shared_accounts flag.

---

## MODULE 2 — Conversion Truth Layer

### User Stories
- US-2.1: As a user, I connect GA4 to cross-reference conversion data.
- US-2.2: As a user, I run a tracking health check on my website.
- US-2.3: As a user, I upload offline conversions via CSV with field mapping.
- US-2.4: As a user, I configure a profit model so AI optimizes toward profit, not just CPA.

### Acceptance Criteria
- GA4 connector stores property_id and refresh_token; sync job pulls sessions/events.
- GTM health check detects gtag.js/GTM container presence and conversion tag patterns.
- CSV upload supports field mapping UI; deduplication on (gclid + conversion_name + timestamp).
- Profit model computes expected_profit_per_lead and target_cpa_max; optimization engine references these.

---

## MODULE 3 — Advanced Change Management

### User Stories
- US-3.1: As a user, I group multiple changes into a change set and apply them atomically.
- US-3.2: As a user, I schedule change sets to apply at a specific time.
- US-3.3: As a user, I define freeze windows to prevent autopilot changes.
- US-3.4: As a user, I define rollback policies that auto-revert harmful changes.

### Acceptance Criteria
- Change sets group change_log entries with ordered application.
- Scheduled changes execute via Celery beat at tenant-local time.
- Freeze windows block all autopilot actions; manual overrides require admin role.
- Rollback triggers fire within 1 hour of metric threshold breach; alert created.

---

## MODULE 4 — Connector Framework

### User Stories
- US-4.1: As a developer, I implement a new connector using the standard interface.
- US-4.2: As a user, I configure webhook destinations for alerts.
- US-4.3: As a user, I connect my CRM to auto-push offline conversions.

### Acceptance Criteria
- Connector base class enforces connect/sync/push/health_check interface.
- Credential storage uses encryption_key; never stored in plaintext.
- Event logs capture all connector activities with structured payloads.
- Webhook connector sends JSON POST with retry/backoff.

---

## MODULE 5 — Policy Compliance

### User Stories
- US-5.1: As a user, generated ads are scanned for policy violations before preview.
- US-5.2: As a user, I enable strict compliance mode to prevent superlatives/claims.

### Acceptance Criteria
- Policy rules engine checks all ad text against configurable rule sets.
- Scan results display inline in campaign preview with severity levels.
- Strict mode blocks ad submission if violations found.

---

## MODULE 6 — Prompt-Injection Defense

### Acceptance Criteria
- All crawled content stored with source provenance (url, hash, timestamp).
- Sanitization pipeline strips scripts, hidden text, instruction-like patterns.
- LLM prompts include hard guardrails against instruction injection.

---

## MODULE 7 — Evaluation Framework

### User Stories
- US-7.1: As an admin, I view recommendation quality scorecards.
- US-7.2: As a user, I see AI performance stats (wins, accuracy).

### Acceptance Criteria
- Each recommendation tracks predicted vs actual impact at 7/14/30 days.
- Playbook leaderboard ranks strategies by industry vertical.
- Regression alerts fire if prediction accuracy degrades below threshold.

---

## MODULE 8 — Competitor Intel V2

### Acceptance Criteria
- SERP provider abstraction with pluggable implementations.
- Competitor creative tracking with change detection.
- Alerts for new competitors, offer changes, outranking shifts.

---

## MODULE 9 — Billing & Metering (Stripe)

### User Stories
- US-9.1: As a tenant, I subscribe to a plan via Stripe checkout.
- US-9.2: As a tenant, I see my usage dashboard with limits.
- US-9.3: The system blocks/degrades features when plan limits are exceeded.

### Acceptance Criteria
- Stripe customer + subscription created per tenant.
- Usage counters track prompts, SERP scans, seopix credits, connected accounts.
- Plan enforcement middleware checks limits before expensive operations.

---

## MODULE 10 — Alerting & Delivery

### Acceptance Criteria
- Notification channels: Slack webhook, email (SendGrid), generic webhook.
- Per-tenant rules with severity thresholds and quiet hours.
- Delivery tracked with status and retry.
