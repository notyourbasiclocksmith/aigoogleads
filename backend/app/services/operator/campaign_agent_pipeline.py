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
import traceback
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
from app.models.tenant import Tenant
from app.models.pipeline_execution_log import PipelineExecutionLog
from app.services.operator.ahrefs_keyword_service import AhrefsKeywordService
from app.services.operator.llm_fallback_service import LLMFallbackService
from app.integrations.callflux.client import callflux_client

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

    # ── Keyword overlap with existing campaigns ──
    existing_keywords = set(spec.get("_existing_campaign_keywords", []))
    if existing_keywords:
        for ag_idx, ag in enumerate(spec.get("ad_groups", [])):
            for kw in ag.get("keywords", []):
                text = kw.get("text", "").lower() if isinstance(kw, dict) else str(kw).lower()
                if text in existing_keywords:
                    issues.append({
                        "severity": "warning",
                        "field": f"ad_groups[{ag_idx}].keywords",
                        "message": f"Keyword '{text}' already exists in another active campaign — may cause self-competition",
                        "check": "existing_overlap",
                    })

    # ── Minimum keywords per ad group ──
    for ag_idx, ag in enumerate(spec.get("ad_groups", [])):
        kw_count = len(ag.get("keywords", []))
        if 0 < kw_count < 5:
            issues.append({
                "severity": "warning",
                "field": f"ad_groups[{ag_idx}].keywords",
                "message": f"Only {kw_count} keywords — Google recommends 5-20 per ad group",
                "check": "min_keywords",
            })

    # ── Missing display_path ──
    for ag_idx, ag in enumerate(spec.get("ad_groups", [])):
        for ad_idx, ad in enumerate(ag.get("ads", [])):
            if not ad.get("display_path"):
                issues.append({
                    "severity": "warning",
                    "field": f"ad_groups[{ag_idx}].ads[{ad_idx}].display_path",
                    "message": "Missing display path — ads look more professional with URL paths",
                    "check": "missing_display_path",
                })

    # ── Budget vs Target CPA feasibility ──
    target_cpa_micros = spec.get("campaign", {}).get("target_cpa_micros", 0)
    if target_cpa_micros > 0 and budget_daily > 0:
        target_cpa = target_cpa_micros / 1_000_000
        daily_conversions = budget_daily / target_cpa if target_cpa > 0 else 0
        if daily_conversions < 1.0:
            issues.append({
                "severity": "warning",
                "field": "campaign.budget_micros",
                "message": (
                    f"Budget ${budget_daily:.0f}/day with target CPA ${target_cpa:.0f} = "
                    f"only {daily_conversions:.1f} conversions/day. "
                    f"Google recommends budget >= 2x target CPA (${target_cpa * 2:.0f}/day) "
                    f"for smart bidding to learn effectively."
                ),
                "check": "budget_cpa_feasibility",
            })

    # ── Headline diversity (near-duplicate detection) ──
    for ag_idx, ag in enumerate(spec.get("ad_groups", [])):
        for ad_idx, ad in enumerate(ag.get("ads", [])):
            headlines = ad.get("headlines", [])
            # Check for headlines starting with the same 2 words
            first_words = []
            for h in headlines:
                text = h if isinstance(h, str) else h.get("text", "") if isinstance(h, dict) else str(h)
                words = text.lower().split()[:2]
                prefix = " ".join(words)
                first_words.append(prefix)

            from collections import Counter as _Counter
            prefix_counts = _Counter(first_words)
            for prefix, count in prefix_counts.items():
                if count >= 4 and prefix:
                    issues.append({
                        "severity": "warning",
                        "field": f"ad_groups[{ag_idx}].ads[{ad_idx}].headlines",
                        "message": f"{count} headlines start with '{prefix}...' — lacks variety, will reduce ad effectiveness",
                        "check": "headline_diversity",
                    })

    # ── Structured snippet value limits ──
    snippets = spec.get("structured_snippets", {})
    for v_idx, v in enumerate(snippets.get("values", [])):
        if len(str(v)) > 25:
            issues.append({
                "severity": "critical",
                "field": f"structured_snippets.values[{v_idx}]",
                "message": f"Snippet value '{str(v)[:30]}...' is {len(str(v))} chars (max 25)",
                "fix": str(v)[:25],
                "check": "char_limit",
            })

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
        self._last_context: Dict[str, Any] = {}
        self._intent_hints: Dict[str, Any] = {}

    # ── ORCHESTRATOR ─────────────────────────────────────────────

    async def run(
        self,
        user_prompt: str,
        account_context: Dict[str, Any],
        conversation_id: str,
        intent_hints: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute the full 6-agent pipeline. Returns deploy_full_campaign spec."""
        self._intent_hints = intent_hints or {}
        self.conversation_id = conversation_id
        self._pipeline_start = time.time()
        self._agent_timings = []
        logger.info("Campaign pipeline started", conversation_id=conversation_id)

        try:
            return await self._run_pipeline_inner(user_prompt, account_context, conversation_id)
        except Exception as e:
            logger.error("Campaign pipeline failed with traceback",
                error=str(e),
                traceback=traceback.format_exc(),
                conversation_id=conversation_id)
            return self._fallback_spec(user_prompt, {"business": {}})

    async def _run_pipeline_inner(
        self,
        user_prompt: str,
        account_context: Dict[str, Any],
        conversation_id: str,
    ) -> Dict[str, Any]:
        """Inner pipeline logic — separated so run() can catch and log tracebacks."""
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
        self._last_context = context  # Store for PMax asset group builder

        # ── Agent 1: Strategist (everything depends on this) ──
        await self._emit_progress("Strategist", "running", "Analyzing your business, competitors, and existing campaigns to design the optimal campaign architecture...")
        t0 = time.time()
        strategy = await self._agent_strategist(context, user_prompt)
        self._agent_timings.append({"agent": "Strategist", "duration_ms": int((time.time() - t0) * 1000), "status": "done" if strategy else "error"})
        if not strategy:
            await self._emit_progress("Strategist", "error", "Failed to generate strategy")
            await self._finalize_log(exec_log, "failed", error="Strategist agent failed")
            return self._fallback_spec(user_prompt, context)
        # Normalize: gpt-4o fallback may return services as dict instead of list
        if isinstance(strategy.get("services"), dict):
            strategy["services"] = list(strategy["services"].keys())
        if not isinstance(strategy.get("services"), list):
            strategy["services"] = []
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
                await self._emit_progress("Keyword Research", "running", f"Found {ahrefs_count} real keywords from Ahrefs (avg CPC: ${ahrefs_data.get('summary', {}).get('avg_cpc') or 0:.2f}). Now building strategy...")
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

        # ── RETRY: If ad copy failed or returned 0 ad groups, retry once ──
        if ag_count == 0:
            logger.warning("Ad copy agent returned 0 ad groups — retrying...")
            await self._emit_progress("Ad Copy", "running", "Retrying ad copy generation...")
            t0 = time.time()
            ad_copy = await self._agent_ad_copy(context, strategy, keywords or {})
            self._agent_timings.append({"agent": "Ad Copy (retry)", "duration_ms": int((time.time() - t0) * 1000), "status": "done" if ad_copy else "error"})
            ag_count = len(ad_copy.get("ad_groups", [])) if ad_copy else 0

        await self._emit_progress("Ad Copy", "done" if ag_count > 0 else "error",
            f"{ag_count} ad groups with full RSA copy" if ag_count > 0 else "Failed to generate ad copy — campaign may deploy without ads")

        # ── Assemble the full spec ──
        is_pmax = strategy.get("campaign_type", "SEARCH") == "PERFORMANCE_MAX"
        spec = self._assemble_spec(
            strategy or {},
            keywords or {},
            ad_copy or {},
            targeting or {},
            extensions or {},
        )

        # For PMax: emit asset group progress
        if is_pmax and spec.get("asset_groups"):
            ag_count = len(spec["asset_groups"])
            theme_count = sum(len(ag.get("search_themes", [])) for ag in spec["asset_groups"])
            await self._emit_progress("Asset Groups", "done",
                f"{ag_count} PMax asset groups built with {theme_count} search themes")

        # Inject existing keywords for overlap detection in QA
        spec["_existing_campaign_keywords"] = list(context.get("existing_keywords", set()))

        # ── CallFlux: Auto-create tracking number BEFORE landing pages ──
        # (so tracking number can be injected into landing page CTAs)
        tracking_num = ""
        tracking_result = await self._setup_callflux_tracking(spec, context)
        if tracking_result and tracking_result.get("tracking_number"):
            tracking_num = tracking_result["tracking_number"]
            spec["call_extension"] = {"phone": tracking_num, "country": "US"}
            spec["_pipeline_metadata"]["callflux"] = tracking_result
            await self._emit_progress("Call Tracking", "done",
                f"Tracking number {tracking_num} assigned "
                f"(forwards to {tracking_result.get('forward_to', 'business phone')}, "
                f"records calls for AI analysis)")
        elif tracking_result and tracking_result.get("error"):
            await self._emit_progress("Call Tracking", "done",
                f"Skipped — {tracking_result['error'][:100]}")
        else:
            await self._emit_progress("Call Tracking", "done", "Skipped — CallFlux not configured")

        # ── Image Generation + Landing Pages (parallel) ──────────
        # Generate campaign images in parallel with landing page creation
        async def _generate_campaign_images() -> List[Dict]:
            """Generate hero images for the campaign using the image generator."""
            try:
                from app.integrations.image_generator.client import ImageGeneratorClient
                img_client = ImageGeneratorClient()
                if not img_client.is_configured:
                    return []

                await self._emit_progress("Image Generation", "running",
                    "Generating campaign images...")

                biz = context.get("business", {})
                raw_services = strategy.get("services") or []
                if isinstance(raw_services, dict):
                    raw_services = list(raw_services.keys())
                if not isinstance(raw_services, list):
                    raw_services = list(raw_services) if raw_services else []
                services = raw_services[:3]  # Top 3 services
                image_results = []

                for svc in services:
                    try:
                        result = await img_client.generate_ad_image(
                            business_name=biz.get("name", ""),
                            business_type=biz.get("type", ""),
                            service=svc,
                            city=biz.get("city", ""),
                            state=biz.get("state", ""),
                            size="1200x628",
                            engine="google",
                        )
                        if result.get("success") or result.get("imageUrl"):
                            image_results.append({
                                "service": svc,
                                "url": result.get("imageUrl", ""),
                                "filename": result.get("filename", ""),
                                "status": "success",
                            })
                    except Exception as img_err:
                        logger.warning("Image generation failed for service",
                            service=svc, error=str(img_err)[:200])
                        image_results.append({
                            "service": svc,
                            "status": "failed",
                            "error": str(img_err)[:100],
                        })

                success_count = sum(1 for r in image_results if r.get("status") == "success")
                await self._emit_progress("Image Generation", "done",
                    f"{success_count}/{len(services)} images generated")
                return image_results
            except Exception as e:
                logger.warning("Image generation skipped", error=str(e)[:200])
                return []

        # ── Landing Page Agent: Check/create landing pages per service ──
        try:
            from app.services.operator.landing_page_agent import LandingPageAgent
            lp_agent = LandingPageAgent(self.db, self.tenant_id)
            await self._emit_progress("Landing Pages", "running", "Checking landing pages for each service...")
            t0 = time.time()

            # Build keyword/headline maps per service
            kw_by_svc = {}
            hl_by_svc = {}
            for ag in spec.get("ad_groups", []):
                ag_name = ag.get("name", "")
                kw_texts = [kw.get("text", "") if isinstance(kw, dict) else str(kw) for kw in ag.get("keywords", [])]
                kw_by_svc[ag_name] = kw_texts
                for ad in ag.get("ads", []):
                    hl_by_svc[ag_name] = ad.get("headlines", [])[:5]

            lp_result = await lp_agent.run_for_campaign(
                services=strategy.get("services", []),
                locations=strategy.get("locations", []),
                campaign_keywords=kw_by_svc,
                campaign_headlines=hl_by_svc,
                conversation_id=conversation_id,
                business_context=context.get("business", {}),
                tracking_phone=tracking_num,  # Inject tracking number into CTAs
            )
            lp_ms = int((time.time() - t0) * 1000)
            self._agent_timings.append({"agent": "Landing Pages", "duration_ms": lp_ms, "status": "done"})

            # Update ad group final_urls with landing page URLs
            for page in lp_result.get("pages", []):
                if page.get("url") and page.get("service"):
                    for ag in spec.get("ad_groups", []):
                        if page["service"].lower() in ag.get("name", "").lower():
                            for ad in ag.get("ads", []):
                                ad["final_url"] = page["url"]
                                ad["final_urls"] = [page["url"]]

            # Store landing page data in pipeline metadata
            spec["_pipeline_metadata"]["landing_pages"] = lp_result.get("pages", [])

            generated_count = sum(1 for p in lp_result.get("pages", []) if p.get("status") == "generated")
            existing_count = sum(1 for p in lp_result.get("pages", []) if p.get("status") == "existing")
            await self._emit_progress("Landing Pages", "done",
                f"{existing_count} existing + {generated_count} new landing pages "
                f"linked to ad groups")

        except Exception as e:
            logger.warning("Landing page agent failed — continuing without", error=str(e))
            self._agent_timings.append({"agent": "Landing Pages", "duration_ms": 0, "status": "error"})
            await self._emit_progress("Landing Pages", "done", "Skipped (will use existing URLs)")

        # ── Image Generation (runs while QA prepares) ──
        image_results = []
        try:
            image_results = await _generate_campaign_images()
            if image_results:
                spec["_image_results"] = image_results
                # Add image URLs to PMax asset groups if applicable
                if spec.get("asset_groups"):
                    success_images = [r for r in image_results if r.get("status") == "success" and r.get("url")]
                    for i, ag in enumerate(spec["asset_groups"]):
                        if i < len(success_images):
                            ag.setdefault("images", []).append({
                                "url": success_images[i]["url"],
                                "field_type": "MARKETING_IMAGE",
                            })
        except Exception as img_err:
            logger.warning("Image generation phase failed", error=str(img_err)[:200])

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

        # ── Build rich campaign summary for user ──
        campaign_summary = self._build_campaign_summary(spec, qa_result)
        spec["_campaign_summary"] = campaign_summary

        # Emit the full summary as a progress message so user sees it in chat
        await self._emit_progress(
            "Campaign Summary", "done",
            campaign_summary.get("text", "Campaign ready for review."),
            extra={
                "type": "campaign_summary",
                **campaign_summary,
            },
        )

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
            from app.services.operator.performance_feedback_service import get_pipeline_learnings
            feedback_context = await get_pipeline_learnings(
                tenant_id=self.tenant_id,
                services=biz.get("services", []),
                db=self.db,
            )
            if feedback_context.get("top_performing_headlines"):
                logger.info("Loaded performance feedback",
                    headlines=len(feedback_context.get("top_performing_headlines", [])),
                    keywords=len(feedback_context.get("top_performing_keywords", [])),
                )
        except Exception as e:
            logger.warning("Could not load performance feedback", error=str(e))

        # Extract existing campaign keywords for overlap detection
        existing_keywords = set()
        for kw_data in account_context.get("keyword_performance", []):
            text = kw_data.get("text", "").lower().strip()
            if text and kw_data.get("status") == "ENABLED":
                existing_keywords.add(text)

        return {
            "business": biz,
            "account": account_context,
            "competitors": competitor_summary,
            "feedback": feedback_context,
            "existing_keywords": existing_keywords,
        }

    # ── PROGRESS MESSAGES ────────────────────────────────────────

    async def _emit_progress(self, agent_name: str, status: str, detail: str, extra: Dict = None):
        """Insert a progress message into the conversation."""
        if not self.conversation_id:
            return
        payload = {
            "type": "pipeline_progress",
            "agent": agent_name,
            "status": status,
            "detail": detail,
        }
        if extra:
            payload.update(extra)
        msg = OperatorMessage(
            id=str(uuid.uuid4()),
            conversation_id=self.conversation_id,
            role="assistant",
            content=f"{agent_name}: {detail}",
            structured_payload=payload,
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
        raw_campaigns = account.get("campaigns") or []
        if isinstance(raw_campaigns, dict):
            raw_campaigns = list(raw_campaigns.values())
        if raw_campaigns:
            lines = []
            for c in list(raw_campaigns)[:10]:
                lines.append(f"  [{c.get('status', '?')}] {c.get('name', '?')} \u2014 Budget:${c.get('budget_daily') or '?'}/day | Cost:${c.get('cost') or 0:.0f} | Conv:{c.get('conversions') or 0} | CPA:${c.get('cpa') or 0:.0f}")
            campaigns_text = "\n".join(lines)

        system = """You are a senior Google Ads strategist. You're designing the architecture for a new campaign.

Your job is to make ONE set of decisions:
- What type of campaign (SEARCH, CALL, PERFORMANCE_MAX)
- What services to target (each becomes its own ad group for tight theming)
- What budget and bidding strategy
- Campaign naming convention
- What the strategic angle is (why THIS campaign, why NOW)

Campaign type guide:
- SEARCH: Best for high-intent services (people searching for specific services). Most reliable for local businesses.
- CALL: Best for emergency/mobile-heavy services (towing, emergency locksmith). Phone call IS the conversion.
- PERFORMANCE_MAX: Best for visual products/services. Shows ads across ALL Google channels (Search, Display, YouTube, Maps). Requires images.

Think step by step:
1. What does the user actually want? Parse their intent carefully.
2. Look at existing campaigns — what's already covered? Don't duplicate. Fill gaps.
3. What services would be MOST profitable? Consider the business's specialties.
4. What budget makes sense given the competitive landscape and ticket size?
5. What campaign type best fits the business? (Emergency → CALL, High-intent local → SEARCH, Visual + broad → PERFORMANCE_MAX)
6. If the user specified a campaign type, RESPECT their choice.

Be SPECIFIC. Don't be generic. If the user says "BMW specialized services" and the business is an automotive locksmith, think about what BMW owners actually search for: FRM repair, key programming, comfort access, CAS module, coding. These are HIGH-TICKET services ($500-2000+).

Respond with ONLY valid JSON."""

        # Pass along any campaign type preference from user's intent
        campaign_type_hint = ""
        if self._intent_hints.get("campaign_type"):
            campaign_type_hint = f"\nUSER REQUESTED CAMPAIGN TYPE: {self._intent_hints['campaign_type']} — respect this choice unless there's a strong reason not to.\n"

        user_msg = f"""USER REQUEST: "{user_prompt}"
{campaign_type_hint}
BUSINESS CONTEXT:
  Name: {biz.get('name', 'Unknown')}
  Industry: {biz.get('industry', 'Unknown')}
  Services offered: {json.dumps(biz.get('services', []))}
  Locations: {biz.get('city', '')}, {biz.get('state', '')} (radius: {biz.get('service_radius_miles', 40)} miles)
  Avg ticket: ${biz.get('avg_ticket') or 'N/A'}
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
  "campaign_type": "SEARCH" or "CALL" or "PERFORMANCE_MAX",
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
                key=lambda k: k.get("volume") or 0, reverse=True,
            )[:30]
            seed_lines = [
                f"  {kw['keyword']} — vol:{kw.get('volume') or 0} CPC:${kw.get('cpc') or 0:.2f} diff:{kw.get('difficulty') or 0}"
                for kw in top_seeds
            ]

            top_expanded = sorted(
                ahrefs.get("expanded_keywords", []),
                key=lambda k: k.get("volume") or 0, reverse=True,
            )[:40]
            expanded_lines = [
                f"  {kw['keyword']} — vol:{kw.get('volume') or 0} CPC:${kw.get('cpc') or 0:.2f} [from: {kw.get('parent_service', kw.get('source', ''))}]"
                for kw in top_expanded
            ]

            top_suggestions = sorted(
                ahrefs.get("search_suggestions", []),
                key=lambda k: k.get("volume") or 0, reverse=True,
            )[:20]
            suggestion_lines = [
                f"  {kw['keyword']} — vol:{kw.get('volume') or 0} CPC:${kw.get('cpc') or 0:.2f}"
                for kw in top_suggestions
            ]

            comp_kws = sorted(
                ahrefs.get("competitor_keywords", []),
                key=lambda k: k.get("volume") or 0, reverse=True,
            )[:25]
            comp_lines = [
                f"  {kw['keyword']} — vol:{kw.get('volume') or 0} CPC:${kw.get('cpc') or 0:.2f} [{kw.get('competitor_domain', '')}]"
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

- Promotion extensions: If the business has offers/discounts/deals, create 1-2 promotions.
  promotion_target max 20 chars. Include percent_off (integer) or money_off_micros (dollars * 1000000).
  Include final_url linking to the offer page. Only create if there's a real offer.

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
  }},
  "promotion_extensions": [
    {{"promotion_target": "Service (max 20)", "percent_off": 15, "final_url": "https://...", "start_date": "", "end_date": ""}}
  ]
}}

