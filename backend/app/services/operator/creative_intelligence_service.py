"""
Creative Intelligence Service — audits ad copy, assets, and generates
advanced creative replacements and image prompts.
"""
import structlog
import json
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI

from app.core.config import settings
from app.services.operator.schemas import (
    AccountSnapshot, AdData, CampaignData, RecommendationOutput,
    RecType, RecGroup, RiskLevel, ImpactProjection,
)

logger = structlog.get_logger()


async def run_creative_audit(
    snapshot: AccountSnapshot,
    business_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Audit all ads in the account and generate creative recommendations.
    Returns per-campaign creative audit results.
    """
    audits = []
    camp_map = {c.campaign_id: c for c in snapshot.campaigns}

    # Group ads by campaign
    campaign_ads: Dict[str, List[AdData]] = {}
    for ad in snapshot.ads:
        if ad.campaign_id not in campaign_ads:
            campaign_ads[ad.campaign_id] = []
        campaign_ads[ad.campaign_id].append(ad)

    for campaign_id, ads in campaign_ads.items():
        campaign = camp_map.get(campaign_id)
        if not campaign:
            continue

        audit = _audit_campaign_creatives(campaign, ads, snapshot, business_context)
        audits.append(audit)

    return {"campaign_audits": audits}


def _audit_campaign_creatives(
    campaign: CampaignData,
    ads: List[AdData],
    snapshot: AccountSnapshot,
    business_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Audit creatives for a single campaign."""
    all_headlines = []
    all_descriptions = []
    ad_strengths = []

    for ad in ads:
        all_headlines.extend(ad.headlines)
        all_descriptions.extend(ad.descriptions)
        if ad.ad_strength:
            ad_strengths.append(ad.ad_strength)

    # Headline analysis
    headline_issues = []
    if len(all_headlines) < 8:
        headline_issues.append("Too few unique headlines — aim for 12-15")
    unique_headlines = set(h.lower().strip() for h in all_headlines)
    if len(unique_headlines) < len(all_headlines) * 0.7:
        headline_issues.append("High headline duplication — add more variety")

    # Check for missing angles
    missing_angles = _detect_missing_angles(all_headlines, all_descriptions, business_context)

    # Check for weak patterns
    weak_patterns = []
    generic_phrases = ["best", "top", "great", "#1", "quality", "affordable", "professional"]
    for h in all_headlines:
        h_lower = h.lower()
        if any(g in h_lower for g in generic_phrases) and len(h) < 20:
            weak_patterns.append(f'Generic headline: "{h}"')

    # CTA analysis
    cta_found = any(
        any(cta in d.lower() for cta in ["call now", "call today", "get a quote", "book now", "schedule", "contact us", "free estimate"])
        for d in all_descriptions
    )

    return {
        "campaign_id": campaign.campaign_id,
        "campaign_name": campaign.name,
        "ad_count": len(ads),
        "ad_strengths": ad_strengths,
        "headline_count": len(all_headlines),
        "unique_headline_count": len(unique_headlines),
        "headline_issues": headline_issues,
        "description_count": len(all_descriptions),
        "missing_angles": missing_angles,
        "weak_patterns": weak_patterns,
        "has_strong_cta": cta_found,
        "recommendations": _generate_copy_recommendations(campaign, ads, missing_angles, headline_issues),
    }


def _detect_missing_angles(
    headlines: List[str],
    descriptions: List[str],
    business_context: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Detect missing creative angles based on best practices."""
    all_text = " ".join(headlines + descriptions).lower()
    missing = []

    angle_checks = {
        "urgency": ["now", "today", "immediate", "fast", "quick", "asap", "emergency", "24/7", "24 hour"],
        "trust": ["licensed", "insured", "certified", "bonded", "rated", "reviews", "trusted", "years"],
        "local": ["near", "local", "city", "area", "neighborhood", "community"],
        "price/value": ["free", "estimate", "affordable", "no hidden", "upfront", "flat rate", "discount", "save"],
        "specificity": ["mobile", "on-site", "same-day", "key", "lock", "rekey", "install", "repair"],
        "social proof": ["5-star", "5 star", "reviews", "rated", "customers", "served", "trusted by"],
        "guarantee": ["guarantee", "warranty", "satisfaction", "money back"],
    }

    for angle_name, indicators in angle_checks.items():
        if not any(ind in all_text for ind in indicators):
            missing.append(angle_name)

    return missing


def _generate_copy_recommendations(
    campaign: CampaignData,
    ads: List[AdData],
    missing_angles: List[str],
    headline_issues: List[str],
) -> List[Dict[str, Any]]:
    """Generate specific copy improvement recommendations."""
    recs = []

    if "urgency" in missing_angles:
        recs.append({
            "type": "add_urgency",
            "description": "Add urgency-driven headlines",
            "examples": [
                "Fast Response — Call Now",
                "Available 24/7 — No Wait",
                "Same-Day Service Available",
                "Emergency? We're On The Way",
            ],
        })

    if "trust" in missing_angles:
        recs.append({
            "type": "add_trust",
            "description": "Add trust and credibility signals",
            "examples": [
                "Licensed & Insured Pros",
                "Background-Checked Techs",
                "10+ Years Serving [City]",
                "Fully Bonded & Certified",
            ],
        })

    if "social proof" in missing_angles:
        recs.append({
            "type": "add_social_proof",
            "description": "Add social proof elements",
            "examples": [
                "5-Star Rated on Google",
                "1,000+ Happy Customers",
                "See Our 5-Star Reviews",
            ],
        })

    if "price/value" in missing_angles:
        recs.append({
            "type": "add_value",
            "description": "Add price/value messaging",
            "examples": [
                "Free Estimates — No Obligation",
                "Upfront Pricing, No Surprises",
                "Affordable Rates, Expert Service",
            ],
        })

    if headline_issues:
        recs.append({
            "type": "headline_diversity",
            "description": "Increase headline diversity for better RSA optimization",
            "detail": "; ".join(headline_issues),
        })

    return recs


# ── Image Prompt Generation ──────────────────────────────────────────────────

async def generate_image_prompts(
    snapshot: AccountSnapshot,
    business_context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Generate deeply specific ad image prompts for the account.
    Each prompt is tailored to the business, audience, and campaign context.
    """
    prompts = []
    biz = business_context or {}
    business_type = biz.get("business_type", "local service business")
    business_name = biz.get("business_name", "")
    city = biz.get("city", "")
    services = biz.get("services", [])

    # Generate per-campaign-type prompts
    for campaign in snapshot.campaigns:
        if campaign.impressions < 50:
            continue

        camp_name_lower = campaign.name.lower()

        # Emergency / lockout imagery
        if any(term in camp_name_lower for term in ["emergency", "lockout", "locked", "24/7"]):
            prompts.append(_build_prompt(
                category="emergency_service",
                business_type=business_type,
                city=city,
                campaign_name=campaign.name,
                scene="A professional mobile technician arriving at a customer's location at night or early evening, "
                      "with van headlights illuminating the scene. Customer looks relieved. Technician is mid-stride "
                      "carrying a professional tool bag, wearing a branded uniform polo. Residential suburban setting "
                      "with warm porch light visible.",
                emotional_angle="relief, urgency resolved, trust in the professional",
                composition="Medium-wide shot, slightly low angle on technician for authority. "
                            "Warm practical lighting mixing van headlights and porch light. Shallow depth of field.",
                avoid="Do NOT show break-in imagery, police, crime scenes, or panicked expressions.",
                text_overlay="Text-safe negative space in upper-right for overlay like 'Emergency Service — We Come To You'",
                placements=["search_companion", "performance_max", "display"],
            ))

        # Premium / specialty service
        elif any(term in camp_name_lower for term in ["bmw", "mercedes", "audi", "lexus", "tesla", "premium", "luxury"]):
            brand = next((b for b in ["bmw", "mercedes", "audi", "lexus", "tesla"] if b in camp_name_lower), "luxury vehicle")
            prompts.append(_build_prompt(
                category="premium_specialist",
                business_type=business_type,
                city=city,
                campaign_name=campaign.name,
                scene=f"A professionally dressed mobile technician beside a late-model {brand.title()} in an upscale "
                      f"residential driveway at golden hour, holding a modern diagnostic tablet and OEM-style key fob. "
                      f"Service van with subtle branding visible in background. Clean, premium composition.",
                emotional_angle="legitimacy, precision, technical expertise, premium quality",
                composition="Medium-wide, realistic, crisp. Clean reflections on vehicle paint, subtle depth of field, "
                            "natural skin tones.",
                avoid="Avoid police-light aesthetics, break-in vibes, overly staged stock-photo smiles, "
                      "cartoon styling, or low-quality compositing.",
                text_overlay=f"Text-safe negative space in upper-left for overlay like '{brand.title()} Key Replacement On-Site'",
                placements=["search_companion", "performance_max"],
            ))

        # General service
        else:
            prompts.append(_build_prompt(
                category="general_service_trust",
                business_type=business_type,
                city=city,
                campaign_name=campaign.name,
                scene=f"A friendly, competent technician completing a service job at a residential front door "
                      f"in {city or 'a clean suburban neighborhood'}. Customer smiling and receiving keys/receipt. "
                      f"Daytime, clear weather, well-maintained property.",
                emotional_angle="trust, competence, friendly professionalism, neighborhood reliability",
                composition="Medium shot, eye-level, natural daylight. Warm color palette. "
                            "Both subjects in frame, genuine interaction.",
                avoid="Avoid dark/moody lighting, empty stock-photo backgrounds, overly corporate styling.",
                text_overlay="Negative space at top for text overlay like 'Your Trusted Local Expert'",
                placements=["search_companion", "performance_max", "display"],
            ))

    return prompts


def _build_prompt(
    category: str,
    business_type: str,
    city: str,
    campaign_name: str,
    scene: str,
    emotional_angle: str,
    composition: str,
    avoid: str,
    text_overlay: str,
    placements: List[str],
) -> Dict[str, Any]:
    return {
        "category": category,
        "campaign_name": campaign_name,
        "business_type": business_type,
        "location_context": city,
        "prompt": scene,
        "emotional_angle": emotional_angle,
        "composition": composition,
        "avoid": avoid,
        "text_overlay_guidance": text_overlay,
        "placements": placements,
        "aspect_ratios": ["1.91:1", "1:1", "4:5"],
    }


# ── LLM-powered creative generation ─────────────────────────────────────────

async def generate_ad_copy_with_llm(
    campaign: CampaignData,
    existing_ads: List[AdData],
    business_context: Dict[str, Any],
    missing_angles: List[str],
) -> Optional[Dict[str, Any]]:
    """
    Use LLM to generate new RSA headlines, descriptions, and extensions
    based on the campaign context, existing ads, and missing angles.
    """
    if not settings.OPENAI_API_KEY:
        logger.warning("OpenAI key not set — skipping LLM creative generation")
        return None

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    existing_headlines = []
    existing_descriptions = []
    for ad in existing_ads:
        existing_headlines.extend(ad.headlines)
        existing_descriptions.extend(ad.descriptions)

    biz = business_context
    prompt = f"""You are a senior Google Ads copywriter for a {biz.get('business_type', 'local service business')} 
in {biz.get('city', 'the local area')} called "{biz.get('business_name', 'the business')}".

Campaign: {campaign.name}
Campaign type: {campaign.campaign_type}
Current headlines: {json.dumps(existing_headlines[:10])}
Current descriptions: {json.dumps(existing_descriptions[:5])}
Missing creative angles: {', '.join(missing_angles) if missing_angles else 'None identified'}

Generate:
1. 10 new unique headlines (max 30 chars each) that fill the missing angles and complement the existing ones
2. 4 new descriptions (max 90 chars each) 
3. 4 sitelink suggestions (title + description)
4. 4 callout suggestions (max 25 chars each)

Focus on: specificity, local relevance, trust signals, urgency where appropriate, clear CTAs.
Do NOT use generic phrases like "Best Service" or "#1 Provider".

Respond in JSON format:
{{"headlines": [...], "descriptions": [...], "sitelinks": [{{"title": "...", "description": "..."}}], "callouts": [...]}}
"""

    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.8,
            max_tokens=1000,
        )
        content = response.choices[0].message.content
        return json.loads(content) if content else None
    except Exception as e:
        logger.error("LLM creative generation failed", error=str(e))
        return None
