# Ignite Ads AI — Product Requirements Document

## 1. Vision
The most intelligent Google Ads campaign assistant for service SMBs. From prompt to plan to prefilled campaign to approval and launch, with continuous performance monitoring, diagnosis, safe auto-adjustments, and cross-tenant learning.

## 2. Target Users
Service-based SMBs: locksmiths, roofers, auto repair, HVAC, plumbers, tax preparers, dentists, etc.

### User Roles
| Role | Permissions |
|------|------------|
| Owner | Full access, connect accounts, enable autopilot, approve high-risk changes, manage billing |
| Admin | Same as Owner except billing/ownership transfer |
| Analyst | Create drafts, recommendations, view all data |
| Viewer | Read-only dashboards and reports |

## 3. Core User Stories

### A. Tenant Onboarding
- **US-A1**: As a new user, I can sign up and create a tenant for my business.
- **US-A2**: As an owner, I can enter my business details (name, website, industry, service area, phone, conversion goal).
- **US-A3**: As an owner, I can link social profiles and GBP.
- **US-A4**: As an owner, I can connect my Google Ads account via OAuth.
- **US-A5**: As an owner, I can optionally connect call tracking.
- **US-A6**: As an owner, I can set budget limits, autonomy mode, and risk tolerance.
- **Acceptance**: Onboarding wizard saves all data, triggers business scan, and syncs Google Ads account.

### B. Business Intelligence Scanner
- **US-B1**: As a user, I can see extracted business info (services, areas, offers, trust signals) from my website.
- **US-B2**: As a user, I can edit/override extracted data.
- **Acceptance**: Scanner crawls key pages, extracts structured data, builds BusinessProfile JSON.

### C. Google Ads Connector + Audit
- **US-C1**: As an owner, I can connect multiple Google Ads accounts.
- **US-C2**: As a user, I can see account health score, structure summary, and issues.
- **US-C3**: As a user, I can see conversion tracking validation status.
- **Acceptance**: OAuth flow completes, tokens encrypted, daily sync runs, audit issues listed with severity.

### D. Prompt-to-Campaign Generator
- **US-D1**: As an analyst+, I can type a prompt describing what I want to advertise.
- **US-D2**: I see a full campaign plan preview (campaign settings, ad groups, keywords, negatives, ads, extensions, budget).
- **US-D3**: I can edit the plan before approving.
- **US-D4**: I can "Approve & Launch" to push to Google Ads or "Save as Draft".
- **Acceptance**: Generated campaign follows playbook, avoids duplicates, includes all required assets.

### E. Creative Studio
- **US-E1**: As a user, I can generate ad copy variants (headlines, descriptions, callouts, sitelinks).
- **US-E2**: As a user, I can generate images via seopix.ai templates.
- **US-E3**: As a user, I can manage an asset library with brand kit.
- **Acceptance**: Copy variants follow brand voice, images match templates, assets stored and reusable.

### F. Performance Monitoring + Diagnostics
- **US-F1**: As a user, I see KPI cards and trend charts on the dashboard.
- **US-F2**: I see alerts for budget pacing, tracking issues, CTR drops, CPA spikes.
- **US-F3**: I see diagnostic reports with root cause candidates.
- **Acceptance**: Daily diagnostics run, alerts generated with severity, root causes ranked by confidence.

### G. Optimization Engine
- **US-G1**: As a user, I see a feed of recommendations (like PRs) with diff previews.
- **US-G2**: I can approve/reject each recommendation.
- **US-G3**: In semi-auto mode, low-risk changes apply automatically.
- **US-G4**: All changes are logged with before/after and rollback token.
- **Acceptance**: Recommendations include rationale, expected impact, risk. Rollback works.

### H. Competitive Intelligence
- **US-H1**: As a user, I see competitor ad themes from SERP scans.
- **US-H2**: I see auction insights data from my account.
- **US-H3**: I see landing page comparisons.
- **Acceptance**: Competitor data is public-only, no private data claims.

### I. Experiments Engine
- **US-I1**: As an analyst+, I can create A/B experiments for ad copy.
- **US-I2**: I see experiment results and can promote winners.
- **Acceptance**: Bandit rotation after minimum data, budget caps respected.

### J. Learning Layer
- **US-J1**: The system uses anonymized cross-tenant patterns to improve defaults.
- **US-J2**: Playbooks are updated based on aggregated evidence.
- **Acceptance**: No PII leaked, confidence scoring based on sample size.

### K. Reporting
- **US-K1**: I receive weekly AI CMO reports (PDF).
- **US-K2**: I can generate monthly growth reviews.
- **US-K3**: I can export CSV and share reports via link.
- **Acceptance**: Reports include KPIs, changes, recommendations, competitor moves.

### L. Guardrails & Approvals
- **US-L1**: Budget caps enforced per tenant/day.
- **US-L2**: Change cooldown enforced (72h between major changes).
- **US-L3**: Conversion tracking health monitored; autopilot stops if broken.
- **US-L4**: One-click rollback for last N changes.
- **Acceptance**: All guardrails enforced, audit trail complete.

## 4. Monetization Tiers

| Feature | Starter | Pro | Elite |
|---------|---------|-----|-------|
| Google Ads accounts | 1 | 3 | Unlimited |
| Autonomy mode | Suggest only | Semi-auto | Full autopilot |
| Reports | 1/month | Weekly | Weekly + monthly |
| Competitor SERP scans | — | ✓ | Advanced |
| Creative studio | Limited | Full | Full + seopix credits |
| Experiments | — | — | ✓ |
| Multi-location playbooks | — | — | ✓ |
| Prompts/month | 10 | 50 | Unlimited |

## 5. Implementation Phases

### Phase 1 (MVP, 2-4 weeks)
- Multi-tenant auth + onboarding wizard
- Google Ads connect + read-only sync
- Business scanner (website + social)
- Prompt-to-campaign drafts (no autopilot)
- Approval flow + launch campaigns
- Basic dashboard

### Phase 2
- Performance monitoring + diagnostics
- Recommendation feed + approval UX
- Semi-auto low-risk changes
- Basic competitor SERP scans + auction insights

### Phase 3
- Experiments + bandit testing
- Learning layer + playbooks
- Autopilot advanced with guardrails
- Full creative studio + seopix integration

### Phase 4
- Profit-based optimization (CRM/payments data)
- Landing page optimizer suggestions
- Advanced multi-location campaigns
