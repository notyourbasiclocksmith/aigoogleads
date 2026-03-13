"""
Recommendation Engine — hybrid rules + heuristics + LLM reasoning.
Converts raw AccountSnapshot into actionable recommendations.
"""
import structlog
from typing import List, Dict, Any

from app.services.operator.schemas import (
    AccountSnapshot, RecommendationOutput, ImpactProjection,
    RecType, RecGroup, RiskLevel,
    CampaignData, KeywordData, SearchTermData, AdData, AdGroupData,
)

logger = structlog.get_logger()

# ── Thresholds (configurable per account/industry later) ─────────────────────
MIN_CLICKS_FOR_KEYWORD_PAUSE = 20
MIN_SPEND_FOR_SEARCH_TERM_NEGATIVE = 10.0
MIN_CLICKS_FOR_DEVICE_ANALYSIS = 50
BUDGET_LIMITED_THRESHOLD = 0.15  # 15% lost IS budget = budget limited
HIGH_CPA_MULTIPLIER = 2.0  # 2x account avg CPA = high CPA
LOW_CTR_THRESHOLD = 0.02  # below 2% CTR = low
ZERO_CONV_SPEND_THRESHOLD = 25.0  # spent $25+ with 0 conversions


async def generate_recommendations(
    snapshot: AccountSnapshot,
    scan_goal: str = "full_review",
) -> List[RecommendationOutput]:
    """
    Run all analysis passes and return merged, deduplicated recommendations.
    """
    recommendations: List[RecommendationOutput] = []

    # Pass 1: Deterministic rules
    recommendations.extend(_rule_waste_keywords(snapshot))
    recommendations.extend(_rule_negative_candidates(snapshot))
    recommendations.extend(_rule_budget_limited_campaigns(snapshot))
    recommendations.extend(_rule_zero_conversion_keywords(snapshot))

    # Pass 2: Heuristics
    recommendations.extend(_heuristic_device_optimization(snapshot))
    recommendations.extend(_heuristic_daypart_optimization(snapshot))
    recommendations.extend(_heuristic_ad_strength_audit(snapshot))
    recommendations.extend(_heuristic_ad_group_theme_split(snapshot))
    recommendations.extend(_heuristic_missing_exact_match(snapshot))
    recommendations.extend(_heuristic_ad_fatigue_detection(snapshot))
    recommendations.extend(_heuristic_budget_reallocation(snapshot))
    recommendations.extend(_heuristic_geo_bid_modifier(snapshot))
    recommendations.extend(_heuristic_roas_bidding_strategy(snapshot))

    # Pass 3: Strategic (new campaign opportunities)
    recommendations.extend(_strategic_missing_campaigns(snapshot))

    # Filter by scan goal
    if scan_goal != "full_review":
        recommendations = _filter_by_goal(recommendations, scan_goal)

    # Deduplicate and prioritize
    recommendations = _deduplicate(recommendations)
    recommendations = _assign_priorities(recommendations)

    logger.info(
        "Recommendations generated",
        total=len(recommendations),
        by_risk={rl.value: sum(1 for r in recommendations if r.risk_level == rl) for rl in RiskLevel},
    )

    return recommendations


# ═══════════════════════════════════════════════════════════════════════════════
# PASS 1: DETERMINISTIC RULES
# ═══════════════════════════════════════════════════════════════════════════════

def _rule_waste_keywords(snapshot: AccountSnapshot) -> List[RecommendationOutput]:
    """Keywords with significant spend and zero conversions."""
    recs = []
    account_avg_cpa = snapshot.avg_cpa

    for kw in snapshot.keywords:
        if kw.clicks >= MIN_CLICKS_FOR_KEYWORD_PAUSE and kw.conversions == 0 and kw.cost >= ZERO_CONV_SPEND_THRESHOLD:
            recs.append(RecommendationOutput(
                recommendation_type=RecType.PAUSE_KEYWORD,
                group_name=RecGroup.KEYWORDS_SEARCH_TERMS,
                entity_type="keyword",
                entity_id=kw.keyword_id,
                entity_name=f'"{kw.text}" [{kw.match_type}]',
                parent_entity_id=kw.ad_group_id,
                title=f'Pause "{kw.text}" — ${kw.cost:.0f} spent, 0 conversions',
                rationale=f'This keyword has received {kw.clicks} clicks and spent ${kw.cost:.2f} over the analysis period with zero conversions. '
                          f'At this volume, it is statistically unlikely to convert profitably.',
                evidence={"clicks": kw.clicks, "cost": kw.cost, "conversions": 0, "ctr": kw.ctr},
                current_state={"status": kw.status, "cost": kw.cost, "clicks": kw.clicks},
                proposed_state={"status": "PAUSED"},
                impact=ImpactProjection(
                    spend_delta=-kw.cost,
                    assumptions=["Spend from this keyword is fully wasted", "No conversion lag expected"],
                    confidence=0.85,
                ),
                confidence_score=0.85,
                risk_level=RiskLevel.LOW,
                generated_by="rule",
            ))

        # High CPA keywords (spending but CPA > 2x account average)
        elif kw.conversions > 0 and account_avg_cpa > 0 and kw.cost_per_conversion > account_avg_cpa * HIGH_CPA_MULTIPLIER:
            recs.append(RecommendationOutput(
                recommendation_type=RecType.LOWER_KEYWORD_BID,
                group_name=RecGroup.KEYWORDS_SEARCH_TERMS,
                entity_type="keyword",
                entity_id=kw.keyword_id,
                entity_name=f'"{kw.text}" [{kw.match_type}]',
                parent_entity_id=kw.ad_group_id,
                title=f'Lower bid on "{kw.text}" — CPA ${kw.cost_per_conversion:.0f} vs acct avg ${account_avg_cpa:.0f}',
                rationale=f'This keyword converts at ${kw.cost_per_conversion:.2f} per conversion, which is '
                          f'{kw.cost_per_conversion/account_avg_cpa:.1f}x the account average. '
                          f'Reducing bid may improve blended CPA.',
                evidence={"cpa": kw.cost_per_conversion, "account_avg_cpa": account_avg_cpa, "conversions": kw.conversions},
                current_state={"cost_per_conversion": kw.cost_per_conversion},
                proposed_state={"action": "reduce_bid_20pct"},
                impact=ImpactProjection(
                    cpa_delta=-(kw.cost_per_conversion - account_avg_cpa) * 0.3,
                    assumptions=["20% bid reduction yields ~30% CPA improvement based on typical elasticity"],
                    confidence=0.55,
                ),
                confidence_score=0.55,
                risk_level=RiskLevel.MEDIUM,
                generated_by="rule",
            ))

    return recs


