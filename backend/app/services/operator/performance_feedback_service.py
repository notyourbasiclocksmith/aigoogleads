"""
Performance Feedback Service — mines past pipeline runs and Google Ads
performance to build a "learnings" context injected into Strategist and
Ad Copy agents on future pipeline runs.

Pure data analysis — no LLM calls.  Every public method returns an empty
dict / empty string on failure so callers never need to guard against
exceptions.
"""

import structlog
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline_execution_log import PipelineExecutionLog

logger = structlog.get_logger()

# ── Thresholds ──────────────────────────────────────────────────────────
CTR_HIGH_THRESHOLD = 5.0        # Headlines with CTR above this are "top"
CTR_LOW_THRESHOLD = 1.5         # Headlines below this are "failed"
MIN_IMPRESSIONS = 200           # Ignore low-traffic noise
LOOKBACK_DAYS = 90              # How far back to scan pipeline logs
MAX_TOP_HEADLINES = 20
MAX_FAILED_HEADLINES = 15
MAX_TOP_KEYWORDS = 20
MAX_FAILED_KEYWORDS = 15

# Ad-copy angle keywords (simple heuristic classification)
ANGLE_KEYWORDS: Dict[str, List[str]] = {
    "urgency": ["now", "today", "fast", "hurry", "limited", "immediate", "emergency", "24/7", "same day", "same-day"],
    "premium": ["expert", "certified", "trusted", "professional", "top-rated", "licensed", "award", "#1", "best"],
    "price": ["free", "affordable", "$", "cheap", "discount", "save", "low cost", "no fee", "special offer", "deal"],
    "guarantee": ["guarantee", "warranty", "money back", "satisfaction", "risk-free", "no risk"],
    "social_proof": ["reviews", "rated", "customers", "families", "trusted by", "5-star", "testimonial"],
}


# ═══════════════════════════════════════════════════════════════════════
#  1. Pipeline-log learnings (from PipelineExecutionLog.output_full)
# ═══════════════════════════════════════════════════════════════════════

