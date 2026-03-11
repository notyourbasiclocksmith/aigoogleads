"""
Projection Engine — estimates likely outcome ranges if recommendations are applied.
Uses scenario bands: conservative, base, upside.
"""
import structlog
from typing import List, Dict, Any

from app.services.operator.schemas import (
    AccountSnapshot, RecommendationOutput, ImpactProjection, ExecutiveSummary,
    RecType, RecGroup, RiskLevel,
)

logger = structlog.get_logger()

# ── Uplift priors by recommendation type ─────────────────────────────────────
# These are industry-average priors that get confidence-weighted
TYPE_PRIORS: Dict[RecType, Dict[str, float]] = {
    RecType.PAUSE_KEYWORD:              {"spend_save_pct": 1.0, "conv_loss_pct": 0.0},
    RecType.ADD_NEGATIVE_KEYWORD:       {"spend_save_pct": 0.85, "conv_loss_pct": 0.02},
    RecType.LOWER_KEYWORD_BID:          {"cpa_improve_pct": 0.15, "click_loss_pct": 0.10},
    RecType.RAISE_KEYWORD_BID:          {"click_gain_pct": 0.12, "cpa_increase_pct": 0.05},
    RecType.INCREASE_BUDGET:            {"click_gain_pct": 0.25, "conv_gain_pct": 0.20},
    RecType.DECREASE_BUDGET:            {"spend_save_pct": 0.20, "conv_loss_pct": 0.10},
    RecType.REWRITE_RSA:                {"ctr_improve_pct": 0.15, "conv_gain_pct": 0.08},
    RecType.ADJUST_DEVICE_MODIFIER:     {"cpa_improve_pct": 0.10, "spend_save_pct": 0.08},
    RecType.ADD_AD_SCHEDULE_RULE:       {"spend_save_pct": 0.12, "conv_loss_pct": 0.02},
    RecType.SPLIT_AD_GROUP:             {"cpa_improve_pct": 0.08, "ctr_improve_pct": 0.10},
    RecType.ADD_BRAND_SPECIFIC_CAMPAIGN:{"conv_gain_pct": 0.15, "cpa_improve_pct": 0.12},
    RecType.ADD_HIGH_INTENT_CAMPAIGN:   {"conv_gain_pct": 0.20, "cpa_improve_pct": 0.15},
    RecType.CREATE_IMAGE_ASSET_PACK:    {"ctr_improve_pct": 0.05},
    RecType.ADD_SITELINKS:              {"ctr_improve_pct": 0.08},
    RecType.ADD_CALLOUTS:               {"ctr_improve_pct": 0.05},
}

SCENARIO_MULTIPLIERS = {
    "conservative": 0.5,
    "base": 1.0,
    "upside": 1.5,
}


def build_projections(
    snapshot: AccountSnapshot,
    recommendations: List[RecommendationOutput],
) -> ExecutiveSummary:
    """
    Build executive summary projections from all recommendations.
    Each recommendation's impact is confidence-weighted and scenario-banded.
    """
    total_spend_delta = 0.0
    total_conv_delta = 0.0
    total_click_delta = 0.0
    wasted_spend = 0.0
    missed_opportunity = 0.0

    for rec in recommendations:
        impact = rec.impact
        weight = rec.confidence_score

        # Accumulate spend delta (negative = savings)
        if impact.spend_delta < 0:
            wasted_spend += abs(impact.spend_delta) * weight
        elif impact.spend_delta > 0:
            missed_opportunity += impact.spend_delta * weight

        total_spend_delta += impact.spend_delta * weight
        total_conv_delta += impact.conversion_delta * weight
        total_click_delta += impact.click_delta * weight

        # Also accumulate from CPA delta if no explicit conversion delta
        if impact.conversion_delta == 0 and impact.cpa_delta < 0 and snapshot.avg_cpa > 0:
            implicit_conv_gain = abs(impact.cpa_delta) / snapshot.avg_cpa
            total_conv_delta += implicit_conv_gain * weight

    # Build scenario bands
    conv_low = total_conv_delta * SCENARIO_MULTIPLIERS["conservative"]
    conv_high = total_conv_delta * SCENARIO_MULTIPLIERS["upside"]

    # CPA improvement estimate
    current_cpa = snapshot.avg_cpa
    if current_cpa > 0 and total_conv_delta > 0:
        new_spend = snapshot.total_spend + total_spend_delta
        new_conv = snapshot.total_conversions + total_conv_delta
        projected_cpa = new_spend / new_conv if new_conv > 0 else current_cpa
        cpa_improvement_pct = round((1 - projected_cpa / current_cpa) * 100, 1)
    else:
        cpa_improvement_pct = 0.0

    # Risk & confidence scoring
    risk_scores = {RiskLevel.LOW: 0.2, RiskLevel.MEDIUM: 0.5, RiskLevel.HIGH: 0.9}
    avg_confidence = (
        sum(r.confidence_score for r in recommendations) / len(recommendations)
        if recommendations else 0.0
    )
    avg_risk = (
        sum(risk_scores.get(r.risk_level, 0.5) for r in recommendations) / len(recommendations)
        if recommendations else 0.0
    )

    safe_count = sum(1 for r in recommendations if r.risk_level == RiskLevel.LOW)
    med_count = sum(1 for r in recommendations if r.risk_level == RiskLevel.MEDIUM)
    high_count = sum(1 for r in recommendations if r.risk_level == RiskLevel.HIGH)

    return ExecutiveSummary(
        spend_analyzed=round(snapshot.total_spend, 2),
        conversions_analyzed=round(snapshot.total_conversions, 1),
        wasted_spend_estimate=round(wasted_spend, 2),
        missed_opportunity_estimate=round(missed_opportunity, 2),
        projected_conversion_lift_low=round(conv_low, 1),
        projected_conversion_lift_high=round(conv_high, 1),
        projected_cpa_improvement_pct=cpa_improvement_pct,
        confidence_score=round(avg_confidence, 2),
        risk_score=round(avg_risk, 2),
        safe_change_count=safe_count,
        moderate_change_count=med_count,
        high_risk_change_count=high_count,
        total_recommendations=len(recommendations),
    )


def project_selected_changes(
    snapshot: AccountSnapshot,
    selected_recs: List[RecommendationOutput],
) -> Dict[str, Any]:
    """
    Project impact of only the selected (approved) recommendations.
    Returns scenario-banded projections.
    """
    scenarios: Dict[str, Dict[str, float]] = {}

    for scenario_name, mult in SCENARIO_MULTIPLIERS.items():
        s_spend = 0.0
        s_conv = 0.0
        s_clicks = 0.0

        for rec in selected_recs:
            w = rec.confidence_score * mult
            s_spend += rec.impact.spend_delta * w
            s_conv += rec.impact.conversion_delta * w
            s_clicks += rec.impact.click_delta * w

        current_cpa = snapshot.avg_cpa
        new_spend = snapshot.total_spend + s_spend
        new_conv = snapshot.total_conversions + s_conv
        projected_cpa = new_spend / new_conv if new_conv > 0 else current_cpa

        scenarios[scenario_name] = {
            "spend_delta": round(s_spend, 2),
            "conversion_delta": round(s_conv, 1),
            "click_delta": round(s_clicks, 0),
            "projected_cpa": round(projected_cpa, 2),
            "projected_spend": round(new_spend, 2),
            "projected_conversions": round(new_conv, 1),
        }

    return {
        "scenarios": scenarios,
        "selected_count": len(selected_recs),
        "current_spend": snapshot.total_spend,
        "current_conversions": snapshot.total_conversions,
        "current_cpa": round(snapshot.avg_cpa, 2),
    }