def _rule_negative_candidates(snapshot: AccountSnapshot) -> List[RecommendationOutput]:
    """Search terms with spend and no conversions that should be negated."""
    recs = []
    existing_negatives = {n.keyword_text.lower() for n in snapshot.negatives}

    for st in snapshot.search_terms:
        if (st.cost >= MIN_SPEND_FOR_SEARCH_TERM_NEGATIVE
                and st.conversions == 0
                and st.search_term.lower() not in existing_negatives):
            recs.append(RecommendationOutput(
                recommendation_type=RecType.ADD_NEGATIVE_KEYWORD,
                group_name=RecGroup.NEGATIVE_KEYWORDS,
                entity_type="search_term",
                entity_name=f'"{st.search_term}"',
                parent_entity_id=st.campaign_id,
                title=f'Add negative: "{st.search_term}" — ${st.cost:.0f} wasted',
                rationale=f'This search term triggered ads and spent ${st.cost:.2f} with {st.clicks} clicks '
                          f'but produced zero conversions. Adding it as a negative will prevent future waste.',
                evidence={"search_term": st.search_term, "cost": st.cost, "clicks": st.clicks, "conversions": 0},
                current_state={"negative_exists": False},
                proposed_state={"keyword_text": st.search_term, "match_type": "EXACT", "level": "campaign"},
                impact=ImpactProjection(
                    spend_delta=-st.cost,
                    assumptions=["Search term will recur at similar volume", "No conversion lag"],
                    confidence=0.80,
                ),
                confidence_score=0.80,
                risk_level=RiskLevel.LOW,
                generated_by="rule",
            ))

    return recs


def _rule_budget_limited_campaigns(snapshot: AccountSnapshot) -> List[RecommendationOutput]:
    """Campaigns losing impression share due to budget with healthy CPA."""
    recs = []
    account_avg_cpa = snapshot.avg_cpa

    for c in snapshot.campaigns:
        if (c.search_lost_is_budget and c.search_lost_is_budget > BUDGET_LIMITED_THRESHOLD
                and c.conversions > 0
                and (account_avg_cpa == 0 or c.cost_per_conversion <= account_avg_cpa * 1.2)):
            lost_pct = c.search_lost_is_budget
            potential_extra_clicks = int(c.clicks * (lost_pct / (1 - lost_pct))) if lost_pct < 1 else c.clicks
            potential_extra_conv = round(potential_extra_clicks * c.conv_rate, 1)
            suggested_increase = round(c.budget_daily * (1 + lost_pct), 2)

            recs.append(RecommendationOutput(
                recommendation_type=RecType.INCREASE_BUDGET,
                group_name=RecGroup.BUDGET_BIDDING,
                entity_type="campaign",
                entity_id=c.campaign_id,
                entity_name=c.name,
                title=f'Increase budget on "{c.name}" — losing {lost_pct:.0%} IS to budget',
                rationale=f'This campaign has a healthy CPA of ${c.cost_per_conversion:.2f} but is losing '
                          f'{lost_pct:.0%} of impression share due to budget constraints. '
                          f'Increasing the daily budget could capture an estimated {potential_extra_conv:.0f} '
                          f'additional conversions per period.',
                evidence={
                    "current_budget": c.budget_daily, "cpa": c.cost_per_conversion,
                    "lost_is_budget": lost_pct, "conv_rate": c.conv_rate,
                },
                current_state={"budget_daily": c.budget_daily},
                proposed_state={"budget_daily": suggested_increase},
                impact=ImpactProjection(
                    spend_delta=round((suggested_increase - c.budget_daily) * 30, 2),
                    conversion_delta=potential_extra_conv,
                    assumptions=[
                        f"CVR of {c.conv_rate:.2%} holds at increased volume",
                        "Incremental traffic quality similar to existing",
                    ],
                    confidence=0.65,
                ),
                confidence_score=0.65,
                risk_level=RiskLevel.MEDIUM,
                generated_by="rule",
            ))

    return recs


def _rule_zero_conversion_keywords(snapshot: AccountSnapshot) -> List[RecommendationOutput]:
    """Additional pass: keywords with moderate spend heading toward waste."""
    recs = []
    # Already covered in _rule_waste_keywords for high-spend.
    # This pass catches medium-spend keywords approaching the threshold.
    for kw in snapshot.keywords:
        if (kw.clicks >= 10 and kw.clicks < MIN_CLICKS_FOR_KEYWORD_PAUSE
                and kw.conversions == 0 and kw.cost >= 15.0):
            recs.append(RecommendationOutput(
                recommendation_type=RecType.PAUSE_KEYWORD,
                group_name=RecGroup.KEYWORDS_SEARCH_TERMS,
                entity_type="keyword",
                entity_id=kw.keyword_id,
                entity_name=f'"{kw.text}" [{kw.match_type}]',
                parent_entity_id=kw.ad_group_id,
                title=f'Watch / pause "{kw.text}" — ${kw.cost:.0f} spent, 0 conversions, approaching waste',
                rationale=f'This keyword has {kw.clicks} clicks and ${kw.cost:.2f} spent with no conversions. '
                          f'While the sample is moderate, the trend suggests poor performance.',
                evidence={"clicks": kw.clicks, "cost": kw.cost},
                current_state={"status": kw.status},
                proposed_state={"status": "PAUSED"},
                impact=ImpactProjection(
                    spend_delta=-kw.cost * 0.8,
                    assumptions=["Trend continues without conversion"],
                    confidence=0.60,
                ),
                confidence_score=0.60,
                risk_level=RiskLevel.LOW,
                generated_by="rule",
            ))
    return recs


