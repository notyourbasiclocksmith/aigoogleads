"""
Narrative Generator — uses LLM to produce plain-English executive summary
and strategic analysis from scan results.
"""
import json
import structlog
from typing import List, Optional, Dict, Any
from openai import AsyncOpenAI

from app.core.config import settings
from app.services.operator.schemas import (
    AccountSnapshot, RecommendationOutput, ExecutiveSummary, RecGroup,
)

logger = structlog.get_logger()


async def generate_narrative(
    snapshot: AccountSnapshot,
    summary: ExecutiveSummary,
    recommendations: List[RecommendationOutput],
    business_context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate a plain-English AI narrative explaining the scan findings.
    Falls back to template-based narrative if LLM is unavailable.
    """
    if settings.OPENAI_API_KEY:
        try:
            return await _llm_narrative(snapshot, summary, recommendations, business_context)
        except Exception as e:
            logger.error("LLM narrative generation failed, using template", error=str(e))

    return _template_narrative(snapshot, summary, recommendations)


async def _llm_narrative(
    snapshot: AccountSnapshot,
    summary: ExecutiveSummary,
    recommendations: List[RecommendationOutput],
    business_context: Optional[Dict[str, Any]] = None,
) -> str:
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    # Build compact recommendation summary for the prompt
    rec_summary = {}
    for rec in recommendations:
        group = rec.group_name.value
        if group not in rec_summary:
            rec_summary[group] = []
        rec_summary[group].append({
            "title": rec.title,
            "risk": rec.risk_level.value,
            "confidence": rec.confidence_score,
        })

    biz = business_context or {}

    prompt = f"""You are the AI Campaign Operator for IntelliAds.ai — a senior Google Ads strategist
analyzing a client's account.

ACCOUNT CONTEXT:
- Business: {biz.get('business_name', 'Local service business')} in {biz.get('city', 'their market')}
- Period: {snapshot.date_range_start} to {snapshot.date_range_end}
- Total spend: ${summary.spend_analyzed:,.2f}
- Total conversions: {summary.conversions_analyzed:.0f}
- Average CPA: ${snapshot.avg_cpa:,.2f}
- Campaigns: {len(snapshot.campaigns)}
- Keywords: {len(snapshot.keywords)}
- Search terms analyzed: {len(snapshot.search_terms)}

FINDINGS:
- Estimated wasted spend: ${summary.wasted_spend_estimate:,.2f}
- Missed opportunity: ${summary.missed_opportunity_estimate:,.2f}
- Total recommendations: {summary.total_recommendations}
  - Safe changes: {summary.safe_change_count}
  - Moderate risk: {summary.moderate_change_count}
  - High risk: {summary.high_risk_change_count}
- Projected conversion lift: {summary.projected_conversion_lift_low:.0f}-{summary.projected_conversion_lift_high:.0f}
- Projected CPA improvement: {summary.projected_cpa_improvement_pct:.1f}%

RECOMMENDATION GROUPS:
{json.dumps(rec_summary, indent=2)}

Write a concise executive summary (3-5 short paragraphs) that:
1. Opens with the key finding in ONE sentence
2. States the top 3 problems found
3. States the top 3 growth opportunities
4. Explains what you would do first and why
5. Closes with projected upside if all safe changes are approved

Write in confident, direct, professional language. No fluff or caveats.
Use specific numbers from the data. Address the business owner directly ("Your account...").
Do not use markdown headers — just flowing paragraphs.
"""

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=800,
    )
    return response.choices[0].message.content or _template_narrative(snapshot, summary, recommendations)


def _template_narrative(
    snapshot: AccountSnapshot,
    summary: ExecutiveSummary,
    recommendations: List[RecommendationOutput],
) -> str:
    """Fallback template-based narrative when LLM is unavailable."""
    parts = []

    # Opening
    if summary.wasted_spend_estimate > 0:
        parts.append(
            f"Your Google Ads account spent ${summary.spend_analyzed:,.2f} over this period and generated "
            f"{summary.conversions_analyzed:.0f} conversions. I identified approximately "
            f"${summary.wasted_spend_estimate:,.2f} in wasted spend that can be recovered."
        )
    else:
        parts.append(
            f"Your Google Ads account spent ${summary.spend_analyzed:,.2f} over this period and generated "
            f"{summary.conversions_analyzed:.0f} conversions at ${snapshot.avg_cpa:,.2f} CPA."
        )

    # Top problems
    problems = []
    waste_recs = [r for r in recommendations if r.group_name in {RecGroup.KEYWORDS_SEARCH_TERMS, RecGroup.NEGATIVE_KEYWORDS}]
    if waste_recs:
        waste_total = sum(abs(r.impact.spend_delta) for r in waste_recs)
        problems.append(f"${waste_total:,.0f} in spend going to non-converting keywords and search terms")

    budget_recs = [r for r in recommendations if r.group_name == RecGroup.BUDGET_BIDDING]
    if budget_recs:
        problems.append("Budget-limited campaigns that are leaving conversions on the table")

    copy_recs = [r for r in recommendations if r.group_name == RecGroup.AD_COPY]
    if copy_recs:
        problems.append("Weak or generic ad copy that could be performing significantly better")

    if problems:
        parts.append("Top issues found: " + "; ".join(problems[:3]) + ".")

    # Opportunities
    new_camp_recs = [r for r in recommendations if r.group_name == RecGroup.NEW_CAMPAIGNS]
    if new_camp_recs:
        parts.append(
            f"I also identified {len(new_camp_recs)} new campaign opportunities that could capture "
            f"additional high-intent traffic currently not covered by your account."
        )

    # Projected upside
    if summary.projected_conversion_lift_high > 0:
        parts.append(
            f"If all {summary.safe_change_count} safe changes are approved, I project "
            f"{summary.projected_conversion_lift_low:.0f}-{summary.projected_conversion_lift_high:.0f} "
            f"additional conversions and a potential CPA improvement of {summary.projected_cpa_improvement_pct:.1f}%."
        )

    return "\n\n".join(parts)
