"""
Expert-Level Prompt-to-Campaign Generator Service

Pipeline:
1) Parse intent from prompt (service, geo, offer, urgency, goal)
2) Pull competitor intelligence (messaging, USPs, gaps to exploit)
3) Pull industry keyword database — tiered by intent (emergency / high / medium / informational)
4) Pull performance learnings from same-industry tenants
5) Determine best campaign type + bidding strategy with reasoning
6) Build TIGHTLY themed ad groups (SKAGs / close variants) — NOT one big ad group
7) Use OpenAI to write psychology-driven ad copy per ad group
8) Generate expert-level extensions: sitelinks, callouts, structured snippets, call, location, price
9) Set smart budget, bid strategy, scheduling, device bids, location bid adjustments
10) Return full preview with expert reasoning for every decision
"""
import asyncio
import re
import uuid
import json
import time
import structlog
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.models.business_profile import BusinessProfile
from app.models.campaign import Campaign
from app.models.playbook import Playbook
from app.models.learning import Learning
from app.models.competitor_profile import CompetitorProfile
from app.models.tenant import Tenant

logger = structlog.get_logger()


class BuilderLog:
    """
    Collects timestamped, human-readable log entries for every AI step
    during campaign generation. Embedded in the draft so the user can
    see exactly what the AI did and why.
    """

    def __init__(self, progress_queue=None):
        self._entries: List[Dict[str, Any]] = []
        self._start = time.monotonic()
        self._step_start: Optional[float] = None
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._queue = progress_queue  # optional asyncio.Queue for SSE streaming

    def step_start(self, step: str, detail: str = ""):
        """Mark the beginning of a pipeline step."""
        self._step_start = time.monotonic()
        self._entries.append({
            "step": step,
            "status": "running",
            "detail": detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_ms": None,
            "result_summary": None,
        })
        if self._queue:
            self._queue.put_nowait({"type": "step", "step": step, "status": "running", "detail": detail})

    def step_end(self, result_summary: str = "", extra: Optional[Dict] = None):
        """Mark the end of the current pipeline step."""
        if not self._entries:
            return
        entry = self._entries[-1]
        elapsed = round((time.monotonic() - (self._step_start or self._start)) * 1000)
        entry["status"] = "done"
        entry["elapsed_ms"] = elapsed
        entry["result_summary"] = result_summary
        if extra:
            entry["extra"] = extra
        if self._queue:
            self._queue.put_nowait({"type": "step", "step": entry["step"], "status": "done", "detail": result_summary, "elapsed_ms": elapsed})

    def step_error(self, error: str):
        """Mark the current step as failed."""
        if not self._entries:
            return
        entry = self._entries[-1]
        elapsed = round((time.monotonic() - (self._step_start or self._start)) * 1000)
        entry["status"] = "error"
        entry["elapsed_ms"] = elapsed
        entry["result_summary"] = f"ERROR: {error}"

    def to_dict(self) -> Dict[str, Any]:
        total_ms = round((time.monotonic() - self._start) * 1000)
        return {
            "started_at": self._started_at,
            "total_elapsed_ms": total_ms,
            "total_elapsed_sec": round(total_ms / 1000, 1),
            "steps": self._entries,
            "step_count": len(self._entries),
        }