# ═══════════════════════════════════════════════════════════════════════════════
# PASS 2: HEURISTICS
# ═══════════════════════════════════════════════════════════════════════════════

def _heuristic_device_optimization(snapshot: AccountSnapshot) -> List[RecommendationOutput]:
    """Detect device performance gaps and recommend bid adjustments."""
    recs = []
    # Aggregate device data per campaign
    camp_devices: Dict[str, Dict[str, Any]] = {}
    for seg in snapshot.device_segments:
        if seg.campaign_id not in camp_devices:
            camp_devices[seg.campaign_id] = {}
        camp_devices[seg.campaign_id][seg.device] = seg

    camp_names = {c.campaign_id: c.name for c in snapshot.campaigns}

    for cid, devices in camp_devices.items():
        total_clicks = sum(d.clicks for d in devices.values())
        if total_clicks < MIN_CLICKS_FOR_DEVICE_ANALYSIS:
            continue

        for device_name, seg in devices.items():
            if seg.clicks < 10:
                continue
            # Compare device CPA to campaign average
            camp = next((c for c in snapshot.campaigns if c.campaign_id == cid), None)
            if not camp or camp.conversions == 0:
                continue

            camp_cpa = camp.cost_per_conversion
            if seg.conversions > 0 and seg.cost_per_conversion > camp_cpa * 1.8:
                recs.append(RecommendationOutput(
                    recommendation_type=RecType.ADJUST_DEVICE_MODIFIER,
                    group_name=RecGroup.DEVICE_MODIFIERS,
                    entity_type="campaign",
                    entity_id=cid,
                    entity_name=camp_names.get(cid, cid),
                    title=f'Reduce {device_name} bid on "{camp_names.get(cid, "")}" — CPA ${seg.cost_per_conversion:.0f} vs ${camp_cpa:.0f} avg',
                    rationale=f'{device_name} traffic converts at ${seg.cost_per_conversion:.2f} per conversion, '
                              f'which is {seg.cost_per_conversion/camp_cpa:.1f}x the campaign average. '
                              f'A negative bid modifier may improve blended CPA.',
                    evidence={"device": device_name, "device_cpa": seg.cost_per_conversion, "campaign_cpa": camp_cpa},
                    current_state={"device_bid_modifier": 0},
                    proposed_state={"device_bid_modifier": -30},
                    impact=ImpactProjection(
                        cpa_delta=-round((seg.cost_per_conversion - camp_cpa) * 0.25, 2),
                        confidence=0.50,
                    ),
                    confidence_score=0.50,
                    risk_level=RiskLevel.MEDIUM,
                    generated_by="heuristic",
                ))
            elif seg.conversions == 0 and seg.cost > ZERO_CONV_SPEND_THRESHOLD:
                recs.append(RecommendationOutput(
                    recommendation_type=RecType.ADJUST_DEVICE_MODIFIER,
                    group_name=RecGroup.DEVICE_MODIFIERS,
                    entity_type="campaign",
                    entity_id=cid,
                    entity_name=camp_names.get(cid, cid),
                    title=f'Reduce {device_name} bid on "{camp_names.get(cid, "")}" — ${seg.cost:.0f} spent, 0 conversions',
                    rationale=f'{device_name} has spent ${seg.cost:.2f} with zero conversions on this campaign.',
                    evidence={"device": device_name, "cost": seg.cost, "conversions": 0},
                    current_state={"device_bid_modifier": 0},
                    proposed_state={"device_bid_modifier": -50},
                    impact=ImpactProjection(
                        spend_delta=-seg.cost * 0.5,
                        confidence=0.60,
                    ),
                    confidence_score=0.60,
                    risk_level=RiskLevel.LOW,
                    generated_by="heuristic",
                ))

    return recs


def _heuristic_daypart_optimization(snapshot: AccountSnapshot) -> List[RecommendationOutput]:
    """Detect time-of-day performance patterns."""
    recs = []
    # Aggregate by hour across all campaigns
    hour_data: Dict[int, Dict[str, float]] = {}
    for seg in snapshot.hour_of_day_segments:
        if seg.hour not in hour_data:
            hour_data[seg.hour] = {"cost": 0, "conversions": 0, "clicks": 0}
        hour_data[seg.hour]["cost"] += seg.cost
        hour_data[seg.hour]["conversions"] += seg.conversions
        hour_data[seg.hour]["clicks"] += seg.clicks

    total_cost = sum(h["cost"] for h in hour_data.values())
    total_conv = sum(h["conversions"] for h in hour_data.values())
    if total_cost < 100 or total_conv < 5:
        return recs

    avg_cpa = total_cost / total_conv if total_conv > 0 else 0

    # Find expensive zero-conversion hour blocks
    waste_hours = []
    for hour, data in sorted(hour_data.items()):
        if data["cost"] > 5 and data["conversions"] == 0 and data["clicks"] >= 3:
            waste_hours.append(hour)

    if waste_hours and len(waste_hours) >= 2:
        waste_spend = sum(hour_data[h]["cost"] for h in waste_hours)
        hours_str = ", ".join(f"{h}:00" for h in sorted(waste_hours))
        recs.append(RecommendationOutput(
            recommendation_type=RecType.ADD_AD_SCHEDULE_RULE,
            group_name=RecGroup.AD_SCHEDULE,
            entity_type="account",
            title=f'Reduce bids during low-converting hours — ${waste_spend:.0f} wasted',
            rationale=f'Hours {hours_str} collectively spent ${waste_spend:.2f} with zero conversions. '
                      f'Adding ad schedule bid reductions for these hours may recover wasted spend.',
            evidence={"waste_hours": waste_hours, "waste_spend": waste_spend},
            current_state={"schedule_rules": "none"},
            proposed_state={"reduce_bid_hours": waste_hours, "modifier": -50},
            impact=ImpactProjection(
                spend_delta=-waste_spend * 0.5,
                assumptions=["50% bid reduction applied to identified hours"],
                confidence=0.50,
            ),
            confidence_score=0.50,
            risk_level=RiskLevel.MEDIUM,
            generated_by="heuristic",
        ))

    return recs


