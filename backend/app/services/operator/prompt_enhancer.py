"""
Prompt Enhancer — transforms messy user input into a structured campaign brief.

Uses OpenAI (fast + cheap) to:
1. Fix typos and grammar
2. Extract campaign intent (services, locations, radius, goals)
3. Build structured campaign brief with ad groups, keyword themes, negative keywords
4. Generate premium image prompts per ad group/service
5. Return a clean, expert-level prompt for the Opus pipeline agents

Why OpenAI not Claude: This is a formatting/structuring task, not a quality-critical
decision. GPT-4o-mini does this in <2s for ~$0.001. We save Claude Opus for the
actual keyword research, ad copy, and QA where model quality = money.
"""

import json
import structlog
from typing import Dict, Any, Optional

import openai
from app.core.config import settings

logger = structlog.get_logger()


async def enhance_prompt(
    raw_prompt: str,
    business_context: Dict[str, Any],
    existing_campaigns: list = None,
) -> Dict[str, Any]:
    """
    Transform a raw user prompt into a structured campaign brief.

    Returns:
    {
        "enhanced_prompt": "Clean, structured version of user's request",
        "campaign_brief": {
            "campaign_name": "BMW | DFW | 25mi | High Intent | Search",
            "services": ["FRM Module Repair", "FEM/BDC Module Repair", "BMW Key Replacement"],
            "locations": ["Dallas", "Fort Worth", "Arlington"],
            "radius_miles": 25,
            "campaign_type": "SEARCH",
            "objective": "calls",
            "notes": "User wants separate ads per service, check existing campaigns"
        },
        "ad_group_briefs": [
            {
                "name": "FRM Module Repair",
                "keyword_themes": ["frm repair", "footwell module", "bmw electrical"],
                "search_intent": "emergency/high-intent — BMW owners with electrical failures",
                "usp_angle": "Same-day repair, save vs dealer, mobile service"
            },
            ...
        ],
        "suggested_negatives": ["cheap", "free", "diy", "how to", "amazon", "ebay", ...],
        "image_prompts": [
            {
                "service": "FRM Module Repair",
                "prompt": "Luxury BMW interior dashboard with warning lights illuminated...",
                "style": "premium European automotive, cinematic lighting"
            },
            ...
        ]
    }
    """
    if not settings.OPENAI_API_KEY:
        logger.info("OpenAI not configured — skipping prompt enhancement")
        return {"enhanced_prompt": raw_prompt, "skipped": True}

    client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    biz_name = business_context.get("name", "")
    biz_industry = business_context.get("industry", "")
    biz_services = business_context.get("services", [])
    biz_city = business_context.get("city", "")
    biz_state = business_context.get("state", "")

    existing_text = "None"
    if existing_campaigns:
        lines = []
        for c in existing_campaigns[:10]:
            lines.append(f"  [{c.get('status', '?')}] {c.get('name', '?')} — Budget:${c.get('budget_daily', '?')}/day")
        existing_text = "\n".join(lines)

    system = """You are a Google Ads campaign architect. You take a raw, messy user prompt
(often with typos) and transform it into a structured, expert-level campaign brief.

YOUR JOB:
1. Fix typos and understand the user's actual intent
2. Extract: services to target, locations, radius, campaign type, goals
3. Structure ad groups (1 per service) with keyword themes
4. Generate PREMIUM image prompts for each service (for ad images)
5. Suggest negative keywords

IMAGE PROMPT RULES — CRITICAL:
- Images must look PREMIUM, EUROPEAN, DEALER-LEVEL
- Clean modern workshop, cinematic lighting, shallow depth of field
- Include the specific service being shown (diagnostics, key programming, module repair)
- Style: professional automotive photography, high detail, realistic
- NO text or logos in the image
- Resolution: mention "high resolution, 4K quality"

Respond with ONLY valid JSON."""

    user_msg = f"""RAW USER PROMPT (may have typos):
"{raw_prompt}"

BUSINESS CONTEXT:
  Name: {biz_name}
  Industry: {biz_industry}
  Services: {json.dumps(biz_services)}
  Location: {biz_city}, {biz_state}

EXISTING CAMPAIGNS:
{existing_text}

Transform this into a structured brief. Return this JSON:
{{
  "enhanced_prompt": "Clean, grammatically correct version of user's full request with all details preserved",
  "campaign_brief": {{
    "campaign_name": "Business | Location | Radius | Intent | Type",
    "services": ["Service 1", "Service 2", "Service 3"],
    "locations": ["City 1", "City 2"],
    "radius_miles": 25,
    "campaign_type": "SEARCH",
    "objective": "calls" or "leads",
    "budget_suggestion": "Suggested daily budget based on services and competition",
    "notes": "Any special instructions from the user"
  }},
  "ad_group_briefs": [
    {{
      "name": "Service Name",
      "keyword_themes": ["theme1", "theme2", "theme3"],
      "search_intent": "Describe who searches for this and why",
      "usp_angle": "What makes this business stand out for this service",
      "sample_headlines": ["Headline 1 (max 30 chars)", "Headline 2", "Headline 3"],
      "sample_descriptions": ["Description 1 (max 90 chars)", "Description 2"]
    }}
  ],
  "suggested_negatives": ["negative1", "negative2", ...],
  "image_prompts": [
    {{
      "service": "Service Name",
      "prompt": "Detailed premium image generation prompt, cinematic, photorealistic, European automotive...",
      "style": "photorealistic",
      "engine": "flux"
    }}
  ]
}}"""

    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL or "gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=4096,
            temperature=0.4,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)

        logger.info(
            "Prompt enhanced",
            services=len(result.get("campaign_brief", {}).get("services", [])),
            image_prompts=len(result.get("image_prompts", [])),
            ad_groups=len(result.get("ad_group_briefs", [])),
        )

        return result

    except json.JSONDecodeError as e:
        logger.warning("Prompt enhancer JSON parse failed", error=str(e))
        return {"enhanced_prompt": raw_prompt, "error": "JSON parse failed"}
    except Exception as e:
        logger.error("Prompt enhancer failed", error=str(e))
        return {"enhanced_prompt": raw_prompt, "error": str(e)[:200]}