class CampaignGeneratorService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self._biz_name_cache: Optional[str] = None

    @staticmethod
    def _normalize_trust_signals(raw: Any, bp: Optional[BusinessProfile] = None) -> Dict[str, Any]:
        """
        Normalize trust_signals_json to a consistent dict.
        Handles two formats:
          1. Scanner format: {"list": ["licensed & insured", "15+ years experience", ...]}
          2. Structured format: {"years_experience": 15, "google_rating": 4.9, ...}
        If a BusinessProfile is passed, structured GBP fields (google_rating,
        review_count, service_radius_miles, etc.) are merged in as authoritative
        overrides — they come directly from the GBP API.
        Returns a dict with both structured keys (if parseable) and a "signals_list" key.
        """
        if not raw or not isinstance(raw, dict):
            raw = {}

        result: Dict[str, Any] = {}
        signals_list: list = []

        # Handle scanner format: {"list": [...]}
        if "list" in raw and isinstance(raw["list"], list):
            signals_list = [str(s) for s in raw["list"] if s]
            # Try to parse structured data from string signals
            for s in signals_list:
                s_lower = s.lower().strip()
                # "15+ years experience" or "15 years of experience"
                m = re.search(r'(\d+)\+?\s*years?', s_lower)
                if m and "years_experience" not in result:
                    result["years_experience"] = m.group(1) + "+"
                # "4.9 star" or "5-star"
                m = re.search(r'(\d+\.?\d*)\s*[\-\s]?star', s_lower)
                if m and "google_rating" not in result:
                    result["google_rating"] = m.group(1)
                # "100+ reviews" or "200 positive reviews"
                m = re.search(r'(\d+)\+?\s*(?:positive\s+)?reviews?', s_lower)
                if m and "review_count" not in result:
                    result["review_count"] = m.group(1)
                # "licensed & insured" or "bonded & insured"
                if "licensed" in s_lower or "bonded" in s_lower:
                    result["license"] = s.strip()
                if "guarantee" in s_lower:
                    result["guarantee"] = s.strip()
                if "certified" in s_lower:
                    result.setdefault("certifications", s.strip())
        else:
            # Structured format — pass through directly
            for k, v in raw.items():
                if v:
                    result[k] = v

        # Merge authoritative GBP fields from BusinessProfile (override parsed values)
        if bp:
            if bp.google_rating:
                result["google_rating"] = str(bp.google_rating)
            if bp.review_count:
                result["review_count"] = str(bp.review_count)
            if bp.years_experience:
                result["years_experience"] = f"{bp.years_experience}+"
            if bp.license_info:
                result["license"] = bp.license_info
            if bp.service_radius_miles:
                result["service_radius"] = f"{bp.service_radius_miles} mile radius"

        result["signals_list"] = signals_list
        return result

    @staticmethod
    def _build_trust_str(ts: Dict[str, Any]) -> str:
        """Build a formatted trust signal string for LLM prompts from normalized trust signals."""
        items = []
        if ts.get("years_experience"):
            items.append(f"{ts['years_experience']} years experience")
        if ts.get("google_rating"):
            items.append(f"{ts['google_rating']}★ Google rating")
        if ts.get("review_count"):
            items.append(f"{ts['review_count']}+ reviews")
        if ts.get("license"):
            items.append(f"Licensed: {ts['license']}")
        if ts.get("insurance"):
            items.append(f"Insurance: {ts['insurance']}")
        if ts.get("certifications"):
            certs = ts["certifications"] if isinstance(ts["certifications"], list) else [ts["certifications"]]
            items.append(f"Certifications: {', '.join(str(c) for c in certs)}")
        if ts.get("service_radius"):
            items.append(f"Service area: {ts['service_radius']}")
        if ts.get("business_hours"):
            items.append(f"Hours: {ts['business_hours']}")
        if ts.get("response_time"):
            items.append(f"Response time: {ts['response_time']}")
        if ts.get("guarantee"):
            items.append(f"Guarantee: {ts['guarantee']}")
        # Include any extra structured keys
        handled = {"years_experience", "google_rating", "review_count", "license",
                   "insurance", "certifications", "service_radius", "business_hours",
                   "response_time", "guarantee", "signals_list"}
        for k, v in ts.items():
            if k not in handled and v:
                items.append(f"{k.replace('_', ' ').title()}: {v}")
        # Append raw scanner signals not already covered
        for s in ts.get("signals_list", []):
            s_lower = s.lower()
            if not any(s_lower in item.lower() for item in items):
                items.append(s)
        return ", ".join(items) if items else "none provided"

    @staticmethod
    def _safe_int(val, default: int = 0) -> int:
        """Safely convert a value to int — AI sometimes returns strings like '30' or '+30%'."""
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            return int(val)
        if isinstance(val, str):
            cleaned = val.replace("%", "").replace("+", "").replace(",", "").strip()
            try:
                return int(float(cleaned))
            except (ValueError, TypeError):
                return default
        return default

    async def _get_business_name(self) -> str:
        """Get business name from Tenant (not on BusinessProfile)."""
        if self._biz_name_cache is not None:
            return self._biz_name_cache
        result = await self.db.execute(
            select(Tenant.name).where(Tenant.id == self.tenant_id)
        )
        self._biz_name_cache = result.scalar_one_or_none() or "Local Service"
        return self._biz_name_cache

    async def generate_from_prompt(
        self,
        prompt: str,
        business_profile: BusinessProfile,
        google_customer_id: Optional[str] = None,
        campaign_type_override: Optional[str] = None,
        progress_queue=None,
    ) -> Dict[str, Any]:
        blog = BuilderLog(progress_queue=progress_queue)
        industry = (business_profile.industry_classification or "general").lower()

        # ══════════════════════════════════════════════════════════════════
        #  PHASE 1: Intent Parsing  (must be first — everything depends on it)
        # ══════════════════════════════════════════════════════════════════
        blog.step_start("Intent Parsing", f"Analyzing prompt: \"{prompt[:80]}{'...' if len(prompt) > 80 else ''}\"")
        intent = await self._parse_intent_ai(prompt, business_profile)
        services = intent.get("services", [])
        locations = intent.get("locations", [])
        blog.step_end(
            f"Extracted {len(services)} service(s), {len(locations)} location(s), goal={intent.get('goal', 'N/A')}, urgency={intent.get('urgency', 'N/A')}",
            extra={"services": services, "locations": locations, "goal": intent.get("goal"), "urgency": intent.get("urgency")},
        )

        campaign_type = (
            campaign_type_override
            or intent.get("campaign_type_override")
            or intent.get("campaign_type")
            or self._determine_campaign_type(intent, business_profile)
        )
        blog.step_start("Campaign Type Selection", f"Override={campaign_type_override or 'none'}, AI suggested={intent.get('campaign_type', 'N/A')}")
        blog.step_end(f"Selected campaign type: {campaign_type}", extra={"campaign_type": campaign_type})

        # ══════════════════════════════════════════════════════════════════
        #  PHASE 2: All DB queries (sequential — fast, ~100ms each)
        # ══════════════════════════════════════════════════════════════════
        blog.step_start("Data Loading", "Fetching existing campaigns, playbook, learnings, competitors from DB")
        existing = await self._get_existing_campaigns()
        playbook = await self._get_playbook(industry, intent.get("goal"))
        learnings = await self._get_relevant_learnings(industry)
        competitors = await self._get_competitor_intelligence()
        blog.step_end(
            f"Loaded {len(existing)} campaigns, {'1 playbook' if playbook else 'no playbook'}, {len(learnings)} learnings, {len(competitors)} competitors",
            extra={"existing": len(existing), "has_playbook": playbook is not None, "learnings": len(learnings), "competitors": len(competitors)},
        )

        # ══════════════════════════════════════════════════════════════════
        #  PHASE 3: Parallel AI calls  (overlap + strategy + competitor + keywords)
        #  These are INDEPENDENT — each only needs intent + DB data
        #  Running them in parallel saves ~8-12 seconds
        # ══════════════════════════════════════════════════════════════════
        blog.step_start("Parallel AI Analysis", "Running overlap, strategy, competitor, keyword analysis simultaneously")

        async def _do_overlap():
            return await self._analyze_overlap_ai(existing, intent)

        async def _do_strategy():
            return await self._synthesize_strategy_ai(industry, intent, playbook, learnings, business_profile)

        async def _do_competitor():
            return await self._analyze_competitors_ai(competitors, intent, industry, business_profile)

        async def _do_keywords():
            if campaign_type == "PERFORMANCE_MAX":
                return {"keywords": [], "negatives": [], "total_keywords": 0, "total_negatives": 0, "tiers": {}}
            return await self._build_keyword_strategy_ai(intent, industry, learnings, playbook, business_profile)

        overlap_analysis, strategy_insights, competitor_insights, keyword_strategy = await asyncio.gather(
            _do_overlap(), _do_strategy(), _do_competitor(), _do_keywords(),
        )

        # Log results from all parallel calls
        overlap_risk = overlap_analysis.get("risk_level", "none") if isinstance(overlap_analysis, dict) else "unknown"
        gaps = competitor_insights.get("gaps", competitor_insights.get("differentiation_angles", []))
        kw_total = keyword_strategy.get("total_keywords", 0)
        neg_total = keyword_strategy.get("total_negatives", 0)
        blog.step_end(
            f"Overlap risk: {overlap_risk} | Strategy synthesized | {len(gaps)} competitor gaps | {kw_total} keywords + {neg_total} negatives",
            extra={
                "overlap_risk": overlap_risk,
                "competitor_gaps": gaps[:5],
                "total_keywords": kw_total,
                "total_negatives": neg_total,
                "has_playbook": playbook is not None,
                "learnings_count": len(learnings),
            },
        )

        # ══════════════════════════════════════════════════════════════════
        #  PHASE 4: Budget, Bidding & Schedule  (needs strategy + competitor results)
        # ══════════════════════════════════════════════════════════════════
        blog.step_start("Budget, Bidding & Schedule", f"Calculating optimal budget and bidding for {campaign_type}")
        bbs = await self._recommend_budget_bidding_schedule_ai(
            industry=industry, intent=intent, profile=business_profile,
            campaign_type=campaign_type, competitor_insights=competitor_insights,
            strategy_insights=strategy_insights,
        )
        budget = bbs.get("budget", {})
        bid_strategy = bbs.get("bidding", {})
        scheduling = bbs.get("schedule", {})
        device_bids = bbs.get("device_bids", {})
        blog.step_end(
            f"Budget: ${budget.get('daily_usd', 0)}/day | Bidding: {bid_strategy.get('strategy', 'N/A')} | Mobile bid adj: {device_bids.get('mobile_bid_adj', 0)}%",
            extra={"daily_usd": budget.get("daily_usd"), "bidding_strategy": bid_strategy.get("strategy"), "schedule": scheduling},
        )

        # ══════════════════════════════════════════════════════════════════
        #  PHASE 5: Build Campaign Draft  (route by campaign type)
        # ══════════════════════════════════════════════════════════════════
        blog.step_start("Campaign Draft Build", f"Building {campaign_type} campaign structure with AI-generated ad copy")
        build_args = dict(
            intent=intent,
            campaign_type=campaign_type,
            business_profile=business_profile,
            existing_campaigns=existing,
            playbook=playbook,
            learnings=learnings,
            keyword_strategy=keyword_strategy,
            bid_strategy=bid_strategy,
            budget=budget,
            scheduling=scheduling,
            device_bids=device_bids,
            competitor_insights=competitor_insights,
            google_customer_id=google_customer_id,
        )

        if campaign_type == "CALL":
            draft = await self._build_call_campaign_draft(**build_args)
        elif campaign_type == "PERFORMANCE_MAX":
            draft = await self._build_pmax_campaign_draft(**build_args)
        elif campaign_type == "DISPLAY":
            draft = await self._build_display_campaign_draft(**build_args)
        else:
            draft = await self._build_campaign_draft(**build_args)

        if campaign_type == "PERFORMANCE_MAX":
            ag_count = len(draft.get("asset_groups", []))
            blog.step_end(
                f"Built {ag_count} asset group(s) with AI-generated text assets + audience signals",
                extra={"asset_groups": ag_count},
            )
        else:
            ag_count = len(draft.get("ad_groups", []))
            kw_count = sum(len(ag.get("keywords", [])) for ag in draft.get("ad_groups", []))
            ad_count = sum(len(ag.get("ads", [])) for ag in draft.get("ad_groups", []))
            ad_type_label = {"CALL": "Call-Only", "DISPLAY": "Responsive Display"}.get(campaign_type, "RSA")
            blog.step_end(
                f"Built {ag_count} ad group(s), {kw_count} keywords, {ad_count} {ad_type_label} ad(s) — all AI-generated",
                extra={"ad_groups": ag_count, "keywords": kw_count, "ads": ad_count, "ad_format": ad_type_label},
            )

        # ══════════════════════════════════════════════════════════════════
        #  PHASE 6: Compliance Validation + Auto-Heal (1 round, skip if already good)
        # ══════════════════════════════════════════════════════════════════
        blog.step_start("Google Compliance Check", "Validating against Google Ads maximum standards + auto-healing issues")
        from app.services.campaign_compliance import CampaignComplianceEngine
        compliance = CampaignComplianceEngine()
        draft, compliance_report = await compliance.validate_and_heal(draft, max_rounds=1)
        healed = draft.get("compliance", {}).get("auto_healed", False)
        blog.step_end(
            f"Score: {compliance_report['score']}/100 ({compliance_report['grade']}) | "
            f"Issues: {compliance_report['critical']} critical, {compliance_report['warnings']} warnings | "
            f"Auto-healed: {'yes' if healed else 'no'}",
            extra={
                "score": compliance_report["score"],
                "grade": compliance_report["grade"],
                "critical": compliance_report["critical"],
                "warnings": compliance_report["warnings"],
                "auto_healed": healed,
            },
        )

        logger.info(
            "Campaign compliance check complete",
            score=compliance_report["score"],
            grade=compliance_report["grade"],
            issues=compliance_report["total_issues"],
            critical=compliance_report["critical"],
        )

        # --- Extensions Summary ---
        extensions = draft.get("extensions", {})
        ext_sl = len(extensions.get("sitelinks", []))
        ext_co = len(extensions.get("callouts", []))
        ext_sn = len(extensions.get("structured_snippets", []))
        blog.step_start("Extensions Summary", "Reviewing sitelinks, callouts, structured snippets")
        blog.step_end(
            f"{ext_sl} sitelinks, {ext_co} callouts, {ext_sn} structured snippets",
            extra={"sitelinks": ext_sl, "callouts": ext_co, "structured_snippets": ext_sn},
        )

        # --- Final: Package everything ---
        blog.step_start("Final Package", "Assembling campaign draft with all AI analysis")
        blog.step_end(f"Campaign \"{draft.get('campaign', {}).get('name', 'N/A')}\" ready for review")

        # Inject AI analysis + builder log into draft
        draft["ai_analysis"] = {
            "intent": {k: v for k, v in intent.items() if k != "_ai_generated"},
            "overlap_analysis": overlap_analysis,
            "strategy_insights": strategy_insights,
            "competitor_insights": competitor_insights,
            "keyword_rationale": keyword_strategy.get("keyword_rationale"),
            "compliance": compliance_report,
        }
        draft["builder_log"] = blog.to_dict()
        return draft

    async def generate_from_prompt_streaming(
        self,
        prompt: str,
        business_profile: BusinessProfile,
        google_customer_id: Optional[str] = None,
    ):
        """
        Async generator that yields progress events during campaign generation.
        ALL steps are AI-powered via OpenAI with rule-based fallbacks.
        Each yield is a dict: {"step": str, "status": str, "message": str, "detail": any}
        The final yield has step="complete" and detail=full draft.
        """
        industry = (business_profile.industry_classification or "general").lower()

        # ── Step 1: AI Intent Parsing ──
        yield {"step": "parse_intent", "status": "running", "message": "🤖 AI is analyzing your prompt — parsing services, locations, urgency, and campaign goal..."}
        intent = await self._parse_intent_ai(prompt, business_profile)
        campaign_type = intent.get("campaign_type") or self._determine_campaign_type(intent, business_profile)
        ai_tag = " (AI)" if intent.get("_ai_generated") else ""
        yield {
            "step": "parse_intent", "status": "done",
            "message": f"Intent parsed{ai_tag} — {campaign_type} campaign for {', '.join(intent.get('services', [])[:3])}",
            "detail": {
                "services": intent.get("services", []),
                "locations": intent.get("locations", []),
                "urgency": intent.get("urgency"),
                "goal": intent.get("goal"),
                "campaign_type": campaign_type,
                "campaign_type_reasoning": intent.get("campaign_type_reasoning"),
                "target_audience": intent.get("target_audience"),
                "seasonal_context": intent.get("seasonal_context"),
                "ai_powered": intent.get("_ai_generated", False),
            },
        }

        # ── Step 2: AI Campaign Overlap Analysis ──
        yield {"step": "existing_campaigns", "status": "running", "message": "🤖 AI is checking existing campaigns for overlap and cannibalization..."}
        existing = await self._get_existing_campaigns()
        overlap_analysis = await self._analyze_overlap_ai(existing, intent)
        ai_tag = " (AI)" if overlap_analysis.get("_ai_generated") else ""
        yield {
            "step": "existing_campaigns", "status": "done",
            "message": f"Overlap analysis{ai_tag} — {overlap_analysis.get('overlap_severity', 'none')} overlap across {len(existing)} campaigns",
            "detail": {
                "count": len(existing),
                "names": [c["name"] for c in existing[:5]],
                "overlap": overlap_analysis,
                "ai_powered": overlap_analysis.get("_ai_generated", False),
            },
        }

        # ── Step 3: AI Strategy Synthesis (Playbook + Learnings) ──
        yield {"step": "research", "status": "running", "message": f"🤖 AI is synthesizing industry strategy for '{industry}' — analyzing playbooks and cross-tenant learnings..."}
        playbook = await self._get_playbook(industry, intent.get("goal"))
        learnings = await self._get_relevant_learnings(industry)
        strategy_insights = await self._synthesize_strategy_ai(industry, intent, playbook, learnings, business_profile)
        ai_tag = " (AI)" if strategy_insights.get("_ai_generated") else ""
        yield {
            "step": "research", "status": "done",
            "message": f"Strategy synthesized{ai_tag} — {len(strategy_insights.get('key_insights', []))} insights, {len(strategy_insights.get('mistakes_to_avoid', []))} pitfalls identified",
            "detail": {
                "has_playbook": playbook is not None,
                "learnings_count": len(learnings),
                "strategy": strategy_insights,
                "ai_powered": strategy_insights.get("_ai_generated", False),
            },
        }

        # ── Step 4: AI Competitor Intelligence ──
        yield {"step": "competitors", "status": "running", "message": "🤖 AI is analyzing competitors — finding gaps, weaknesses, and displacement tactics..."}
        competitors = await self._get_competitor_intelligence()
        competitor_insights = await self._analyze_competitors_ai(competitors, intent, industry, business_profile)
        ai_tag = " (AI)" if competitor_insights.get("_ai_generated") else ""
        gaps_count = len(competitor_insights.get("gaps", competitor_insights.get("differentiation_angles", [])))
        yield {
            "step": "competitors", "status": "done",
            "message": f"Competitive analysis{ai_tag} — {len(competitors)} competitors, {gaps_count} gaps to exploit",
            "detail": {
                "competitor_count": len(competitors),
                "common_themes": competitor_insights.get("common_themes", [])[:5],
                "gaps": competitor_insights.get("gaps", [])[:4],
                "displacement_tactics": competitor_insights.get("displacement_tactics", [])[:3],
                "weaknesses": competitor_insights.get("weaknesses", [])[:3],
                "ai_powered": competitor_insights.get("_ai_generated", False),
            },
        }

        # ── Step 5: AI Keyword Strategy ──
        yield {"step": "keywords", "status": "running", "message": "🤖 AI is building tiered keyword strategy — emergency, high-intent, local, and negative keywords..."}
        keyword_strategy = await self._build_keyword_strategy_ai(intent, industry, learnings, playbook, business_profile)
        ai_tag = " (AI)" if keyword_strategy.get("_ai_generated") else ""
        yield {
            "step": "keywords", "status": "done",
            "message": f"Keyword strategy{ai_tag} — {keyword_strategy['total_keywords']} keywords across {len(keyword_strategy.get('tiers', {}))} tiers + {keyword_strategy['total_negatives']} negatives",
            "detail": {
                "tiers": keyword_strategy.get("tiers", {}),
                "total_keywords": keyword_strategy["total_keywords"],
                "total_negatives": keyword_strategy["total_negatives"],
                "keyword_rationale": keyword_strategy.get("keyword_rationale"),
                "ai_powered": keyword_strategy.get("_ai_generated", False),
            },
        }

        # ── Step 6: AI Budget, Bidding & Schedule ──
        yield {"step": "strategy", "status": "running", "message": "🤖 AI is calculating optimal budget, bidding strategy, ad schedule, and device bids..."}
        bbs = await self._recommend_budget_bidding_schedule_ai(
            industry=industry,
            intent=intent,
            profile=business_profile,
            campaign_type=campaign_type,
            competitor_insights=competitor_insights,
            strategy_insights=strategy_insights,
        )
        ai_tag = " (AI)" if bbs.get("_ai_generated") else ""
        budget = bbs.get("budget", {})
        bid_strategy = bbs.get("bidding", {})
        scheduling = bbs.get("schedule", {})
        device_bids = bbs.get("device_bids", {})
        yield {
            "step": "strategy", "status": "done",
            "message": f"Budget & bidding{ai_tag} — ${budget.get('daily_usd', 0)}/day • {bid_strategy.get('strategy', 'N/A')} • {'24/7' if scheduling.get('all_day') else 'Scheduled'}",
            "detail": {
                "budget": budget,
                "bidding": bid_strategy,
                "schedule": scheduling,
                "device_bids": device_bids,
                "estimated_cpc": bbs.get("estimated_cpc"),
                "estimated_monthly_clicks": bbs.get("estimated_monthly_clicks"),
                "estimated_monthly_conversions": bbs.get("estimated_monthly_conversions"),
                "ai_powered": bbs.get("_ai_generated", False),
            },
        }

        # ── Step 7: AI Ad Copy Generation ──
        yield {"step": "ai_copy", "status": "running", "message": "🤖 AI is generating expert Google Ads RSA copy with pinning strategy..."}
        draft = await self._build_campaign_draft(
            intent=intent,
            campaign_type=campaign_type,
            business_profile=business_profile,
            existing_campaigns=existing,
            playbook=playbook,
            learnings=learnings,
            keyword_strategy=keyword_strategy,
            bid_strategy=bid_strategy,
            budget=budget,
            scheduling=scheduling,
            device_bids=device_bids,
            competitor_insights=competitor_insights,
            google_customer_id=google_customer_id,
        )

        # Inject AI analysis results into draft for frontend display
        draft["ai_analysis"] = {
            "intent": {k: v for k, v in intent.items() if k != "_ai_generated"},
            "overlap_analysis": overlap_analysis,
            "strategy_insights": strategy_insights,
            "competitor_insights": competitor_insights,
            "keyword_rationale": keyword_strategy.get("keyword_rationale"),
            "budget_reasoning": budget.get("reasoning"),
            "bidding_reasoning": bid_strategy.get("reasoning"),
            "schedule_reasoning": scheduling.get("reasoning"),
        }

        # Emit per-ad-group AI details
        for ag in draft.get("ad_groups", []):
            for ad in ag.get("ads", []):
                generated_by = ad.get("generated_by", "template")
                ai_prompt = ad.get("ai_prompt")
                ai_raw = ad.get("ai_raw_response")
                yield {
                    "step": "ai_copy_result", "status": "done",
                    "message": f"Ad group '{ag['name']}' — copy generated by {generated_by}",
                    "detail": {
                        "ad_group": ag["name"],
                        "generated_by": generated_by,
                        "headlines_count": len(ad.get("headlines", [])),
                        "descriptions_count": len(ad.get("descriptions", [])),
                        "ai_prompt": ai_prompt,
                        "ai_raw_response": ai_raw,
                    },
                }

        yield {
            "step": "ai_copy", "status": "done",
            "message": f"Ad copy ready for {len(draft.get('ad_groups', []))} ad groups",
        }

        # ── Step 8: Extensions ──
        yield {"step": "extensions", "status": "done", "message": "Extensions generated (sitelinks, callouts, structured snippets)"}

        # ── Final: Complete ──
        yield {
            "step": "complete", "status": "done",
            "message": "🎉 Campaign draft ready for review! All steps powered by AI.",
            "detail": draft,
        }

    async def _get_competitor_intelligence(self) -> List[Dict]:
        result = await self.db.execute(
            select(CompetitorProfile).where(CompetitorProfile.tenant_id == self.tenant_id)
        )
        profiles = result.scalars().all()
        return [
            {
                "name": c.name,
                "domain": c.domain,
                "messaging_themes": c.messaging_themes_json if isinstance(c.messaging_themes_json, list) else [],
                "landing_pages": c.landing_pages_json if isinstance(c.landing_pages_json, list) else [],
            }
            for c in profiles
        ]

    def _extract_competitor_insights(self, competitors: List[Dict], intent: Dict) -> Dict:
        if not competitors:
            return {"gaps": [], "competitor_themes": [], "differentiation_angles": []}

        all_themes = []
        for c in competitors:
            all_themes.extend(c.get("messaging_themes", []))

        theme_counts: Dict[str, int] = {}
        for t in all_themes:
            theme_counts[t] = theme_counts.get(t, 0) + 1

        common_themes = [t for t, n in sorted(theme_counts.items(), key=lambda x: -x[1])]

        differentiation_angles = []
        all_angles = ["same-day guarantee", "upfront pricing", "background-checked techs",
                      "veteran-owned", "5-star rated", "no hidden fees", "senior discounts",
                      "financing available", "warranty included", "real-time tracking"]
        for angle in all_angles:
            if not any(angle.lower() in t.lower() for t in common_themes):
                differentiation_angles.append(angle)

        return {
            "competitor_count": len(competitors),
            "competitor_names": [c["name"] for c in competitors if c.get("name")],
            "common_themes": common_themes[:5],
            "differentiation_angles": differentiation_angles[:4],
            "gaps": [a for a in differentiation_angles[:3]],
        }

    def _calculate_budget(self, profile: BusinessProfile, playbook: Optional[Dict], intent: Dict) -> Dict:
        constraints = profile.constraints_json or {}
        monthly = constraints.get("monthly_budget", 0)
        if monthly:
            daily_micros = int(monthly / 30 * 1_000_000)
        elif playbook and "default_budget_micros" in playbook:
            daily_micros = playbook["default_budget_micros"]
        else:
            daily_micros = 50_000_000

        if intent.get("urgency") == "high":
            daily_micros = int(daily_micros * 1.2)

        return {
            "daily_micros": daily_micros,
            "daily_usd": round(daily_micros / 1_000_000, 2),
            "monthly_estimate_usd": round(daily_micros / 1_000_000 * 30, 2),
            "reasoning": f"Based on {'tenant monthly budget setting' if monthly else 'industry playbook default'}. "
                         f"{'Increased 20% for high-urgency campaign.' if intent.get('urgency') == 'high' else ''}",
        }

    def _determine_bid_strategy(self, campaign_type: str, intent: Dict, profile: BusinessProfile) -> Dict:
        goal = profile.primary_conversion_goal or "calls"
        if campaign_type in ("CALL", "SEARCH") and goal == "calls":
            strategy = "MAXIMIZE_CONVERSIONS"
            reasoning = "Maximize Conversions lets Google find the most likely callers within your budget."
        elif campaign_type == "PERFORMANCE_MAX":
            strategy = "MAXIMIZE_CONVERSION_VALUE"
            reasoning = "Maximize Conversion Value drives the highest-value leads across all channels."
        elif intent.get("goal") == "leads":
            strategy = "TARGET_CPA"
            reasoning = "Target CPA gives the AI a cost-per-lead target so it can efficiently scale volume."
        else:
            strategy = "MAXIMIZE_CONVERSIONS"
            reasoning = "Maximize Conversions with smart bidding to optimize for conversion actions."

        return {"strategy": strategy, "reasoning": reasoning}

    def _build_schedule(self, industry: str, intent: Dict) -> Dict:
        high_urgency_industries = ["locksmith", "plumbing", "hvac", "auto_repair", "pest_control"]
        if industry in high_urgency_industries or intent.get("urgency") == "high":
            return {
                "all_day": True,
                "reasoning": f"{industry.title()} emergencies happen 24/7. Running all hours captures distressed searchers willing to pay premium rates.",
                "peak_hours_note": "Consider +20% bid adjustment 7am-9pm when call volume is highest.",
            }
        return {
            "all_day": False,
            "hours": {"start": "07:00", "end": "21:00"},
            "days": ["MON", "TUE", "WED", "THU", "FRI", "SAT"],
            "reasoning": "Running 7am-9pm Mon-Sat captures high-intent business hours while avoiding wasted spend overnight.",
        }

    def _build_device_bids(self, industry: str, intent: Dict) -> Dict:
        mobile_heavy = ["locksmith", "plumbing", "hvac", "auto_repair", "towing"]
        if industry in mobile_heavy or intent.get("urgency") == "high":
            return {
                "mobile_bid_adj": 30,
                "desktop_bid_adj": 0,
                "tablet_bid_adj": -20,
                "reasoning": "Emergency searches are 70-80% mobile. +30% mobile bid ensures top placement when someone is stranded or in crisis.",
            }
        return {
            "mobile_bid_adj": 10,
            "desktop_bid_adj": 0,
            "tablet_bid_adj": -10,
            "reasoning": "Slight mobile preference as most local searches happen on mobile.",
        }

    def _parse_intent(self, prompt: str, profile: BusinessProfile) -> Dict[str, Any]:
        prompt_lower = prompt.lower()
        intent = {
            "raw_prompt": prompt,
            "services": [],
            "locations": [],
            "offers": [],
            "usps": [],
            "objective": profile.primary_conversion_goal or "calls",
            "urgency": "normal",
            "goal": "leads",
        }

        services = profile.services_json if isinstance(profile.services_json, list) else (profile.services_json or {}).get("list", [])
        for svc in services:
            svc_name = svc if isinstance(svc, str) else svc.get("name", "")
            if svc_name and svc_name.lower() in prompt_lower:
                intent["services"].append(svc_name)
        if not intent["services"] and services:
            intent["services"] = [s if isinstance(s, str) else s.get("name", "") for s in services[:5]]

        locations = profile.locations_json if isinstance(profile.locations_json, list) else (profile.locations_json or {}).get("cities", [])
        for loc in locations:
            loc_name = loc if isinstance(loc, str) else loc.get("name", "")
            if loc_name and loc_name.lower() in prompt_lower:
                intent["locations"].append(loc_name)
        if not intent["locations"] and locations:
            intent["locations"] = [l if isinstance(l, str) else l.get("name", "") for l in locations[:5]]

        offers = profile.offers_json if isinstance(profile.offers_json, list) else (profile.offers_json or {}).get("list", [])
        intent["offers"] = [o if isinstance(o, str) else o.get("text", "") for o in offers[:3]]

        usps = profile.usp_json if isinstance(profile.usp_json, list) else (profile.usp_json or {}).get("list", [])
        intent["usps"] = [u if isinstance(u, str) else u.get("text", "") for u in usps[:5]]

        emergency_kws = ["emergency", "urgent", "24/7", "same day", "asap", "fast", "immediate", "now"]
        if any(kw in prompt_lower for kw in emergency_kws):
            intent["urgency"] = "high"

        if "remarketing" in prompt_lower or "retarget" in prompt_lower:
            intent["goal"] = "remarketing"
        elif "brand" in prompt_lower or "awareness" in prompt_lower:
            intent["goal"] = "awareness"
        elif "call" in prompt_lower or "phone" in prompt_lower:
            intent["goal"] = "calls"
        elif "form" in prompt_lower or "lead" in prompt_lower or "quote" in prompt_lower:
            intent["goal"] = "leads"

        return intent

    def _determine_campaign_type(self, intent: Dict, profile: BusinessProfile) -> str:
        if intent.get("goal") == "remarketing":
            return "REMARKETING"
        if intent.get("goal") == "awareness":
            return "PERFORMANCE_MAX"
        if intent.get("urgency") == "high" or profile.primary_conversion_goal == "calls":
            return "CALL"
        if profile.primary_conversion_goal in ("forms", "leads", "bookings"):
            return "SEARCH"
        return "SEARCH"

    # ══════════════════════════════════════════════════════════════════════
    #  Reusable OpenAI JSON helper
    # ══════════════════════════════════════════════════════════════════════

    async def _call_openai_json(self, system: str, user_prompt: str, temperature: float = 0.7, max_tokens: int = 2000, retries: int = 3) -> Optional[Dict]:
        """Call OpenAI and parse JSON response. Retries up to `retries` times with backoff."""
        if not settings.OPENAI_API_KEY:
            return None
        import asyncio
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        last_error = None
        for attempt in range(retries):
            try:
                resp = await client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = resp.choices[0].message.content
                if not content:
                    last_error = "Empty response"
                    continue
                return {"_raw": content, **json.loads(content)}
            except json.JSONDecodeError as e:
                last_error = f"JSON parse error: {e}"
                logger.warning("OpenAI returned invalid JSON, retrying", attempt=attempt + 1, error=str(e))
            except Exception as e:
                last_error = str(e)
                logger.warning("OpenAI call failed, retrying", attempt=attempt + 1, error=str(e))
            if attempt < retries - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
        logger.error("OpenAI call failed after all retries", retries=retries, last_error=last_error)
        return None

    # ══════════════════════════════════════════════════════════════════════
    #  Step 1: AI-Powered Intent Parsing
    # ══════════════════════════════════════════════════════════════════════

    async def _parse_intent_ai(self, prompt: str, profile: BusinessProfile) -> Dict[str, Any]:
        """Use GPT to deeply parse the user's prompt into structured campaign intent."""
        services = profile.services_json if isinstance(profile.services_json, list) else []
        svc_names = [s if isinstance(s, str) else s.get("name", "") for s in services]
        locations = profile.locations_json if isinstance(profile.locations_json, list) else []
        loc_names = [l if isinstance(l, str) else l.get("name", "") for l in locations]
        offers = profile.offers_json if isinstance(profile.offers_json, list) else []
        offer_texts = [o if isinstance(o, str) else o.get("text", "") for o in offers]
        usps = profile.usp_json if isinstance(profile.usp_json, list) else []
        usp_texts = [u if isinstance(u, str) else u.get("text", "") for u in usps]
        industry = (profile.industry_classification or "general").lower()

        system = """You are a senior Google Ads strategist. Your job is to parse a business owner's
natural-language campaign request into a precise, structured campaign intent.
You deeply understand search intent, local service marketing, and Google Ads campaign types.
You respond ONLY with valid JSON."""

        user_msg = f"""Parse this campaign request into structured intent.

USER PROMPT: "{prompt}"

BUSINESS CONTEXT:
- Industry: {industry}
- Services offered: {json.dumps(svc_names[:10])}
- Service locations: {json.dumps(loc_names[:10])}
- Active offers: {json.dumps(offer_texts[:5])}
- USPs: {json.dumps(usp_texts[:5])}
- Primary conversion goal: {profile.primary_conversion_goal or 'calls'}

INSTRUCTIONS:
1. Identify which SPECIFIC services from the business's list the user wants to advertise.
   If the prompt is vague, pick the top 3-5 most relevant services.
2. Identify target locations. If not specified, use the business's service areas.
3. Determine urgency level: "high" for emergency/24-7/ASAP requests, "normal" otherwise.
4. Determine the campaign goal: "calls", "leads", "awareness", "remarketing", or "bookings".
5. Identify any seasonal or time-sensitive context.
6. Extract any specific requirements or constraints the user mentioned.
7. Suggest the best campaign type: "SEARCH", "CALL", "PERFORMANCE_MAX", or "REMARKETING".
8. Explain your reasoning for campaign type selection.

Return JSON:
{{
  "services": ["service1", "service2", ...],
  "locations": ["city1", "city2", ...],
  "offers": ["offer1", ...],
  "usps": ["usp1", ...],
  "urgency": "high" or "normal",
  "goal": "calls" | "leads" | "awareness" | "remarketing" | "bookings",
  "objective": "calls" | "forms" | "leads",
  "campaign_type": "SEARCH" | "CALL" | "PERFORMANCE_MAX" | "REMARKETING",
  "campaign_type_reasoning": "Why this campaign type...",
  "seasonal_context": "any seasonal notes or null",
  "user_constraints": "any specific requirements or null",
  "target_audience": "description of the ideal searcher for these ads",
  "raw_prompt": "{prompt}"
}}"""

        result = await self._call_openai_json(system, user_msg, temperature=0.4)
        if result:
            result.pop("_raw", None)
            # Ensure required fields
            result.setdefault("services", svc_names[:5])
            result.setdefault("locations", loc_names[:5])
            result.setdefault("offers", offer_texts[:3])
            result.setdefault("usps", usp_texts[:5])
            result.setdefault("urgency", "normal")
            result.setdefault("goal", "leads")
            result.setdefault("objective", profile.primary_conversion_goal or "calls")
            result.setdefault("raw_prompt", prompt)
            result["_ai_generated"] = True
            return result

        # Retry with simpler prompt before falling back to rules
        logger.warning("AI intent parsing failed — retrying with simpler prompt")
        simple_system = "You are a Google Ads strategist. Parse the campaign request. Respond ONLY with valid JSON."
        simple_msg = f"""Parse this into campaign intent:
Prompt: "{prompt}"
Business services: {json.dumps(svc_names[:5])}
Business locations: {json.dumps(loc_names[:5])}

Return JSON: {{"services": [...], "locations": [...], "offers": [], "usps": [], "urgency": "high"|"normal", "goal": "calls"|"leads"|"awareness", "objective": "calls", "campaign_type": "SEARCH"|"CALL", "campaign_type_reasoning": "...", "raw_prompt": "{prompt}"}}"""
        retry = await self._call_openai_json(simple_system, simple_msg, temperature=0.3, retries=2)
        if retry:
            retry.pop("_raw", None)
            retry.setdefault("services", svc_names[:5])
            retry.setdefault("locations", loc_names[:5])
            retry.setdefault("raw_prompt", prompt)
            retry["_ai_generated"] = True
            return retry

        # Absolute last resort — rule-based (no API key or total AI failure)
        logger.error("All AI intent parsing attempts failed — using emergency rule-based fallback")
        return self._parse_intent(prompt, profile)

    # ══════════════════════════════════════════════════════════════════════
    #  Step 2: AI-Powered Campaign Overlap Analysis
    # ══════════════════════════════════════════════════════════════════════

    async def _analyze_overlap_ai(self, existing: List[Dict], intent: Dict) -> Dict:
        """Use GPT to analyze overlap between new campaign intent and existing campaigns."""
        if not existing:
            return {"has_overlap": False, "recommendation": "No existing campaigns — safe to create.", "overlapping_campaigns": []}

        system = """You are a Google Ads account strategist. Analyze whether a proposed new campaign
overlaps with existing campaigns. Overlapping campaigns cannibalize each other's traffic
and drive up CPCs. You respond ONLY with valid JSON."""

        user_msg = f"""EXISTING CAMPAIGNS in this account:
{json.dumps(existing[:20], default=str)}

PROPOSED NEW CAMPAIGN INTENT:
- Services: {json.dumps(intent.get('services', []))}
- Locations: {json.dumps(intent.get('locations', []))}
- Goal: {intent.get('goal')}
- Urgency: {intent.get('urgency')}

Analyze:
1. Does the new campaign overlap with any existing ones? (same services + locations)
2. If yes, which campaigns overlap and how?
3. What's your recommendation? (proceed, modify, or consolidate)
4. If modifying, what changes would prevent cannibalization?

Return JSON:
{{
  "has_overlap": true/false,
  "overlapping_campaigns": ["campaign name 1", ...],
  "overlap_severity": "none" | "low" | "medium" | "high",
  "recommendation": "Your recommendation...",
  "suggested_modifications": "How to differentiate if overlap exists, or null"
}}"""

        result = await self._call_openai_json(system, user_msg, temperature=0.3)
        if result:
            result.pop("_raw", None)
            result["_ai_generated"] = True
            return result

        # Retry with simpler prompt
        logger.warning("AI overlap analysis failed — retrying with simpler prompt")
        simple_system = "You are a Google Ads account strategist. Respond ONLY with valid JSON."
        simple_msg = f"""Do these existing campaigns overlap with a new campaign for {json.dumps(intent.get('services', [])[:3])}?
Existing: {json.dumps([c['name'] for c in existing[:10]])}
Return JSON: {{"has_overlap": true/false, "overlap_severity": "none"|"low"|"medium"|"high", "recommendation": "...", "overlapping_campaigns": [...]}}"""
        retry = await self._call_openai_json(simple_system, simple_msg, temperature=0.3, retries=2)
        if retry:
            retry.pop("_raw", None)
            retry["_ai_generated"] = True
            return retry

        return {"has_overlap": False, "recommendation": f"Found {len(existing)} existing campaigns.", "overlapping_campaigns": []}

    # ══════════════════════════════════════════════════════════════════════
    #  Step 3: AI-Powered Strategy Synthesis (Playbook + Learnings)
    # ══════════════════════════════════════════════════════════════════════

    async def _synthesize_strategy_ai(self, industry: str, intent: Dict, playbook: Optional[Dict], learnings: List[Dict], profile: BusinessProfile) -> Dict:
        """Use GPT to synthesize industry playbook and cross-tenant learnings into actionable strategy."""
        system = """You are an elite Google Ads strategist who has managed $200M+ in ad spend for local
service businesses. You synthesize industry data, proven patterns, and learnings from
similar businesses into a cohesive campaign strategy. You respond ONLY with valid JSON."""

        playbook_summary = json.dumps(playbook, default=str)[:1500] if playbook else "No industry playbook available."
        learnings_summary = json.dumps(learnings[:10], default=str)[:1500] if learnings else "No cross-tenant learnings available."
        biz_name = await self._get_business_name()

        user_msg = f"""INDUSTRY: {industry}
BUSINESS: {biz_name}
CONVERSION GOAL: {profile.primary_conversion_goal or 'calls'}
SERVICES: {json.dumps(intent.get('services', [])[:5])}
LOCATIONS: {json.dumps(intent.get('locations', [])[:5])}
URGENCY: {intent.get('urgency', 'normal')}

INDUSTRY PLAYBOOK DATA:
{playbook_summary}

CROSS-TENANT LEARNINGS (patterns from similar businesses):
{learnings_summary}

Based on all this data, create a comprehensive campaign strategy:

1. What campaign structure works best for this {industry} business?
2. What ad messaging themes historically perform best?
3. What bidding strategy and budget allocation is optimal?
4. What time-of-day and day-of-week patterns should we target?
5. What are the top 3 mistakes to AVOID for {industry} Google Ads?
6. What is the expected CPC range and conversion rate for this industry?

Return JSON:
{{
  "recommended_structure": "Campaign structure recommendation...",
  "top_messaging_themes": ["theme1", "theme2", ...],
  "bidding_recommendation": "Which strategy and why...",
  "budget_recommendation": "Budget guidance...",
  "scheduling_insights": "When to run ads...",
  "mistakes_to_avoid": ["mistake1", "mistake2", "mistake3"],
  "expected_cpc_range": "$X - $Y",
  "expected_conversion_rate": "X% - Y%",
  "key_insights": ["insight1", "insight2", ...],
  "confidence_level": "high" | "medium" | "low"
}}"""

        result = await self._call_openai_json(system, user_msg, temperature=0.5)
        if result:
            result.pop("_raw", None)
            result["has_playbook"] = playbook is not None
            result["learnings_count"] = len(learnings)
            result["_ai_generated"] = True
            return result

        # Retry with simpler prompt
        logger.warning("AI strategy synthesis failed — retrying with simpler prompt")
        simple_system = "You are a Google Ads strategist. Respond ONLY with valid JSON."
        simple_msg = f"""Create a campaign strategy for a {industry} business.
Services: {json.dumps(intent.get('services', [])[:3])}
Goal: {intent.get('goal', 'leads')}

Return JSON: {{"recommended_structure": "...", "top_messaging_themes": [...], "bidding_recommendation": "...", "mistakes_to_avoid": [...], "key_insights": [...], "confidence_level": "medium"}}"""
        retry = await self._call_openai_json(simple_system, simple_msg, temperature=0.4, retries=2)
        if retry:
            retry.pop("_raw", None)
            retry["has_playbook"] = playbook is not None
            retry["learnings_count"] = len(learnings)
            retry["_ai_generated"] = True
            return retry

        # Absolute last resort — static (no API key or total AI failure)
        logger.error("All AI strategy synthesis failed — using minimal static fallback")
        return {
            "has_playbook": playbook is not None,
            "learnings_count": len(learnings),
            "key_insights": [],
            "recommended_structure": "Standard SKAG structure",
        }

    # ══════════════════════════════════════════════════════════════════════
    #  Step 4: AI-Powered Competitor Analysis
    # ══════════════════════════════════════════════════════════════════════

    async def _analyze_competitors_ai(self, competitors: List[Dict], intent: Dict, industry: str, profile: BusinessProfile) -> Dict:
        """Use GPT to deeply analyze competitors and find displacement tactics."""
        usps = profile.usp_json if isinstance(profile.usp_json, list) else []
        usp_texts = [u if isinstance(u, str) else u.get("text", "") for u in usps][:5]

        system = """You are a competitive intelligence analyst specializing in Google Ads for local
service businesses. You find gaps in competitor messaging that can be exploited for
higher CTR and lower CPC. You respond ONLY with valid JSON."""

        comp_data = json.dumps(competitors[:10], default=str)[:2000] if competitors else "No competitor data available."

        user_msg = f"""INDUSTRY: {industry}
OUR SERVICES: {json.dumps(intent.get('services', [])[:5])}
OUR LOCATIONS: {json.dumps(intent.get('locations', [])[:5])}
OUR USPs: {json.dumps(usp_texts)}

COMPETITOR DATA:
{comp_data}

Perform deep competitive analysis:

1. What messaging themes do competitors use most? (common_themes)
2. What are their WEAKNESSES — things they claim poorly or don't mention at all?
3. What differentiation angles can WE use that they DON'T? (based on our USPs)
4. What specific ad copy angles would DISPLACE them in the SERP?
5. What trust signals are they missing that we could emphasize?
6. Estimate their likely CPC bids and budget levels.

Return JSON:
{{
  "competitor_count": {len(competitors)},
  "competitor_names": ["name1", ...],
  "common_themes": ["theme1", "theme2", ...],
  "weaknesses": ["weakness1", "weakness2", ...],
  "gaps": ["gap1", "gap2", ...],
  "differentiation_angles": ["angle1", "angle2", ...],
  "displacement_tactics": ["tactic1", "tactic2", ...],
  "missing_trust_signals": ["signal1", ...],
  "estimated_competitor_cpc": "$X - $Y",
  "recommended_counter_messaging": ["message1", "message2", ...],
  "confidence_level": "high" | "medium" | "low"
}}"""

        result = await self._call_openai_json(system, user_msg, temperature=0.5)
        if result:
            result.pop("_raw", None)
            result["_ai_generated"] = True
            return result

        # Retry with simpler prompt
        logger.warning("AI competitor analysis failed — retrying with simpler prompt")
        simple_system = "You are a Google Ads competitor analyst. Respond ONLY with valid JSON."
        simple_msg = f"""Analyze competitors for a {industry} business offering {json.dumps(intent.get('services', [])[:3])}.
Competitor data: {json.dumps(competitors[:5], default=str)[:1000] if competitors else 'No data'}
Return JSON: {{"common_themes": [...], "weaknesses": [...], "gaps": [...], "differentiation_angles": [...], "displacement_tactics": [...], "confidence_level": "medium"}}"""
        retry = await self._call_openai_json(simple_system, simple_msg, temperature=0.4, retries=2)
        if retry:
            retry.pop("_raw", None)
            retry["_ai_generated"] = True
            return retry

        # Emergency fallback — rule-based (no API key or total AI failure)
        logger.error("All AI competitor analysis failed — using emergency rule-based fallback")
        return self._extract_competitor_insights(competitors, intent)

    # ══════════════════════════════════════════════════════════════════════
    #  Step 5: AI-Powered Keyword Strategy
    # ══════════════════════════════════════════════════════════════════════

    async def _build_keyword_strategy_ai(self, intent: Dict, industry: str, learnings: List[Dict], playbook: Optional[Dict], profile: BusinessProfile) -> Dict:
        """Use GPT to generate expert-level tiered keyword strategy."""
        system = """You are a Google Ads keyword research expert with 15+ years of experience.
You build SKAG-style tightly themed keyword lists optimized for Quality Score.
You understand match types (EXACT, PHRASE, BROAD), negative keyword strategy,
and tiered bidding by intent level. You respond ONLY with valid JSON."""

        services = intent.get("services", [])[:5]
        locations = intent.get("locations", [])[:5]
        urgency = intent.get("urgency", "normal")
        learnings_summary = json.dumps(learnings[:5], default=str)[:800] if learnings else "None"

        raw_prompt = intent.get("raw_prompt", "")

        user_msg = f"""Build a comprehensive Google Ads keyword strategy.

INDUSTRY: {industry}
SERVICES TO ADVERTISE: {json.dumps(services)}
TARGET LOCATIONS: {json.dumps(locations)}
URGENCY LEVEL: {urgency}
CONVERSION GOAL: {intent.get('goal', 'leads')}
USER'S ORIGINAL PROMPT: "{raw_prompt}"

CROSS-TENANT LEARNINGS (what works for similar businesses):
{learnings_summary}

CRITICAL RULE — KEYWORD SEGMENTATION BY AD GROUP:
Each service listed above will become its own ad group. Keywords MUST be unique
per service. NO keyword should appear in more than one service's list.
This prevents internal keyword competition and improves Quality Score.

For each service, generate keywords across these tiers:

TIER 1 — EMERGENCY (highest intent, highest bid):
  Searchers in immediate need. "emergency [service]", "24/7 [service]", "[problem] help now"
  Match type: EXACT. Bid adjustment: +30%.
  Generate 6-10 keywords PER SERVICE, unique to that service's theme.

TIER 2 — HIGH COMMERCIAL INTENT:
  Ready to buy/hire. "[service] near me", "[service] service", "hire [service]"
  Match type: EXACT + add "near me" variants.
  Generate 8-12 keywords PER SERVICE, unique to that service.

TIER 3 — MEDIUM INTENT:
  Researching options. "best [service]", "affordable [service]", "[service] cost"
  Match type: PHRASE.
  Generate 5-8 keywords PER SERVICE.

TIER 4 — LOCAL (geo-modified):
  Location-specific. "[service] in [city]", "[city] [service]"
  Match type: EXACT.
  Generate 3-5 keywords per service per location.

TIER 5 — SERVICE-SPECIFIC:
  Problem-specific keywords the searcher would actually type.
  Use the user's original prompt for clues about pain points and exact terminology.
  Example: if user mentions "no key detected" → include "jaguar no key detected fix"
  Match type: PHRASE.

NEGATIVES:
  Generate 20-30 negative keywords to block irrelevant traffic (shared across all ad groups).
  Include: DIY, jobs/careers, training/schools, free, complaints, tools/supplies.
  Also include industry-specific negatives.

Return JSON:
{{
  "keywords": [
    {{"text": "keyword", "match_type": "EXACT"|"PHRASE"|"BROAD", "tier": "emergency"|"high"|"medium"|"local"|"service", "bid_adj": "+30%"|null, "service": "exact service name from the list above"}},
    ...
  ],
  "negatives": [
    {{"text": "negative keyword", "match_type": "PHRASE"|"EXACT"}},
    ...
  ],
  "total_keywords": N,
  "total_negatives": N,
  "tiers": {{
    "emergency": N,
    "high": N,
    "medium": N,
    "local": N,
    "service": N
  }},
  "keyword_rationale": "Brief explanation of your keyword strategy and how keywords are segmented across ad groups"
}}

IMPORTANT: Every keyword object MUST have a "service" field set to exactly one of: {json.dumps(services)}.
Keywords must NOT overlap between services. Each ad group must have its own unique set."""

        result = await self._call_openai_json(system, user_msg, temperature=0.6, max_tokens=4000)
        if result:
            raw = result.pop("_raw", None)
            # Validate structure
            kws = result.get("keywords", [])
            negs = result.get("negatives", [])
            if isinstance(kws, list) and len(kws) >= 5:
                # Ensure proper structure for each keyword
                clean_kws = []
                for k in kws:
                    if isinstance(k, dict) and "text" in k:
                        k.setdefault("match_type", "PHRASE")
                        k.setdefault("tier", "medium")
                        clean_kws.append(k)
                clean_negs = []
                for n in negs:
                    if isinstance(n, dict) and "text" in n:
                        n.setdefault("match_type", "PHRASE")
                        clean_negs.append(n)
                    elif isinstance(n, str):
                        clean_negs.append({"text": n, "match_type": "PHRASE"})

                tiers = result.get("tiers", {})
                if not tiers:
                    tiers = {}
                    for k in clean_kws:
                        t = k.get("tier", "medium")
                        tiers[t] = tiers.get(t, 0) + 1

                result["keywords"] = clean_kws
                result["negatives"] = clean_negs
                result["total_keywords"] = len(clean_kws)
                result["total_negatives"] = len(clean_negs)
                result["tiers"] = tiers
                result["_ai_generated"] = True
                return result

        # Retry with simpler prompt
        logger.warning("AI keyword strategy failed — retrying with simpler prompt")
        simple_system = "You are a Google Ads keyword expert. Respond ONLY with valid JSON."
        simple_msg = f"""Generate keywords for a {industry} business.
Services: {json.dumps(services)}
Locations: {json.dumps(locations)}
User prompt: "{intent.get('raw_prompt', '')}"

CRITICAL: Each keyword MUST have a "service" field matching exactly one service above.
No keyword overlap between services.

Return JSON: {{"keywords": [{{"text": "...", "match_type": "EXACT"|"PHRASE", "tier": "high"|"medium"|"local"|"service", "service": "exact service name"}}], "negatives": [{{"text": "...", "match_type": "PHRASE"}}], "total_keywords": N, "total_negatives": N, "tiers": {{}}, "keyword_rationale": "..."}}"""
        retry = await self._call_openai_json(simple_system, simple_msg, temperature=0.5, max_tokens=3000, retries=2)
        if retry:
            raw = retry.pop("_raw", None)
            kws = retry.get("keywords", [])
            if isinstance(kws, list) and len(kws) >= 3:
                clean_kws = [k for k in kws if isinstance(k, dict) and "text" in k]
                for k in clean_kws:
                    k.setdefault("match_type", "PHRASE")
                    k.setdefault("tier", "medium")
                negs = retry.get("negatives", [])
                clean_negs = []
                for n in negs:
                    if isinstance(n, dict) and "text" in n:
                        clean_negs.append(n)
                    elif isinstance(n, str):
                        clean_negs.append({"text": n, "match_type": "PHRASE"})
                retry["keywords"] = clean_kws
                retry["negatives"] = clean_negs
                retry["total_keywords"] = len(clean_kws)
                retry["total_negatives"] = len(clean_negs)
                retry["_ai_generated"] = True
                return retry

        # Absolute last resort — rule-based (no API key or total AI failure)
        logger.error("All AI keyword strategy attempts failed — using emergency rule-based fallback")
        return self._build_keyword_strategy(intent, industry, learnings, playbook)

    # ══════════════════════════════════════════════════════════════════════
    #  Step 6: AI-Powered Budget, Bidding & Schedule
    # ══════════════════════════════════════════════════════════════════════

    async def _recommend_budget_bidding_schedule_ai(
        self, industry: str, intent: Dict, profile: BusinessProfile,
        campaign_type: str, competitor_insights: Dict, strategy_insights: Dict,
    ) -> Dict:
        """Use GPT to recommend budget, bidding strategy, schedule, and device bids."""
        constraints = profile.constraints_json or {}
        monthly_budget = constraints.get("monthly_budget", 0)

        system = """You are a Google Ads budget and bidding strategist. You recommend optimal budget
allocation, bidding strategies, ad scheduling, and device bid adjustments based on
industry benchmarks, competitive landscape, and business constraints.
You respond ONLY with valid JSON."""

        user_msg = f"""Recommend budget, bidding, schedule, and device bids.

INDUSTRY: {industry}
CAMPAIGN TYPE: {campaign_type}
SERVICES: {json.dumps(intent.get('services', [])[:5])}
LOCATIONS: {json.dumps(intent.get('locations', [])[:5])}
URGENCY: {intent.get('urgency', 'normal')}
GOAL: {intent.get('goal', 'leads')}
PRIMARY CONVERSION: {profile.primary_conversion_goal or 'calls'}

BUDGET CONSTRAINT: {"$" + str(monthly_budget) + "/month" if monthly_budget else "No budget set — recommend based on industry"}

COMPETITIVE LANDSCAPE:
- Competitor count: {competitor_insights.get('competitor_count', 'unknown')}
- Estimated competitor CPC: {competitor_insights.get('estimated_competitor_cpc', 'unknown')}

STRATEGY INSIGHTS:
- Expected CPC range: {strategy_insights.get('expected_cpc_range', 'unknown')}
- Expected conversion rate: {strategy_insights.get('expected_conversion_rate', 'unknown')}

Recommend:
1. Daily budget in USD (and monthly estimate)
2. Bidding strategy (MAXIMIZE_CONVERSIONS, TARGET_CPA, MAXIMIZE_CLICKS, etc.) with reasoning
3. Ad schedule (24/7 or specific hours/days) with reasoning
4. Device bid adjustments (mobile/desktop/tablet percentages) with reasoning
5. Target CPA if using TARGET_CPA strategy

Return JSON:
{{
  "budget": {{
    "daily_usd": N,
    "daily_micros": N,
    "monthly_estimate_usd": N,
    "reasoning": "Why this budget..."
  }},
  "bidding": {{
    "strategy": "MAXIMIZE_CONVERSIONS" | "TARGET_CPA" | "MAXIMIZE_CLICKS" | "MAXIMIZE_CONVERSION_VALUE",
    "target_cpa_usd": N or null,
    "reasoning": "Why this strategy..."
  }},
  "schedule": {{
    "all_day": true/false,
    "hours": {{"start": "HH:MM", "end": "HH:MM"}} or null,
    "days": ["MON", "TUE", ...] or null,
    "peak_hours_bid_adj": "+X%",
    "reasoning": "Why this schedule..."
  }},
  "device_bids": {{
    "mobile_bid_adj": N,
    "desktop_bid_adj": N,
    "tablet_bid_adj": N,
    "reasoning": "Why these device bids..."
  }},
  "estimated_cpc": "$X.XX",
  "estimated_monthly_clicks": N,
  "estimated_monthly_conversions": N
}}"""

        result = await self._call_openai_json(system, user_msg, temperature=0.4)
        if result:
            result.pop("_raw", None)
            # Ensure budget has micros
            budget = result.get("budget", {})
            if "daily_usd" in budget and "daily_micros" not in budget:
                budget["daily_micros"] = int(budget["daily_usd"] * 1_000_000)
            if "daily_usd" in budget and "monthly_estimate_usd" not in budget:
                budget["monthly_estimate_usd"] = round(budget["daily_usd"] * 30, 2)
            result["_ai_generated"] = True
            return result

        # Retry with simpler prompt
        logger.warning("AI budget/bidding failed — retrying with simpler prompt")
        simple_system = "You are a Google Ads budget strategist. Respond ONLY with valid JSON."
        simple_msg = f"""Recommend budget and bidding for a {industry} {campaign_type} campaign.
Monthly budget constraint: {"$" + str(monthly_budget) if monthly_budget else "recommend based on industry"}
Goal: {intent.get('goal', 'leads')}

Return JSON: {{
  "budget": {{"daily_usd": N, "daily_micros": N, "monthly_estimate_usd": N, "reasoning": "..."}},
  "bidding": {{"strategy": "MAXIMIZE_CONVERSIONS"|"TARGET_CPA"|"MAXIMIZE_CLICKS", "reasoning": "..."}},
  "schedule": {{"all_day": true, "reasoning": "24/7 coverage"}},
  "device_bids": {{"mobile": "+20%", "desktop": "0%", "tablet": "-10%", "reasoning": "..."}}
}}"""
        retry = await self._call_openai_json(simple_system, simple_msg, temperature=0.3, retries=2)
        if retry:
            retry.pop("_raw", None)
            budget = retry.get("budget", {})
            if "daily_usd" in budget and "daily_micros" not in budget:
                budget["daily_micros"] = int(budget["daily_usd"] * 1_000_000)
            if "daily_usd" in budget and "monthly_estimate_usd" not in budget:
                budget["monthly_estimate_usd"] = round(budget["daily_usd"] * 30, 2)
            retry["_ai_generated"] = True
            return retry

        # Absolute last resort — rule-based (no API key or total AI failure)
        logger.error("All AI budget/bidding attempts failed — using emergency rule-based fallback")
        playbook = await self._get_playbook(industry, intent.get("goal"))
        return {
            "budget": self._calculate_budget(profile, playbook, intent),
            "bidding": self._determine_bid_strategy(campaign_type, intent, profile),
            "schedule": self._build_schedule(industry, intent),
            "device_bids": self._build_device_bids(industry, intent),
        }

    async def _get_existing_campaigns(self) -> List[Dict]:
        result = await self.db.execute(
            select(Campaign).where(Campaign.tenant_id == self.tenant_id)
        )
        campaigns = result.scalars().all()
        return [{"name": c.name, "type": c.type, "status": c.status} for c in campaigns]

    async def _get_playbook(self, industry: Optional[str], goal: Optional[str]) -> Optional[Dict]:
        if not industry:
            return None
        result = await self.db.execute(
            select(Playbook).where(
                Playbook.industry == industry,
                Playbook.goal_type == (goal or "leads"),
            )
        )
        pb = result.scalar_one_or_none()
        return pb.template_json if pb else None

    async def _get_relevant_learnings(self, industry: Optional[str]) -> List[Dict]:
        if not industry:
            return []
        result = await self.db.execute(
            select(Learning).where(Learning.industry == industry, Learning.confidence >= 0.5)
        )
        learnings = result.scalars().all()
        return [{"type": l.pattern_type, "pattern": l.pattern_json, "confidence": l.confidence} for l in learnings]

    def _build_keyword_strategy(self, intent: Dict, industry: str, learnings: List[Dict], playbook: Optional[Dict]) -> Dict:
        """Build deep tiered keyword lists: emergency > high intent > medium intent > informational"""
        services = intent.get("services", [])
        locations = intent.get("locations", [])
        urgency = intent.get("urgency", "normal")

        INDUSTRY_KEYWORDS: Dict[str, Dict[str, List[str]]] = {
            "locksmith": {
                "emergency": ["emergency locksmith", "locked out of house", "locked out of car",
                               "locksmith near me now", "24 hour locksmith", "locksmith open now",
                               "lost car keys", "broken key in lock", "lock change same day"],
                "high": ["locksmith service", "car locksmith", "house lockout", "rekey locks",
                          "deadbolt installation", "lock replacement", "master key system",
                          "commercial locksmith", "residential locksmith", "auto locksmith"],
                "medium": ["affordable locksmith", "licensed locksmith", "local locksmith",
                            "best locksmith", "trusted locksmith", "fast locksmith"],
                "negatives": ["locksmith training", "locksmith school", "lock pick set", "lock picking",
                               "locksmith tools buy", "locksmith certification", "how to pick a lock",
                               "locksmith salary", "locksmith jobs", "become a locksmith"],
            },
            "plumbing": {
                "emergency": ["emergency plumber", "burst pipe", "plumber near me now", "24 hour plumber",
                               "water leak emergency", "drain clog emergency", "flooded basement"],
                "high": ["plumber service", "drain cleaning", "water heater repair", "pipe repair",
                          "toilet repair", "faucet installation", "sewer line repair", "leak detection"],
                "medium": ["local plumber", "affordable plumber", "licensed plumber", "best plumber"],
                "negatives": ["plumbing supplies", "plumbing school", "plumbing jobs", "plumbing code",
                               "diy plumbing", "plumbing tools", "plumbing salary"],
            },
            "hvac": {
                "emergency": ["emergency ac repair", "ac not working", "furnace not working",
                               "hvac repair near me", "no heat emergency", "no ac emergency"],
                "high": ["ac repair", "furnace repair", "hvac installation", "air conditioning service",
                          "heating repair", "ac tune up", "hvac maintenance", "duct cleaning"],
                "medium": ["affordable hvac", "local hvac company", "best hvac service", "hvac contractor"],
                "negatives": ["hvac school", "hvac certification", "hvac jobs", "hvac tools",
                               "hvac salary", "hvac training", "diy hvac"],
            },
            "roofing": {
                "emergency": ["emergency roof repair", "roof leak repair", "storm damage roof",
                               "roof repair near me", "hail damage roof"],
                "high": ["roof replacement", "roofing contractor", "new roof installation",
                          "roof inspection", "shingle replacement", "flat roof repair"],
                "medium": ["local roofer", "affordable roofing", "best roofing company", "licensed roofer",
                            "free roof estimate"],
                "negatives": ["roofing materials", "roofing nails", "roofing jobs", "roofing school",
                               "diy roofing", "roofing salary"],
            },
            "auto_repair": {
                "emergency": ["towing near me", "car broke down", "flat tire help", "roadside assistance"],
                "high": ["auto repair near me", "brake repair", "oil change", "engine repair",
                          "transmission repair", "check engine light", "car diagnostic"],
                "medium": ["affordable auto repair", "trusted mechanic", "local auto shop", "best mechanic"],
                "negatives": ["auto parts store", "car parts online", "junkyard", "salvage yard",
                               "mechanic school", "auto repair jobs"],
            },
            "pest_control": {
                "emergency": ["emergency pest control", "bee removal near me", "wasp nest removal",
                               "pest control near me now"],
                "high": ["pest control service", "termite treatment", "rodent control",
                          "bed bug treatment", "ant exterminator", "cockroach exterminator"],
                "medium": ["local pest control", "affordable exterminator", "best pest control"],
                "negatives": ["pest control school", "pesticide store", "diy pest control",
                               "pest control jobs", "pest control salary"],
            },
            "cleaning": {
                "emergency": ["emergency cleaning service", "water damage cleanup", "biohazard cleanup"],
                "high": ["house cleaning service", "commercial cleaning", "move out cleaning",
                          "deep cleaning service", "maid service", "office cleaning"],
                "medium": ["affordable cleaning service", "local cleaning company", "weekly cleaning"],
                "negatives": ["cleaning products", "cleaning supplies", "cleaning jobs", "cleaning school"],
            },
        }

        industry_data = INDUSTRY_KEYWORDS.get(industry, {
            "emergency": [],
            "high": [s.lower() for s in services],
            "medium": [f"affordable {s.lower()}" for s in services] + [f"best {s.lower()}" for s in services],
            "negatives": ["jobs", "training", "school", "diy", "free"],
        })

        keywords: List[Dict] = []

        # Tier 1: Emergency / High urgency (EXACT match — highest bid)
        if urgency == "high" or industry in ["locksmith", "plumbing", "hvac"]:
            for kw in industry_data.get("emergency", []):
                keywords.append({"text": kw, "match_type": "EXACT", "tier": "emergency", "bid_adj": "+30%"})

        # Tier 2: High commercial intent (EXACT + PHRASE)
        for kw in industry_data.get("high", []):
            keywords.append({"text": kw, "match_type": "EXACT", "tier": "high"})
            keywords.append({"text": kw + " near me", "match_type": "EXACT", "tier": "high"})

        # Tier 3: Medium intent (PHRASE)
        for kw in industry_data.get("medium", []):
            keywords.append({"text": kw, "match_type": "PHRASE", "tier": "medium"})

        # Location-modified keywords (EXACT — highest local intent)
        for loc in locations[:3]:
            for base in (industry_data.get("emergency", []) + industry_data.get("high", []))[:5]:
                keywords.append({"text": f"{base} {loc.lower()}", "match_type": "EXACT", "tier": "local"})
                keywords.append({"text": f"{base} in {loc.lower()}", "match_type": "EXACT", "tier": "local"})

        # Service-specific keywords from business profile (tagged with service for segmentation)
        for svc in services:
            keywords.append({"text": svc.lower(), "match_type": "PHRASE", "tier": "service", "service": svc})
            keywords.append({"text": f"{svc.lower()} near me", "match_type": "EXACT", "tier": "service", "service": svc})
            keywords.append({"text": f"{svc.lower()} service", "match_type": "PHRASE", "tier": "service", "service": svc})

        # Apply learnings: inject proven keywords from same-industry tenants
        learning_kws = []
        for l in learnings:
            if l["type"] == "headline_theme" and "keywords" in l.get("pattern", {}):
                for kw in l["pattern"]["keywords"][:3]:
                    learning_kws.append({"text": kw, "match_type": "PHRASE", "tier": "learned",
                                         "confidence": l["confidence"]})
        keywords.extend(learning_kws)

        # Negatives
        universal_negatives = ["free", "diy", "how to", "youtube", "reddit", "wiki",
                                "salary", "jobs", "hiring", "career", "training", "course",
                                "complaint", "lawsuit", "scam", "cheap", "discount code"]
        negatives = [{"text": n, "match_type": "PHRASE"} for n in universal_negatives]
        for n in industry_data.get("negatives", []):
            negatives.append({"text": n, "match_type": "EXACT"})

        # Apply learned negatives
        for l in learnings:
            if l["type"] == "negative_base" and "negatives" in l.get("pattern", {}):
                for neg in l["pattern"]["negatives"][:5]:
                    negatives.append({"text": neg, "match_type": "PHRASE"})

        return {
            "keywords": keywords,
            "negatives": negatives,
            "total_keywords": len(keywords),
            "total_negatives": len(negatives),
            "tiers": {
                "emergency": len([k for k in keywords if k.get("tier") == "emergency"]),
                "high": len([k for k in keywords if k.get("tier") == "high"]),
                "medium": len([k for k in keywords if k.get("tier") == "medium"]),
                "local": len([k for k in keywords if k.get("tier") == "local"]),
                "learned": len([k for k in keywords if k.get("tier") == "learned"]),
            },
        }

    async def _build_campaign_draft(
        self,
        intent: Dict,
        campaign_type: str,
        business_profile: BusinessProfile,
        existing_campaigns: List[Dict],
        playbook: Optional[Dict],
        learnings: List[Dict],
        keyword_strategy: Dict,
        bid_strategy: Dict,
        budget: Dict,
        scheduling: Dict,
        device_bids: Dict,
        competitor_insights: Dict,
        google_customer_id: Optional[str],
    ) -> Dict[str, Any]:
        services = intent.get("services", ["General Service"])
        locations = intent.get("locations", [])

        # Merge offers from intent + business profile (deduplicated)
        intent_offers = intent.get("offers", [])
        bp_offers = business_profile.offers_json if isinstance(business_profile.offers_json, list) else []
        bp_offer_texts = [o if isinstance(o, str) else o.get("text", "") for o in bp_offers]
        offers = list(dict.fromkeys(intent_offers + [o for o in bp_offer_texts if o]))

        # Merge USPs from intent + business profile (deduplicated)
        intent_usps = intent.get("usps", [])
        bp_usps = business_profile.usp_json if isinstance(business_profile.usp_json, list) else []
        bp_usp_texts = [u if isinstance(u, str) else u.get("text", "") for u in bp_usps]
        usps = list(dict.fromkeys(intent_usps + [u for u in bp_usp_texts if u]))

        phone = business_profile.phone or ""
        website = business_profile.website_url or ""
        industry = (business_profile.industry_classification or "general").lower()
        brand_voice = business_profile.brand_voice_json or {}
        tone = brand_voice.get("tone", "professional")

        # Extract trust signals from business profile for ad personalization
        # Format may be {"list": ["licensed & insured", ...]} or {"years_experience": 15, ...}
        raw_ts = business_profile.trust_signals_json or {}
        trust_signals = self._normalize_trust_signals(raw_ts, bp=business_profile)
        biz_description = business_profile.description or ""

        # Fetch business name from tenant
        tenant = await self.db.get(Tenant, self.tenant_id)
        business_name = tenant.name if tenant else ""

        primary_service = services[0] if services else "Service"
        urgency_tag = "Emergency" if intent.get("urgency") == "high" else "Standard"
        campaign_name = f"{primary_service} | {campaign_type} | {urgency_tag}"

        existing_names = {c["name"] for c in existing_campaigns}
        if campaign_name in existing_names:
            campaign_name = f"{campaign_name} ({str(uuid.uuid4())[:4]})"

        # Build TIGHTLY themed ad groups per service (SKAG-style)
        # Keywords are segmented per service — NO overlap between ad groups
        all_keywords = keyword_strategy["keywords"]
        all_negatives = keyword_strategy["negatives"]

        # Pre-segment keywords by service using the "service" tag from AI
        svc_lower_map = {svc.lower(): svc for svc in services[:5]}
        keywords_by_service: Dict[str, list] = {svc: [] for svc in services[:5]}
        unassigned_keywords: list = []

        for kw in all_keywords:
            kw_service = (kw.get("service") or "").lower()
            matched = False
            # Try exact match on service field
            for svc_lower, svc_original in svc_lower_map.items():
                if kw_service == svc_lower or svc_lower in kw_service:
                    keywords_by_service[svc_original].append(kw)
                    matched = True
                    break
            if not matched:
                # Fuzzy: assign to whichever service name appears in keyword text
                kw_text = kw.get("text", "").lower()
                for svc_lower, svc_original in svc_lower_map.items():
                    # Check if any significant word from service name is in keyword
                    svc_words = [w for w in svc_lower.split() if len(w) > 3]
                    if any(w in kw_text for w in svc_words):
                        keywords_by_service[svc_original].append(kw)
                        matched = True
                        break
            if not matched:
                unassigned_keywords.append(kw)

        # Distribute any unassigned keywords round-robin to ad groups that have fewer
        if unassigned_keywords:
            sorted_svcs = sorted(keywords_by_service.keys(),
                                 key=lambda s: len(keywords_by_service[s]))
            for idx, kw in enumerate(unassigned_keywords):
                target = sorted_svcs[idx % len(sorted_svcs)]
                keywords_by_service[target].append(kw)

        # Deduplicate: if a keyword text appears in multiple ad groups, keep it only in first
        seen_kw_texts: set = set()
        for svc in services[:5]:
            deduped = []
            for kw in keywords_by_service.get(svc, []):
                kw_key = kw.get("text", "").lower().strip()
                if kw_key not in seen_kw_texts:
                    seen_kw_texts.add(kw_key)
                    deduped.append(kw)
            keywords_by_service[svc] = deduped

        # --- Parallel ad copy generation for ALL ad groups simultaneously ---
        # Instead of sequential loop (5 services × ~3s each = ~15s),
        # fire all OpenAI calls at once (~3s total)

        async def _generate_ad_group(svc: str, svc_keywords: list) -> Dict:
            """Generate ad copy for a single service — runs in parallel."""
            if not svc_keywords:
                svc_keywords = [
                    {"text": svc.lower(), "match_type": "PHRASE", "tier": "service"},
                    {"text": f"{svc.lower()} near me", "match_type": "EXACT", "tier": "high"},
                    {"text": f"{svc.lower()} service", "match_type": "PHRASE", "tier": "high"},
                ]
                for loc in locations[:2]:
                    svc_keywords.append({"text": f"{svc.lower()} {loc.lower()}", "match_type": "EXACT", "tier": "local"})

            llm_copy = await self._generate_ad_copy_llm(
                service=svc, locations=locations, offers=offers, usps=usps,
                phone=phone, tone=tone, industry=industry,
                urgency=intent.get("urgency"), competitor_insights=competitor_insights,
                campaign_type=campaign_type, business_name=business_name,
                website=website, raw_prompt=intent.get("raw_prompt", ""),
                trust_signals=trust_signals, biz_description=biz_description,
            )
            if not llm_copy:
                logger.warning("Primary AI ad copy failed, retrying with simplified prompt", service=svc)
                llm_copy = await self._generate_ad_copy_llm_simple(
                    service=svc, locations=locations, industry=industry,
                    business_name=business_name, raw_prompt=intent.get("raw_prompt", ""),
                )

            if llm_copy:
                headlines = llm_copy["headlines"]
                descriptions = llm_copy["descriptions"]
                ad_pinning = llm_copy.get("pinning", {})
                ad_sitelinks = llm_copy.get("sitelinks", [])
                ad_callouts = llm_copy.get("callouts", [])
                ad_rationale = llm_copy.get("rationale", "")
                ai_prompt_used = llm_copy.get("ai_prompt")
                ai_raw_response = llm_copy.get("ai_raw_response")
            else:
                logger.error("All AI ad copy attempts failed — using emergency template fallback", service=svc)
                headlines = self._generate_expert_headlines(
                    svc, locations, offers, usps, phone, tone, industry,
                    intent.get("urgency"), competitor_insights
                )
                descriptions = self._generate_expert_descriptions(
                    svc, locations, offers, usps, phone, tone, industry,
                    intent.get("urgency"), competitor_insights
                )
                ad_pinning, ad_sitelinks, ad_callouts, ad_rationale = {}, [], [], ""
                ai_prompt_used, ai_raw_response = None, None

            url_slug = svc.lower().replace(" ", "-")
            return {
                "name": f"{svc} — {locations[0] if locations else 'All Areas'}",
                "theme": svc,
                "match_strategy": "EXACT + PHRASE (SKAG-style tightly themed)",
                "keywords": svc_keywords[:20],
                "negatives": all_negatives,
                "ads": [{
                    "type": "RESPONSIVE_SEARCH_AD",
                    "headlines": headlines,
                    "descriptions": descriptions,
                    "pinning": ad_pinning,
                    "final_urls": [f"{website}/{url_slug}"] if website else [],
                    "display_path": [svc[:15].replace(" ", "-"), locations[0][:15] if locations else "NearYou"],
                    "generated_by": "openai" if llm_copy else "template",
                    "ai_prompt": ai_prompt_used,
                    "ai_raw_response": ai_raw_response,
                    "ai_rationale": ad_rationale,
                }],
                "llm_sitelinks": ad_sitelinks,
                "llm_callouts": ad_callouts,
            }

        # Fire all ad group generations in parallel
        ad_group_tasks = [
            _generate_ad_group(svc, keywords_by_service.get(svc, []))
            for svc in services[:5]
        ]
        ad_groups = list(await asyncio.gather(*ad_group_tasks))

        extensions = await self._generate_extensions_ai(
            business_profile, services, offers, usps, competitor_insights, intent
        )

        return {
            "campaign": {
                "name": campaign_name,
                "type": campaign_type,
                "objective": intent.get("goal", "leads"),
                "budget_micros": budget["daily_micros"],
                "budget_daily_usd": budget["daily_usd"],
                "budget_monthly_estimate_usd": budget["monthly_estimate_usd"],
                "bidding_strategy": bid_strategy["strategy"],
                "locations": locations,
                "schedule": scheduling,
                "device_bids": device_bids,
                "settings": {
                    "network": "SEARCH" if campaign_type in ("SEARCH", "CALL") else "ALL",
                    "language": "en",
                    "location_bid_adjustments": [
                        {"location": loc, "bid_adj": "+15%"} for loc in locations[:3]
                    ],
                },
            },
            "ad_groups": ad_groups,
            "extensions": extensions,
            "keyword_strategy": keyword_strategy,
            "competitor_insights": competitor_insights,
            "intent": intent,
            "reasoning": {
                "campaign_type": self._explain_campaign_type(campaign_type, intent),
                "bid_strategy": bid_strategy["reasoning"],
                "budget": budget["reasoning"],
                "schedule": scheduling.get("reasoning", ""),
                "device_bids": device_bids.get("reasoning", ""),
                "keyword_tiers": keyword_strategy["tiers"],
                "competitor_gaps_exploited": competitor_insights.get("gaps", []),
                "playbook_used": playbook is not None,
                "learnings_applied": len(learnings),
                "ad_groups_count": len(ad_groups),
                "total_keywords": keyword_strategy["total_keywords"],
                "total_negatives": keyword_strategy["total_negatives"],
            },
        }

    # ══════════════════════════════════════════════════════════════════════
    #  CALL-ONLY Campaign Builder
    # ══════════════════════════════════════════════════════════════════════

    async def _build_call_campaign_draft(
        self, intent: Dict, campaign_type: str, business_profile: BusinessProfile,
        existing_campaigns: List[Dict], playbook: Optional[Dict], learnings: List[Dict],
        keyword_strategy: Dict, bid_strategy: Dict, budget: Dict, scheduling: Dict,
        device_bids: Dict, competitor_insights: Dict, google_customer_id: Optional[str],
    ) -> Dict[str, Any]:
        """Build a Call-Only campaign draft — phone number shows directly in the ad."""
        services = intent.get("services", ["General Service"])
        locations = intent.get("locations", [])
        phone = business_profile.phone or ""
        industry = (business_profile.industry_classification or "general").lower()
        business_name = await self._get_business_name()

        # Extract trust signals + merge USPs/offers from business profile
        trust_signals = self._normalize_trust_signals(business_profile.trust_signals_json or {}, bp=business_profile)
        bp_usps = business_profile.usp_json if isinstance(business_profile.usp_json, list) else []
        usps = list(dict.fromkeys(
            intent.get("usps", []) + [u if isinstance(u, str) else u.get("text", "") for u in bp_usps]
        ))
        bp_offers = business_profile.offers_json if isinstance(business_profile.offers_json, list) else []
        offers = list(dict.fromkeys(
            intent.get("offers", []) + [o if isinstance(o, str) else o.get("text", "") for o in bp_offers]
        ))

        primary_service = services[0] if services else "Service"
        urgency_tag = "Emergency" if intent.get("urgency") == "high" else "Standard"
        campaign_name = f"{primary_service} | CALL | {urgency_tag}"

        existing_names = {c["name"] for c in existing_campaigns}
        if campaign_name in existing_names:
            campaign_name = f"{campaign_name} ({str(uuid.uuid4())[:4]})"

        all_keywords = keyword_strategy.get("keywords", [])
        all_negatives = keyword_strategy.get("negatives", [])

        # Build ad groups with Call-Only ads — parallel AI generation
        async def _build_call_ad_group(i: int, svc: str) -> Dict:
            svc_keywords = [k for k in all_keywords if svc.lower() in k.get("text", "").lower()]
            if not svc_keywords:
                svc_keywords = all_keywords[i * 10:(i + 1) * 10] if all_keywords else [
                    {"text": svc.lower(), "match_type": "PHRASE", "tier": "service"},
                    {"text": f"{svc.lower()} near me", "match_type": "EXACT", "tier": "high"},
                ]

            call_copy = await self._generate_call_ad_copy_llm(
                service=svc, locations=locations, phone=phone,
                industry=industry, business_name=business_name,
                urgency=intent.get("urgency"), competitor_insights=competitor_insights,
                raw_prompt=intent.get("raw_prompt", ""),
                trust_signals=trust_signals, usps=usps,
            )
            if not call_copy:
                loc = locations[0] if locations else "Your Area"
                call_copy = {
                    "headline1": f"{svc[:20]} - Call Now"[:30],
                    "headline2": f"Serving {loc}"[:30],
                    "description1": f"Fast {svc}. Licensed & insured."[:35],
                    "description2": f"Call {phone} for same-day help."[:35] if phone else f"Available 24/7. Call now!"[:35],
                }

            return {
                "name": f"{svc} — {locations[0] if locations else 'All Areas'}",
                "theme": svc,
                "keywords": svc_keywords[:20],
                "negatives": all_negatives,
                "ads": [{
                    "type": "CALL_AD",
                    "headline1": call_copy["headline1"],
                    "headline2": call_copy["headline2"],
                    "description1": call_copy["description1"],
                    "description2": call_copy["description2"],
                    "phone_number": phone,
                    "business_name": business_name,
                    "country_code": "US",
                    "phone_number_verification_url": business_profile.website_url or "",
                    "generated_by": "openai" if call_copy.get("ai_generated") else "template",
                }],
            }

        ad_groups = list(await asyncio.gather(*[
            _build_call_ad_group(i, svc) for i, svc in enumerate(services[:5])
        ]))

        extensions = await self._generate_extensions_ai(
            business_profile, services, offers,
            usps, competitor_insights, intent,
        )

        return {
            "campaign": {
                "name": campaign_name,
                "type": "CALL",
                "channel_type": "SEARCH",
                "objective": intent.get("goal", "calls"),
                "budget_micros": budget["daily_micros"],
                "budget_daily_usd": budget["daily_usd"],
                "budget_monthly_estimate_usd": budget["monthly_estimate_usd"],
                "bidding_strategy": bid_strategy["strategy"],
                "locations": locations,
                "schedule": scheduling,
                "device_bids": {**device_bids, "mobile_bid_adj": max(self._safe_int(device_bids.get("mobile_bid_adj", 30)), 30)},
                "settings": {
                    "network": "SEARCH",
                    "language": "en",
                    "call_only": True,
                    "phone_number": phone,
                },
            },
            "ad_groups": ad_groups,
            "extensions": extensions,
            "keyword_strategy": keyword_strategy,
            "competitor_insights": competitor_insights,
            "intent": intent,
            "reasoning": {
                "campaign_type": "CALL — Phone number shows directly in the ad. Ideal for emergency/urgent services where customers call immediately.",
                "bid_strategy": bid_strategy.get("reasoning", ""),
                "budget": budget.get("reasoning", ""),
                "schedule": scheduling.get("reasoning", ""),
                "device_bids": "Mobile bid increased to +30% minimum — call-only ads perform best on mobile.",
                "ad_groups_count": len(ad_groups),
                "total_keywords": keyword_strategy.get("total_keywords", 0),
            },
        }

    async def _generate_call_ad_copy_llm(
        self, service: str, locations: List[str], phone: str, industry: str,
        business_name: str, urgency: Optional[str], competitor_insights: Dict,
        raw_prompt: str = "", trust_signals: Optional[Dict] = None,
        usps: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate call-only ad copy via AI. Returns headline1/2, description1/2."""
        if not settings.OPENAI_API_KEY:
            return None

        loc = locations[0] if locations else "local area"
        comp_gaps = ", ".join(competitor_insights.get("gaps", competitor_insights.get("differentiation_angles", []))) or "none"
        is_emergency = urgency == "high"
        ts = trust_signals or {}
        trust_str = self._build_trust_str(ts)
        usp_str = " | ".join(usps[:5]) if usps else "none provided"

        system = """You are a Google Ads Call-Only ad specialist. Generate ad copy that maximizes
phone calls. Call-Only ads show the phone number directly — the user taps to call.
You respond ONLY with valid JSON. Count characters precisely.
CRITICAL: Include the business name and real trust signals in the ad copy."""

        user_msg = f"""Generate a Call-Only ad for:
Business: {business_name}
Service: {service}
Industry: {industry}
Location: {loc}
Phone: {phone}
Urgency: {'HIGH — emergency' if is_emergency else 'standard'}
Trust signals: {trust_str}
USPs: {usp_str}
Competitor gaps: {comp_gaps}
User request: "{raw_prompt}"

CALL-ONLY AD FORMAT:
- headline1: ≤30 chars — must contain the service name + business identity. Example: "{service[:15]} | {business_name[:12]}"
- headline2: ≤30 chars — trust signal or location. Example: "{ts.get('years_experience', '10')}+ Yrs Experience" or "Serving {loc}"
- description1: ≤35 chars — value proposition from user request pain points
- description2: ≤35 chars — CTA with differentiator

Extract SPECIFIC pain points from the user request. Do NOT use generic copy.
Include "{business_name}" in at least one headline if it fits in ≤30 chars.

Return JSON:
{{
  "headline1": "≤30 chars",
  "headline2": "≤30 chars",
  "description1": "≤35 chars",
  "description2": "≤35 chars",
  "rationale": "brief strategy note"
}}"""

        result = await self._call_openai_json(system, user_msg, temperature=0.7, max_tokens=500)
        if not result:
            return None
        result.pop("_raw", None)
        # Enforce character limits
        result["headline1"] = (result.get("headline1", "") or "")[:30]
        result["headline2"] = (result.get("headline2", "") or "")[:30]
        result["description1"] = (result.get("description1", "") or "")[:35]
        result["description2"] = (result.get("description2", "") or "")[:35]
        result["ai_generated"] = True
        return result

    # ══════════════════════════════════════════════════════════════════════
    #  PERFORMANCE MAX Campaign Builder
    # ══════════════════════════════════════════════════════════════════════

    async def _build_pmax_campaign_draft(
        self, intent: Dict, campaign_type: str, business_profile: BusinessProfile,
        existing_campaigns: List[Dict], playbook: Optional[Dict], learnings: List[Dict],
        keyword_strategy: Dict, bid_strategy: Dict, budget: Dict, scheduling: Dict,
        device_bids: Dict, competitor_insights: Dict, google_customer_id: Optional[str],
    ) -> Dict[str, Any]:
        """Build a Performance Max campaign — asset groups, audience signals, no keywords."""
        services = intent.get("services", ["General Service"])
        locations = intent.get("locations", [])
        phone = business_profile.phone or ""
        website = business_profile.website_url or ""
        industry = (business_profile.industry_classification or "general").lower()
        business_name = await self._get_business_name()

        # Extract trust signals + merge USPs/offers from business profile
        trust_signals = self._normalize_trust_signals(business_profile.trust_signals_json or {}, bp=business_profile)
        bp_usps = business_profile.usp_json if isinstance(business_profile.usp_json, list) else []
        usps = list(dict.fromkeys(
            intent.get("usps", []) + [u if isinstance(u, str) else u.get("text", "") for u in bp_usps]
        ))
        bp_offers = business_profile.offers_json if isinstance(business_profile.offers_json, list) else []
        offers = list(dict.fromkeys(
            intent.get("offers", []) + [o if isinstance(o, str) else o.get("text", "") for o in bp_offers]
        ))

        primary_service = services[0] if services else "Service"
        campaign_name = f"{primary_service} | PMAX | {'Emergency' if intent.get('urgency') == 'high' else 'Standard'}"

        existing_names = {c["name"] for c in existing_campaigns}
        if campaign_name in existing_names:
            campaign_name = f"{campaign_name} ({str(uuid.uuid4())[:4]})"

        # Generate PMax text assets via AI
        pmax_assets = await self._generate_pmax_assets_llm(
            services=services, locations=locations, phone=phone, website=website,
            industry=industry, business_name=business_name,
            urgency=intent.get("urgency"), competitor_insights=competitor_insights,
            raw_prompt=intent.get("raw_prompt", ""), usps=usps,
            offers=offers, trust_signals=trust_signals,
        )

        if not pmax_assets:
            loc = locations[0] if locations else "Your Area"
            pmax_assets = {
                "headlines": [f"{primary_service} Near You"[:30], f"Call {business_name}"[:30], f"{primary_service} in {loc}"[:30]],
                "long_headlines": [f"Expert {primary_service} — Licensed, Insured, Available Now"[:90]],
                "descriptions": [
                    f"Professional {primary_service} in {loc}. Licensed & insured. Call for free estimate!"[:90],
                    f"Trusted by hundreds of customers. Fast, reliable {primary_service.lower()} service."[:90],
                ],
                "business_name": business_name,
            }

        # Build asset groups (one per service, max 5)
        asset_groups = []
        for svc in services[:5]:
            svc_assets = {
                "name": f"{svc} — {locations[0] if locations else 'All Areas'}",
                "final_url": f"{website}/{svc.lower().replace(' ', '-')}" if website else "",
                "text_assets": {
                    "headlines": pmax_assets.get("headlines", [])[:5],
                    "long_headlines": pmax_assets.get("long_headlines", [])[:5],
                    "descriptions": pmax_assets.get("descriptions", [])[:5],
                    "business_name": business_name,
                },
                "audience_signals": {
                    "search_themes": [svc.lower(), f"{svc.lower()} near me", f"{svc.lower()} service",
                                      f"emergency {svc.lower()}" if intent.get("urgency") == "high" else f"best {svc.lower()}"],
                    "custom_segments": [f"{industry} customers", f"{svc.lower()} seekers"],
                    "demographics": {"age_ranges": ["25-34", "35-44", "45-54", "55-64"], "genders": ["all"]},
                    "in_market_audiences": [industry, svc.lower()],
                },
                "image_assets": [],
            }
            asset_groups.append(svc_assets)

        extensions = await self._generate_extensions_ai(
            business_profile, services, offers,
            usps, competitor_insights, intent,
        )

        return {
            "campaign": {
                "name": campaign_name,
                "type": "PERFORMANCE_MAX",
                "channel_type": "PERFORMANCE_MAX",
                "objective": intent.get("goal", "leads"),
                "budget_micros": budget["daily_micros"],
                "budget_daily_usd": budget["daily_usd"],
                "budget_monthly_estimate_usd": budget["monthly_estimate_usd"],
                "bidding_strategy": bid_strategy["strategy"],
                "locations": locations,
                "schedule": scheduling,
                "device_bids": device_bids,
                "settings": {
                    "network": "ALL",
                    "language": "en",
                    "final_url_expansion": True,
                },
            },
            "asset_groups": asset_groups,
            "ad_groups": [],
            "extensions": extensions,
            "keyword_strategy": keyword_strategy,
            "competitor_insights": competitor_insights,
            "intent": intent,
            "reasoning": {
                "campaign_type": "PERFORMANCE_MAX — AI-optimized across Search, Display, YouTube, Gmail, Maps. Uses asset groups instead of traditional ad groups/keywords.",
                "bid_strategy": bid_strategy.get("reasoning", ""),
                "budget": budget.get("reasoning", ""),
                "schedule": scheduling.get("reasoning", ""),
                "asset_groups_count": len(asset_groups),
                "note": "PMax campaigns require text and image assets. Image assets should be uploaded separately via the Landing Page Studio or manually.",
            },
        }

    async def _generate_pmax_assets_llm(
        self, services: List[str], locations: List[str], phone: str, website: str,
        industry: str, business_name: str, urgency: Optional[str],
        competitor_insights: Dict, raw_prompt: str = "", usps: List[str] = None,
        offers: List[str] = None, trust_signals: Optional[Dict] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate Performance Max text assets via AI."""
        if not settings.OPENAI_API_KEY:
            return None

        loc = locations[0] if locations else "local area"
        svc_list = ", ".join(services[:5])
        usp_block = ", ".join(usps[:5]) if usps else "none"
        offer_block = ", ".join(offers[:3]) if offers else "none"
        comp_gaps = ", ".join(competitor_insights.get("gaps", competitor_insights.get("differentiation_angles", []))) or "none"

        # Build trust signal summary
        ts = trust_signals or {}
        trust_str = self._build_trust_str(ts)

        system = """You are a Google Ads Performance Max specialist. Generate text assets for
PMax asset groups. PMax serves across Search, Display, YouTube, Gmail, and Maps.
Assets must work in ALL these contexts. Respond ONLY with valid JSON.
CRITICAL: Include the business name and real trust signals (years experience, rating, etc.) in the assets."""

        user_msg = f"""Generate PMax text assets for:
Business: {business_name}
Services: {svc_list}
Industry: {industry}
Location: {loc}
Phone: {phone or 'N/A'}
Website: {website or 'N/A'}
Urgency: {'HIGH' if urgency == 'high' else 'standard'}
Trust signals: {trust_str}
USPs: {usp_block}
Offers: {offer_block}
Competitor gaps: {comp_gaps}
User request: "{raw_prompt}"

PMAX TEXT ASSET REQUIREMENTS:
- headlines: 5 headlines, each ≤30 chars — keyword-rich, diverse, include business name
- long_headlines: 5 long headlines, each ≤90 chars — expanded value props with trust signals
- descriptions: 5 descriptions, each ≤90 chars — persuasive, varied, include trust signals
- business_name: ≤25 chars

Include "{business_name}" in at least 2 headlines.
Use REAL trust signals (years experience, rating) — NOT generic phrases.
Headlines must work on Search AND as Display/YouTube overlays.
Descriptions must be compelling standalone AND in combination.

Return JSON:
{{
  "headlines": ["≤30", "≤30", "≤30", "≤30", "≤30"],
  "long_headlines": ["≤90", "≤90", "≤90", "≤90", "≤90"],
  "descriptions": ["≤90", "≤90", "≤90", "≤90", "≤90"],
  "business_name": "≤25",
  "rationale": "brief strategy note"
}}"""

        result = await self._call_openai_json(system, user_msg, temperature=0.7, max_tokens=1500)
        if not result:
            return None
        result.pop("_raw", None)
        # Enforce character limits
        result["headlines"] = [(h or "")[:30] for h in result.get("headlines", []) if h][:5]
        result["long_headlines"] = [(h or "")[:90] for h in result.get("long_headlines", []) if h][:5]
        result["descriptions"] = [(d or "")[:90] for d in result.get("descriptions", []) if d][:5]
        result["business_name"] = (result.get("business_name", business_name) or "")[:25]
        return result

    # ══════════════════════════════════════════════════════════════════════
    #  DISPLAY Campaign Builder
    # ══════════════════════════════════════════════════════════════════════

    async def _build_display_campaign_draft(
        self, intent: Dict, campaign_type: str, business_profile: BusinessProfile,
        existing_campaigns: List[Dict], playbook: Optional[Dict], learnings: List[Dict],
        keyword_strategy: Dict, bid_strategy: Dict, budget: Dict, scheduling: Dict,
        device_bids: Dict, competitor_insights: Dict, google_customer_id: Optional[str],
    ) -> Dict[str, Any]:
        """Build a Display campaign — responsive display ads with audience targeting."""
        services = intent.get("services", ["General Service"])
        locations = intent.get("locations", [])
        phone = business_profile.phone or ""
        website = business_profile.website_url or ""
        industry = (business_profile.industry_classification or "general").lower()
        business_name = await self._get_business_name()

        # Extract trust signals + merge USPs/offers from business profile
        trust_signals = self._normalize_trust_signals(business_profile.trust_signals_json or {}, bp=business_profile)
        bp_usps = business_profile.usp_json if isinstance(business_profile.usp_json, list) else []
        usps = list(dict.fromkeys(
            intent.get("usps", []) + [u if isinstance(u, str) else u.get("text", "") for u in bp_usps]
        ))
        bp_offers = business_profile.offers_json if isinstance(business_profile.offers_json, list) else []
        offers = list(dict.fromkeys(
            intent.get("offers", []) + [o if isinstance(o, str) else o.get("text", "") for o in bp_offers]
        ))

        primary_service = services[0] if services else "Service"
        campaign_name = f"{primary_service} | DISPLAY | {'Remarketing' if intent.get('goal') == 'remarketing' else 'Prospecting'}"

        existing_names = {c["name"] for c in existing_campaigns}
        if campaign_name in existing_names:
            campaign_name = f"{campaign_name} ({str(uuid.uuid4())[:4]})"

        # Generate display ad copy via AI
        display_copy = await self._generate_display_ad_copy_llm(
            services=services, locations=locations, phone=phone, website=website,
            industry=industry, business_name=business_name,
            urgency=intent.get("urgency"), competitor_insights=competitor_insights,
            raw_prompt=intent.get("raw_prompt", ""), usps=usps,
            offers=offers, trust_signals=trust_signals,
        )

        if not display_copy:
            loc = locations[0] if locations else "Your Area"
            display_copy = {
                "short_headlines": [f"{primary_service}"[:30], f"Call {business_name}"[:30]],
                "long_headline": f"Professional {primary_service} — Licensed & Insured in {loc}"[:90],
                "descriptions": [
                    f"Expert {primary_service.lower()} in {loc}. Licensed, insured. Call for free estimate!"[:90],
                ],
                "business_name": business_name,
            }

        # Build ad groups with responsive display ads
        ad_groups = []
        for svc in services[:3]:
            url_slug = svc.lower().replace(" ", "-")
            ad_group = {
                "name": f"{svc} — Display — {locations[0] if locations else 'All Areas'}",
                "type": "DISPLAY_STANDARD",
                "theme": svc,
                "keywords": [],
                "negatives": [],
                "audience_targeting": {
                    "in_market": [industry, svc.lower()],
                    "affinity": [f"{industry} enthusiasts"],
                    "custom_intent": [svc.lower(), f"{svc.lower()} near me", f"hire {svc.lower()}",
                                      f"best {svc.lower()}", f"{svc.lower()} cost"],
                    "remarketing": intent.get("goal") == "remarketing",
                },
                "ads": [{
                    "type": "RESPONSIVE_DISPLAY_AD",
                    "short_headlines": display_copy.get("short_headlines", [])[:5],
                    "long_headline": display_copy.get("long_headline", "")[:90],
                    "descriptions": display_copy.get("descriptions", [])[:5],
                    "business_name": display_copy.get("business_name", business_name)[:25],
                    "final_urls": [f"{website}/{url_slug}"] if website else [],
                    "image_assets": [],
                    "logo_assets": [],
                    "generated_by": "openai" if display_copy.get("ai_generated") else "template",
                }],
            }
            ad_groups.append(ad_group)

        extensions = await self._generate_extensions_ai(
            business_profile, services, offers,
            usps, competitor_insights, intent,
        )

        return {
            "campaign": {
                "name": campaign_name,
                "type": "DISPLAY",
                "channel_type": "DISPLAY",
                "objective": intent.get("goal", "awareness"),
                "budget_micros": budget["daily_micros"],
                "budget_daily_usd": budget["daily_usd"],
                "budget_monthly_estimate_usd": budget["monthly_estimate_usd"],
                "bidding_strategy": bid_strategy["strategy"],
                "locations": locations,
                "schedule": scheduling,
                "device_bids": device_bids,
                "settings": {
                    "network": "DISPLAY",
                    "language": "en",
                    "content_exclusions": ["BELOW_THE_FOLD", "PARKED_DOMAINS", "SEXUALLY_SUGGESTIVE"],
                },
            },
            "ad_groups": ad_groups,
            "extensions": extensions,
            "keyword_strategy": {"keywords": [], "negatives": [], "total_keywords": 0, "total_negatives": 0, "tiers": {}},
            "competitor_insights": competitor_insights,
            "intent": intent,
            "reasoning": {
                "campaign_type": "DISPLAY — Visual banner ads across the Google Display Network. Uses responsive display ads with audience targeting.",
                "bid_strategy": bid_strategy.get("reasoning", ""),
                "budget": budget.get("reasoning", ""),
                "schedule": scheduling.get("reasoning", ""),
                "ad_groups_count": len(ad_groups),
                "note": "Display campaigns require image assets (landscape 1200x628, square 1200x1200, logo 1200x1200). Upload via Landing Page Studio or manually.",
            },
        }

    async def _generate_display_ad_copy_llm(
        self, services: List[str], locations: List[str], phone: str, website: str,
        industry: str, business_name: str, urgency: Optional[str],
        competitor_insights: Dict, raw_prompt: str = "", usps: List[str] = None,
        offers: List[str] = None, trust_signals: Optional[Dict] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate responsive display ad copy via AI."""
        if not settings.OPENAI_API_KEY:
            return None

        loc = locations[0] if locations else "local area"
        svc_list = ", ".join(services[:5])
        usp_block = ", ".join(usps[:5]) if usps else "none"
        offer_block = ", ".join(offers[:3]) if offers else "none"
        comp_gaps = ", ".join(competitor_insights.get("gaps", competitor_insights.get("differentiation_angles", []))) or "none"

        # Build trust signal summary
        ts = trust_signals or {}
        trust_str = self._build_trust_str(ts)

        system = """You are a Google Display Network specialist. Generate responsive display ad copy
that works across websites, apps, and Gmail. Display ads are visual — copy must be
punchy, brand-forward, and work with image overlays. Respond ONLY with valid JSON.
CRITICAL: Include the business name and real trust signals in the copy."""

        user_msg = f"""Generate responsive display ad copy for:
Business: {business_name}
Services: {svc_list}
Industry: {industry}
Location: {loc}
Phone: {phone or 'N/A'}
Urgency: {'HIGH' if urgency == 'high' else 'standard'}
Trust signals: {trust_str}
USPs: {usp_block}
Offers: {offer_block}
Competitor gaps: {comp_gaps}
User request: "{raw_prompt}"

RESPONSIVE DISPLAY AD FORMAT:
- short_headlines: 5 headlines, each ≤30 chars — punchy, brand-forward, include business name
- long_headline: 1 expanded headline, ≤90 chars — full value prop with trust signals
- descriptions: 5 descriptions, each ≤90 chars — persuasive, varied, include trust signals
- business_name: ≤25 chars

Include "{business_name}" in at least 1 headline.
Use REAL trust signals (years experience, rating) — NOT generic phrases.
Display ads appear on websites/apps — they need to INTERRUPT attention.
Use bold claims, urgency, and specific numbers (not vague superlatives).

Return JSON:
{{
  "short_headlines": ["≤30", "≤30", "≤30", "≤30", "≤30"],
  "long_headline": "≤90",
  "descriptions": ["≤90", "≤90", "≤90", "≤90", "≤90"],
  "business_name": "≤25",
  "rationale": "brief strategy note"
}}"""

        result = await self._call_openai_json(system, user_msg, temperature=0.7, max_tokens=1200)
        if not result:
            return None
        result.pop("_raw", None)
        result["short_headlines"] = [(h or "")[:30] for h in result.get("short_headlines", []) if h][:5]
        result["long_headline"] = (result.get("long_headline", "") or "")[:90]
        result["descriptions"] = [(d or "")[:90] for d in result.get("descriptions", []) if d][:5]
        result["business_name"] = (result.get("business_name", business_name) or "")[:25]
        result["ai_generated"] = True
        return result

    async def _generate_ad_copy_llm(
        self,
        service: str,
        locations: List[str],
        offers: List[str],
        usps: List[str],
        phone: str,
        tone: str,
        industry: str,
        urgency: Optional[str],
        competitor_insights: Dict,
        campaign_type: str,
        business_name: str,
        website: str,
        raw_prompt: str = "",
        trust_signals: Optional[Dict] = None,
        biz_description: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        Use OpenAI to generate expert-quality Google Ads RSA copy.
        Returns {"headlines": [...], "descriptions": [...], "pinning": [...],
                 "sitelinks": [...], "callouts": [...], "ai_prompt": str,
                 "ai_raw_response": str} or None on failure.
        """
        if not settings.OPENAI_API_KEY:
            logger.info("OpenAI key not set — using template fallback for ad copy")
            return None

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        loc = locations[0] if locations else "the local area"
        loc_list = ", ".join(locations[:5]) if locations else "local area"
        usp_block = "\n".join(f"  - {u}" for u in usps) if usps else "  (none provided)"
        offer_block = "\n".join(f"  - {o}" for o in offers) if offers else "  (none provided)"
        comp_themes = ", ".join(competitor_insights.get("common_themes", [])) or "unknown"
        comp_gaps = ", ".join(competitor_insights.get("gaps", competitor_insights.get("differentiation_angles", []))) or "none identified"
        comp_weaknesses = ", ".join(competitor_insights.get("weaknesses", [])) or "unknown"

        # Build trust signals block from business profile
        ts = trust_signals or {}
        trust_str = self._build_trust_str(ts)
        if trust_str and trust_str != "none provided":
            trust_block = "\n".join(f"  - {item.strip()}" for item in trust_str.split(", ") if item.strip())
        else:
            trust_block = "  (none provided — use generic trust language)"

        is_emergency = urgency == "high" or industry in (
            "locksmith", "plumbing", "hvac", "towing", "restoration", "pest control",
            "roofing", "electrical", "garage door",
        )

        system_message = f"""You are a Google Ads Search specialist with 15+ years managing $100M+ in
search ad spend across 500+ local service businesses. You hold Google Ads Search,
Display, and Shopping certifications. You optimize for three metrics simultaneously:

1. QUALITY SCORE (Expected CTR + Ad Relevance + Landing Page Experience)
2. AD STRENGTH (Google's RSA scoring: Poor → Average → Good → Excellent)
3. CONVERSION RATE (psychological triggers that drive action, not just clicks)

You understand that Google's RSA system tests ~43,680 possible combinations from 15
headlines and 4 descriptions. Your job is to maximize the probability that ANY
combination Google serves is high-performing.

You ALWAYS count characters precisely:
- Headlines: STRICTLY ≤30 characters (including spaces and punctuation)
- Descriptions: STRICTLY ≤90 characters (including spaces and punctuation)
- Callouts: STRICTLY ≤25 characters
- Sitelink text: STRICTLY ≤25 characters

You respond ONLY with valid JSON. No markdown, no explanation outside JSON."""

        prompt = f"""
╔══════════════════════════════════════════════════════════════════╗
║  GOOGLE ADS RSA GENERATION — EXPERT BRIEF                       ║
╚══════════════════════════════════════════════════════════════════╝

── CLIENT PROFILE (BUSINESS IDENTITY — USE THIS IN ADS!) ──────
Business:       {business_name or '[Name not set]'}
Industry:       {industry}
Website:        {website or 'N/A'}
Phone:          {phone or 'N/A'}
Brand tone:     {tone}
Service areas:  {loc_list}
{'Description:    ' + biz_description if biz_description else ''}

── TRUST SIGNALS (INJECT THESE INTO HEADLINES & DESCRIPTIONS!) ─
{trust_block}

CRITICAL: You MUST use these trust signals in your ad copy. They are REAL,
verified facts about this business. Ads with specific trust signals
(e.g. "15+ Years Experience", "4.9★ Rating") outperform generic ads by 30-50%.
Include the business name "{business_name}" in at least 2 headlines.

── AD GROUP CONTEXT ────────────────────────────────────────────
Target service: {service}
Campaign type:  {campaign_type}
Urgency level:  {'HIGH — emergency/immediate-need searchers' if is_emergency else urgency or 'standard'}
Primary KW:     "{service.lower()}" and close variants

── USER'S ORIGINAL REQUEST (mine this for pain triggers!) ──────
"{raw_prompt}"

IMPORTANT: Extract specific pain points, price comparisons, and emotional triggers
from the user's request above. For example:
- If they mention "dealer charges $4-5k" → use "Avoid $4k+ Dealer Bill" as a headline
- If they mention a specific problem like "no key detected" → use it in headlines
- If they mention "fix on site" → highlight "On-Site Repair" in headlines
These SPECIFIC pain triggers dramatically increase CTR because they match the
searcher's exact situation. Generic copy like "Quality Service" will NOT work.

USPs (use these — they are REAL differentiators):
{usp_block}

Active offers:
{offer_block}

── COMPETITIVE INTELLIGENCE ────────────────────────────────────
What competitors emphasize:  {comp_themes}
Competitor weaknesses:       {comp_weaknesses}
Gaps to exploit (they DON'T mention these): {comp_gaps}

── GOOGLE ADS RSA REQUIREMENTS ─────────────────────────────────

HEADLINES — Generate exactly 15 (each ≤30 chars):

Google needs DIVERSE headlines to reach "Excellent" Ad Strength.
Structure your 15 headlines across these MANDATORY categories:

H1-H3 — KEYWORD RELEVANCE (boosts Quality Score "Ad Relevance"):
  Pin H1 to Position 1. Must contain "{service}" or a very close variant.
  H2 and H3 should contain the service term in different phrasings.
  Example for locksmith: "Emergency Locksmith Near You", "24/7 Locksmith Service", "Fast Lock Repair"

H4-H5 — GEO-TARGETING (boosts Quality Score "Expected CTR"):
  Include "{loc}" by name. Geo-specific headlines get 15-25% higher CTR.
  Example: "{service} in {loc}", "Serving {loc} & Nearby"

H6-H8 — TRUST & SOCIAL PROOF (reduces bounce rate → better landing page score):
  License numbers, years in business, review counts, ratings, insurance status.
  Example: "Licensed & Insured", "4.9★ Google Rating", "Trusted Since 2010"
  {'CRITICAL for ' + industry + ': consumers need trust signals before calling.' if is_emergency else ''}

H9-H10 — VALUE PROPOSITION (from the USPs above):
  Translate each USP into a punchy ≤30 char headline. Be specific, not generic.
  "Flat-Rate Pricing" beats "Great Prices". "90-Day Warranty" beats "Quality Work".

H11-H12 — OFFER / CTA (drives conversion action):
  Include the offer if one exists. Strong CTAs with specificity.
  "Free Estimate Today", "$20 Off First Visit", "Call Now — Save 15%"
  {'For emergency: "Call Now" and "Open Now" CTAs are critical.' if is_emergency else ''}

H13-H14 — URGENCY / AVAILABILITY (time-pressure triggers):
  {'CRITICAL for emergency ' + industry + ' — these are panicked searchers.' if is_emergency else 'Use scarcity/time pressure where natural.'}
  "Available Right Now", "Same-Day Service", "30-Min Response Time"

H15 — BRAND / BUSINESS NAME:
  Include "{business_name}" if ≤30 chars. Builds brand recognition for remarketing.

DESCRIPTIONS — Generate exactly 4 (each ≤90 chars):

Google shows 2 descriptions at a time. Each must stand alone AND pair well.

D1 (pin to Position 1) — PROBLEM → SOLUTION → CTA:
  Address the exact pain point a "{service}" searcher has. Offer your solution. End with CTA.
  {'For emergency: "Locked out? We arrive in 30 min or less. Call now for fast help!"' if is_emergency else 'Example: "Need [service]? Our licensed pros deliver same-day. Get your free quote!"'}

D2 — TRUST PROOF + DIFFERENTIATOR:
  Combine a trust signal with what makes this business different from competitors.
  Use competitor gaps: things they DON'T say that you CAN say.

D3 — OFFER + URGENCY + CTA:
  Lead with the offer/promotion, add time pressure, close with action verb.
  If no offer, emphasize value: "No hidden fees. Transparent pricing. Book online now."

D4 — LOCAL AUTHORITY + REASSURANCE:
  Establish local expertise. Reference the service area. Reduce anxiety.
  "Proudly serving {loc} for 10+ years. Licensed, bonded & insured. Call today!"

PINNING STRATEGY:
  Specify which headlines/descriptions to pin. This is CRITICAL for RSA performance.
  Pin your BEST keyword-match headline to Position 1.
  Pin your BEST trust/CTA headline to Position 2.
  Pin D1 to Description Position 1.
  Let Google rotate the rest for machine learning optimization.

SITELINKS — Generate exactly 4:
  Each sitelink: "text" (≤25 chars), "desc1" (≤35 chars), "desc2" (≤35 chars)
  Must cover: Services page, Reviews/Testimonials, About/Why Us, Contact/Free Quote
  Use URLs based on: {website or 'https://example.com'}

CALLOUTS — Generate exactly 6 (each ≤25 chars):
  Punchy trust signals. No periods. No CTAs (those go in headlines).
  Mix: licensing, guarantee, speed, availability, pricing transparency, experience.

── EXPERT RULES ────────────────────────────────────────────────
1. COUNT EVERY CHARACTER. Even 1 char over = Google rejects the asset.
2. Each headline must be UNIQUE in wording — Google penalizes repetitive copy
   and it tanks your Ad Strength score.
3. NEVER use: "Best [service]", "#1 Provider", "Quality Work", "Great Service",
   "Top Rated" (without a specific rating), or any vague superlative.
4. Use ACTIVE VOICE and SECOND PERSON: "Get your", "Call us", "Book your".
5. For {industry}: use industry-specific terminology that matches what real
   customers search for. Match the searcher's vocabulary, not marketing jargon.
6. The primary keyword "{service}" must appear in at least 3 headlines for
   Ad Relevance scoring.
7. Every piece of copy must answer: "Why THIS business, why NOW, why not them?"

── OUTPUT FORMAT ────────────────────────────────────────────────
Respond with ONLY this JSON structure:
{{
  "headlines": ["H1", "H2", ..., "H15"],
  "descriptions": ["D1", "D2", "D3", "D4"],
  "pinning": {{
    "headline_pins": {{"1": 0, "2": 5}},
    "description_pins": {{"1": 0}}
  }},
  "sitelinks": [
    {{"text": "...", "desc1": "...", "desc2": "...", "url": "..."}},
    ...
  ],
  "callouts": ["...", "...", "...", "...", "...", "..."],
  "rationale": "Brief explanation of your strategic choices (2-3 sentences)"
}}

headline_pins: maps Position (1/2/3) to headline INDEX (0-14).
description_pins: maps Position (1/2) to description INDEX (0-3).
"""

        try:
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.8,
                max_tokens=2500,
            )
            content = response.choices[0].message.content
            if not content:
                return None

            data = json.loads(content)
            headlines = data.get("headlines", [])
            descriptions = data.get("descriptions", [])

            # Enforce Google Ads character limits strictly
            headlines = [h[:30] for h in headlines if isinstance(h, str) and h.strip()]
            descriptions = [d[:90] for d in descriptions if isinstance(d, str) and d.strip()]

            # Deduplicate headlines
            seen = set()
            unique_headlines = []
            for h in headlines:
                h_lower = h.lower().strip()
                if h_lower not in seen:
                    seen.add(h_lower)
                    unique_headlines.append(h)

            if len(unique_headlines) < 5 or len(descriptions) < 2:
                logger.warning(
                    "LLM returned too few ad components — falling back to templates",
                    headlines=len(unique_headlines), descriptions=len(descriptions),
                )
                return None

            # Extract extensions and pinning from LLM response
            sitelinks = data.get("sitelinks", [])
            if not isinstance(sitelinks, list):
                sitelinks = []
            sitelinks = [s for s in sitelinks if isinstance(s, dict) and "text" in s][:4]

            callouts = [c[:25] for c in data.get("callouts", []) if isinstance(c, str) and c.strip()][:8]
            pinning = data.get("pinning", {})
            rationale = data.get("rationale", "")

            logger.info(
                "LLM ad copy generated successfully",
                service=service,
                headlines=len(unique_headlines),
                descriptions=len(descriptions),
                sitelinks=len(sitelinks),
                callouts=len(callouts),
            )
            return {
                "headlines": unique_headlines[:15],
                "descriptions": descriptions[:4],
                "pinning": pinning,
                "sitelinks": sitelinks,
                "callouts": callouts,
                "rationale": rationale,
                "ai_prompt": prompt,
                "ai_raw_response": content,
            }

        except Exception as e:
            logger.error("OpenAI ad copy generation failed — using template fallback", error=str(e))
            return None

    async def _generate_ad_copy_llm_simple(
        self,
        service: str,
        locations: List[str],
        industry: str,
        business_name: str,
        raw_prompt: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Simplified AI ad copy generation — used as retry when the full prompt fails."""
        loc = locations[0] if locations else "local area"

        system = """You are a Google Ads expert. Generate RSA ad copy. Respond ONLY with valid JSON.
Headlines must be ≤30 characters. Descriptions must be ≤90 characters. Count carefully."""

        prompt = f"""Generate Google Ads copy for:
Business: {business_name or 'Local Service'}
Service: {service}
Industry: {industry}
Location: {loc}
User request: "{raw_prompt}"

Extract pain points from the user request (prices, problems, urgency) and use them in headlines.

Return JSON:
{{
  "headlines": ["H1", "H2", ..., "H15"],
  "descriptions": ["D1", "D2", "D3", "D4"],
  "pinning": {{"headline_pins": {{"1": 0}}, "description_pins": {{"1": 0}}}},
  "sitelinks": [{{"text": "...", "desc1": "...", "desc2": "..."}}],
  "callouts": ["...", "...", "...", "...", "...", "..."],
  "rationale": "Brief strategy explanation"
}}"""

        result = await self._call_openai_json(system, prompt, temperature=0.7, max_tokens=2000)
        if not result:
            return None

        content = result.pop("_raw", "")
        headlines = [h[:30] for h in result.get("headlines", []) if isinstance(h, str) and h.strip()]
        descriptions = [d[:90] for d in result.get("descriptions", []) if isinstance(d, str) and d.strip()]

        # Deduplicate headlines
        seen = set()
        unique = []
        for h in headlines:
            if h.lower().strip() not in seen:
                seen.add(h.lower().strip())
                unique.append(h)

        if len(unique) < 5 or len(descriptions) < 2:
            return None

        sitelinks = [s for s in result.get("sitelinks", []) if isinstance(s, dict) and "text" in s][:4]
        callouts = [c[:25] for c in result.get("callouts", []) if isinstance(c, str) and c.strip()][:8]

        return {
            "headlines": unique[:15],
            "descriptions": descriptions[:4],
            "pinning": result.get("pinning", {}),
            "sitelinks": sitelinks,
            "callouts": callouts,
            "rationale": result.get("rationale", ""),
            "ai_prompt": prompt,
            "ai_raw_response": content,
        }

    async def _generate_extensions_ai(
        self,
        profile: BusinessProfile,
        services: List[str],
        offers: List[str],
        usps: List[str],
        competitor_insights: Dict,
        intent: Dict,
    ) -> Dict[str, Any]:
        """AI-powered extensions generation — sitelinks, callouts, structured snippets."""
        website = profile.website_url or ""
        industry = (profile.industry_classification or "service").lower()
        phone = profile.phone or ""
        raw_prompt = intent.get("raw_prompt", "")
        loc = ", ".join(intent.get("locations", [])[:3]) or "local area"
        usp_block = ", ".join(usps[:5]) if usps else "none"
        offer_block = ", ".join(offers[:3]) if offers else "none"
        comp_gaps = ", ".join(competitor_insights.get("gaps", competitor_insights.get("differentiation_angles", []))) or "none"

        system = """You are a Google Ads extensions specialist. Generate high-performing ad extensions
that boost CTR and Quality Score. You respond ONLY with valid JSON.
Sitelink text: ≤25 chars. Sitelink descriptions: ≤35 chars each.
Callout text: ≤25 chars each. Structured snippet values: ≤25 chars each."""

        ext_biz_name = await self._get_business_name()
        user_msg = f"""Generate Google Ads extensions for:

Business: {ext_biz_name}
Industry: {industry}
Website: {website or 'N/A'}
Phone: {phone or 'N/A'}
Services: {json.dumps(services[:5])}
Locations: {loc}
USPs: {usp_block}
Offers: {offer_block}
Competitor gaps to exploit: {comp_gaps}
User's original request: "{raw_prompt}"

Generate:
1. 6 sitelinks — link to key pages (services, reviews, about, contact, service areas, emergency)
2. 8-10 callouts — trust signals, differentiators, speed, guarantees
3. 1-2 structured snippets — services list, service types

Use pain points from the user's request in the extensions where relevant.

Return JSON:
{{
  "sitelinks": [
    {{"text": "≤25 chars", "desc1": "≤35 chars", "desc2": "≤35 chars", "url": "{website}/page"}},
    ...
  ],
  "callouts": ["≤25 chars", ...],
  "structured_snippets": [
    {{"header": "Services"|"Types"|"Amenities", "values": ["val1", "val2", ...]}},
    ...
  ]
}}"""

        result = await self._call_openai_json(system, user_msg, temperature=0.6, max_tokens=1500)
        if result:
            result.pop("_raw", None)
            sitelinks = [s for s in result.get("sitelinks", []) if isinstance(s, dict) and "text" in s]
            for s in sitelinks:
                s["text"] = s["text"][:25]
            callouts = [c[:25] for c in result.get("callouts", []) if isinstance(c, str) and c.strip()]
            snippets = result.get("structured_snippets", [])

            ext: Dict[str, Any] = {
                "sitelinks": sitelinks[:6],
                "callouts": callouts[:10],
                "structured_snippets": snippets[:3],
                "recommended": ["call_extension", "location_extension", "sitelink", "callout", "structured_snippet"],
                "ai_generated": True,
            }
            if phone:
                ext["call_extension"] = {"phone": phone, "call_conversion_reporting": True, "call_only": False}
            if offers:
                ext["promotion_extension"] = {"promotion_target": services[0] if services else "Service", "discount_modifier": offers[0][:30]}
            return ext

        # Fallback to template extensions only if AI completely fails
        logger.warning("AI extensions failed — using template fallback")
        return self._generate_expert_extensions(profile, services, offers, usps, competitor_insights)

    def _generate_expert_headlines(
        self, service: str, locations: List[str], offers: List[str], usps: List[str],
        phone: str, tone: str, industry: str, urgency: Optional[str], competitor_insights: Dict
    ) -> List[str]:
        """15 psychology-driven headlines using urgency, social proof, value props, FOMO, CTAs"""
        svc = service.strip()
        loc = locations[0] if locations else ""
        headlines = []

        # Urgency / Emergency triggers (for high-urgency industries)
        if urgency == "high" or industry in ("locksmith", "plumbing", "hvac"):
            headlines += [
                f"24/7 Emergency {svc}",
                f"Fast {svc} - Call Now",
                f"{svc} Open Now - 30 Min",
                f"Locked Out? Call Us Now",
            ]

        # Location-specific authority
        if loc:
            headlines += [
                f"{svc} in {loc}",
                f"#{1} {svc} in {loc}",
                f"{loc}'s Trusted {svc}",
            ]

        # Social proof & trust signals
        headlines += [
            f"5-Star Rated {svc}",
            f"Licensed & Insured {svc}",
            f"500+ Happy Customers",
            f"Trusted {svc} Experts",
        ]

        # Value propositions from USPs
        for usp in usps[:2]:
            if usp and len(usp) <= 30:
                headlines.append(usp)

        # Offer-based headlines (FOMO)
        for offer in offers[:2]:
            if offer and len(offer) <= 30:
                headlines.append(offer)

        # Competitor differentiation angles
        gaps = competitor_insights.get("differentiation_angles", [])
        for gap in gaps[:2]:
            if len(gap) <= 30:
                headlines.append(gap.title())

        # CTAs
        headlines += [
            f"Get Free {svc} Quote",
            f"Call for Same-Day {svc}",
            f"{svc} - Book Online Now",
        ]

        # Deduplicate and enforce 30-char Google limit
        seen = set()
        result = []
        for h in headlines:
            h = h[:30]
            if h not in seen:
                seen.add(h)
                result.append(h)

        return result[:15]

    def _generate_expert_descriptions(
        self, service: str, locations: List[str], offers: List[str], usps: List[str],
        phone: str, tone: str, industry: str, urgency: Optional[str], competitor_insights: Dict
    ) -> List[str]:
        """4 psychology-driven descriptions: problem-agitate-solve, social proof, offer, local"""
        svc = service.strip()
        loc = locations[0] if locations else "your area"
        loc_list = ", ".join(locations[:3]) if locations else "your area"
        usp_str = " | ".join(usps[:3]) if usps else "Licensed & Insured | Fast Response | Satisfaction Guaranteed"
        offer_str = offers[0] if offers else "Free Estimate"
        gaps = competitor_insights.get("differentiation_angles", [])
        diff = gaps[0].title() if gaps else "Upfront Pricing"

        descriptions = []

        # 1) Urgency + trust (emergency industries)
        if urgency == "high" or industry in ("locksmith", "plumbing", "hvac"):
            descriptions.append(
                f"Stuck? Our {svc} team arrives fast — 24/7, no extra charge for nights/weekends. "
                f"Licensed, insured & background-checked. Call now!"
            )
        else:
            descriptions.append(
                f"Professional {svc} serving {loc}. {usp_str}. "
                f"Call today for a fast, no-obligation quote!"
            )

        # 2) Social proof + differentiation
        descriptions.append(
            f"5-star rated {svc} with 500+ reviews. {diff}. "
            f"Serving {loc_list} — same-day availability. Book online or call!"
        )

        # 3) Offer-driven with urgency
        descriptions.append(
            f"{offer_str} — limited spots available. Trusted {svc} experts near you. "
            f"Licensed & insured. Satisfaction guaranteed or we make it right."
        )

        # 4) Local authority
        descriptions.append(
            f"Locally owned {svc} in {loc}. We know the area, the codes & your neighbors trust us. "
            f"{usp_str}. No hidden fees — ever."
        )

        # Enforce 90-char Google RSA description limit
        return [d[:90] for d in descriptions[:4]]

    def _generate_expert_extensions(
        self, profile: BusinessProfile, services: List[str], offers: List[str],
        usps: List[str], competitor_insights: Dict
    ) -> Dict[str, Any]:
        """Expert-level extensions: sitelinks, callouts, structured snippets, call, price"""
        website = profile.website_url or ""
        industry = (profile.industry_classification or "service").lower()
        gaps = competitor_insights.get("differentiation_angles", [])

        # Sitelinks — high-value pages with compelling descriptions
        sitelinks = [
            {"text": "Get Free Estimate", "desc1": "No obligation quote", "desc2": "Response within 1 hour",
             "url": f"{website}/contact"},
            {"text": "See Our Reviews", "desc1": "500+ 5-star reviews", "desc2": "Verified Google & Yelp",
             "url": f"{website}/reviews"},
            {"text": "Our Services", "desc1": f"Full {industry} service menu", "desc2": "Residential & commercial",
             "url": f"{website}/services"},
            {"text": "About Our Team", "desc1": "Licensed & background-checked", "desc2": "10+ years experience",
             "url": f"{website}/about"},
            {"text": "Service Areas", "desc1": "See if we cover your area", "desc2": "Fast local response",
             "url": f"{website}/service-areas"},
            {"text": "Emergency Service", "desc1": "Available 24/7", "desc2": "30-min response time",
             "url": f"{website}/emergency"},
        ]

        # Callouts — trust signals + differentiators from competitor gap analysis
        callouts = [
            "Licensed & Insured",
            "Same-Day Service",
            "No Hidden Fees",
            "Satisfaction Guaranteed",
            "Background-Checked Techs",
            "Free Estimates",
            "Locally Owned",
            "24/7 Availability",
        ]
        # Add competitor differentiation angles as callouts
        for gap in gaps[:3]:
            if gap.title() not in callouts:
                callouts.append(gap.title())

        # Add USPs as callouts
        for usp in usps[:3]:
            if usp and usp not in callouts:
                callouts.append(usp[:25])

        # Structured snippets
        structured_snippets = [
            {"header": "Services", "values": [s[:25] for s in services[:8]]},
        ]
        if industry in ("locksmith", "plumbing", "hvac", "auto_repair"):
            structured_snippets.append({
                "header": "Service Areas",
                "values": ["Residential", "Commercial", "Emergency", "Same-Day"],
            })

        result: Dict[str, Any] = {
            "sitelinks": sitelinks[:6],
            "callouts": callouts[:10],
            "structured_snippets": structured_snippets,
            "recommended": ["call_extension", "location_extension", "sitelink", "callout", "structured_snippet"],
        }

        if profile.phone:
            result["call_extension"] = {
                "phone": profile.phone,
                "call_conversion_reporting": True,
                "call_only": False,
            }

        # Price extensions for non-emergency industries
        if offers:
            result["promotion_extension"] = {
                "promotion_target": services[0] if services else "Service",
                "discount_modifier": offers[0][:30] if offers else "",
            }

        return result

    def _explain_campaign_type(self, campaign_type: str, intent: Dict) -> str:
        reasons = {
            "SEARCH": "Search campaigns target high-intent users actively searching for your exact service. Every click is someone raising their hand to buy.",
            "CALL": "Call-only campaigns are the highest ROI format for emergency services — they eliminate the landing page step and connect the caller directly. Critical for locksmith, plumbing, HVAC.",
            "PERFORMANCE_MAX": "Performance Max runs across Search, Display, YouTube, Maps and Gmail simultaneously. Best for broad awareness + conversion volume at scale.",
            "REMARKETING": "Remarketing re-engages the 95% of visitors who didn't convert. Extremely cost-efficient — these users already know your brand.",
        }
        return reasons.get(campaign_type, "Selected based on business profile, conversion goal, and intent analysis.")