def _heuristic_ad_strength_audit(snapshot: AccountSnapshot) -> List[RecommendationOutput]:
    """Flag ads with weak ad strength for rewrite."""
    recs = []
    weak_strengths = {"POOR", "AVERAGE", "UNSPECIFIED"}
    camp_names = {c.campaign_id: c.name for c in snapshot.campaigns}

    for ad in snapshot.ads:
        if ad.ad_strength and ad.ad_strength in weak_strengths and ad.impressions > 100:
            recs.append(RecommendationOutput(
                recommendation_type=RecType.REWRITE_RSA,
                group_name=RecGroup.AD_COPY,
                entity_type="ad",
                entity_id=ad.ad_id,
                entity_name=f"Ad in {camp_names.get(ad.campaign_id, ad.campaign_id)}",
                parent_entity_id=ad.ad_group_id,
                title=f'Rewrite RSA — ad strength "{ad.ad_strength}" in campaign "{camp_names.get(ad.campaign_id, "")}"',
                rationale=f'This ad has "{ad.ad_strength}" ad strength with {ad.impressions} impressions. '
                          f'Improving headline diversity, unique descriptions, and keyword relevance '
                          f'can boost CTR and Quality Score.',
                evidence={"ad_strength": ad.ad_strength, "headlines": ad.headlines[:3], "ctr": ad.ctr},
                current_state={"headlines": ad.headlines, "descriptions": ad.descriptions, "ad_strength": ad.ad_strength},
                proposed_state={"action": "rewrite_rsa", "target_strength": "GOOD_OR_EXCELLENT"},
                impact=ImpactProjection(
                    click_delta=round(ad.clicks * 0.15, 0),
                    assumptions=["15% CTR improvement from stronger ad copy based on industry benchmarks"],
                    confidence=0.45,
                ),
                confidence_score=0.45,
                risk_level=RiskLevel.LOW,
                generated_by="heuristic",
            ))

    return recs


def _heuristic_ad_group_theme_split(snapshot: AccountSnapshot) -> List[RecommendationOutput]:
    """Detect ad groups with mixed keyword themes that should be split."""
    recs = []
    # Group keywords by ad group
    ag_keywords: Dict[str, List[KeywordData]] = {}
    for kw in snapshot.keywords:
        if kw.ad_group_id not in ag_keywords:
            ag_keywords[kw.ad_group_id] = []
        ag_keywords[kw.ad_group_id].append(kw)

    ag_names = {ag.ad_group_id: ag.name for ag in snapshot.ad_groups}
    camp_names = {c.campaign_id: c.name for c in snapshot.campaigns}

    for ag_id, keywords in ag_keywords.items():
        if len(keywords) < 5:
            continue
        # Simple heuristic: check if keyword texts share a common root
        words = set()
        for kw in keywords:
            words.update(kw.text.lower().split())
        # If keywords span many unrelated terms (high unique-word ratio)
        unique_ratio = len(words) / len(keywords)
        if unique_ratio > 3.0 and len(keywords) >= 8:
            ag_name = ag_names.get(ag_id, ag_id)
            camp_id = keywords[0].campaign_id
            total_cost = sum(kw.cost for kw in keywords)
            recs.append(RecommendationOutput(
                recommendation_type=RecType.SPLIT_AD_GROUP,
                group_name=RecGroup.AD_GROUPS,
                entity_type="ad_group",
                entity_id=ag_id,
                entity_name=ag_name,
                parent_entity_id=camp_id,
                title=f'Split ad group "{ag_name}" — {len(keywords)} keywords, high theme diversity',
                rationale=f'This ad group contains {len(keywords)} keywords with high thematic diversity '
                          f'(~{len(words)} unique terms). Splitting into tighter themed ad groups '
                          f'will improve ad relevance and Quality Score.',
                evidence={"keyword_count": len(keywords), "unique_words": len(words), "total_cost": total_cost},
                current_state={"keyword_count": len(keywords)},
                proposed_state={"action": "split_into_themed_groups"},
                impact=ImpactProjection(
                    cpa_delta=-round(total_cost * 0.05, 2) if total_cost > 0 else 0,
                    assumptions=["Better ad relevance improves QS by ~1 point", "QS improvement reduces CPC ~5-10%"],
                    confidence=0.40,
                ),
                confidence_score=0.40,
                risk_level=RiskLevel.MEDIUM,
                generated_by="heuristic",
            ))

    return recs