async def get_pipeline_learnings(
    tenant_id: str,
    services: List[str],
    db: AsyncSession,
) -> Dict[str, Any]:
    """
    Query completed pipeline runs for this tenant and extract reusable
    patterns: top headlines, keywords, quality scores, budget insights,
    and failed patterns.

    Parameters
    ----------
    tenant_id : str
    services  : list[str]  – the services being requested now (used to
                filter relevant past runs)
    db        : AsyncSession

    Returns
    -------
    dict with keys: top_performing_headlines, top_performing_keywords,
    winning_angles, avg_pipeline_quality, budget_insights, failed_patterns.
    Returns empty dict on error.
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

        stmt = (
            select(PipelineExecutionLog)
            .where(
                and_(
                    PipelineExecutionLog.tenant_id == tenant_id,
                    PipelineExecutionLog.service_type == "campaign_pipeline",
                    PipelineExecutionLog.status == "completed",
                    PipelineExecutionLog.started_at >= cutoff,
                )
            )
            .order_by(desc(PipelineExecutionLog.started_at))
            .limit(50)
        )
        result = await db.execute(stmt)
        logs: List[PipelineExecutionLog] = list(result.scalars().all())

        if not logs:
            logger.info("No completed pipeline logs found for learnings", tenant_id=tenant_id)
            return _empty_learnings()

        # Aggregate data across all past runs
        all_headlines: List[Dict[str, Any]] = []
        all_keywords: List[Dict[str, Any]] = []
        qa_scores: List[float] = []
        budget_values: List[float] = []
        service_budgets: Dict[str, List[float]] = defaultdict(list)

        for log in logs:
            output = log.output_full or {}
            summary = log.output_summary or {}

            # ── QA scores ──────────────────────────────────────────
            qa_score = summary.get("qa_score")
            if qa_score is not None:
                qa_scores.append(float(qa_score))

            # ── Budget insights ────────────────────────────────────
            daily_budget = summary.get("budget_daily")
            if daily_budget is not None:
                budget_values.append(float(daily_budget))
                # Associate budget with services from input
                input_services = (log.input_summary or {}).get("services", [])
                if isinstance(input_services, list):
                    for svc in input_services:
                        service_budgets[svc].append(float(daily_budget))

            # ── Headlines + keywords from output_full ──────────────
            _extract_headlines_from_output(output, all_headlines)
            _extract_keywords_from_output(output, all_keywords)

        # ── Process aggregated data ────────────────────────────────────
        top_headlines = _rank_headlines(all_headlines, top=True)[:MAX_TOP_HEADLINES]
        failed_headlines = _rank_headlines(all_headlines, top=False)[:MAX_FAILED_HEADLINES]

        top_keywords = _rank_keywords(all_keywords, top=True)[:MAX_TOP_KEYWORDS]
        failed_keywords = _rank_keywords(all_keywords, top=False)[:MAX_FAILED_KEYWORDS]

        winning_angles = _compute_winning_angles(top_headlines)

        # Budget insights for the requested services
        budget_insights = {}
        for svc in services:
            svc_budgets = service_budgets.get(svc, budget_values)
            if svc_budgets:
                budget_insights[svc] = {
                    "avg_daily": round(sum(svc_budgets) / len(svc_budgets), 2),
                    "min_daily": round(min(svc_budgets), 2),
                    "max_daily": round(max(svc_budgets), 2),
                    "sample_count": len(svc_budgets),
                }

        learnings = {
            "top_performing_headlines": top_headlines,
            "top_performing_keywords": top_keywords,
            "winning_angles": winning_angles,
            "avg_pipeline_quality": round(sum(qa_scores) / len(qa_scores), 1) if qa_scores else None,
            "budget_insights": budget_insights,
            "failed_patterns": {
                "headlines": failed_headlines,
                "keywords": failed_keywords,
            },
            "pipeline_runs_analyzed": len(logs),
        }

        logger.info(
            "Pipeline learnings extracted",
            tenant_id=tenant_id,
            runs_analyzed=len(logs),
            top_headlines=len(top_headlines),
            top_keywords=len(top_keywords),
        )
        return learnings

    except Exception:
        logger.exception("Failed to extract pipeline learnings", tenant_id=tenant_id)
        return _empty_learnings()


# ═══════════════════════════════════════════════════════════════════════
#  2. Live Google Ads performance patterns
# ═══════════════════════════════════════════════════════════════════════

async def get_ad_performance_patterns(
    tenant_id: str,
    ads_client: Any,
) -> Dict[str, Any]:
    """
    Pull real performance data from Google Ads and surface patterns.

    Parameters
    ----------
    tenant_id  : str
    ads_client : GoogleAdsClient instance (from app.integrations.google_ads.client)

    Returns
    -------
    dict with keys: top_headlines, bottom_headlines, keywords_by_conversion_rate,
    best_ad_groups_by_roas, time_of_day_patterns.
    Returns empty dict on error.
    """
    if ads_client is None:
        return _empty_ad_patterns()

    try:
        client = ads_client._get_client()
        ga_service = client.get_service("GoogleAdsService")
        customer_id = ads_client.customer_id

        # Run queries in parallel-ish (sequential here, but each is fast)
        headline_data = await _query_headline_performance(ga_service, customer_id)
        keyword_data = await _query_keyword_conversions(ga_service, customer_id)
        ad_group_data = await _query_ad_group_roas(ga_service, customer_id)
        hour_data = await _query_hour_of_day(ga_service, customer_id)

        # ── Rank headlines by CTR ──────────────────────────────────
        sorted_by_ctr = sorted(headline_data, key=lambda h: h["ctr"], reverse=True)
        top_headlines = sorted_by_ctr[:10]
        bottom_headlines = sorted_by_ctr[-10:] if len(sorted_by_ctr) >= 10 else []

        # ── Keywords by conversion rate ────────────────────────────
        converting = [k for k in keyword_data if k["conversions"] > 0]
        keywords_by_conv = sorted(converting, key=lambda k: k["conv_rate"], reverse=True)[:20]

        # ── Ad groups by ROAS ──────────────────────────────────────
        roas_groups = [g for g in ad_group_data if g["cost"] > 0]
        for g in roas_groups:
            g["roas"] = round(g["conv_value"] / g["cost"], 2) if g["cost"] > 0 else 0
        best_groups = sorted(roas_groups, key=lambda g: g["roas"], reverse=True)[:10]

        # ── Time-of-day patterns ───────────────────────────────────
        time_patterns = _analyze_hour_data(hour_data)

        patterns = {
            "top_headlines": top_headlines,
            "bottom_headlines": bottom_headlines,
            "keywords_by_conversion_rate": keywords_by_conv,
            "best_ad_groups_by_roas": best_groups,
            "time_of_day_patterns": time_patterns,
        }

        logger.info(
            "Ad performance patterns extracted",
            tenant_id=tenant_id,
            headlines_analyzed=len(headline_data),
            converting_keywords=len(converting),
        )
        return patterns

    except Exception:
        logger.exception("Failed to extract ad performance patterns", tenant_id=tenant_id)
        return _empty_ad_patterns()


# ═══════════════════════════════════════════════════════════════════════
#  3. Combined feedback context for agent prompts
# ═══════════════════════════════════════════════════════════════════════

async def build_feedback_context(
    tenant_id: str,
    services: List[str],
    db: AsyncSession,
    ads_client: Optional[Any] = None,
) -> str:
    """
    Combine pipeline learnings and live ad performance into a single
    formatted text block suitable for injection into agent system prompts.

    Returns an empty string if no useful data is available.
    """
    try:
        pipeline_learnings = await get_pipeline_learnings(tenant_id, services, db)
        ad_patterns = await get_ad_performance_patterns(tenant_id, ads_client)

        sections: List[str] = []

        # ── Pipeline quality ───────────────────────────────────────
        avg_qa = pipeline_learnings.get("avg_pipeline_quality")
        runs = pipeline_learnings.get("pipeline_runs_analyzed", 0)
        if avg_qa is not None:
            sections.append(
                f"PIPELINE HISTORY: {runs} past runs analyzed, average QA score: {avg_qa}/100."
            )

        # ── Top-performing headlines ───────────────────────────────
        top_hl = pipeline_learnings.get("top_performing_headlines", [])
        live_top = ad_patterns.get("top_headlines", [])
        all_top_hl = _merge_headline_lists(top_hl, live_top)
        if all_top_hl:
            hl_lines = [f'  - "{h["text"]}" (CTR {h["ctr"]}%)' for h in all_top_hl[:12]]
            sections.append("TOP-PERFORMING HEADLINES (reuse these patterns):\n" + "\n".join(hl_lines))

        # ── Failed headlines ───────────────────────────────────────
        failed_hl = pipeline_learnings.get("failed_patterns", {}).get("headlines", [])
        live_bottom = ad_patterns.get("bottom_headlines", [])
        all_failed_hl = _merge_headline_lists(failed_hl, live_bottom)
        if all_failed_hl:
            fh_lines = [f'  - "{h["text"]}" (CTR {h["ctr"]}%)' for h in all_failed_hl[:8]]
            sections.append("UNDERPERFORMING HEADLINES (avoid these patterns):\n" + "\n".join(fh_lines))

        # ── Top keywords ──────────────────────────────────────────
        top_kw = pipeline_learnings.get("top_performing_keywords", [])
        live_kw = ad_patterns.get("keywords_by_conversion_rate", [])
        all_kw = _merge_keyword_lists(top_kw, live_kw)
        if all_kw:
            kw_lines = [f'  - "{k["text"]}" ({k.get("conversions", 0)} conv, CPC ${k.get("cpc", "?")})' for k in all_kw[:10]]
            sections.append("TOP-PERFORMING KEYWORDS:\n" + "\n".join(kw_lines))

        # ── Winning angles ─────────────────────────────────────────
        angles = pipeline_learnings.get("winning_angles", {})
        if angles:
            angle_lines = [f"  - {angle}: {data['score']:.0f} avg CTR, {data['count']} examples"
                           for angle, data in sorted(angles.items(), key=lambda x: x[1]["score"], reverse=True)]
            sections.append("WINNING AD COPY ANGLES:\n" + "\n".join(angle_lines))

        # ── Budget insights ────────────────────────────────────────
        budgets = pipeline_learnings.get("budget_insights", {})
        if budgets:
            budget_lines = [f"  - {svc}: avg ${b['avg_daily']}/day (range ${b['min_daily']}-${b['max_daily']}, {b['sample_count']} runs)"
                            for svc, b in budgets.items()]
            sections.append("BUDGET INSIGHTS FROM PAST CAMPAIGNS:\n" + "\n".join(budget_lines))

        # ── Best ad groups by ROAS ─────────────────────────────────
        best_groups = ad_patterns.get("best_ad_groups_by_roas", [])
        if best_groups:
            group_lines = [f'  - "{g["name"]}" ROAS {g["roas"]}x (${g["cost"]:.0f} spend)'
                           for g in best_groups[:5]]
            sections.append("BEST AD GROUPS BY ROAS:\n" + "\n".join(group_lines))

        # ── Time-of-day patterns ───────────────────────────────────
        time_patterns = ad_patterns.get("time_of_day_patterns", {})
        if time_patterns.get("best_hours") or time_patterns.get("worst_hours"):
            tp_lines = []
            if time_patterns.get("best_hours"):
                tp_lines.append(f"  - Best hours: {', '.join(str(h) for h in time_patterns['best_hours'])}")
            if time_patterns.get("worst_hours"):
                tp_lines.append(f"  - Worst hours: {', '.join(str(h) for h in time_patterns['worst_hours'])}")
            sections.append("TIME-OF-DAY PATTERNS:\n" + "\n".join(tp_lines))

        if not sections:
            return ""

        header = "=== PERFORMANCE FEEDBACK (from past campaigns) ==="
        footer = "=== END PERFORMANCE FEEDBACK ==="
        return f"{header}\n\n" + "\n\n".join(sections) + f"\n\n{footer}"

    except Exception:
        logger.exception("Failed to build feedback context", tenant_id=tenant_id)
        return ""


# ═══════════════════════════════════════════════════════════════════════
#  Private helpers — pipeline log extraction
# ═══════════════════════════════════════════════════════════════════════

def _empty_learnings() -> Dict[str, Any]:
    return {
        "top_performing_headlines": [],
        "top_performing_keywords": [],
        "winning_angles": {},
        "avg_pipeline_quality": None,
        "budget_insights": {},
        "failed_patterns": {"headlines": [], "keywords": []},
        "pipeline_runs_analyzed": 0,
    }


def _empty_ad_patterns() -> Dict[str, Any]:
    return {
        "top_headlines": [],
        "bottom_headlines": [],
        "keywords_by_conversion_rate": [],
        "best_ad_groups_by_roas": [],
        "time_of_day_patterns": {},
    }


def _extract_headlines_from_output(output: Dict, accumulator: List[Dict]) -> None:
    """Walk output_full JSON to find headline performance data."""
    if not isinstance(output, dict):
        return

    # Check for ad_copy agent output which typically contains headlines
    ad_copy = output.get("ad_copy", output.get("ad_copy_agent", {}))
    if isinstance(ad_copy, dict):
        for ad_group in ad_copy.get("ad_groups", []):
            if not isinstance(ad_group, dict):
                continue
            for ad in ad_group.get("ads", ad_group.get("responsive_search_ads", [])):
                if not isinstance(ad, dict):
                    continue
                headlines = ad.get("headlines", [])
                ctr = ad.get("ctr", ad.get("expected_ctr"))
                for hl in headlines:
                    text = hl.get("text", hl) if isinstance(hl, dict) else str(hl)
                    if text and len(text) > 3:
                        accumulator.append({
                            "text": text,
                            "ctr": float(ctr) if ctr is not None else 0.0,
                            "source": "pipeline",
                        })

    # Also check top-level campaigns list
    for campaign in output.get("campaigns", []):
        if not isinstance(campaign, dict):
            continue
        for ag in campaign.get("ad_groups", []):
            if not isinstance(ag, dict):
                continue
            for ad in ag.get("ads", ag.get("responsive_search_ads", [])):
                if not isinstance(ad, dict):
                    continue
                headlines = ad.get("headlines", [])
                ctr = ad.get("ctr")
                for hl in headlines:
                    text = hl.get("text", hl) if isinstance(hl, dict) else str(hl)
                    if text and len(text) > 3:
                        accumulator.append({
                            "text": text,
                            "ctr": float(ctr) if ctr is not None else 0.0,
                            "source": "pipeline",
                        })


def _extract_keywords_from_output(output: Dict, accumulator: List[Dict]) -> None:
    """Walk output_full JSON to find keyword data."""
    if not isinstance(output, dict):
        return

    keyword_data = output.get("keyword_research", output.get("keyword_research_agent", {}))
    if isinstance(keyword_data, dict):
        for kw in keyword_data.get("keywords", []):
            if not isinstance(kw, dict):
                continue
            text = kw.get("text", kw.get("keyword", ""))
            if text:
                accumulator.append({
                    "text": text,
                    "conversions": float(kw.get("conversions", 0)),
                    "cpc": float(kw.get("cpc", kw.get("avg_cpc", 0))),
                    "ctr": float(kw.get("ctr", 0)),
                    "impressions": int(kw.get("impressions", 0)),
                    "source": "pipeline",
                })

    # Walk campaigns -> ad_groups -> keywords
    for campaign in output.get("campaigns", []):
        if not isinstance(campaign, dict):
            continue
        for ag in campaign.get("ad_groups", []):
            if not isinstance(ag, dict):
                continue
            for kw in ag.get("keywords", []):
                if not isinstance(kw, dict):
                    continue
                text = kw.get("text", kw.get("keyword", ""))
                if text:
                    accumulator.append({
                        "text": text,
                        "conversions": float(kw.get("conversions", 0)),
                        "cpc": float(kw.get("cpc", kw.get("avg_cpc", 0))),
                        "ctr": float(kw.get("ctr", 0)),
                        "impressions": int(kw.get("impressions", 0)),
                        "source": "pipeline",
                    })


def _rank_headlines(headlines: List[Dict], top: bool = True) -> List[Dict]:
    """Deduplicate and rank headlines by CTR."""
    seen: Dict[str, Dict] = {}
    for h in headlines:
        text = h.get("text", "").strip().lower()
        if not text:
            continue
        existing = seen.get(text)
        if existing is None:
            seen[text] = {**h, "text": h.get("text", "").strip(), "count": 1}
        else:
            # Keep the better CTR and increment count
            if h.get("ctr", 0) > existing.get("ctr", 0):
                seen[text]["ctr"] = h["ctr"]
            seen[text]["count"] = existing.get("count", 1) + 1

    ranked = list(seen.values())
    if top:
        # High CTR, with minimum impressions filter for live data
        ranked = [h for h in ranked if h.get("ctr", 0) >= CTR_HIGH_THRESHOLD or h.get("source") == "pipeline"]
        ranked.sort(key=lambda h: h.get("ctr", 0), reverse=True)
    else:
        # Low CTR with enough impressions to be meaningful
        ranked = [h for h in ranked if h.get("ctr", 0) < CTR_LOW_THRESHOLD and h.get("impressions", MIN_IMPRESSIONS) >= MIN_IMPRESSIONS]
        ranked.sort(key=lambda h: h.get("ctr", 0))

    return ranked


def _rank_keywords(keywords: List[Dict], top: bool = True) -> List[Dict]:
    """Deduplicate and rank keywords."""
    seen: Dict[str, Dict] = {}
    for k in keywords:
        text = k.get("text", "").strip().lower()
        if not text:
            continue
        existing = seen.get(text)
        if existing is None:
            seen[text] = {**k, "text": k.get("text", "").strip()}
        else:
            # Accumulate conversions, keep best CPC
            seen[text]["conversions"] = seen[text].get("conversions", 0) + k.get("conversions", 0)
            if k.get("cpc", 999) < seen[text].get("cpc", 999):
                seen[text]["cpc"] = k["cpc"]

    ranked = list(seen.values())
    if top:
        ranked = [k for k in ranked if k.get("conversions", 0) > 0]
        ranked.sort(key=lambda k: (k.get("conversions", 0), -k.get("cpc", 999)), reverse=True)
    else:
        # Keywords that spent but never converted
        ranked = [k for k in ranked if k.get("conversions", 0) == 0 and k.get("impressions", 0) >= MIN_IMPRESSIONS]
        ranked.sort(key=lambda k: k.get("impressions", 0), reverse=True)

    return ranked


def _compute_winning_angles(top_headlines: List[Dict]) -> Dict[str, Dict[str, Any]]:
    """Classify top headlines into ad copy angles and score them."""
    angle_stats: Dict[str, List[float]] = defaultdict(list)

    for h in top_headlines:
        text = h.get("text", "").lower()
        ctr = h.get("ctr", 0)
        for angle, trigger_words in ANGLE_KEYWORDS.items():
            if any(word in text for word in trigger_words):
                angle_stats[angle].append(ctr)

    result = {}
    for angle, ctrs in angle_stats.items():
        if ctrs:
            result[angle] = {
                "score": round(sum(ctrs) / len(ctrs), 2),
                "count": len(ctrs),
                "best_ctr": round(max(ctrs), 2),
            }

    return result


# ═══════════════════════════════════════════════════════════════════════
#  Private helpers — Google Ads queries
# ═══════════════════════════════════════════════════════════════════════

async def _query_headline_performance(ga_service: Any, customer_id: str) -> List[Dict]:
    """Query ad-level data and extract per-headline performance estimates."""
    try:
        query = """
            SELECT
                ad_group_ad.ad.id,
                ad_group_ad.ad.responsive_search_ad.headlines,
                ad_group_ad.ad.responsive_search_ad.descriptions,
                ad_group.name,
                metrics.impressions, metrics.clicks, metrics.ctr,
                metrics.conversions, metrics.cost_micros
            FROM ad_group_ad
            WHERE campaign.status != 'REMOVED'
                AND ad_group_ad.status != 'REMOVED'
                AND segments.date DURING LAST_30_DAYS
                AND metrics.impressions > 50
            ORDER BY metrics.impressions DESC
            LIMIT 100
        """
        response = ga_service.search(customer_id=customer_id, query=query)

        headlines = []
        for row in response:
            impressions = row.metrics.impressions
            clicks = row.metrics.clicks
            ctr = round(row.metrics.ctr * 100, 2) if row.metrics.ctr else 0
            conversions = row.metrics.conversions

            try:
                for hl in row.ad_group_ad.ad.responsive_search_ad.headlines:
                    headlines.append({
                        "text": hl.text,
                        "ctr": ctr,
                        "impressions": impressions,
                        "clicks": clicks,
                        "conversions": conversions,
                        "ad_group": row.ad_group.name,
                        "source": "google_ads",
                    })
            except Exception:
                pass

        return headlines
    except Exception:
        logger.exception("Failed to query headline performance")
        return []


async def _query_keyword_conversions(ga_service: Any, customer_id: str) -> List[Dict]:
    """Query keyword-level conversion data."""
    try:
        query = """
            SELECT
                ad_group_criterion.keyword.text,
                ad_group_criterion.keyword.match_type,
                ad_group.name,
                campaign.name,
                metrics.impressions, metrics.clicks, metrics.cost_micros,
                metrics.conversions, metrics.conversions_value,
                metrics.average_cpc
            FROM keyword_view
            WHERE campaign.status != 'REMOVED'
                AND ad_group_criterion.status != 'REMOVED'
                AND segments.date DURING LAST_30_DAYS
                AND metrics.impressions > 10
            ORDER BY metrics.conversions DESC
            LIMIT 200
        """
        response = ga_service.search(customer_id=customer_id, query=query)

        keywords = []
        for row in response:
            impressions = row.metrics.impressions
            clicks = row.metrics.clicks
            conversions = row.metrics.conversions
            cost = row.metrics.cost_micros / 1_000_000
            conv_rate = round((conversions / clicks) * 100, 2) if clicks > 0 else 0

            keywords.append({
                "text": row.ad_group_criterion.keyword.text,
                "match_type": row.ad_group_criterion.keyword.match_type.name,
                "impressions": impressions,
                "clicks": clicks,
                "conversions": conversions,
                "conv_value": row.metrics.conversions_value,
                "cost": round(cost, 2),
                "cpc": round(row.metrics.average_cpc / 1_000_000, 2),
                "conv_rate": conv_rate,
                "campaign": row.campaign.name,
                "ad_group": row.ad_group.name,
                "source": "google_ads",
            })

        return keywords
    except Exception:
        logger.exception("Failed to query keyword conversions")
        return []


async def _query_ad_group_roas(ga_service: Any, customer_id: str) -> List[Dict]:
    """Query ad group level ROAS data."""
    try:
        query = """
            SELECT
                ad_group.id, ad_group.name,
                campaign.name,
                metrics.cost_micros, metrics.conversions,
                metrics.conversions_value, metrics.clicks, metrics.impressions
            FROM ad_group
            WHERE campaign.status != 'REMOVED'
                AND ad_group.status != 'REMOVED'
                AND segments.date DURING LAST_30_DAYS
                AND metrics.cost_micros > 0
            ORDER BY metrics.conversions_value DESC
            LIMIT 50
        """
        response = ga_service.search(customer_id=customer_id, query=query)

        groups = []
        for row in response:
            cost = row.metrics.cost_micros / 1_000_000
            groups.append({
                "ad_group_id": str(row.ad_group.id),
                "name": row.ad_group.name,
                "campaign": row.campaign.name,
                "cost": round(cost, 2),
                "conversions": row.metrics.conversions,
                "conv_value": round(row.metrics.conversions_value, 2),
                "clicks": row.metrics.clicks,
                "impressions": row.metrics.impressions,
            })

        return groups
    except Exception:
        logger.exception("Failed to query ad group ROAS")
        return []


async def _query_hour_of_day(ga_service: Any, customer_id: str) -> List[Dict]:
    """Query performance by hour of day."""
    try:
        query = """
            SELECT
                segments.hour,
                metrics.impressions, metrics.clicks, metrics.cost_micros,
                metrics.conversions, metrics.conversions_value
            FROM campaign
            WHERE campaign.status = 'ENABLED'
                AND segments.date DURING LAST_14_DAYS
            ORDER BY segments.hour
        """
        response = ga_service.search(customer_id=customer_id, query=query)

        # Aggregate by hour
        hours: Dict[int, Dict] = defaultdict(lambda: {
            "impressions": 0, "clicks": 0, "cost_micros": 0,
            "conversions": 0, "conv_value": 0,
        })
        for row in response:
            h = row.segments.hour
            hours[h]["impressions"] += row.metrics.impressions
            hours[h]["clicks"] += row.metrics.clicks
            hours[h]["cost_micros"] += row.metrics.cost_micros
            hours[h]["conversions"] += row.metrics.conversions
            hours[h]["conv_value"] += row.metrics.conversions_value

        result = []
        for hour, data in sorted(hours.items()):
            clicks = data["clicks"]
            cost = data["cost_micros"] / 1_000_000
            conversions = data["conversions"]
            result.append({
                "hour": hour,
                "impressions": data["impressions"],
                "clicks": clicks,
                "cost": round(cost, 2),
                "conversions": conversions,
                "conv_value": round(data["conv_value"], 2),
                "ctr": round((clicks / data["impressions"]) * 100, 2) if data["impressions"] > 0 else 0,
                "conv_rate": round((conversions / clicks) * 100, 2) if clicks > 0 else 0,
                "cpa": round(cost / conversions, 2) if conversions > 0 else None,
            })

        return result
    except Exception:
        logger.exception("Failed to query hour-of-day performance")
        return []


def _analyze_hour_data(hour_data: List[Dict]) -> Dict[str, Any]:
    """Identify best and worst hours from aggregated hour-of-day data."""
    if not hour_data:
        return {}

    # Score each hour: prefer high conv_rate and low CPA
    scored = []
    for h in hour_data:
        # Simple composite score: conversion rate weighted higher
        conv_rate = h.get("conv_rate", 0)
        ctr = h.get("ctr", 0)
        score = conv_rate * 2 + ctr
        scored.append({"hour": h["hour"], "score": score, "conv_rate": conv_rate, "ctr": ctr})

    scored.sort(key=lambda x: x["score"], reverse=True)

    # Filter to hours with meaningful traffic
    active_hours = [s for s in scored if s["conv_rate"] > 0 or s["ctr"] > 0]
    if not active_hours:
        return {}

    best = [s["hour"] for s in active_hours[:5]]
    worst = [s["hour"] for s in active_hours[-5:]]

    return {
        "best_hours": best,
        "worst_hours": worst,
        "best_conv_rate_hour": active_hours[0]["hour"] if active_hours else None,
        "detail": [{"hour": h["hour"], "conv_rate": h.get("conv_rate", 0), "ctr": h.get("ctr", 0), "cpa": h.get("cpa")} for h in hour_data],
    }


# ═══════════════════════════════════════════════════════════════════════
#  Private helpers — merging pipeline + live data
# ═══════════════════════════════════════════════════════════════════════

def _merge_headline_lists(pipeline_hl: List[Dict], live_hl: List[Dict]) -> List[Dict]:
    """Merge and deduplicate headlines from pipeline logs and live ads."""
    seen: Dict[str, Dict] = {}

    # Live data takes priority (has real performance)
    for h in live_hl:
        text = h.get("text", "").strip().lower()
        if text:
            seen[text] = {**h, "text": h.get("text", "").strip()}

    for h in pipeline_hl:
        text = h.get("text", "").strip().lower()
        if text and text not in seen:
            seen[text] = {**h, "text": h.get("text", "").strip()}

    result = list(seen.values())
    result.sort(key=lambda h: h.get("ctr", 0), reverse=True)
    return result


def _merge_keyword_lists(pipeline_kw: List[Dict], live_kw: List[Dict]) -> List[Dict]:
    """Merge and deduplicate keywords from pipeline logs and live ads."""
    seen: Dict[str, Dict] = {}

    for k in live_kw:
        text = k.get("text", "").strip().lower()
        if text:
            seen[text] = {**k, "text": k.get("text", "").strip()}

    for k in pipeline_kw:
        text = k.get("text", "").strip().lower()
        if text and text not in seen:
            seen[text] = {**k, "text": k.get("text", "").strip()}

    result = list(seen.values())
    result.sort(key=lambda k: (k.get("conversions", 0), -k.get("cpc", 999)), reverse=True)
    return result
