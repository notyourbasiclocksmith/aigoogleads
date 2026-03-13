# Google LSA + CallFlux + IgniteAds Integration Plan

**Date:** 2026-03-13
**Status:** AUDIT COMPLETE — Detailed plan ready for review

---

## 1. Executive Summary

This plan connects three systems for a unified locksmith (or any local service) call intelligence platform:

1. **Google Local Services Ads (LSA)** — Google's pay-per-lead platform for local businesses (calls, messages, bookings)
2. **CallFlux** — Call tracking + AI call analysis platform (Twilio, Deepgram, OpenAI, DNI, Google Ads offline conversions)
3. **IgniteAds (aigoogleads)** — Google Ads management platform (campaigns, search terms, recommendations, optimizations)

**Goal:** See every call's full lifecycle in one place — who called, what Google charged, what happened on the call, whether it was a real lead, and feed that intelligence back to optimize ad spend.

---

## 2. Google LSA API — What Data We Can Pull

### 2.1 Available Resources (via Google Ads API v23 GAQL)

Google exposes LSA data through **read-only report resources** when the account has a `LOCAL_SERVICES` campaign:

#### `local_services_lead` — Every lead received
```sql
SELECT
  local_services_lead.id,
  local_services_lead.lead_type,              -- PHONE_CALL, MESSAGE, BOOKING
  local_services_lead.category_id,            -- Service category (locksmith = 33)
  local_services_lead.service_id,             -- Specific service type
  local_services_lead.contact_details,        -- Caller name, phone, email (if not WIPED_OUT)
  local_services_lead.lead_status,            -- NEW, ACTIVE, BOOKED, DECLINED, EXPIRED, WIPED_OUT
  local_services_lead.creation_date_time,     -- When the lead came in
  local_services_lead.locale,
  local_services_lead.lead_charged,           -- TRUE if Google charged for this lead
  local_services_lead.credit_details.credit_state,  -- PENDING, CREDITED, NOT_CREDITED
  local_services_lead.credit_details.credit_state_last_update_date_time
FROM local_services_lead
```

**Key fields:**
- **`lead_charged`** — Whether Google charged you for this lead (= cost per lead)
- **`credit_details.credit_state`** — Whether you successfully disputed a bad lead
- **`contact_details`** — Caller's phone number, name, email
- **`lead_type`** — PHONE_CALL, MESSAGE, or BOOKING
- **`lead_status`** — Lifecycle state

#### `local_services_lead_conversation` — Call details + recordings
```sql
SELECT
  local_services_lead_conversation.id,
  local_services_lead_conversation.conversation_channel,    -- PHONE_CALL, MESSAGE
  local_services_lead_conversation.participant_type,        -- ADVERTISER, CONSUMER
  local_services_lead_conversation.lead,                    -- Parent lead resource name
  local_services_lead_conversation.event_date_time,
  local_services_lead_conversation.phone_call_details.call_duration_millis,   -- Call duration
  local_services_lead_conversation.phone_call_details.call_recording_url,     -- RECORDING URL!
  local_services_lead_conversation.message_details.text,
  local_services_lead_conversation.message_details.attachment_urls
FROM local_services_lead_conversation
WHERE local_services_lead_conversation.conversation_channel = 'PHONE_CALL'
```

**Key fields:**
- **`call_recording_url`** — Google saves the call recording! We can download and transcribe it
- **`call_duration_millis`** — Duration in milliseconds
- **`message_details.text`** — For message-type leads, the actual message content

#### `local_services_verification_artifact` — Business verification status
#### `local_services_employee` — Employees linked to the LSA profile

### 2.2 Write Operations Available
- **`ProvideLeadFeedback()`** — Submit feedback/rating on leads (accept/dispute)
- **Edit campaigns** — Status, budget, bidding (ManualCpa, MaximizeConversions)
- **Set ad schedules, locations, service types**
- **Cannot create/remove campaigns** — Only manage existing ones