def _heuristic_missing_exact_match(snapshot: AccountSnapshot) -> List[RecommendationOutput]:
    """Find high-converting search terms not covered by exact match keywords."""
    recs = []
    existing_exact = {kw.text.lower() for kw in snapshot.keywords if kw.match_type == "EXACT"}

    for st in snapshot.search_terms:
        if (st.conversions >= 2
                and st.search_term.lower() not in existing_exact
                and st.cost_per_conversion > 0):
            recs.append(RecommendationOutput(
                recommendation_type=RecType.RAISE_KEYWORD_BID,
                group_name=RecGroup.KEYWORDS_SEARCH_TERMS,
                entity_type="search_term",
                entity_name=f'"{st.search_term}"',
                parent_entity_id=st.ad_group_id,
                title=f'Add exact match: "{st.search_term}" — {st.conversions:.0f} conversions at ${st.cost_per_conversion:.0f}',
                rationale=f'This search term has driven {st.conversions:.0f} conversions at ${st.cost_per_conversion:.2f} CPA '
                          f'but is not covered by an exact match keyword. Adding it ensures consistent coverage '
                          f'and may improve Quality Score.',
                evidence={"search_term": st.search_term, "conversions": st.conversions, "cpa": st.cost_per_conversion},
                current_state={"exact_match_exists": False},
                proposed_state={"keyword_text": st.search_term, "match_type": "EXACT"},
                impact=ImpactProjection(
                    conversion_delta=round(st.conversions * 0.1, 1),
                    assumptions=["Exact match improves QS and coverage consistency"],
                    confidence=0.60,
                ),
                confidence_score=0.60,
                risk_level=RiskLevel.LOW,
                generated_by="heuristic",
            ))

    return recs


def _heuristic_ad_fatigue_detection(snapshot: AccountSnapshot) -> List[RecommendationOutput]:
    """
    Detect ad fatigue — ads with high impressions but declining CTR.
    Signs: CTR well below account average despite significant spend,
    or ads running as sole ad in an ad group with below-average CTR.
    """
    recs = []
    camp_names = {c.campaign_id: c.name for c in snapshot.campaigns}

    # Calculate account average CTR
    total_clicks = sum(a.clicks for a in snapshot.ads if a.impressions > 0)
    total_impr = sum(a.impressions for a in snapshot.ads if a.impressions > 0)
    account_avg_ctr = total_clicks / total_impr if total_impr > 0 else 0

    if account_avg_ctr <= 0:
        return recs

    # Group ads by ad group to detect single-ad groups
    ad_groups: Dict[str, list] = {}
    for ad in snapshot.ads:
        if ad.ad_group_id not in ad_groups:
            ad_groups[ad.ad_group_id] = []
        ad_groups[ad.ad_group_id].append(ad)

    for ad in snapshot.ads:
        if ad.impressions < 500 or ad.clicks < 5:
            continue

        # Ad fatigue indicator: CTR < 50% of account average with significant impressions
        if ad.ctr < account_avg_ctr * 0.5 and ad.impressions >= 1000:
            # Check if it's the only ad in its ad group (no rotation possible)
            sibling_count = len(ad_groups.get(ad.ad_group_id, []))
            severity = "high" if sibling_count <= 1 else "medium"

            recs.append(RecommendationOutput(
                recommendation_type=RecType.PAUSE_AD if sibling_count > 1 else RecType.CREATE_AD_VARIANTS,
                group_name=RecGroup.AD_COPY,
                entity_type="ad",
                entity_id=ad.ad_id,
                entity_name=f"Ad in {camp_names.get(ad.campaign_id, ad.campaign_id)}",
                parent_entity_id=ad.ad_group_id,
                title=(
                    f'Ad fatigue detected — CTR {ad.ctr:.2%} vs account avg {account_avg_ctr:.2%}'
                    if sibling_count > 1 else
                    f'Single ad in ad group with low CTR ({ad.ctr:.2%}) — create variants'
                ),
                rationale=(
                    f'This ad has {ad.impressions:,} impressions but a CTR of {ad.ctr:.2%}, '
                    f'which is {((account_avg_ctr - ad.ctr) / account_avg_ctr * 100):.0f}% below '
                    f'the account average of {account_avg_ctr:.2%}. '
                    + (f'It is the only ad in its ad group — creating new variants will '
                       f'enable A/B testing and ad rotation.' if sibling_count <= 1 else
                       f'Pausing this ad will shift impressions to better-performing variants.')
                ),
                evidence={
                    "ad_ctr": round(ad.ctr, 4),
                    "account_avg_ctr": round(account_avg_ctr, 4),
                    "impressions": ad.impressions,
                    "clicks": ad.clicks,
                    "cost": ad.cost,
                    "sibling_ads": sibling_count,
                    "headlines": ad.headlines[:3],
                },
                current_state={
                    "ctr": ad.ctr,
                    "impressions": ad.impressions,
                    "ad_strength": ad.ad_strength,
                },
                proposed_state={
                    "action": "pause_ad" if sibling_count > 1 else "create_ad_variants",
                    "target_ctr": round(account_avg_ctr, 4),
                },
                impact=ImpactProjection(
                    click_delta=round(ad.impressions * (account_avg_ctr - ad.ctr) * 0.5, 0),
                    assumptions=[
                        "Shifting impressions to better ads increases CTR toward account average",
                        "50% of potential CTR gap recovery assumed",
                    ],
                    confidence=0.50 if sibling_count > 1 else 0.40,
                ),
                confidence_score=0.50 if sibling_count > 1 else 0.40,
                risk_level=RiskLevel.LOW if sibling_count > 1 else RiskLevel.MEDIUM,
                generated_by="heuristic",
            ))

    return recs


# ═══════════════════════════════════════════════════════════════════════════════
# PASS 3: STRATEGIC — NEW CAMPAIGN OPPORTUNITIES
# ═══════════════════════════════════════════════════════════════════════════════