Only include promotion_extensions if the business has real offers. Empty array [] if no offers."""

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
Competitor dominant themes to AVOID (overused): {json.dumps(competitors.get('overused_angles', competitors.get('dominant_themes', []))[:5])}

{self._format_competitor_ad_context(competitors)}

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

        # ── Phase 1b: URL reachability checks (async HTTP HEAD) ──
        try:
            url_issues = await self._check_final_url_reachability(spec)
            programmatic_issues.extend(url_issues)
        except Exception as e:
            logger.warning("URL reachability check failed", error=str(e))

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
                           if (kw.get("volume") or 0) >= 30][:20]
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
- Keyword-headline match: avg {avg_match_score or 0:.0f}% across ad groups

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
  Budget: ${(spec.get('campaign', {}).get('budget_micros') or 0) / 1_000_000:.0f}/day
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
                f"Keyword-headline match: {avg_match_score or 0:.0f}%. "
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
            lines.append(f"  Avg budget that converted: ${bi.get('avg_converting_budget') or 0:.0f}/day")
            lines.append(f"  Best performing campaign type: {bi.get('best_campaign_type', 'SEARCH')}")
        if feedback.get("avg_pipeline_quality"):
            lines.append(f"  Avg pipeline QA score: {feedback.get('avg_pipeline_quality') or 0:.0f}/100")
        if feedback.get("winning_angles"):
            lines.append(f"  Best ad copy angles: {', '.join(feedback['winning_angles'][:3])}")
        lines.append("  Use these learnings to inform your budget and strategy decisions.")
        return "\n".join(lines)

    def _format_feedback_for_ad_copy(self, feedback: Dict) -> str:
        """Format performance feedback for the Ad Copy agent's prompt."""
        if not feedback or not isinstance(feedback, dict):
            return ""

        def _ensure_list(val):
            """Safely coerce feedback values to a list of dicts."""
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                return list(val.values()) if val else []
            return []

        lines = []
        top_headlines = _ensure_list(feedback.get("top_performing_headlines"))
        if top_headlines:
            lines.append("PROVEN HEADLINES FROM PAST CAMPAIGNS (high CTR — use this style):")
            for h in top_headlines[:8]:
                if isinstance(h, dict):
                    lines.append(f'  "{h.get("text", "")}" — CTR: {h.get("ctr", 0):.1%}')
            lines.append("  ↑ Write NEW headlines in a SIMILAR style to these winners.")

        failed = _ensure_list(feedback.get("failed_patterns"))
        if failed:
            lines.append("\nFAILED HEADLINES (low CTR — avoid this style):")
            for h in failed[:5]:
                if isinstance(h, dict):
                    lines.append(f'  "{h.get("text", "")}" — CTR: {h.get("ctr", 0):.1%}')
            lines.append("  ↑ Do NOT repeat these patterns.")

        top_keywords = _ensure_list(feedback.get("top_performing_keywords"))
        if top_keywords:
            lines.append("\nKEYWORDS THAT ACTUALLY CONVERT (include these terms in headlines):")
            for kw in top_keywords[:5]:
                if isinstance(kw, dict):
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
        # Safety: gpt-4o fallback sometimes returns services as a dict
        if isinstance(services, dict):
            services = list(services.keys())

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
            headlines = svc_copy.get("headlines", [])
            descriptions = svc_copy.get("descriptions", [])

            # If no ad copy was generated, create minimal fallback headlines/descriptions
            if not headlines:
                biz_name = strategy.get("business_name", "")
                location = strategy.get("locations", [""])[0] if strategy.get("locations") else ""
                headlines = [
                    svc[:30],
                    f"{svc} - {location}"[:30] if location else svc[:30],
                    f"Call Now - {svc}"[:30],
                    f"{biz_name}"[:30] if biz_name else f"Expert {svc}"[:30],
                    f"{location} {svc}"[:30] if location else f"Professional {svc}"[:30],
                ]
                logger.warning("Using fallback headlines for ad group", service=svc)

            if not descriptions:
                descriptions = [
                    f"Professional {svc} services. Call now for a free estimate!"[:90],
                    f"Licensed & insured. Serving the {strategy.get('locations', ['local'])[0]} area."[:90],
                ]
                logger.warning("Using fallback descriptions for ad group", service=svc)

            # Skip ad groups with no keywords
            if not svc_keywords:
                logger.warning("Skipping ad group with no keywords", service=svc)
                continue

            final_url = svc_copy.get("final_url", strategy.get("website", ""))
            display_path = svc_copy.get("display_path", [])

            # Build headline/description dicts with pinning if available
            pinning = svc_copy.get("pinning", {})
            headline_pins = pinning.get("headline_pins", {})
            description_pins = pinning.get("description_pins", {})

            pinned_headlines = []
            for i, h in enumerate(headlines):
                text = h if isinstance(h, str) else h.get("text", "") if isinstance(h, dict) else str(h)
                h_dict = {"text": text}
                # Check if this headline has a pin assignment
                pin_key = str(i)  # Pinning map uses string indices or headline text
                pin_pos = headline_pins.get(pin_key) or headline_pins.get(text, "")
                if pin_pos:
                    h_dict["pinned_position"] = pin_pos
                elif isinstance(h, dict) and h.get("pinned_position"):
                    h_dict["pinned_position"] = h["pinned_position"]
                pinned_headlines.append(h_dict)

            pinned_descriptions = []
            for i, d in enumerate(descriptions):
                text = d if isinstance(d, str) else d.get("text", "") if isinstance(d, dict) else str(d)
                d_dict = {"text": text}
                pin_key = str(i)
                pin_pos = description_pins.get(pin_key) or description_pins.get(text, "")
                if pin_pos:
                    d_dict["pinned_position"] = pin_pos
                elif isinstance(d, dict) and d.get("pinned_position"):
                    d_dict["pinned_position"] = d["pinned_position"]
                pinned_descriptions.append(d_dict)

            ad_group = {
                "name": f"{svc} \u2014 {strategy.get('locations', ['DFW'])[0] if strategy.get('locations') else 'All Areas'}",
                "keywords": svc_keywords,
                "ads": [{
                    "headlines": pinned_headlines,
                    "descriptions": pinned_descriptions,
                    "final_url": final_url,
                    "final_urls": [final_url] if final_url else [],
                    "display_path": display_path,
                }],
                "negative_keywords": negatives,
            }
            ad_groups.append(ad_group)

        # Assemble the full spec
        geo = targeting.get("geo", {})
        device_bids = targeting.get("device_bids", {})

        campaign_type = strategy.get("campaign_type", "SEARCH")
        is_pmax = campaign_type == "PERFORMANCE_MAX"

        spec = {
            "campaign": {
                "name": strategy.get("campaign_name", "AI Campaign"),
                "budget_micros": strategy.get("budget_micros", 50_000_000),
                "bidding_strategy": strategy.get("bidding_strategy", "MAXIMIZE_CONVERSIONS"),
                "target_cpa_micros": strategy.get("target_cpa_micros", 0),
                "channel_type": campaign_type,
                "network": "SEARCH" if not is_pmax else "ALL",
            },
            "ad_groups": ad_groups if not is_pmax else [],
            "sitelinks": extensions.get("sitelinks", []),
            "callouts": extensions.get("callouts", []),
            "structured_snippets": extensions.get("structured_snippets", {}),
            "call_extension": extensions.get("call_extension", {}),
            "promotion_extensions": extensions.get("promotion_extensions", []),
            # GBP location data for location extensions
            "gbp_place_id": self._last_context.get("business", {}).get("gbp_place_id", ""),
            "gbp_account_id": self._last_context.get("business", {}).get("gbp_account_id", ""),
            # Campaign-level negative keywords (cross-cutting)
            "campaign_negative_keywords": self._build_campaign_negatives(keywords),
            # Store metadata for display
            "_pipeline_metadata": {
                "strategy": strategy,
                "targeting": targeting,
                "extensions": extensions,
                "keyword_stats": keywords.get("tiers", {}),
                "qa_score": None,  # Filled by QA agent
            },
        }

        # For PMax: build asset groups instead of ad groups
        if is_pmax:
            spec["asset_groups"] = self._build_pmax_asset_groups(
                strategy, keywords, ad_copy, self._last_context or {},
            )

        return spec

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

    # ── CAMPAIGN SUMMARY BUILDER ────────────────────────────────

    # ── CALLFLUX INTEGRATION ────────────────────────────────────

    async def _setup_callflux_tracking(self, spec: Dict, context: Dict) -> Optional[Dict]:
        """
        Auto-create a CallFlux campaign + tracking number for this campaign.

        Flow:
        1. Load tenant from DB
        2. If no callflux_tenant_id → register with CallFlux (auto-creates account)
        3. Create a CallFlux campaign (mirrors Google Ads campaign)
        4. Purchase a tracking number from Twilio via CallFlux
        5. Store credentials back on the Tenant model
        6. Return tracking number for use in call extensions & landing pages
        """
        if not callflux_client.is_configured:
            logger.info("CallFlux not configured — skipping call tracking setup")
            return None

        try:
            await self._emit_progress("Call Tracking", "running",
                "Setting up call tracking number via CallFlux...")

            # Load tenant
            tenant_result = await self.db.execute(
                select(Tenant).where(Tenant.id == self.tenant_id)
            )
            tenant = tenant_result.scalar_one_or_none()
            if not tenant:
                return {"error": "Tenant not found"}

            # Get business phone (forward-to number)
            # Priority: user-confirmed phone from intent > business profile phone
            biz_phone = self._intent_hints.get("forward_phone") or context.get("business", {}).get("phone", "")
            if not biz_phone:
                return {"error": "No business phone number configured — cannot set up call forwarding"}

            # Step 1: Ensure tenant is registered with CallFlux
            access_token = tenant.callflux_access_token or ""
            if not tenant.callflux_tenant_id:
                # Auto-register this tenant with CallFlux
                biz_name = context.get("business", {}).get("name", tenant.name or "Business")
                email = tenant.callflux_email or f"tenant-{self.tenant_id[:8]}@aigoogleads.internal"

                logger.info("Registering new CallFlux tenant", tenant_id=self.tenant_id, email=email)
                reg_result = await callflux_client.register_tenant(
                    tenant_name=biz_name,
                    email=email,
                )
                if reg_result.get("error"):
                    return {"error": f"CallFlux registration failed: {reg_result['error']}"}

                # Store CallFlux credentials on tenant
                tenant.callflux_tenant_id = str(reg_result.get("tenant_id", ""))
                tenant.callflux_access_token = reg_result.get("access_token", "")
                tenant.callflux_refresh_token = reg_result.get("refresh_token", "")
                tenant.callflux_email = email
                if reg_result.get("password"):
                    # Store password encrypted (using Fernet from settings)
                    try:
                        from cryptography.fernet import Fernet
                        f = Fernet(settings.ENCRYPTION_KEY.encode() if isinstance(settings.ENCRYPTION_KEY, str) else settings.ENCRYPTION_KEY)
                        tenant.callflux_password_encrypted = f.encrypt(
                            reg_result["password"].encode()
                        ).decode()
                    except Exception as enc_err:
                        logger.warning("Could not encrypt CallFlux password", error=str(enc_err))
                        tenant.callflux_password_encrypted = ""

                access_token = reg_result.get("access_token", "")
                try:
                    await self.db.flush()
                except Exception:
                    pass

                logger.info("CallFlux tenant registered",
                    callflux_tenant_id=tenant.callflux_tenant_id)

            # If we have a token but it might be expired, try refresh
            if not access_token and tenant.callflux_refresh_token:
                refresh_result = await callflux_client.refresh_token(tenant.callflux_refresh_token)
                if refresh_result.get("access_token"):
                    access_token = refresh_result["access_token"]
                    tenant.callflux_access_token = access_token
                    try:
                        await self.db.flush()
                    except Exception:
                        pass

            if not access_token:
                # Try login with stored credentials
                if tenant.callflux_email and tenant.callflux_password_encrypted:
                    try:
                        from cryptography.fernet import Fernet
                        f = Fernet(settings.ENCRYPTION_KEY.encode() if isinstance(settings.ENCRYPTION_KEY, str) else settings.ENCRYPTION_KEY)
                        password = f.decrypt(tenant.callflux_password_encrypted.encode()).decode()
                        login_result = await callflux_client.login(tenant.callflux_email, password)
                        if login_result.get("access_token"):
                            access_token = login_result["access_token"]
                            tenant.callflux_access_token = access_token
                            if login_result.get("refresh_token"):
                                tenant.callflux_refresh_token = login_result["refresh_token"]
                            try:
                                await self.db.flush()
                            except Exception:
                                pass
                    except Exception as login_err:
                        logger.warning("CallFlux re-login failed", error=str(login_err))

            if not access_token:
                return {"error": "Could not authenticate with CallFlux"}

            # Step 2: Create campaign + purchase tracking number
            campaign_name = spec.get("campaign", {}).get("name", "Campaign")
            area_code = context.get("business", {}).get("phone", "")[:3] if biz_phone else ""
            # Extract area code from phone number (skip +1 country code)
            if biz_phone.startswith("+1") and len(biz_phone) >= 5:
                area_code = biz_phone[2:5]
            elif biz_phone.startswith("1") and len(biz_phone) >= 4:
                area_code = biz_phone[1:4]
            elif len(biz_phone) >= 3 and not biz_phone.startswith("+"):
                # Strip non-digits
                digits = "".join(c for c in biz_phone if c.isdigit())
                if digits.startswith("1") and len(digits) >= 4:
                    area_code = digits[1:4]
                elif len(digits) >= 3:
                    area_code = digits[:3]

            # Build whisper message so business owner knows which campaign the call is from
            whisper_msg = f"Google Ads call for {campaign_name}"

            result = await callflux_client.setup_campaign_tracking(
                access_token=access_token,
                campaign_name=campaign_name,
                forward_to_number=biz_phone,
                area_code=area_code,
                record_calls=True,
                whisper_message=whisper_msg,
            )

            if result.get("error") or result.get("tracking_error"):
                error = result.get("error") or result.get("tracking_error")
                logger.warning("CallFlux tracking setup failed", error=error)
                return {"error": error}

            logger.info("CallFlux tracking number provisioned",
                tracking_number=result.get("tracking_number"),
                campaign_id=result.get("campaign_id"),
                forward_to=biz_phone)

            # Step 3: Create DNI pool for website call tracking with GCLID attribution
            dni_pool = None
            try:
                campaign_name = spec.get("campaign", {}).get("name", "Campaign")
                pool_name = f"DNI - {campaign_name}"
                dni_result = await callflux_client.create_dni_pool(
                    access_token=access_token,
                    pool_name=pool_name,
                    purpose="GOOGLE_ADS",
                )
                if dni_result.get("pool_id"):
                    dni_pool = dni_result
                    logger.info("CallFlux DNI pool created",
                        pool_id=dni_result["pool_id"],
                        pool_name=pool_name)
                else:
                    logger.warning("DNI pool creation returned no pool_id",
                        result=dni_result)
            except Exception as dni_err:
                logger.warning("DNI pool creation failed (non-critical)",
                    error=str(dni_err))

            return {
                "tracking_number": result.get("tracking_number", ""),
                "callflux_campaign_id": result.get("campaign_id"),
                "phone_number_id": result.get("phone_number_id"),
                "forward_to": biz_phone,
                "status": result.get("status", "active"),
                "dni_pool": dni_pool,
            }

        except Exception as e:
            logger.error("CallFlux tracking setup error", error=str(e))
            return {"error": str(e)}

    def _build_campaign_summary(self, spec: Dict, qa_result: Optional[Dict]) -> Dict:
        """
        Build a rich, human-readable campaign summary for the user to review
        before approving. Includes all critical settings, what to expect,
        and estimated performance.
        """
        campaign = spec.get("campaign", {})
        ad_groups = spec.get("ad_groups", [])
        meta = spec.get("_pipeline_metadata", {})
        strategy = meta.get("strategy", {})
        targeting = meta.get("targeting", {})
        kw_stats = meta.get("keyword_stats", {})
        extensions = meta.get("extensions", {})

        # ── Campaign basics
        name = campaign.get("name", "Campaign")
        budget_daily = campaign.get("budget_micros", 0) / 1_000_000
        budget_monthly = budget_daily * 30.4
        campaign_type = campaign.get("channel_type", "SEARCH")
        bidding = campaign.get("bidding_strategy", "MAXIMIZE_CONVERSIONS")
        target_cpa = campaign.get("target_cpa_micros", 0) / 1_000_000 if campaign.get("target_cpa_micros") else None

        # ── Ad group stats
        total_keywords = sum(len(ag.get("keywords", [])) for ag in ad_groups)
        total_negatives = sum(len(ag.get("negative_keywords", [])) for ag in ad_groups)
        total_headlines = sum(
            len(ad.get("headlines", []))
            for ag in ad_groups
            for ad in ag.get("ads", [])
        )
        total_descriptions = sum(
            len(ad.get("descriptions", []))
            for ag in ad_groups
            for ad in ag.get("ads", [])
        )

        # ── Keyword tiers
        tier_summary = []
        for tier_name in ["emergency", "high", "medium", "local", "service"]:
            count = kw_stats.get(tier_name, 0)
            if count > 0:
                tier_summary.append(f"{tier_name.capitalize()}: {count}")

        # ── Targeting
        geo = targeting.get("geo", {})
        geo_desc = ""
        if geo.get("type") == "radius":
            geo_desc = f"{geo.get('radius_miles', 40)}-mile radius"
        elif geo.get("type") == "cities":
            cities = geo.get("locations", [])
            geo_desc = f"{len(cities)} cities: {', '.join(cities[:3])}" + ("..." if len(cities) > 3 else "")

        device = targeting.get("device_bids", {})
        mobile_adj = device.get("mobile_bid_adj", 0)
        tablet_adj = device.get("tablet_bid_adj", 0)

        schedule = targeting.get("schedule", {})
        schedule_desc = "24/7" if schedule.get("all_day") else ""
        peaks = schedule.get("peak_adjustments", [])
        if peaks:
            peak_strs = []
            for p in peaks[:2]:
                days = p.get("days", [])
                hours = p.get("hours", "")
                adj = p.get("bid_adj", 0)
                peak_strs.append(f"{','.join(d[:3] for d in days[:3])} {hours} (+{adj}%)")
            schedule_desc = " | ".join(peak_strs)

        # ── Extensions
        sitelink_count = len(spec.get("sitelinks", []))
        callout_count = len(spec.get("callouts", []))
        has_snippets = bool(spec.get("structured_snippets", {}).get("values"))
        has_call_ext = bool(spec.get("call_extension", {}).get("phone"))
        call_phone = spec.get("call_extension", {}).get("phone", "")
        callflux_data = meta.get("callflux", {})
        tracking_number = callflux_data.get("tracking_number", "")
        forward_to = callflux_data.get("forward_to", "")

        # ── QA
        qa_score = qa_result.get("score", 0) if qa_result else None
        qa_grade = qa_result.get("grade", "?") if qa_result else "?"
        kw_match = qa_result.get("avg_keyword_match", 0) if qa_result else 0

        # ── Landing pages
        lp_data = meta.get("landing_pages", [])
        lp_generated = sum(1 for p in lp_data if p.get("status") == "generated")
        lp_existing = sum(1 for p in lp_data if p.get("status") == "existing")

        # ── Build ad group details
        ag_details = []
        for ag in ad_groups:
            kws = ag.get("keywords", [])
            ads = ag.get("ads", [])
            headlines_count = len(ads[0].get("headlines", [])) if ads else 0
            descs_count = len(ads[0].get("descriptions", [])) if ads else 0

            # Top 5 keywords
            top_kws = [
                (kw.get("text", kw) if isinstance(kw, dict) else str(kw))
                for kw in kws[:5]
            ]

            # Top 3 headlines
            top_headlines = []
            if ads:
                for h in ads[0].get("headlines", [])[:3]:
                    top_headlines.append(h if isinstance(h, str) else h.get("text", "") if isinstance(h, dict) else str(h))

            ag_details.append({
                "name": ag.get("name", "Ad Group"),
                "keywords": len(kws),
                "headlines": headlines_count,
                "descriptions": descs_count,
                "top_keywords": top_kws,
                "top_headlines": top_headlines,
                "final_url": ads[0].get("final_url", "") if ads else "",
            })

        # ── Estimate performance (rough)
        # Average local service CPC: $3-12, conversion rate: 5-15%
        est_clicks_day = int(budget_daily / 6)  # ~$6 avg CPC for local services
        est_clicks_month = int(est_clicks_day * 30.4)
        est_conversions_month = max(1, int(est_clicks_month * 0.08))  # ~8% CVR
        est_cpa = budget_monthly / est_conversions_month if est_conversions_month > 0 else 0

        # ── Build text summary
        lines = [
            f"📋 **{name}**",
            f"",
            f"**Campaign Settings**",
            f"• Type: Google {campaign_type} Campaign",
            f"• Budget: ${budget_daily:.0f}/day (${budget_monthly:.0f}/month)",
            f"• Bidding: {bidding.replace('_', ' ').title()}",
        ]
        if target_cpa:
            lines.append(f"• Target CPA: ${target_cpa:.2f}")
        lines.append(f"• Status: Created PAUSED (you enable when ready)")
        lines.append(f"")

        # PMax asset groups or standard ad groups
        pmax_asset_groups = spec.get("asset_groups", [])
        if pmax_asset_groups:
            lines.append(f"**Asset Groups ({len(pmax_asset_groups)}) — Performance Max**")
            for pag in pmax_asset_groups:
                h_count = len(pag.get("headlines", []))
                lh_count = len(pag.get("long_headlines", []))
                d_count = len(pag.get("descriptions", []))
                st_count = len(pag.get("search_themes", []))
                lines.append(f"• {pag.get('name', 'Asset Group')}: "
                    f"{h_count} headlines, {lh_count} long headlines, {d_count} descriptions, "
                    f"{st_count} search themes")
                if pag.get("final_url"):
                    lines.append(f"  Landing page: {pag['final_url']}")
                if pag.get("search_themes"):
                    lines.append(f"  Search themes: {', '.join(pag['search_themes'][:3])}...")
            lines.append(f"")
        else:
            lines.append(f"**Ad Groups ({len(ad_groups)})**")
            for ag in ag_details:
                lines.append(f"• {ag['name']}: {ag['keywords']} keywords, {ag['headlines']} headlines, {ag['descriptions']} descriptions")
                if ag.get("top_keywords"):
                    lines.append(f"  Top keywords: {', '.join(ag['top_keywords'][:3])}")
                if ag.get("final_url"):
                    lines.append(f"  Landing page: {ag['final_url']}")
        lines.append(f"")

        lines.append(f"**Keywords ({total_keywords} total, {total_negatives} negatives)**")
        if tier_summary:
            lines.append(f"• Tiers: {' | '.join(tier_summary)}")
        lines.append(f"")

        lines.append(f"**Ad Copy**")
        lines.append(f"• {total_headlines} headlines (max 30 chars each)")
        lines.append(f"• {total_descriptions} descriptions (max 90 chars each)")
        lines.append(f"• Keyword-headline match: {kw_match}%")
        lines.append(f"")

        lines.append(f"**Targeting**")
        if geo_desc:
            lines.append(f"• Location: {geo_desc}")
        lines.append(f"• Mobile bid: {mobile_adj:+d}%")
        if tablet_adj:
            lines.append(f"• Tablet bid: {tablet_adj:+d}%")
        if schedule_desc:
            lines.append(f"• Schedule: {schedule_desc}")
        lines.append(f"")

        lines.append(f"**Extensions**")
        lines.append(f"• Sitelinks: {sitelink_count}")
        lines.append(f"• Callouts: {callout_count}")
        if has_snippets:
            lines.append(f"• Structured snippets: ✓")
        if has_call_ext:
            lines.append(f"• Call extension: {call_phone}")
        lines.append(f"")

        if tracking_number:
            lines.append(f"**Call Tracking (CallFlux)**")
            lines.append(f"• Tracking number: {tracking_number}")
            lines.append(f"• Forwards to: {forward_to}")
            lines.append(f"• Call recording: Enabled (AI transcription + lead scoring)")
            lines.append(f"• GCLID tracking: Enabled (offline conversion attribution)")
            lines.append(f"")

        if lp_generated or lp_existing:
            lines.append(f"**Landing Pages**")
            if lp_existing:
                lines.append(f"• {lp_existing} existing pages linked")
            if lp_generated:
                lines.append(f"• {lp_generated} new AI pages generated")
            lines.append(f"")

        lines.append(f"**Quality Score: {qa_score}/100 ({qa_grade})**")
        lines.append(f"")

        lines.append(f"**What to Expect (estimated)**")
        lines.append(f"• ~{est_clicks_day}-{est_clicks_day * 2} clicks/day")
        lines.append(f"• ~{est_clicks_month}-{est_clicks_month * 2} clicks/month")
        lines.append(f"• ~{est_conversions_month}-{est_conversions_month * 2} conversions/month")
        lines.append(f"• Est. CPA: ${est_cpa:.0f}-${est_cpa * 1.5:.0f}")
        lines.append(f"• Campaign starts PAUSED — enable it when you're ready")
        lines.append(f"• Google's learning period: 1-2 weeks to optimize bidding")
        lines.append(f"• First results: expect meaningful data after 7-14 days")

        text = "\n".join(lines)

        return {
            "text": text,
            "campaign_name": name,
            "campaign_type": campaign_type,
            "budget_daily": budget_daily,
            "budget_monthly": budget_monthly,
            "bidding_strategy": bidding,
            "target_cpa": target_cpa,
            "ad_groups": ag_details,
            "total_keywords": total_keywords,
            "total_negatives": total_negatives,
            "total_headlines": total_headlines,
            "total_descriptions": total_descriptions,
            "keyword_tiers": kw_stats,
            "geo": geo_desc,
            "mobile_bid_adj": mobile_adj,
            "schedule": schedule_desc,
            "sitelinks": sitelink_count,
            "callouts": callout_count,
            "has_snippets": has_snippets,
            "call_extension": call_phone,
            "tracking_number": tracking_number,
            "forward_to": forward_to,
            "landing_pages_generated": lp_generated,
            "landing_pages_existing": lp_existing,
            "qa_score": qa_score,
            "qa_grade": qa_grade,
            "keyword_headline_match": kw_match,
            "asset_groups": spec.get("asset_groups", []),
            "campaign_negatives": len(spec.get("campaign_negative_keywords", [])),
            "est_clicks_month": f"{est_clicks_month}-{est_clicks_month * 2}",
            "est_conversions_month": f"{est_conversions_month}-{est_conversions_month * 2}",
            "est_cpa": f"${est_cpa:.0f}-${est_cpa * 1.5:.0f}",
        }

    # ── FALLBACK ─────────────────────────────────────────────────

    def _format_competitor_ad_context(self, competitors: Dict) -> str:
        """
        Format competitor ad copy data so the Ad Copy agent can see what
        competitors are running and deliberately differentiate.
        """
        if not competitors:
            return ""

        lines = []

        # Top competitor domains with impression share
        top_comps = competitors.get("top_competitors", [])
        if top_comps:
            lines.append("COMPETITOR LANDSCAPE:")
            for c in top_comps[:5]:
                domain = c.get("domain", "?")
                imp_share = c.get("avg_impression_share", 0)
                outranking = c.get("avg_outranking_share", 0)
                lines.append(
                    f"  {domain} — {imp_share:.0%} impression share, "
                    f"outranks you {outranking:.0%} of the time"
                )

        # Messaging heatmap — what themes competitors use most
        heatmap = competitors.get("messaging_heatmap", {})
        themes = heatmap.get("themes", [])
        if themes:
            lines.append("\nCOMPETITOR MESSAGING THEMES (frequency):")
            for t in themes[:8]:
                theme = t.get("theme", "") if isinstance(t, dict) else str(t)
                freq = t.get("frequency", 0) if isinstance(t, dict) else 0
                lines.append(f"  \"{theme}\" — used by {freq} competitors")
            lines.append("  → Do NOT copy these themes. Differentiate.")

        # Differentiation suggestions from the competitor intel engine
        diff = competitors.get("differentiation_strategy", [])
        if diff:
            lines.append("\nDIFFERENTIATION OPPORTUNITIES:")
            for d in diff[:3]:
                lines.append(f"  • {d}")

        return "\n".join(lines) if lines else ""

    def _build_campaign_negatives(self, keywords: Dict) -> List[str]:
        """
        Build campaign-level negative keywords — cross-cutting terms that should
        be blocked for ALL ad groups. These prevent wasteful clicks from
        job seekers, DIY-ers, students, etc.
        """
        # Universal negatives for local service businesses
        universal_negatives = [
            "free", "diy", "how to", "tutorial", "course", "training",
            "jobs", "careers", "hiring", "salary", "intern",
            "complaints", "lawsuit", "scam", "fraud", "bbb complaint",
            "used", "parts only", "wholesale", "tools",
            "youtube", "video", "reddit", "quora", "wiki",
        ]

        # Add agent-generated negatives (deduplicated)
        agent_negatives = set()
        for neg in keywords.get("negatives", []):
            text = neg.get("text", "").lower().strip() if isinstance(neg, dict) else str(neg).lower().strip()
            if text:
                agent_negatives.add(text)

        # Merge: universal + agent-generated, remove any that conflict with positive keywords
        all_positives = set()
        for kw in keywords.get("keywords", []):
            text = kw.get("text", "").lower().strip() if isinstance(kw, dict) else str(kw).lower().strip()
            all_positives.add(text)

        campaign_negatives = []
        for neg in universal_negatives:
            # Don't add if any positive keyword contains this term
            if not any(neg in pos for pos in all_positives):
                campaign_negatives.append(neg)

        for neg in agent_negatives:
            if neg not in campaign_negatives and not any(neg in pos for pos in all_positives):
                campaign_negatives.append(neg)

        return campaign_negatives

    async def _check_final_url_reachability(self, spec: Dict) -> List[Dict]:
        """
        HTTP HEAD check on all final URLs in the spec.
        Returns list of issues for unreachable URLs.
        """
        import httpx
        issues = []
        checked_urls = set()

        urls_to_check = []
        for ag in spec.get("ad_groups", []):
            for ad in ag.get("ads", []):
                for url in ad.get("final_urls", []):
                    if url and url not in checked_urls:
                        checked_urls.add(url)
                        urls_to_check.append((ag.get("name", ""), url))
        for sl in spec.get("sitelinks", []):
            url = sl.get("final_url", "")
            if url and url not in checked_urls:
                checked_urls.add(url)
                urls_to_check.append(("sitelink", url))

        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            for source, url in urls_to_check[:15]:  # Cap at 15 to avoid delays
                try:
                    resp = await client.head(url)
                    if resp.status_code >= 400:
                        issues.append({
                            "severity": "critical",
                            "field": f"final_url ({source})",
                            "message": f"URL {url} returned HTTP {resp.status_code} — ad will be disapproved",
                            "check": "url_reachability",
                        })
                except Exception:
                    issues.append({
                        "severity": "warning",
                        "field": f"final_url ({source})",
                        "message": f"URL {url} is unreachable — verify before enabling campaign",
                        "check": "url_reachability",
                    })

        return issues

    def _build_pmax_asset_groups(
        self, strategy: Dict, keywords: Dict, ad_copy: Dict, context: Dict
    ) -> List[Dict]:
        """
        Build PMax asset group specs from pipeline agent outputs.

        PMax Asset Group requirements (Google Ads API):
        - headlines: up to 5, max 30 chars each (min 3)
        - long_headlines: up to 5, max 90 chars each (min 1)
        - descriptions: up to 5, max 90 chars each (min 2, one ≤60 chars)
        - business_name: max 25 chars (required)
        - final_url: required
        - search_themes: up to 10 per asset group (audience signals)
        - images: at least 1 landscape (1.91:1) and 1 square (1:1)
        """
        biz = context.get("business", {})
        services = strategy.get("services", [])
        locations = strategy.get("locations", [])

        # Group keywords by service for search themes
        kw_by_service = {}
        for kw in keywords.get("keywords", []):
            svc = kw.get("service", "")
            kw_by_service.setdefault(svc, []).append(kw)

        # Map ad copy by service
        copy_by_service = {}
        for ag in ad_copy.get("ad_groups", []):
            copy_by_service[ag.get("service", "")] = ag

        asset_groups = []
        for svc in services:
            svc_kws = kw_by_service.get(svc, [])
            svc_copy = copy_by_service.get(svc, {})

            # Headlines: take top 5 from the ad copy agent (max 30 chars)
            raw_headlines = svc_copy.get("headlines", [])
            headlines = []
            for h in raw_headlines[:5]:
                text = h if isinstance(h, str) else h.get("text", "") if isinstance(h, dict) else str(h)
                if text.strip():
                    headlines.append(text.strip()[:30])
            # Ensure minimum 3 headlines
            while len(headlines) < 3:
                location = locations[0] if locations else ""
                fallbacks = [
                    f"{svc[:30]}",
                    f"{svc} in {location}"[:30] if location else f"Expert {svc}"[:30],
                    f"Call Now for {svc}"[:30],
                ]
                for fb in fallbacks:
                    if fb not in headlines and len(headlines) < 3:
                        headlines.append(fb)

            # Long headlines: descriptions repurposed or generated (max 90 chars)
            raw_descs = svc_copy.get("descriptions", [])
            long_headlines = []
            for d in raw_descs[:3]:
                text = d if isinstance(d, str) else d.get("text", "") if isinstance(d, dict) else str(d)
                if text.strip():
                    long_headlines.append(text.strip()[:90])
            # Build additional long headlines from service + location + USP
            usps = biz.get("usps", [])
            if len(long_headlines) < 1:
                long_headlines.append(f"Professional {svc} Services — Call Today"[:90])
            if len(long_headlines) < 2 and usps:
                long_headlines.append(f"{svc} — {usps[0]}"[:90])

            # Descriptions: up to 5, max 90 chars (need one ≤60 chars)
            descriptions = []
            for d in raw_descs[:5]:
                text = d if isinstance(d, str) else d.get("text", "") if isinstance(d, dict) else str(d)
                if text.strip():
                    descriptions.append(text.strip()[:90])
            while len(descriptions) < 2:
                fallback_descs = [
                    f"Expert {svc} from {biz.get('name', 'us')}. Call for a free estimate!"[:90],
                    f"Trusted {svc} in {locations[0] if locations else 'your area'}. Licensed & insured."[:90],
                ]
                for fd in fallback_descs:
                    if len(descriptions) < 2:
                        descriptions.append(fd)
            # Ensure at least one description ≤60 chars (Google requirement)
            has_short = any(len(d) <= 60 for d in descriptions)
            if not has_short and descriptions:
                short_desc = descriptions[0][:60]
                descriptions.append(short_desc)

            # Business name
            business_name = biz.get("name", "")[:25] or svc[:25]

            # Final URL
            final_url = svc_copy.get("final_url", biz.get("website", ""))

            # Search themes: top keywords as audience signals (up to 10)
            search_themes = []
            # Prioritize high-intent keywords
            sorted_kws = sorted(svc_kws, key=lambda k: (
                {"emergency": 4, "high": 3, "medium": 2, "local": 1}.get(k.get("tier", ""), 0)
            ), reverse=True)
            for kw in sorted_kws[:10]:
                text = kw.get("text", "")
                if text and text not in search_themes:
                    search_themes.append(text)

            asset_group = {
                "name": f"{svc} — {locations[0] if locations else 'All Areas'}",
                "service": svc,
                "final_url": final_url,
                "headlines": headlines[:5],
                "long_headlines": long_headlines[:5],
                "descriptions": descriptions[:5],
                "business_name": business_name,
                "search_themes": search_themes[:10],
                # Image assets will be populated by image generation step
                "images": [],
            }
            asset_groups.append(asset_group)

        return asset_groups

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