### 2.3 What Google DOES NOT Provide via API
- ❌ No cost-per-lead amount directly in the API (only `lead_charged` boolean)
- ❌ No invoice-level line items per lead
- ❌ No real-time call forwarding number (LSA uses Google's own numbers)
- ❌ No transcription (only recording URL — we must transcribe ourselves)

### 2.4 How to Get Cost Per Lead
- **Campaign budget:** Query `campaign_budget.amount_micros` for the LSA campaign
- **Lead count:** Count leads where `lead_charged = TRUE`
- **Estimated CPL:** `budget_spent / charged_leads_count`
- **Google's LSA Detailed Lead Reports API** (separate from Ads API) has exact cost per lead, but requires partner access

---

## 3. CallFlux Audit — What We Already Have

### 3.1 Data Available Per Call

| Data | Model | Field(s) | Status |
|---|---|---|---|
| **Call Recording** | `Call` | `recording_url`, `recording_duration` | ✅ Working via Twilio |
| **Call Transcription** | `Transcription` | `text`, `segments` (speaker-separated, word-level) | ✅ Working via Deepgram |
| **AI Insights** | `AIInsight` | `summary`, `sentiment`, `intents`, `action_items` | ✅ Working via OpenAI GPT-4o |
| **Lead Quality Score** | `AIInsight` | `lead_quality_score` (0-100), `qualified_lead`, `qualified_reason` | ✅ Working |
| **Call Disposition** | `CallDisposition` | `name`, `is_positive`, `is_conversion` | ✅ Working |
| **Keyword Detection** | `KeywordHit` | `phrase`, `count`, `matches` (with timestamps) | ✅ Working |
| **DNI Attribution** | `Call` + `DNISession` | `click_id_type`, `click_id_value`, `attribution_source`, `attribution_confidence` | ✅ Working |
| **Google Ads Upload** | `GoogleAdsConversionUpload` | Offline conversion queue with retry | ✅ Working |
| **UTM Tracking** | `DNISession` | `utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content` | ✅ Working |
| **Visitor Context** | `DNISession` | `landing_url`, `referrer`, `user_agent`, `ip_trunc` | ✅ Working |

### 3.2 CallFlux Tenant Model
- `Tenant` has: `id` (integer), `name`, `slug`, `plan` (starter/growth/pro/enterprise), `stripe_customer_id`
- `Integration` stores OAuth tokens per tenant per platform (`platform = "google_ads"`)
- `Integration.platform_account_id` = Google Ads Customer ID
- `Integration.settings` (JSONB) = `{conversion_action_id, login_customer_id}`

### 3.3 CallFlux → Google Ads Flow (Already Built)
1. Call comes in via Twilio → `Call` record created
2. DNI session matched → `click_id_value` (gclid) attached to call
3. Recording received → Transcription started (Deepgram)
4. Transcription done → AI Insights generated (GPT-4o)
5. If `qualified_lead = true` AND `click_id_value` exists → Google Ads offline conversion queued
6. Background worker uploads conversions to Google Ads API

### 3.4 What CallFlux is Missing
- ❌ No LSA lead data (only regular Google Ads via search/display campaigns)
- ❌ No cost-per-call from Google (CallFlux knows Twilio cost, not Google ad cost)
- ❌ No cross-platform tenant linking with IgniteAds
- ❌ No LSA call recordings (Google stores these separately from Twilio)

---

## 4. How to Connect Both Systems (Tenant-Specific)

### 4.1 Tenant Linking Strategy

Both systems have their own tenant models. The link is the **Google Ads Customer ID**:

| System | Tenant ID | Google Ads CID |
|---|---|---|
| **IgniteAds** | `tenants.id` (UUID) | `integration_google_ads.customer_id` (e.g., `579-537-8641`) |
| **CallFlux** | `tenants.id` (integer) | `integrations.platform_account_id` where `platform = "google_ads"` |

**Linking approach:** Create a shared API key / webhook system between the two platforms, keyed on Google Ads Customer ID. When either system has data for a CID, it can push/pull from the other.

### 4.2 Option A: API Bridge (Recommended)

Add a cross-platform API to IgniteAds that CallFlux calls (and vice versa):

```
IgniteAds ←→ CallFlux
    ↑              ↑
    └── Google Ads API ──┘
         (shared CID)
```

**IgniteAds exposes:**
- `GET /api/bridge/lsa/leads?customer_id=XXX&days=30` — LSA leads from Google
- `GET /api/bridge/lsa/conversations?lead_id=XXX` — Call recordings + details
- `GET /api/bridge/campaigns/cost?customer_id=XXX` — Campaign spend data

**CallFlux exposes:**
- `GET /api/bridge/calls?customer_id=XXX&days=30` — Calls with AI insights
- `GET /api/bridge/calls/{id}/transcript` — Full transcript
- `GET /api/bridge/calls/{id}/insights` — AI analysis
- `POST /api/bridge/calls/{id}/cost` — Attach Google ad cost to a call

### 4.3 Option B: Shared Database View (Simpler but Tighter Coupling)

If both apps share the same Render PostgreSQL or use a shared schema, create cross-references directly.

---

## 5. Integration Plan — Phases

### Phase 1: LSA Data Sync into IgniteAds (Backend)

**Goal:** Pull all LSA lead data into IgniteAds so users can see their Local Services call history, costs, and statuses.

**New Models:**
```python
class LSALead(Base):
    __tablename__ = "lsa_leads"
    id = Column(String, primary_key=True)  # Google's lead ID
    tenant_id = Column(UUID, ForeignKey("tenants.id"))
    lead_type = Column(String)           # PHONE_CALL, MESSAGE, BOOKING
    category_id = Column(String)
    service_id = Column(String)
    contact_name = Column(String)
    contact_phone = Column(String)
    contact_email = Column(String)
    lead_status = Column(String)         # NEW, ACTIVE, BOOKED, DECLINED
    lead_charged = Column(Boolean)       # Did Google charge for this?
    credit_state = Column(String)        # PENDING, CREDITED, NOT_CREDITED
    creation_date_time = Column(DateTime)
    synced_at = Column(DateTime)

class LSAConversation(Base):
    __tablename__ = "lsa_conversations"
    id = Column(String, primary_key=True)
    lead_id = Column(String, ForeignKey("lsa_leads.id"))
    tenant_id = Column(UUID, ForeignKey("tenants.id"))
    channel = Column(String)             # PHONE_CALL, MESSAGE
    event_date_time = Column(DateTime)
    call_duration_ms = Column(Integer)
    recording_url = Column(String)       # Google's recording URL
    message_text = Column(Text)
    # CallFlux enrichment (Phase 3)
    callflux_call_id = Column(Integer, nullable=True)
    transcription_text = Column(Text, nullable=True)
    ai_summary = Column(Text, nullable=True)
    lead_quality_score = Column(Integer, nullable=True)
```

**New Google Ads Client Methods:**
```python
async def get_lsa_leads(self, days=30) -> List[Dict]:
    """Query local_services_lead resource via GAQL."""

async def get_lsa_conversations(self, lead_id=None) -> List[Dict]:
    """Query local_services_lead_conversation for call details + recordings."""

async def submit_lsa_lead_feedback(self, lead_id, feedback) -> Dict:
    """Submit feedback on a lead (accept/dispute)."""
```

**Sync Task:** Add to existing sync worker — pull LSA leads + conversations every sync cycle.

**Estimated effort:** 2-3 days

### Phase 2: LSA Frontend Page in IgniteAds

**Goal:** New "Local Services" page showing all LSA calls with Google's data.

**Displays:**
- Lead list with type, status, charged status, timestamp
- Call duration and recording player (link to Google's recording URL)
- Credit dispute status
- Cost summary: total charged leads, estimated CPL
- Lead feedback buttons (accept/dispute via API)

**Estimated effort:** 1-2 days

### Phase 3: CallFlux AI Enrichment of LSA Calls

**Goal:** Take Google LSA call recordings → run them through CallFlux's AI pipeline → get transcriptions + insights.

**Flow:**
1. IgniteAds syncs LSA lead conversations with recording URLs
2. For each PHONE_CALL conversation with a recording URL:
   a. Download the recording from Google's URL
   b. Send to CallFlux API: `POST /api/bridge/transcribe` with audio URL
   c. CallFlux runs Deepgram transcription → GPT-4o insights
   d. Returns: `{transcript, summary, sentiment, lead_quality_score, qualified_lead, intents, action_items}`
3. IgniteAds stores the enrichment on the `LSAConversation` record

**Alternative:** CallFlux processes the audio directly if we give it the Google recording URL. This avoids downloading/re-uploading.

**Estimated effort:** 2-3 days

### Phase 4: Cost Attribution (Google → CallFlux)

**Goal:** For calls tracked by CallFlux (via DNI), attach the Google ad cost so CallFlux knows the true cost-per-call.

**How:**
- CallFlux already captures `gclid` via DNI sessions
- IgniteAds already syncs campaign performance (cost, clicks, conversions)
- Connect: When CallFlux has a call with a gclid → query IgniteAds for the click cost
- For LSA: Each charged lead ≈ the LSA bid amount (ManualCpa setting)

**New field on CallFlux `Call` model:**
```python
google_ad_cost = Column(Numeric(10, 4), nullable=True)  # Cost Google charged for this click/lead
google_campaign_name = Column(String, nullable=True)
google_campaign_type = Column(String, nullable=True)     # SEARCH, LOCAL_SERVICES, etc.
```

**Estimated effort:** 1-2 days

### Phase 5: Unified Dashboard

**Goal:** Single view in IgniteAds showing:
- All Google Ads calls (Search + LSA) with costs
- CallFlux AI insights for each call
- Lead quality scores
- Cost per qualified lead (not just cost per lead)
- Wasted spend on bad calls (spam, wrong numbers) with AI evidence

**Estimated effort:** 2-3 days

---

## 6. CallFlux Power Features We Can Leverage

Here's what CallFlux already has that can supercharge the Google Ads integration:

### 6.1 AI Call Analysis (Already Built)
- **Call Summary** — 2-3 sentence summary of every call
- **Sentiment Analysis** — positive/neutral/negative
- **Intent Detection** — ["price_quote", "schedule_service", "emergency_lockout"]
- **Lead Quality Score** — 0-100 scale
- **Qualified Lead Detection** — Boolean with reasoning
- **Action Items** — Follow-up tasks extracted from the call

**Power move:** Run this on LSA recordings to know which LSA leads were actually good vs garbage.

### 6.2 Keyword Detection (Already Built)
- Define keywords like "lockout", "emergency", "price", "how much"
- CallFlux scans transcripts and flags matches with timestamps
- **Power move:** Auto-detect high-value service types from call content, compare to what Google's LSA categorized them as.

### 6.3 Auto-Disposition (Already Built)
- Rules engine that auto-tags calls based on duration, keywords, AI scores
- `is_positive`, `is_conversion` flags on dispositions
- **Power move:** Auto-dispute LSA leads that AI determined were spam/wrong numbers.

### 6.4 DNI + Offline Conversions (Already Built)
- Dynamic Number Insertion captures gclid from website visitors
- Qualified leads automatically uploaded as Google Ads offline conversions
- Smart Bidding then optimizes for REAL leads, not just clicks
- **Power move:** Feed LSA qualified lead data back to improve LSA bidding too.

### 6.5 What to Add to CallFlux

| Feature | Description | Effort |
|---|---|---|
| **Google Ad Cost per Call** | New field `google_ad_cost` on Call model | 1 day |
| **LSA Lead Matching** | Match LSA leads to CallFlux calls by phone number + timestamp | 1 day |
| **Cross-Platform Tenant Link** | Store `igniteads_tenant_id` or shared API key on CallFlux Integration | 0.5 day |
| **Bridge API** | REST endpoints for IgniteAds to pull call data | 1 day |
| **LSA Recording Ingestion** | Accept Google recording URLs for transcription | 1 day |

---

## 7. Tenant Connection Architecture

### 7.1 How Both Systems Identify the Same Customer

```
┌─────────────┐          ┌─────────────┐
│  IgniteAds   │          │  CallFlux   │
│              │          │              │
│ tenant.id    │          │ tenant.id    │
│ (UUID)       │          │ (integer)    │
│              │          │              │
│ integration_ │──SAME──▶│ integration. │
│ google_ads.  │  CID     │ platform_    │
│ customer_id  │◀──────── │ account_id   │
│ "5795378641" │          │ "5795378641" │
└─────────────┘          └─────────────┘
```

### 7.2 Linking Method

**Option A: API Key Exchange (Recommended)**
1. In IgniteAds Settings, user enters their CallFlux API key
2. IgniteAds stores it: `business_profile.constraints_json.callflux_api_key`
3. IgniteAds can now call CallFlux API endpoints authenticated as that tenant
4. Vice versa: CallFlux stores IgniteAds API key

**Option B: Shared Secret per CID**
1. Both systems generate a shared secret keyed on Google Ads CID
2. API calls between systems include this secret as auth

**Option C: OAuth Between Systems**
1. Full OAuth flow — most secure but most complex
2. Overkill for two internal systems

### 7.3 Data Flow Diagram

```
Google Ads API (CID: 579-537-8641)
        │
        ├──── LSA Leads ────────────▶ IgniteAds (sync task)
        │     - lead_type                  │
        │     - contact_details            │ recording_url
        │     - lead_charged               ▼
        │     - recording_url         CallFlux AI Pipeline
        │                                  │
        │                                  ├── Deepgram Transcription
        │                                  ├── GPT-4o Analysis
        │                                  ├── Lead Quality Score
        │                                  └── Keyword Detection
        │                                  │
        ├──── Search Campaigns ─────▶ IgniteAds (existing sync)
        │     - clicks, cost               │
        │     - search terms               │
        │                                  ▼
        │                             CallFlux DNI
        │                                  │
        │                                  ├── gclid capture
        │                                  ├── Call recording
        │                                  ├── AI analysis
        │                                  └── Qualified? → Offline Conversion Upload
        │                                                          │
        └──────────── Google Ads Smart Bidding ◀───────────────────┘
```

---

## 8. Priority Order (What to Build First)

| # | Feature | Value | Effort | Priority |
|---|---|---|---|---|
| 1 | **LSA lead sync** into IgniteAds | See all LSA calls + costs | 2-3 days | 🔴 HIGH |
| 2 | **LSA frontend page** | Users can view/manage LSA leads | 1-2 days | 🔴 HIGH |
| 3 | **CallFlux bridge API** | Cross-platform data access | 1 day | 🟡 MEDIUM |
| 4 | **LSA recording → CallFlux AI** | AI insights on LSA calls | 2-3 days | 🟡 MEDIUM |
| 5 | **Google ad cost on CallFlux calls** | True cost-per-call | 1 day | 🟡 MEDIUM |
| 6 | **Auto-dispute bad LSA leads** | Save money on garbage leads | 1 day | 🟢 NICE |
| 7 | **Unified call dashboard** | One view across all sources | 2-3 days | 🟢 NICE |
| 8 | **Cost per qualified lead metric** | Smart ROI calculation | 1 day | 🟢 NICE |

**Total estimated effort: 11-16 days**

---

## 9. Quick Wins (Can Do Now)

1. **Add LSA GAQL queries** to the existing `GoogleAdsClient` in IgniteAds — the client already supports GAQL, just need new query methods
2. **Add `google_ad_cost` field** to CallFlux's Call model — simple Alembic migration
3. **Create LSA models** in IgniteAds — new tables for leads and conversations
4. **Add LSA sync** to the existing sync task — it already loops through campaigns, just add LSA lead queries

---

## 10. Answers to Specific Questions

### "Can we pull LSA call data?"
**YES.** Google exposes `local_services_lead` and `local_services_lead_conversation` via GAQL. We get: lead type, contact details, status, charged/credited, call duration, and **recording URLs**.

### "Cost per lead / recordings?"
**Recordings: YES** — `phone_call_details.call_recording_url` gives us the audio URL.
**Cost per lead: PARTIAL** — We get `lead_charged` (boolean) but not the exact dollar amount per lead. We can estimate CPL from budget ÷ charged leads. Google's separate Local Services API has exact costs but requires partner access.

### "Can we use CallFlux AI on LSA calls?"
**YES.** Download Google's recording → send to Deepgram → run GPT-4o analysis. Exact same pipeline CallFlux already uses for Twilio calls.

### "How to connect both systems per tenant?"
**By Google Ads Customer ID.** Both systems store the same CID. Add an API bridge with shared API keys stored per tenant.

### "Can we add Google ad cost to CallFlux per call?"
**YES for Search/Display:** When CallFlux has a `gclid`, query IgniteAds for the click cost from the campaign performance data.
**PARTIAL for LSA:** We know if the lead was charged but not the exact amount. Estimated from CPA bid setting.