def _strategic_missing_campaigns(snapshot: AccountSnapshot) -> List[RecommendationOutput]:
    """
    Identify missing campaign types based on account structure and local service patterns.
    Locksmith / local service first-class patterns.
    """
    recs = []
    campaign_names_lower = [c.name.lower() for c in snapshot.campaigns]
    all_keywords_lower = [kw.text.lower() for kw in snapshot.keywords]
    all_search_terms_lower = [st.search_term.lower() for st in snapshot.search_terms]

    # Check for brand/model-specific campaigns
    brand_indicators = ["bmw", "mercedes", "audi", "lexus", "tesla", "honda", "toyota", "ford", "chevy"]
    brand_terms_found = set()
    for st in all_search_terms_lower:
        for brand in brand_indicators:
            if brand in st:
                brand_terms_found.add(brand)

    for brand in brand_terms_found:
        has_brand_campaign = any(brand in cn for cn in campaign_names_lower)
        if not has_brand_campaign:
            brand_spend = sum(
                st.cost for st in snapshot.search_terms
                if brand in st.search_term.lower()
            )
            brand_conv = sum(
                st.conversions for st in snapshot.search_terms
                if brand in st.search_term.lower()
            )
            if brand_spend >= 10:
                recs.append(RecommendationOutput(
                    recommendation_type=RecType.ADD_BRAND_SPECIFIC_CAMPAIGN,
                    group_name=RecGroup.NEW_CAMPAIGNS,
                    entity_type="campaign",
                    entity_name=f"{brand.title()} Campaign",
                    title=f'Create {brand.title()}-specific campaign — ${brand_spend:.0f} existing demand',
                    rationale=f'Search terms containing "{brand}" drove ${brand_spend:.2f} in spend '
                              f'and {brand_conv:.0f} conversions, but there is no dedicated campaign. '
                              f'A brand-specific campaign enables tailored ad copy, landing pages, and bidding.',
                    evidence={"brand": brand, "spend": brand_spend, "conversions": brand_conv},
                    current_state={"dedicated_campaign": False},
                    proposed_state={"action": "create_brand_campaign", "brand": brand},
                    impact=ImpactProjection(
                        conversion_delta=round(brand_conv * 0.2, 1) if brand_conv > 0 else 1.0,
                        assumptions=["Dedicated campaign improves relevance and CTR ~20%"],
                        confidence=0.45,
                    ),
                    confidence_score=0.45,
                    risk_level=RiskLevel.MEDIUM,
                    generated_by="heuristic",
                ))

    # Check for emergency vs scheduled service split
    has_emergency = any("emergency" in cn or "lockout" in cn or "24/7" in cn for cn in campaign_names_lower)
    emergency_demand = sum(
        st.cost for st in snapshot.search_terms
        if any(term in st.search_term.lower() for term in ["emergency", "lockout", "locked out", "urgent", "24 hour", "24/7"])
    )
    if not has_emergency and emergency_demand >= 20:
        recs.append(RecommendationOutput(
            recommendation_type=RecType.ADD_HIGH_INTENT_CAMPAIGN,
            group_name=RecGroup.NEW_CAMPAIGNS,
            entity_type="campaign",
            entity_name="Emergency / Lockout Campaign",
            title=f'Create Emergency/Lockout campaign — ${emergency_demand:.0f} existing demand',
            rationale=f'Emergency and lockout search terms show ${emergency_demand:.2f} in spend '
                      f'but are not separated into a dedicated campaign. '
                      f'Emergency callers have highest intent and conversion rates — dedicated messaging converts better.',
            evidence={"emergency_spend": emergency_demand},
            current_state={"dedicated_campaign": False},
            proposed_state={"action": "create_emergency_campaign"},
            impact=ImpactProjection(
                conversion_delta=round(emergency_demand * 0.1 / max(snapshot.avg_cpa, 1), 1),
                assumptions=["Emergency intent converts at 2x+ normal rate"],
                confidence=0.50,
            ),
            confidence_score=0.50,
            risk_level=RiskLevel.MEDIUM,
            generated_by="heuristic",
        ))

    # Check for "near me" exact match cluster
    near_me_terms = [st for st in snapshot.search_terms if "near me" in st.search_term.lower()]
    has_near_me_exact = any("near me" in kw.text.lower() and kw.match_type == "EXACT" for kw in snapshot.keywords)
    near_me_spend = sum(st.cost for st in near_me_terms)
    near_me_conv = sum(st.conversions for st in near_me_terms)
    if not has_near_me_exact and near_me_spend >= 15:
        recs.append(RecommendationOutput(
            recommendation_type=RecType.ADD_HIGH_INTENT_CAMPAIGN,
            group_name=RecGroup.NEW_CAMPAIGNS,
            entity_type="campaign",
            entity_name="Near Me High-Intent Campaign",
            title=f'Create "near me" exact-match campaign — ${near_me_spend:.0f} demand, {near_me_conv:.0f} conversions',
            rationale=f'"Near me" queries represent high local intent. Currently generating '
                      f'${near_me_spend:.2f} in spend. A dedicated exact-match campaign with '
                      f'location-focused ad copy can significantly improve conversion rate.',
            evidence={"near_me_spend": near_me_spend, "near_me_conversions": near_me_conv},
            current_state={"near_me_exact": False},
            proposed_state={"action": "create_near_me_campaign"},
            impact=ImpactProjection(
                conversion_delta=round(near_me_conv * 0.15, 1) if near_me_conv > 0 else 1.0,
                confidence=0.50,
            ),
            confidence_score=0.50,
            risk_level=RiskLevel.LOW,
            generated_by="heuristic",
        ))

    return recs


# ═══════════════════════════════════════════════════════════════════════════════
# PASS 2b: ENHANCED AUTOPILOT RULES
# ═══════════════════════════════════════════════════════════════════════════════

