"""
Multi-Agent Campaign Creation Pipeline
======================================

6 specialized Claude agents collaborate to build expert-quality Google Ads campaigns.
Each agent focuses deeply on one aspect, receives rich context, and produces
validated output that feeds into the next stage.

Pipeline:
  1. Strategist Agent (sequential) — campaign architecture
  2. Keyword Research Agent  ─┐
  3. Targeting Agent          ├─ parallel
  4. Extensions Agent        ─┘
  5. Ad Copy Agent (sequential, needs keywords)
  6. QA Agent (sequential, reviews assembled spec)
"""

import json
import time
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import anthropic
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.models.operator import OperatorMessage
from app.models.business_profile import BusinessProfile
from app.models.pipeline_execution_log import PipelineExecutionLog
from app.services.operator.ahrefs_keyword_service import AhrefsKeywordService
from app.services.operator.llm_fallback_service import LLMFallbackService

logger = structlog.get_logger()


# ── PROGRAMMATIC QA CHECKS (run BEFORE LLM QA) ───────────────────
def _programmatic_qa(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Hard validation of campaign spec — character limits, counts, duplicates.
    Returns list of issues found. These are FACTS, not opinions.
    """
    issues = []

    # ── Character limits ──
    for ag_idx, ag in enumerate(spec.get("ad_groups", [])):
        for ad_idx, ad in enumerate(ag.get("ads", [])):
            for h_idx, h in enumerate(ad.get("headlines", [])):
                text = h if isinstance(h, str) else h.get("text", "") if isinstance(h, dict) else str(h)
                if len(text) > 30:
                    issues.append({
                        "severity": "critical",
                        "field": f"ad_groups[{ag_idx}].ads[{ad_idx}].headlines[{h_idx}]",
                        "message": f"Headline '{text[:40]}...' is {len(text)} chars (max 30)",
                        "fix": text[:30],
                        "check": "char_limit",
                    })
            for d_idx, d in enumerate(ad.get("descriptions", [])):
                text = d if isinstance(d, str) else d.get("text", "") if isinstance(d, dict) else str(d)
                if len(text) > 90:
                    issues.append({
                        "severity": "critical",
                        "field": f"ad_groups[{ag_idx}].ads[{ad_idx}].descriptions[{d_idx}]",
                        "message": f"Description '{text[:50]}...' is {len(text)} chars (max 90)",
                        "fix": text[:90],
                        "check": "char_limit",
                    })

            # ── Minimum counts ──
            h_count = len(ad.get("headlines", []))
            d_count = len(ad.get("descriptions", []))
            if h_count < 3:
                issues.append({
                    "severity": "critical",
                    "field": f"ad_groups[{ag_idx}].ads[{ad_idx}].headlines",
                    "message": f"Only {h_count} headlines (Google requires minimum 3)",
                    "check": "min_count",
                })
            if d_count < 2:
                issues.append({
                    "severity": "critical",
                    "field": f"ad_groups[{ag_idx}].ads[{ad_idx}].descriptions",
                    "message": f"Only {d_count} descriptions (Google requires minimum 2)",
                    "check": "min_count",
                })

            # ── Duplicate headlines within same ad ──
            headline_texts = []
            for h in ad.get("headlines", []):
                text = (h if isinstance(h, str) else h.get("text", "")).lower().strip()
                if text in headline_texts:
                    issues.append({
                        "severity": "warning",
                        "field": f"ad_groups[{ag_idx}].ads[{ad_idx}].headlines",
                        "message": f"Duplicate headline: '{text}'",
                        "check": "duplicate",
                    })
                headline_texts.append(text)

            # ── Missing final_urls ──
            urls = ad.get("final_urls", ad.get("final_url", ""))
            if isinstance(urls, list):
                if not urls or not urls[0]:
                    issues.append({
                        "severity": "critical",
                        "field": f"ad_groups[{ag_idx}].ads[{ad_idx}].final_urls",
                        "message": "Missing final_url — ad will fail to deploy",
                        "check": "missing_url",
                    })
            elif not urls:
                issues.append({
                    "severity": "critical",
                    "field": f"ad_groups[{ag_idx}].ads[{ad_idx}].final_url",
                    "message": "Missing final_url — ad will fail to deploy",
                    "check": "missing_url",
                })

    # ── Keyword cross-contamination (same keyword in multiple ad groups) ──
    kw_to_ag = {}
    for ag_idx, ag in enumerate(spec.get("ad_groups", [])):
        for kw in ag.get("keywords", []):
            text = kw.get("text", "") if isinstance(kw, dict) else str(kw)
            text_lower = text.lower().strip()
            if text_lower in kw_to_ag:
                issues.append({
                    "severity": "warning",
                    "field": f"ad_groups[{ag_idx}].keywords",
                    "message": f"Keyword '{text}' also in ad group {kw_to_ag[text_lower]}",
                    "check": "cross_contamination",
                })
            else:
                kw_to_ag[text_lower] = ag.get("name", f"#{ag_idx}")

    # ── Negative keywords blocking own keywords ──
    all_keywords = set()
    for ag in spec.get("ad_groups", []):
        for kw in ag.get("keywords", []):
            text = kw.get("text", "").lower() if isinstance(kw, dict) else str(kw).lower()
            all_keywords.add(text)
        for neg in ag.get("negative_keywords", []):
            neg_text = neg.get("text", "").lower() if isinstance(neg, dict) else str(neg).lower()
            for pos_kw in all_keywords:
                if neg_text in pos_kw:
                    issues.append({
                        "severity": "critical",
                        "field": "negative_keywords",
                        "message": f"Negative '{neg_text}' blocks positive keyword '{pos_kw}'",
                        "check": "neg_blocking",
                    })
                    break  # One per negative is enough

    # ── Sitelink limits ──
    for sl_idx, sl in enumerate(spec.get("sitelinks", [])):
        if len(sl.get("link_text", "")) > 25:
            issues.append({
                "severity": "critical",
                "field": f"sitelinks[{sl_idx}].link_text",
                "message": f"Sitelink text '{sl['link_text']}' is {len(sl['link_text'])} chars (max 25)",
                "fix": sl["link_text"][:25],
                "check": "char_limit",
            })
        for desc_key in ("description1", "description2"):
            if sl.get(desc_key) and len(sl[desc_key]) > 35:
                issues.append({
                    "severity": "critical",
                    "field": f"sitelinks[{sl_idx}].{desc_key}",
                    "message": f"Sitelink desc '{sl[desc_key][:30]}...' is {len(sl[desc_key])} chars (max 35)",
                    "fix": sl[desc_key][:35],
                    "check": "char_limit",
                })

    # ── Callout limits ──
    for c_idx, c in enumerate(spec.get("callouts", [])):
        text = c if isinstance(c, str) else str(c)
        if len(text) > 25:
            issues.append({
                "severity": "critical",
                "field": f"callouts[{c_idx}]",
                "message": f"Callout '{text}' is {len(text)} chars (max 25)",
                "fix": text[:25],
                "check": "char_limit",
            })

    # ── Budget sanity ──
    budget_micros = spec.get("campaign", {}).get("budget_micros", 0)
    budget_daily = budget_micros / 1_000_000
    if budget_daily <= 0:
        issues.append({"severity": "critical", "field": "campaign.budget_micros", "message": "Budget is $0", "check": "budget"})
    elif budget_daily > 5000:
        issues.append({"severity": "warning", "field": "campaign.budget_micros", "message": f"Budget ${budget_daily}/day seems very high for local business", "check": "budget"})

    return issues


def _compute_keyword_headline_match(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mathematical scoring of keyword-to-headline relevance per ad group.
    Returns match scores and suggestions.
    """
    results = {}
    for ag in spec.get("ad_groups", []):
        ag_name = ag.get("name", "Unknown")
        keywords = [kw.get("text", "").lower() if isinstance(kw, dict) else str(kw).lower()
                    for kw in ag.get("keywords", [])]
        headlines = []
        for ad in ag.get("ads", []):
            for h in ad.get("headlines", []):
                text = h.lower() if isinstance(h, str) else h.get("text", "").lower() if isinstance(h, dict) else ""
                headlines.append(text)

        if not keywords or not headlines:
            results[ag_name] = {"score": 0, "matched": 0, "total_keywords": len(keywords)}
            continue

        # Count how many keyword root terms appear in at least one headline
        matched = 0
        unmatched_keywords = []
        for kw in keywords:
            # Extract root terms (skip stop words)
            stop_words = {"in", "the", "a", "an", "for", "and", "or", "near", "me", "my", "at", "on", "to"}
            kw_terms = [t for t in kw.split() if t not in stop_words and len(t) > 2]
            found = False
            for term in kw_terms:
                if any(term in h for h in headlines):
                    found = True
                    break
            if found:
                matched += 1
            else:
                unmatched_keywords.append(kw)

        score = round((matched / len(keywords)) * 100) if keywords else 0
        results[ag_name] = {
            "score": score,
            "matched": matched,
            "total_keywords": len(keywords),
            "unmatched_keywords": unmatched_keywords[:5],  # Top 5 for review
        }

    return results


class CampaignAgentPipeline:
    """Multi-agent Claude pipeline for expert-quality campaign creation."""

    def __init__(self, db: AsyncSession, tenant_id: str, customer_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.customer_id = customer_id
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.llm = LLMFallbackService()
        # Pipeline agents use Opus for maximum quality — keyword strategy,
        # ad copy, and QA are where model intelligence directly impacts ROI
        self.model = "claude-opus-4-6"
        self.conversation_id: Optional[str] = None
        self.ahrefs = AhrefsKeywordService()
        # Per-agent timing for execution log
        self._agent_timings: List[Dict] = []
        self._pipeline_start: float = 0

    # ── ORCHESTRATOR ─────────────────────────────────────────────

    async def run(
        self,
        user_prompt: str,
        account_context: Dict[str, Any],
        conversation_id: str,
    ) -> Dict[str, Any]:
        """Execute the full 6-agent pipeline. Returns deploy_full_campaign spec."""
        self.conversation_id = conversation_id
        self._pipeline_start = time.time()
        self._agent_timings = []
        logger.info("Campaign pipeline started", conversation_id=conversation_id)

        # Initialize execution log
        exec_log = PipelineExecutionLog(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_id,
            customer_id=self.customer_id,
            conversation_id=conversation_id,
            service_type="campaign_pipeline",
            status="running",
            input_summary={"user_prompt": user_prompt[:500], "account_context_keys": list(account_context.keys())},
            model_used=self.model,
        )
        self.db.add(exec_log)
        try:
            await self.db.flush()
        except Exception:
            pass

        # Gather all context the agents will need
        context = await self._gather_context(account_context)

        # ── Agent 1: Strategist (everything depends on this) ──
        await self._emit_progress("Strategist", "running", "Analyzing your business, competitors, and existing campaigns to design the optimal campaign architecture...")
        t0 = time.time()
        strategy = await self._agent_strategist(context, user_prompt)
        self._agent_timings.append({"agent": "Strategist", "duration_ms": int((time.time() - t0) * 1000), "status": "done" if strategy else "error"})
        if not strategy:
            await self._emit_progress("Strategist", "error", "Failed to generate strategy")
            await self._finalize_log(exec_log, "failed", error="Strategist agent failed")
            return self._fallback_spec(user_prompt, context)
        await self._emit_progress("Strategist", "done",
            f"{strategy.get('campaign_type', 'SEARCH')} campaign \u2022 ${strategy.get('budget_daily', 50)}/day \u2022 {len(strategy.get('services', []))} ad groups")

        # ── Ahrefs Enrichment (real keyword data) ──────────────
        ahrefs_data = {}
        if self.ahrefs.available:
            await self._emit_progress("Keyword Research", "running", "Pulling real search volume & CPC data from Ahrefs...")
            t0 = time.time()
            competitor_domains = [
                c.get("domain", "") for c in context.get("competitors", {}).get("top_competitors", [])[:3]
            ]
            ahrefs_data = await self.ahrefs.enrich_keyword_research(
                services=strategy.get("services", []),
                locations=strategy.get("locations", []),
                business_website=context["business"].get("website", ""),
                competitor_domains=competitor_domains,
                country="us",
            )
            self._agent_timings.append({"agent": "Ahrefs Enrichment", "duration_ms": int((time.time() - t0) * 1000), "status": "done", "keywords_found": ahrefs_data.get("summary", {}).get("total_keywords_found", 0)})
            context["ahrefs"] = ahrefs_data
            exec_log.ahrefs_data = ahrefs_data.get("summary", {})
            ahrefs_count = ahrefs_data.get("summary", {}).get("total_keywords_found", 0)
            if ahrefs_count > 0:
                await self._emit_progress("Keyword Research", "running", f"Found {ahrefs_count} real keywords from Ahrefs (avg CPC: ${ahrefs_data.get('summary', {}).get('avg_cpc', 0):.2f}). Now building strategy...")
        else:
            await self._emit_progress("Keyword Research", "running", f"Building tiered keyword strategy across {len(strategy.get('services', []))} services...")

        # ── Agents 2-4: Parallel (independent of each other) ──
        await self._emit_progress("Targeting", "running", "Configuring geo-targeting, device bids, and ad schedule...")
        await self._emit_progress("Extensions", "running", "Generating sitelinks, callouts, and structured snippets...")

        t0 = time.time()
        keywords, targeting, extensions = await asyncio.gather(
            self._agent_keyword_research(context, strategy),
            self._agent_targeting(context, strategy),
            self._agent_extensions(context, strategy),
        )
        parallel_ms = int((time.time() - t0) * 1000)
        self._agent_timings.append({"agent": "Keyword Research", "duration_ms": parallel_ms, "status": "done" if keywords else "error"})
        self._agent_timings.append({"agent": "Targeting", "duration_ms": parallel_ms, "status": "done" if targeting else "error"})
        self._agent_timings.append({"agent": "Extensions", "duration_ms": parallel_ms, "status": "done" if extensions else "error"})

        kw_count = len(keywords.get("keywords", [])) if keywords else 0
        neg_count = len(keywords.get("negatives", [])) if keywords else 0
        await self._emit_progress("Keyword Research", "done", f"{kw_count} keywords \u2022 {neg_count} negatives \u2022 tiered by intent")
        await self._emit_progress("Targeting", "done",
            f"{targeting.get('geo', {}).get('radius_miles', 40)}-mile radius \u2022 Mobile +{targeting.get('device_bids', {}).get('mobile_bid_adj', 0)}%"
            if targeting else "Targeting configured")
        await self._emit_progress("Extensions", "done",
            f"{len(extensions.get('sitelinks', []))} sitelinks \u2022 {len(extensions.get('callouts', []))} callouts"
            if extensions else "Extensions generated")

        # ── Agent 5: Ad Copy (needs keywords for ad group alignment) ──
        await self._emit_progress("Ad Copy", "running", f"Writing 15 headlines + 4 descriptions per ad group with pinning strategy...")
        t0 = time.time()
        ad_copy = await self._agent_ad_copy(context, strategy, keywords or {})
        self._agent_timings.append({"agent": "Ad Copy", "duration_ms": int((time.time() - t0) * 1000), "status": "done" if ad_copy else "error"})
        ag_count = len(ad_copy.get("ad_groups", [])) if ad_copy else 0
        await self._emit_progress("Ad Copy", "done", f"{ag_count} ad groups with full RSA copy")

        # ── Assemble the full spec ──
        spec = self._assemble_spec(
            strategy or {},
            keywords or {},
            ad_copy or {},
            targeting or {},
            extensions or {},
        )

        # ── Agent 6: QA Review ──
        await self._emit_progress("Quality Assurance", "running", "Auditing compliance, keyword-ad relevance, character limits, and campaign structure...")
        t0 = time.time()
        qa_result = await self._agent_qa(spec, context, user_prompt)
        self._agent_timings.append({"agent": "Quality Assurance", "duration_ms": int((time.time() - t0) * 1000), "status": "done" if qa_result else "error"})
        if qa_result:
            score = qa_result.get("score", 0)
            spec = self._apply_qa_fixes(spec, qa_result)
            prog_count = len(qa_result.get("programmatic_issues", []))
            strat_count = len(qa_result.get("strategic_issues", []))
            kw_match = qa_result.get("avg_keyword_match", 0)
            await self._emit_progress("Quality Assurance", "done",
                f"Score: {score}/100 ({qa_result.get('grade', '?')}) \u2022 "
                f"{prog_count} programmatic + {strat_count} strategic issues \u2022 "
                f"Keyword-headline match: {kw_match}% \u2022 Auto-fixed")
        else:
            await self._emit_progress("Quality Assurance", "done", "Review complete")

        # ── Finalize execution log ──
        output_summary = {
            "campaign_name": spec.get("campaign", {}).get("name"),
            "ad_groups": len(spec.get("ad_groups", [])),
            "total_keywords": sum(len(ag.get("keywords", [])) for ag in spec.get("ad_groups", [])),
            "total_negatives": sum(len(ag.get("negative_keywords", [])) for ag in spec.get("ad_groups", [])),
            "qa_score": qa_result.get("score") if qa_result else None,
            "budget_daily": spec.get("campaign", {}).get("budget_micros", 0) / 1_000_000,
            "sitelinks": len(spec.get("sitelinks", [])),
            "callouts": len(spec.get("callouts", [])),
        }
        await self._finalize_log(exec_log, "completed", output_summary=output_summary, output_full=spec)

        logger.info("Campaign pipeline complete",
            campaign_name=spec.get("campaign", {}).get("name"),
            ad_groups=len(spec.get("ad_groups", [])),
        )
        return spec

    async def _finalize_log(
        self, log: PipelineExecutionLog, status: str,
        output_summary: Optional[Dict] = None, output_full: Optional[Dict] = None,
        error: Optional[str] = None,
    ):
        """Finalize the pipeline execution log."""
        log.status = status
        log.completed_at = datetime.now(timezone.utc)
        log.duration_seconds = round(time.time() - self._pipeline_start, 2)
        log.agent_results = self._agent_timings
        if output_summary:
            log.output_summary = output_summary
        if output_full:
            log.output_full = output_full
        if error:
            log.error_message = error
        try:
            await self.db.flush()
        except Exception:
            pass

    # ── CONTEXT GATHERING ────────────────────────────────────────

    async def _gather_context(self, account_context: Dict) -> Dict[str, Any]:
        """Load business profile, competitor intel, and format existing campaign data."""
        # Business profile
        bp_result = await self.db.execute(
            select(BusinessProfile).where(BusinessProfile.tenant_id == self.tenant_id)
        )
        profile = bp_result.scalar_one_or_none()

        biz = {}
        if profile:
            biz = {
                "name": getattr(profile, "description", "") or "",
                "website": profile.website_url or "",
                "phone": profile.phone or "",
                "industry": profile.industry_classification or "",
                "services": profile.services_json or [],
                "locations": profile.locations_json or [],
                "usps": profile.usp_json or [],
                "offers": profile.offers_json or [],
                "trust_signals": profile.trust_signals_json or [],
                "brand_voice": profile.brand_voice_json or {},
                "city": profile.city or "",
                "state": profile.state or "",
                "service_radius_miles": profile.service_radius_miles or 40,
                "years_experience": profile.years_experience or 0,
                "google_rating": profile.google_rating or 0,
                "review_count": profile.review_count or 0,
                "license_info": profile.license_info or "",
                "address": profile.address or "",
                "primary_goal": profile.primary_conversion_goal or "calls",
                "avg_ticket": profile.avg_ticket_estimate or 0,
            }

        # Competitor intel
        competitor_summary = {}
        try:
            from app.services.competitor_intel_service import CompetitorIntelService
            comp_svc = CompetitorIntelService(self.db, self.tenant_id)
            competitor_summary = await comp_svc.get_market_summary()
        except Exception as e:
            logger.warning("Could not load competitor intel", error=str(e))

        # Performance feedback from past campaigns (learnings)
        feedback_context = {}
        try:
            from app.services.operator.performance_feedback_service import PerformanceFeedbackService
            feedback_svc = PerformanceFeedbackService(self.db, self.tenant_id)
            feedback_context = await feedback_svc.get_pipeline_learnings(
                services=biz.get("services", []),
            )
            if feedback_context.get("top_performing_headlines"):
                logger.info("Loaded performance feedback",
                    headlines=len(feedback_context.get("top_performing_headlines", [])),
                    keywords=len(feedback_context.get("top_performing_keywords", [])),
                )
        except Exception as e:
            logger.warning("Could not load performance feedback", error=str(e))

        return {
            "business": biz,
            "account": account_context,
            "competitors": competitor_summary,
            "feedback": feedback_context,
        }

    # ── PROGRESS MESSAGES ────────────────────────────────────────

    async def _emit_progress(self, agent_name: str, status: str, detail: str):
        """Insert a progress message into the conversation."""
        if not self.conversation_id:
            return
        msg = OperatorMessage(
            id=str(uuid.uuid4()),
            conversation_id=self.conversation_id,
            role="assistant",
            content=f"{agent_name}: {detail}",
            structured_payload={
                "type": "pipeline_progress",
                "agent": agent_name,
                "status": status,
                "detail": detail,
            },
        )
        self.db.add(msg)
        try:
            await self.db.flush()
        except Exception:
            pass  # Non-critical if progress message fails

    # ── CLAUDE API HELPER ────────────────────────────────────────

    async def _call_claude_json(
        self, system: str, user_msg: str,
        max_tokens: int = 4096, temperature: float = 0.5,
    ) -> Optional[Dict]:
        """Call Claude API with GPT-4o fallback. Parse JSON response."""
        result = await self.llm.call_json(
            system=system,
            user_msg=user_msg,
            max_tokens=max_tokens,
            temperature=temperature,
            preferred_model=self.model,
        )
        if result is None:
            return None
        if result.get("fallback"):
            logger.info("Pipeline agent used fallback model", model=result.get("model_used"))
        return result.get("data")

    # ── AGENT 1: STRATEGIST ──────────────────────────────────────

    async def _agent_strategist(self, context: Dict, user_prompt: str) -> Optional[Dict]:
        biz = context["business"]
        account = context["account"]
        competitors = context.get("competitors", {})

        # Format existing campaigns for context
        campaigns_text = "No existing campaigns found."
        if account.get("campaigns"):
            lines = []
            for c in account["campaigns"][:10]:
                lines.append(f"  [{c.get('status', '?')}] {c.get('name', '?')} \u2014 Budget:${c.get('budget_daily', '?')}/day | Cost:${c.get('cost', 0):.0f} | Conv:{c.get('conversions', 0)} | CPA:${c.get('cpa', 0):.0f}")
            campaigns_text = "\n".join(lines)

        system = """You are a senior Google Ads strategist. You're designing the architecture for a new campaign.

Your job is to make ONE set of decisions:
- What type of campaign (SEARCH, CALL, PERFORMANCE_MAX)
- What services to target (each becomes its own ad group for tight theming)
- What budget and bidding strategy
- Campaign naming convention
- What the strategic angle is (why THIS campaign, why NOW)

Think step by step:
1. What does the user actually want? Parse their intent carefully.
2. Look at existing campaigns — what's already covered? Don't duplicate. Fill gaps.
3. What services would be MOST profitable? Consider the business's specialties.
4. What budget makes sense given the competitive landscape and ticket size?
5. Is this a SEARCH campaign (intent-driven) or CALL campaign (emergency/mobile)?

Be SPECIFIC. Don't be generic. If the user says "BMW specialized services" and the business is an automotive locksmith, think about what BMW owners actually search for: FRM repair, key programming, comfort access, CAS module, coding. These are HIGH-TICKET services ($500-2000+).

Respond with ONLY valid JSON."""

        user_msg = f"""USER REQUEST: "{user_prompt}"

BUSINESS CONTEXT:
  Name: {biz.get('name', 'Unknown')}
  Industry: {biz.get('industry', 'Unknown')}
  Services offered: {json.dumps(biz.get('services', []))}
  Locations: {biz.get('city', '')}, {biz.get('state', '')} (radius: {biz.get('service_radius_miles', 40)} miles)
  Avg ticket: ${biz.get('avg_ticket', 0)}
  Primary goal: {biz.get('primary_goal', 'calls')}
  Phone: {biz.get('phone', '')}
  Website: {biz.get('website', '')}

EXISTING CAMPAIGNS:
{campaigns_text}

COMPETITIVE LANDSCAPE:
  Dominant themes: {json.dumps(competitors.get('dominant_themes', []))}
  Opportunity gaps: {json.dumps(competitors.get('opportunity_gaps', []))}
  Top competitors: {json.dumps([c.get('domain', '') for c in competitors.get('top_competitors', [])[:5]])}

{self._format_feedback_for_strategist(context.get('feedback', {}))}
Return this JSON structure:
{{
  "campaign_name": "A.X | [Service Theme] | [Location]",
  "campaign_type": "SEARCH" or "CALL",
  "objective": "calls" or "leads",
  "services": ["Service 1", "Service 2", "Service 3"],
  "locations": ["City 1", "City 2"],
  "budget_daily": 50,
  "budget_micros": 50000000,
  "bidding_strategy": "MAXIMIZE_CONVERSIONS",
  "target_cpa_micros": 0,
  "reasoning": "2-3 sentences on WHY these choices",
  "overlap_risk": "none" or "low" or "high — explain what overlaps",
  "profit_potential": "Estimated ticket size and margin for these services"
}}"""

        return await self._call_claude_json(system, user_msg, max_tokens=2048, temperature=0.4)

    # ── AGENT 2: KEYWORD RESEARCH ────────────────────────────────

    async def _agent_keyword_research(self, context: Dict, strategy: Dict) -> Optional[Dict]:
        biz = context["business"]
        competitors = context.get("competitors", {})
        ahrefs = context.get("ahrefs", {})
        services = strategy.get("services", [])
        locations = strategy.get("locations", biz.get("locations", []))

        # Build Ahrefs data section for the prompt
        ahrefs_section = ""
        if ahrefs and ahrefs.get("seed_keywords"):
            # Format real keyword data for Claude
            top_seeds = sorted(
                ahrefs.get("seed_keywords", []),
                key=lambda k: k.get("volume", 0), reverse=True,
            )[:30]
            seed_lines = [
                f"  {kw['keyword']} — vol:{kw.get('volume', 0)} CPC:${kw.get('cpc', 0):.2f} diff:{kw.get('difficulty', 0)}"
                for kw in top_seeds
            ]

            top_expanded = sorted(
                ahrefs.get("expanded_keywords", []),
                key=lambda k: k.get("volume", 0), reverse=True,
            )[:40]
            expanded_lines = [
                f"  {kw['keyword']} — vol:{kw.get('volume', 0)} CPC:${kw.get('cpc', 0):.2f} [from: {kw.get('parent_service', kw.get('source', ''))}]"
                for kw in top_expanded
            ]

            top_suggestions = sorted(
                ahrefs.get("search_suggestions", []),
                key=lambda k: k.get("volume", 0), reverse=True,
            )[:20]
            suggestion_lines = [
                f"  {kw['keyword']} — vol:{kw.get('volume', 0)} CPC:${kw.get('cpc', 0):.2f}"
                for kw in top_suggestions
            ]

            comp_kws = sorted(
                ahrefs.get("competitor_keywords", []),
                key=lambda k: k.get("volume", 0), reverse=True,
            )[:25]
            comp_lines = [
                f"  {kw['keyword']} — vol:{kw.get('volume', 0)} CPC:${kw.get('cpc', 0):.2f} [{kw.get('competitor_domain', '')}]"
                for kw in comp_kws
            ]

            ahrefs_section = f"""
REAL KEYWORD DATA FROM AHREFS (use this as ground truth for volume and CPC):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SEED KEYWORDS (real search volume & CPC):
{chr(10).join(seed_lines)}

EXPANDED KEYWORD IDEAS:
{chr(10).join(expanded_lines)}

AUTOCOMPLETE SUGGESTIONS (what people actually type):
{chr(10).join(suggestion_lines)}

COMPETITOR PAID KEYWORDS (what competitors are bidding on):
{chr(10).join(comp_lines)}

IMPORTANT: Prioritize keywords with volume >= 30 and reasonable CPC.
Keywords from Ahrefs with 0 volume should be deprioritized.
Use CPC data to gauge competitiveness — high CPC = high commercial intent.
"""

        system = f"""You are a Google Ads keyword research expert with deep knowledge of search intent.

Your job: build a COMPREHENSIVE keyword list for a Google Ads campaign. You think about keywords the way a real searcher types — not marketing jargon, but actual queries people use when they need this service.

{"You have REAL keyword data from Ahrefs below. USE IT. Prioritize keywords with proven search volume over guesses. But also add problem-based and long-tail keywords that Ahrefs might not capture." if ahrefs_section else ""}

CRITICAL RULES:
1. SEGMENT BY SERVICE: Each service becomes its own ad group. Keywords MUST be unique per service. NO keyword can appear in two services — this causes internal competition and tanks Quality Score.

2. TIER YOUR KEYWORDS BY INTENT:
   - EMERGENCY (highest bid): "emergency [X]", "[X] help now", "24/7 [X]" — EXACT match
   - HIGH INTENT (ready to buy): "[X] near me", "[X] service", "hire [X]" — EXACT match
   - MEDIUM INTENT (researching): "best [X]", "[X] cost", "how much [X]" — PHRASE match
   - LOCAL (geo-modified): "[X] in [city]", "[city] [X]" — EXACT match
   - SERVICE-SPECIFIC (long-tail): problem-specific queries real people type — PHRASE match

3. THINK LIKE THE SEARCHER: Someone whose BMW key stopped working doesn't search "BMW key programming" — they search "bmw key not working", "lost bmw key", "bmw key fob dead". Include PROBLEM-BASED keywords, not just service-based ones.

4. NEGATIVES ARE CRITICAL: Block DIY, jobs, training, free, complaints, tools, parts-only, used. Also block adjacent services you DON'T offer.

5. MINIMUM: 20 keywords per service, 20 negatives total. More is better for coverage.

{"6. INCLUDE AHREFS VOLUME: For keywords from Ahrefs data, include the real volume in an 'ahrefs_volume' field." if ahrefs_section else ""}

Respond with ONLY valid JSON."""

        user_msg = f"""CAMPAIGN STRATEGY:
  Type: {strategy.get('campaign_type', 'SEARCH')}
  Services (each = 1 ad group): {json.dumps(services)}
  Target locations: {json.dumps(locations)}

BUSINESS:
  Industry: {biz.get('industry', '')}
  Full service list: {json.dumps(biz.get('services', []))}

COMPETITOR THEMES (what they bid on):
  {json.dumps(competitors.get('dominant_themes', []))}
GAPS (what they DON'T target):
  {json.dumps(competitors.get('opportunity_gaps', []))}
{ahrefs_section}
Return this JSON:
{{
  "keywords": [
    {{"text": "keyword phrase", "match_type": "EXACT"|"PHRASE", "tier": "emergency"|"high"|"medium"|"local"|"service", "service": "exact service name", "ahrefs_volume": 0, "ahrefs_cpc": 0}},
    ...
  ],
  "negatives": [
    {{"text": "negative term", "match_type": "PHRASE"}},
    ...
  ],
  "total_keywords": N,
  "total_negatives": N,
  "tiers": {{"emergency": N, "high": N, "medium": N, "local": N, "service": N}},
  "keyword_rationale": "Brief strategy explanation",
  "ahrefs_used": {"true" if ahrefs_section else "false"}
}}

IMPORTANT: Every keyword MUST have a "service" field matching exactly one of: {json.dumps(services)}"""

        return await self._call_claude_json(system, user_msg, max_tokens=8192, temperature=0.6)

    # ── AGENT 3: TARGETING ───────────────────────────────────────

    async def _agent_targeting(self, context: Dict, strategy: Dict) -> Optional[Dict]:
        biz = context["business"]

        system = """You are a Google Ads targeting specialist. You configure geo-targeting, device bids, and ad schedules to maximize ROI.

Think about the BUSINESS TYPE to make targeting decisions:
- Emergency services (locksmith, plumber, towing): 24/7 schedule, heavy mobile bid boost (+30-50%), radius targeting
- Professional services (lawyer, dentist): business hours + evenings, moderate mobile boost, city-level targeting
- E-commerce: all hours, balanced device bids, broader geo

For device bids, think about HOW people search for this service:
- If they're locked out of their car, they're on their PHONE → mobile +40%
- If they're researching BMW repair options, they might be on desktop → balanced
- Tablets are rarely used for urgent searches → usually neutral or negative

Respond with ONLY valid JSON."""

        user_msg = f"""CAMPAIGN:
  Type: {strategy.get('campaign_type', 'SEARCH')}
  Services: {json.dumps(strategy.get('services', []))}
  Objective: {strategy.get('objective', 'calls')}

BUSINESS LOCATION:
  City: {biz.get('city', '')}, {biz.get('state', '')}
  Address: {biz.get('address', '')}
  Service radius: {biz.get('service_radius_miles', 40)} miles
  Target locations from strategy: {json.dumps(strategy.get('locations', []))}

Return this JSON:
{{
  "geo": {{
    "type": "radius" or "cities",
    "locations": ["City 1", "City 2"],
    "radius_miles": 40,
    "reasoning": "Why this geo config"
  }},
  "device_bids": {{
    "mobile_bid_adj": 30,
    "desktop_bid_adj": 0,
    "tablet_bid_adj": -20,
    "reasoning": "Why these device adjustments"
  }},
  "schedule": {{
    "all_day": true,
    "peak_adjustments": [
      {{"days": ["MONDAY", "TUESDAY"], "hours": "8-20", "bid_adj": 15}},
      {{"days": ["SATURDAY", "SUNDAY"], "hours": "18-23", "bid_adj": 25}}
    ],
    "reasoning": "Why this schedule"
  }}
}}"""

        return await self._call_claude_json(system, user_msg, max_tokens=1536, temperature=0.4)

    # ── AGENT 4: EXTENSIONS ──────────────────────────────────────

    async def _agent_extensions(self, context: Dict, strategy: Dict) -> Optional[Dict]:
        biz = context["business"]
        services = strategy.get("services", [])

        system = """You are a Google Ads extensions specialist. You create sitelinks, callouts, and structured snippets that boost CTR and Ad Rank.

RULES:
- Sitelinks: text max 25 chars, description1 max 35 chars, description2 max 35 chars. Need 4-6.
  Each sitelink should deep-link to a REAL page on the website. Use the website URL to construct logical paths.
  Good: "/services/bmw-programming", "/about", "/contact", "/reviews"
  Bad: "/sitelink1", generic pages

- Callouts: max 25 chars each. Need 6-10. Punchy trust signals. No CTAs (those go in headlines).
  Good: "Licensed & Insured", "24/7 Available", "Same-Day Service"
  Bad: "Call Now", "Click Here", "Best Service Ever"

- Structured snippets: header must be one of Google's approved headers (Services, Brands, Types, etc.)
  Values should be specific services, not generic descriptions.

- Call extension: include the business phone number.

COUNT EVERY CHARACTER. Google rejects assets that exceed limits.

Respond with ONLY valid JSON."""

        user_msg = f"""CAMPAIGN:
  Services: {json.dumps(services)}
  Business: {biz.get('name', '')}
  Website: {biz.get('website', '')}
  Phone: {biz.get('phone', '')}
  USPs: {json.dumps(biz.get('usps', []))}
  Offers: {json.dumps(biz.get('offers', []))}
  Trust signals: {json.dumps(biz.get('trust_signals', []))}
  Years experience: {biz.get('years_experience', 0)}
  Google rating: {biz.get('google_rating', 0)} ({biz.get('review_count', 0)} reviews)
  License: {biz.get('license_info', '')}

Return this JSON:
{{
  "sitelinks": [
    {{"link_text": "text (max 25)", "final_url": "https://...", "description1": "desc (max 35)", "description2": "desc (max 35)"}},
    ...
  ],
  "callouts": ["text (max 25)", ...],
  "structured_snippets": {{
    "header": "Services",
    "values": ["Service 1", "Service 2", ...]
  }},
  "call_extension": {{
    "phone": "{biz.get('phone', '')}",
    "country_code": "US"
  }}
}}"""

        return await self._call_claude_json(system, user_msg, max_tokens=2048, temperature=0.5)

    # ── AGENT 5: AD COPY ─────────────────────────────────────────

    async def _agent_ad_copy(self, context: Dict, strategy: Dict, keywords: Dict) -> Optional[Dict]:
        biz = context["business"]
        competitors = context.get("competitors", {})
        services = strategy.get("services", [])

        # Group keywords by service for per-ad-group context
        kw_by_service = {}
        for kw in keywords.get("keywords", []):
            svc = kw.get("service", "")
            kw_by_service.setdefault(svc, []).append(kw["text"])

        services_context = []
        for svc in services:
            svc_kws = kw_by_service.get(svc, [])[:15]
            services_context.append(f"  AD GROUP: {svc}\n    Keywords: {', '.join(svc_kws)}")

        system = f"""You are an elite Google Ads RSA (Responsive Search Ad) copywriter. You write ads that convert.

You are writing ads for: {biz.get('name', 'this business')}
Industry: {biz.get('industry', '')}
Phone: {biz.get('phone', '')}
Website: {biz.get('website', '')}

YOUR APPROACH — Think like a customer, not a marketer:
Someone searching for "{services[0] if services else 'this service'}" is probably:
- In a stressful situation (locked out, car won't start, module failed)
- Comparing options quickly on their phone
- Looking for PROOF you can actually do this (credentials, experience, reviews)
- Price-sensitive but willing to pay for expertise on premium/specialized work

HEADLINE STRATEGY (15 per ad group, each max 30 chars):
H1-H3: Keyword match — must contain the primary service term. Pin H1 to position 1.
H4-H5: Location — include the target city/area. Geo-headlines get 15-25% higher CTR.
H6-H8: Trust proof — use REAL trust signals: "{biz.get('google_rating', 0)}\u2605 Rating", "{biz.get('years_experience', 0)}+ Years Exp", license info.
H9-H10: USP — translate unique selling points into punchy headlines.
H11-H12: Offer/CTA — "Free Estimate", "Call Now", specific offers.
H13-H14: Urgency — "Available Now", "Same-Day Service", "30-Min Response".
H15: Brand name — "{biz.get('name', '')}" if it fits.

DESCRIPTION STRATEGY (4 per ad group, each max 90 chars):
D1: Problem \u2192 Solution \u2192 CTA (pin to position 1)
D2: Trust proof + differentiator
D3: Offer + urgency
D4: Local authority + reassurance

CHARACTER LIMITS ARE ABSOLUTE:
- Headlines: EXACTLY 30 characters max. Not 31. Count carefully.
- Descriptions: EXACTLY 90 characters max. Count carefully.
- If the business name is too long, abbreviate it.

NEVER USE: "Best", "#1", "Top Rated" (without proof), "Quality Service", "Great Prices" — these are generic garbage that tanks CTR.
ALWAYS USE: Specific numbers, credentials, real trust signals, the actual service name.

Competitor gaps to exploit: {json.dumps(competitors.get('opportunity_gaps', []))}

{self._format_feedback_for_ad_copy(context.get('feedback', {}))}
Respond with ONLY valid JSON."""

        user_msg = f"""CAMPAIGN: {strategy.get('campaign_name', 'New Campaign')}
LOCATIONS: {json.dumps(strategy.get('locations', []))}
BUSINESS USPs: {json.dumps(biz.get('usps', []))}
OFFERS: {json.dumps(biz.get('offers', []))}
TRUST SIGNALS: {json.dumps(biz.get('trust_signals', []))}

AD GROUPS AND THEIR KEYWORDS:
{chr(10).join(services_context)}

For EACH ad group, generate a complete RSA. Return this JSON:
{{
  "ad_groups": [
    {{
      "service": "exact service name",
      "headlines": ["H1", "H2", ..., "H15"],
      "descriptions": ["D1", "D2", "D3", "D4"],
      "pinning": {{
        "headline_pins": {{"1": 0}},
        "description_pins": {{"1": 0}}
      }},
      "final_url": "{biz.get('website', 'https://example.com')}/relevant-page",
      "display_path": ["Path1", "Path2"]
    }},
    ...
  ]
}}

CRITICAL: Generate ads for ALL {len(services)} services: {json.dumps(services)}
Each ad group MUST have exactly 15 headlines and 4 descriptions."""

        return await self._call_claude_json(system, user_msg, max_tokens=8192, temperature=0.7)

    # ── AGENT 6: QA (HARDENED — programmatic + LLM) ────────────────

    async def _agent_qa(self, spec: Dict, context: Dict, user_prompt: str) -> Optional[Dict]:
        """
        Two-phase QA:
        1. Programmatic checks (character limits, duplicates, missing URLs) — FACTS
        2. LLM review (strategic quality, ad relevance, campaign coherence) — JUDGMENT
        3. Keyword-headline match scoring — MATHEMATICAL
        """
        # ── Phase 1: Programmatic checks (instant, free, 100% accurate) ──
        programmatic_issues = _programmatic_qa(spec)
        critical_count = sum(1 for i in programmatic_issues if i["severity"] == "critical")
        warning_count = len(programmatic_issues) - critical_count

        # ── Phase 2: Keyword-headline match scoring ──
        kw_match = _compute_keyword_headline_match(spec)
        avg_match_score = 0
        if kw_match:
            scores = [v["score"] for v in kw_match.values()]
            avg_match_score = sum(scores) / len(scores) if scores else 0

        # ── Phase 3: Ahrefs relevance check ──
        ahrefs_section = ""
        ahrefs = context.get("ahrefs", {})
        if ahrefs and ahrefs.get("seed_keywords"):
            high_vol_kws = [kw["keyword"] for kw in ahrefs.get("seed_keywords", [])
                           if kw.get("volume", 0) >= 30][:20]
            if high_vol_kws:
                # Check how many high-volume Ahrefs keywords made it into the spec
                spec_keywords = set()
                for ag in spec.get("ad_groups", []):
                    for kw in ag.get("keywords", []):
                        text = kw.get("text", "").lower() if isinstance(kw, dict) else str(kw).lower()
                        spec_keywords.add(text)
                matched_ahrefs = [kw for kw in high_vol_kws if kw.lower() in spec_keywords]
                ahrefs_section = f"""
AHREFS KEYWORD COVERAGE:
  High-volume keywords from Ahrefs: {len(high_vol_kws)}
  Keywords that made it into the campaign: {len(matched_ahrefs)}
  Coverage: {round(len(matched_ahrefs) / len(high_vol_kws) * 100) if high_vol_kws else 0}%
  Missing high-volume keywords: {json.dumps([kw for kw in high_vol_kws if kw.lower() not in spec_keywords][:10])}
"""

        # ── Phase 4: LLM strategic review (only what programmatic can't check) ──
        system = f"""You are a Google Ads campaign quality reviewer. You evaluate STRATEGIC quality — not character limits (those are already checked programmatically).

PROGRAMMATIC CHECKS ALREADY DONE (don't re-check these):
- Character limits: {critical_count} critical, {warning_count} warnings found
- Keyword-headline match: avg {avg_match_score:.0f}% across ad groups

YOUR JOB — Strategic quality only:
1. Does the ad copy match search intent? (Someone searching "emergency locksmith" should see urgency, not generic "quality service")
2. Are the headlines compelling and differentiated? (Not 15 variations of the same generic headline)
3. Do the keywords cover the full search funnel? (Emergency + high-intent + research + local)
4. Is the bidding strategy appropriate for this business type and budget?
5. Are sitelink URLs realistic and relevant?
6. Does the campaign name follow conventions?
7. Will this campaign actually CONVERT? Rate the persuasion quality.
{ahrefs_section}
KEYWORD-HEADLINE MATCH BY AD GROUP:
{json.dumps(kw_match, indent=2)}

Score STRATEGIC quality 0-100 (separate from programmatic issues).
If keyword-headline match is below 50%, flag it as a warning.

Respond with ONLY valid JSON."""

        user_msg = f"""ORIGINAL USER REQUEST: "{user_prompt}"

CAMPAIGN SPEC (abbreviated — focus on quality not structure):
  Campaign: {spec.get('campaign', {}).get('name')}
  Budget: ${spec.get('campaign', {}).get('budget_micros', 0) / 1_000_000:.0f}/day
  Ad Groups: {len(spec.get('ad_groups', []))}
  Sitelinks: {len(spec.get('sitelinks', []))}
  Callouts: {len(spec.get('callouts', []))}

AD GROUPS DETAIL:
{json.dumps([{
    'name': ag.get('name'),
    'keywords': len(ag.get('keywords', [])),
    'headlines': [h[:30] if isinstance(h, str) else h.get('text', '')[:30] for h in ag.get('ads', [{}])[0].get('headlines', [])[:5]] if ag.get('ads') else [],
    'descriptions': [d[:50] if isinstance(d, str) else d.get('text', '')[:50] for d in ag.get('ads', [{}])[0].get('descriptions', [])[:2]] if ag.get('ads') else [],
} for ag in spec.get('ad_groups', [])], indent=2)}

Return this JSON:
{{
  "strategic_score": 85,
  "grade": "B+",
  "strategic_issues": [
    {{"severity": "warning", "area": "ad_copy|keywords|targeting|budget|extensions", "message": "What's wrong strategically", "suggestion": "How to improve"}},
    ...
  ],
  "strengths": ["What's done well"],
  "approved": true,
  "summary": "1-2 sentence assessment"
}}"""

        llm_result = await self._call_claude_json(system, user_msg, max_tokens=2048, temperature=0.2)

        # ── Merge programmatic + LLM results ──
        strategic_score = llm_result.get("strategic_score", 75) if llm_result else 75
        programmatic_penalty = min(critical_count * 5 + warning_count * 2, 30)
        kw_match_penalty = max(0, (50 - avg_match_score) * 0.3) if avg_match_score < 50 else 0
        final_score = max(0, strategic_score - programmatic_penalty - kw_match_penalty)

        combined = {
            "score": round(final_score),
            "grade": self._score_to_grade(final_score),
            "strategic_score": strategic_score,
            "programmatic_issues": programmatic_issues,
            "strategic_issues": llm_result.get("strategic_issues", []) if llm_result else [],
            "strengths": llm_result.get("strengths", []) if llm_result else [],
            "keyword_headline_match": kw_match,
            "avg_keyword_match": round(avg_match_score),
            "issues": programmatic_issues + (llm_result.get("strategic_issues", []) if llm_result else []),
            "approved": final_score >= 60,
            "summary": (
                f"Score {round(final_score)}/100 ({self._score_to_grade(final_score)}). "
                f"{critical_count} critical issues, {warning_count} warnings. "
                f"Keyword-headline match: {avg_match_score:.0f}%. "
                f"{llm_result.get('summary', '') if llm_result else ''}"
            ),
        }
        return combined

    @staticmethod
    def _score_to_grade(score: float) -> str:
        if score >= 95: return "A+"
        if score >= 90: return "A"
        if score >= 85: return "A-"
        if score >= 80: return "B+"
        if score >= 75: return "B"
        if score >= 70: return "B-"
        if score >= 65: return "C+"
        if score >= 60: return "C"
        if score >= 50: return "D"
        return "F"

    # ── FEEDBACK FORMATTERS ─────────────────────────────────────

    def _format_feedback_for_strategist(self, feedback: Dict) -> str:
        """Format performance feedback for the Strategist agent's prompt."""
        if not feedback or not feedback.get("budget_insights"):
            return ""

        lines = ["PERFORMANCE LEARNINGS FROM PAST CAMPAIGNS:"]
        if feedback.get("budget_insights"):
            bi = feedback["budget_insights"]
            lines.append(f"  Avg budget that converted: ${bi.get('avg_converting_budget', 0):.0f}/day")
            lines.append(f"  Best performing campaign type: {bi.get('best_campaign_type', 'SEARCH')}")
        if feedback.get("avg_pipeline_quality"):
            lines.append(f"  Avg pipeline QA score: {feedback['avg_pipeline_quality']:.0f}/100")
        if feedback.get("winning_angles"):
            lines.append(f"  Best ad copy angles: {', '.join(feedback['winning_angles'][:3])}")
        lines.append("  Use these learnings to inform your budget and strategy decisions.")
        return "\n".join(lines)

    def _format_feedback_for_ad_copy(self, feedback: Dict) -> str:
        """Format performance feedback for the Ad Copy agent's prompt."""
        if not feedback:
            return ""

        lines = []
        if feedback.get("top_performing_headlines"):
            lines.append("PROVEN HEADLINES FROM PAST CAMPAIGNS (high CTR — use this style):")
            for h in feedback["top_performing_headlines"][:8]:
                lines.append(f'  "{h.get("text", "")}" — CTR: {h.get("ctr", 0):.1%}')
            lines.append("  ↑ Write NEW headlines in a SIMILAR style to these winners.")

        if feedback.get("failed_patterns"):
            lines.append("\nFAILED HEADLINES (low CTR — avoid this style):")
            for h in feedback["failed_patterns"][:5]:
                lines.append(f'  "{h.get("text", "")}" — CTR: {h.get("ctr", 0):.1%}')
            lines.append("  ↑ Do NOT repeat these patterns.")

        if feedback.get("top_performing_keywords"):
            lines.append("\nKEYWORDS THAT ACTUALLY CONVERT (include these terms in headlines):")
            for kw in feedback["top_performing_keywords"][:5]:
                lines.append(f'  "{kw.get("text", "")}" — {kw.get("conversions", 0)} conversions')

        return "\n".join(lines) if lines else ""

    # ── SPEC ASSEMBLY ────────────────────────────────────────────

    def _assemble_spec(
        self,
        strategy: Dict,
        keywords: Dict,
        ad_copy: Dict,
        targeting: Dict,
        extensions: Dict,
    ) -> Dict[str, Any]:
        """Map all agent outputs into the deploy_full_campaign spec format."""
        services = strategy.get("services", [])

        # Group keywords by service
        kw_by_service: Dict[str, List] = {}
        for kw in keywords.get("keywords", []):
            svc = kw.get("service", "")
            kw_by_service.setdefault(svc, []).append({
                "text": kw["text"],
                "match_type": kw.get("match_type", "PHRASE"),
            })

        # Global negatives
        negatives = [n.get("text", "") for n in keywords.get("negatives", []) if n.get("text")]

        # Build ad groups by merging keywords + ad copy per service
        ad_groups = []
        ad_copy_by_service = {}
        for ag in ad_copy.get("ad_groups", []):
            ad_copy_by_service[ag.get("service", "")] = ag

        for svc in services:
            svc_keywords = kw_by_service.get(svc, [])
            svc_copy = ad_copy_by_service.get(svc, {})

            ad_group = {
                "name": f"{svc} \u2014 {strategy.get('locations', ['DFW'])[0] if strategy.get('locations') else 'All Areas'}",
                "keywords": svc_keywords,
                "ads": [{
                    "headlines": svc_copy.get("headlines", []),
                    "descriptions": svc_copy.get("descriptions", []),
                    "final_url": svc_copy.get("final_url", strategy.get("website", "")),
                    "final_urls": [svc_copy.get("final_url", strategy.get("website", ""))],
                }],
                "negative_keywords": negatives,
            }
            ad_groups.append(ad_group)

        # Assemble the full spec
        geo = targeting.get("geo", {})
        device_bids = targeting.get("device_bids", {})

        return {
            "campaign": {
                "name": strategy.get("campaign_name", "AI Campaign"),
                "budget_micros": strategy.get("budget_micros", 50_000_000),
                "bidding_strategy": strategy.get("bidding_strategy", "MAXIMIZE_CONVERSIONS"),
                "target_cpa_micros": strategy.get("target_cpa_micros", 0),
                "channel_type": strategy.get("campaign_type", "SEARCH"),
                "network": "SEARCH",
            },
            "ad_groups": ad_groups,
            "sitelinks": extensions.get("sitelinks", []),
            "callouts": extensions.get("callouts", []),
            "structured_snippets": extensions.get("structured_snippets", {}),
            # Store metadata for display
            "_pipeline_metadata": {
                "strategy": strategy,
                "targeting": targeting,
                "keyword_stats": keywords.get("tiers", {}),
                "qa_score": None,  # Filled by QA agent
            },
        }

    # ── QA FIX APPLICATION ───────────────────────────────────────

    def _apply_qa_fixes(self, spec: Dict, qa_result: Dict) -> Dict:
        """Apply QA corrections — programmatic fixes are deterministic, strategic are logged."""
        if not qa_result:
            return spec

        # Store QA score in metadata
        if "_pipeline_metadata" in spec:
            spec["_pipeline_metadata"]["qa_score"] = qa_result.get("score")
            spec["_pipeline_metadata"]["qa_grade"] = qa_result.get("grade")
            spec["_pipeline_metadata"]["keyword_headline_match"] = qa_result.get("avg_keyword_match")
            spec["_pipeline_metadata"]["programmatic_issues"] = len(qa_result.get("programmatic_issues", []))
            spec["_pipeline_metadata"]["strategic_issues"] = len(qa_result.get("strategic_issues", []))

        # ── Auto-fix all programmatic issues (character limits, etc.) ──
        # These are deterministic — just truncate to limits
        for ag in spec.get("ad_groups", []):
            for ad in ag.get("ads", []):
                # Remove duplicates while preserving order
                seen_headlines = set()
                unique_headlines = []
                for h in ad.get("headlines", []):
                    text = h if isinstance(h, str) else h.get("text", "")
                    if text.lower().strip() not in seen_headlines:
                        seen_headlines.add(text.lower().strip())
                        unique_headlines.append(h[:30] if isinstance(h, str) else h)
                ad["headlines"] = unique_headlines

                # Truncate all to limits
                ad["headlines"] = [h[:30] if isinstance(h, str) else h for h in ad.get("headlines", [])]
                ad["descriptions"] = [d[:90] if isinstance(d, str) else d for d in ad.get("descriptions", [])]

        # Truncate sitelink fields
        for sl in spec.get("sitelinks", []):
            if sl.get("link_text"):
                sl["link_text"] = sl["link_text"][:25]
            if sl.get("description1"):
                sl["description1"] = sl["description1"][:35]
            if sl.get("description2"):
                sl["description2"] = sl["description2"][:35]

        # Truncate callouts
        spec["callouts"] = [c[:25] if isinstance(c, str) else str(c)[:25] for c in spec.get("callouts", [])]

        # ── If QA score < 70 and we haven't retried, trigger correction round ──
        if qa_result.get("score", 100) < 70 and not spec.get("_qa_retry"):
            spec["_qa_retry"] = True
            logger.warning("QA score below 70 — correction round recommended",
                score=qa_result.get("score"),
                critical=len([i for i in qa_result.get("programmatic_issues", []) if i.get("severity") == "critical"]),
            )

        return spec

    # ── FALLBACK ─────────────────────────────────────────────────

    def _fallback_spec(self, user_prompt: str, context: Dict) -> Dict:
        """Minimal fallback spec if the pipeline fails entirely."""
        biz = context.get("business", {})
        return {
            "campaign": {
                "name": f"AI Campaign \u2014 {user_prompt[:50]}",
                "budget_micros": 50_000_000,
                "bidding_strategy": "MAXIMIZE_CONVERSIONS",
                "channel_type": "SEARCH",
                "network": "SEARCH",
            },
            "ad_groups": [],
            "sitelinks": [],
            "callouts": [],
            "structured_snippets": {},
            "_pipeline_error": "Pipeline failed — please try again or create manually",
        }