def _heuristic_budget_reallocation(snapshot: AccountSnapshot) -> List[RecommendationOutput]:
    """
    Reallocate budget from high-CPA / low-ROAS campaigns to efficient ones.
    Identifies donor (wasteful) and receiver (budget-limited + efficient) campaigns.
    """
    recs = []
    if len(snapshot.campaigns) < 2:
        return recs

    active = [c for c in snapshot.campaigns if c.status == "ENABLED" and c.cost > 0]
    if len(active) < 2:
        return recs

    account_avg_cpa = snapshot.avg_cpa
    if account_avg_cpa <= 0:
        return recs

    # Identify donors: campaigns with CPA > 2x average and meaningful spend
    donors = [c for c in active if c.conversions > 0 and c.cost_per_conversion > account_avg_cpa * 2.0 and c.cost > 50]
    # Identify receivers: budget-limited campaigns with good CPA
    receivers = [
        c for c in active
        if c.search_lost_is_budget and c.search_lost_is_budget > 0.10
        and c.conversions > 0
        and c.cost_per_conversion <= account_avg_cpa * 1.1
    ]

    for donor in donors:
        for receiver in receivers:
            if donor.campaign_id == receiver.campaign_id:
                continue
            # Suggest moving 20% of donor budget to receiver
            realloc_amount = round(donor.budget_daily * 0.20, 2)
            potential_extra_conv = round(realloc_amount / receiver.cost_per_conversion, 1) if receiver.cost_per_conversion > 0 else 0

            recs.append(RecommendationOutput(
                recommendation_type=RecType.DECREASE_BUDGET,
                group_name=RecGroup.BUDGET_BIDDING,
                entity_type="campaign",
                entity_id=donor.campaign_id,
                entity_name=donor.name,
                title=f'Reallocate ${realloc_amount:.0f}/day from "{donor.name}" → "{receiver.name}"',
                rationale=(
                    f'"{donor.name}" has a CPA of ${donor.cost_per_conversion:.2f} '
                    f'({donor.cost_per_conversion/account_avg_cpa:.1f}x account avg), while '
                    f'"{receiver.name}" converts at ${receiver.cost_per_conversion:.2f} but is '
                    f'losing {receiver.search_lost_is_budget:.0%} impression share to budget. '
                    f'Shifting ${realloc_amount:.2f}/day could yield ~{potential_extra_conv:.0f} extra conversions.'
                ),
                evidence={
                    "donor_cpa": donor.cost_per_conversion,
                    "receiver_cpa": receiver.cost_per_conversion,
                    "donor_budget": donor.budget_daily,
                    "receiver_lost_is_budget": receiver.search_lost_is_budget,
                    "realloc_amount": realloc_amount,
                },
                current_state={"donor_budget": donor.budget_daily, "receiver_budget": receiver.budget_daily},
                proposed_state={
                    "donor_new_budget": round(donor.budget_daily - realloc_amount, 2),
                    "receiver_new_budget": round(receiver.budget_daily + realloc_amount, 2),
                },
                impact=ImpactProjection(
                    spend_delta=0,  # net-zero spend change
                    conversion_delta=potential_extra_conv,
                    cpa_delta=-round((donor.cost_per_conversion - account_avg_cpa) * 0.15, 2),
                    assumptions=[
                        "Receiver campaign CVR holds at increased volume",
                        "Donor campaign loses proportional conversions at its higher CPA",
                        "Net effect is improved blended CPA",
                    ],
                    confidence=0.55,
                ),
                confidence_score=0.55,
                risk_level=RiskLevel.MEDIUM,
                generated_by="heuristic",
            ))
            break  # one reallocation per donor

    return recs


def _heuristic_geo_bid_modifier(snapshot: AccountSnapshot) -> List[RecommendationOutput]:
    """
    Detect geographic performance gaps and recommend bid adjustments.
    Identifies geos with high spend + zero conversions or very high CPA.
    """
    recs = []
    if not snapshot.geo_segments:
        return recs

    # Aggregate geo data per campaign
    camp_geos: Dict[str, Dict[str, Any]] = {}
    for seg in snapshot.geo_segments:
        key = (seg.campaign_id, seg.location_name)
        if key not in camp_geos:
            camp_geos[key] = {"cost": 0, "conversions": 0, "clicks": 0, "impressions": 0}
        camp_geos[key]["cost"] += seg.cost
        camp_geos[key]["conversions"] += seg.conversions
        camp_geos[key]["clicks"] += seg.clicks
        camp_geos[key]["impressions"] += seg.impressions

    camp_names = {c.campaign_id: c.name for c in snapshot.campaigns}
    account_avg_cpa = snapshot.avg_cpa

    for (cid, loc), data in camp_geos.items():
        if data["clicks"] < 10:
            continue
        camp = next((c for c in snapshot.campaigns if c.campaign_id == cid), None)
        if not camp or camp.conversions == 0:
            continue

        geo_cpa = data["cost"] / data["conversions"] if data["conversions"] > 0 else float("inf")

        # Zero-conversion geo with significant spend
        if data["conversions"] == 0 and data["cost"] > ZERO_CONV_SPEND_THRESHOLD:
            recs.append(RecommendationOutput(
                recommendation_type=RecType.EXCLUDE_LOCATION,
                group_name=RecGroup.GEO_TARGETING,
                entity_type="campaign",
                entity_id=cid,
                entity_name=camp_names.get(cid, cid),
                title=f'Reduce bid for location {loc} in "{camp_names.get(cid, "")}" — ${data["cost"]:.0f}, 0 conversions',
                rationale=(
                    f'Location {loc} spent ${data["cost"]:.2f} with {data["clicks"]} clicks '
                    f'but zero conversions. A negative bid modifier or exclusion may reduce waste.'
                ),
                evidence={"location": loc, "cost": data["cost"], "clicks": data["clicks"]},
                current_state={"geo_bid_modifier": 0},
                proposed_state={"geo_bid_modifier": -50},
                impact=ImpactProjection(
                    spend_delta=-data["cost"] * 0.5,
                    confidence=0.55,
                ),
                confidence_score=0.55,
                risk_level=RiskLevel.LOW,
                generated_by="heuristic",
            ))
        # High-CPA geo (> 2.5x account average)
        elif data["conversions"] > 0 and account_avg_cpa > 0 and geo_cpa > account_avg_cpa * 2.5:
            recs.append(RecommendationOutput(
                recommendation_type=RecType.EXCLUDE_LOCATION,
                group_name=RecGroup.GEO_TARGETING,
                entity_type="campaign",
                entity_id=cid,
                entity_name=camp_names.get(cid, cid),
                title=f'Reduce bid for location {loc} — CPA ${geo_cpa:.0f} vs ${account_avg_cpa:.0f} avg',
                rationale=(
                    f'Location {loc} converts at ${geo_cpa:.2f}/conv, which is '
                    f'{geo_cpa/account_avg_cpa:.1f}x the account average. '
                    f'A negative bid modifier can improve blended CPA.'
                ),
                evidence={"location": loc, "geo_cpa": geo_cpa, "account_avg_cpa": account_avg_cpa},
                current_state={"geo_bid_modifier": 0},
                proposed_state={"geo_bid_modifier": -30},
                impact=ImpactProjection(
                    cpa_delta=-round((geo_cpa - account_avg_cpa) * 0.2, 2),
                    confidence=0.45,
                ),
                confidence_score=0.45,
                risk_level=RiskLevel.MEDIUM,
                generated_by="heuristic",
            ))

    return recs


def _heuristic_roas_bidding_strategy(snapshot: AccountSnapshot) -> List[RecommendationOutput]:
    """
    Recommend switching to Target ROAS bidding for campaigns with enough conversion
    data and good ROAS but using suboptimal bidding strategies.
    """
    recs = []
    suboptimal_strategies = {"MANUAL_CPC", "ENHANCED_CPC", "MAXIMIZE_CLICKS", "MANUAL_CPM"}

    for c in snapshot.campaigns:
        if c.status != "ENABLED" or c.conversions < 15:
            continue
        if c.bidding_strategy not in suboptimal_strategies:
            continue
        if c.conversion_value <= 0 or c.cost <= 0:
            continue

        roas = c.conversion_value / c.cost
        if roas < 1.5:
            continue  # not profitable enough to recommend ROAS bidding

        recs.append(RecommendationOutput(
            recommendation_type=RecType.CHANGE_BIDDING_STRATEGY,
            group_name=RecGroup.BUDGET_BIDDING,
            entity_type="campaign",
            entity_id=c.campaign_id,
            entity_name=c.name,
            title=f'Switch "{c.name}" to Target ROAS — current ROAS {roas:.1f}x',
            rationale=(
                f'"{c.name}" has {c.conversions:.0f} conversions with a ROAS of {roas:.1f}x '
                f'using {c.bidding_strategy.replace("_", " ").title()} bidding. '
                f'With sufficient conversion data, switching to Target ROAS allows Google\'s '
                f'algorithm to optimize bids for maximum conversion value.'
            ),
            evidence={
                "current_strategy": c.bidding_strategy,
                "roas": round(roas, 2),
                "conversions": c.conversions,
                "conversion_value": c.conversion_value,
                "cost": c.cost,
            },
            current_state={"bidding_strategy": c.bidding_strategy, "roas": round(roas, 2)},
            proposed_state={
                "bidding_strategy": "TARGET_ROAS",
                "target_roas": round(roas * 0.9, 2),  # 90% of current as starting target
            },
            impact=ImpactProjection(
                conversion_delta=round(c.conversions * 0.10, 1),
                assumptions=[
                    "Target ROAS bidding with sufficient data typically improves ROAS 10-20%",
                    "Conservative target (90% of current) allows algorithm to learn",
                ],
                confidence=0.50,
            ),
            confidence_score=0.50,
            risk_level=RiskLevel.MEDIUM,
            generated_by="heuristic",
        ))

    return recs


# ═══════════════════════════════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════════════════════════════

def _filter_by_goal(recs: List[RecommendationOutput], goal: str) -> List[RecommendationOutput]:
    goal_groups = {
        "reduce_waste": {RecGroup.KEYWORDS_SEARCH_TERMS, RecGroup.NEGATIVE_KEYWORDS, RecGroup.DEVICE_MODIFIERS, RecGroup.AD_SCHEDULE},
        "increase_conversions": {RecGroup.BUDGET_BIDDING, RecGroup.NEW_CAMPAIGNS, RecGroup.AD_COPY, RecGroup.EXTENSIONS_ASSETS},
        "improve_cpa": {RecGroup.KEYWORDS_SEARCH_TERMS, RecGroup.NEGATIVE_KEYWORDS, RecGroup.DEVICE_MODIFIERS, RecGroup.AD_SCHEDULE, RecGroup.BUDGET_BIDDING},
        "scale_winners": {RecGroup.BUDGET_BIDDING, RecGroup.NEW_CAMPAIGNS, RecGroup.KEYWORDS_SEARCH_TERMS},
    }
    allowed = goal_groups.get(goal, set())
    if not allowed:
        return recs
    return [r for r in recs if r.group_name in allowed]


def _deduplicate(recs: List[RecommendationOutput]) -> List[RecommendationOutput]:
    seen = set()
    unique = []
    for r in recs:
        key = (r.recommendation_type, r.entity_id or "", r.entity_name or "")
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def _assign_priorities(recs: List[RecommendationOutput]) -> List[RecommendationOutput]:
    """Assign priority order: high confidence + low risk first."""
    for i, r in enumerate(sorted(recs, key=lambda x: (-x.confidence_score, x.risk_level.value))):
        r.priority_order = i + 1
    return recs
