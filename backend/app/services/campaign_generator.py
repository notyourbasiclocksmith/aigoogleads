"""
Expert-Level Prompt-to-Campaign Generator Service

Pipeline:
1) Parse intent from prompt (service, geo, offer, urgency, goal)
2) Pull competitor intelligence (messaging, USPs, gaps to exploit)
3) Pull industry keyword database — tiered by intent (emergency / high / medium / informational)
4) Pull performance learnings from same-industry tenants
5) Determine best campaign type + bidding strategy with reasoning
6) Build TIGHTLY themed ad groups (SKAGs / close variants) — NOT one big ad group
7) Write psychology-driven ad copy per ad group: urgency, social proof, value props, CTAs
8) Generate expert-level extensions: sitelinks, callouts, structured snippets, call, location, price
9) Set smart budget, bid strategy, scheduling, device bids, location bid adjustments
10) Return full preview with expert reasoning for every decision
"""
import uuid
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.business_profile import BusinessProfile
from app.models.campaign import Campaign
from app.models.playbook import Playbook
from app.models.learning import Learning
from app.models.competitor_profile import CompetitorProfile


class CampaignGeneratorService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def generate_from_prompt(
        self,
        prompt: str,
        business_profile: BusinessProfile,
        google_customer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        industry = (business_profile.industry_classification or "general").lower()

        # --- Research Phase ---
        intent = self._parse_intent(prompt, business_profile)
        campaign_type = self._determine_campaign_type(intent, business_profile)
        existing = await self._get_existing_campaigns()
        playbook = await self._get_playbook(industry, intent.get("goal"))
        learnings = await self._get_relevant_learnings(industry)
        competitors = await self._get_competitor_intelligence()

        # --- Strategy Phase ---
        keyword_strategy = self._build_keyword_strategy(intent, industry, learnings, playbook)
        bid_strategy = self._determine_bid_strategy(campaign_type, intent, business_profile)
        budget = self._calculate_budget(business_profile, playbook, intent)
        scheduling = self._build_schedule(industry, intent)
        device_bids = self._build_device_bids(industry, intent)
        competitor_insights = self._extract_competitor_insights(competitors, intent)

        draft = self._build_campaign_draft(
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
        return draft

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

        # Service-specific keywords from business profile
        for svc in services:
            keywords.append({"text": svc.lower(), "match_type": "PHRASE", "tier": "service"})
            keywords.append({"text": f"{svc.lower()} near me", "match_type": "EXACT", "tier": "service"})
            keywords.append({"text": f"{svc.lower()} service", "match_type": "PHRASE", "tier": "service"})

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

    def _build_campaign_draft(
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
        offers = intent.get("offers", [])
        usps = intent.get("usps", [])
        phone = business_profile.phone or ""
        website = business_profile.website_url or ""
        industry = (business_profile.industry_classification or "general").lower()
        brand_voice = business_profile.brand_voice_json or {}
        tone = brand_voice.get("tone", "professional")

        primary_service = services[0] if services else "Service"
        urgency_tag = "Emergency" if intent.get("urgency") == "high" else "Standard"
        campaign_name = f"{primary_service} | {campaign_type} | {urgency_tag}"

        existing_names = {c["name"] for c in existing_campaigns}
        if campaign_name in existing_names:
            campaign_name = f"{campaign_name} ({str(uuid.uuid4())[:4]})"

        # Build TIGHTLY themed ad groups per service (SKAG-style)
        all_keywords = keyword_strategy["keywords"]
        all_negatives = keyword_strategy["negatives"]

        ad_groups = []
        for i, svc in enumerate(services[:5]):
            # Each service gets its own tightly themed ad group
            svc_keywords = [k for k in all_keywords
                            if svc.lower() in k["text"] or k.get("tier") in ("emergency", "high")]
            if not svc_keywords:
                svc_keywords = all_keywords[:15]

            headlines = self._generate_expert_headlines(
                svc, locations, offers, usps, phone, tone, industry,
                intent.get("urgency"), competitor_insights
            )
            descriptions = self._generate_expert_descriptions(
                svc, locations, offers, usps, phone, tone, industry,
                intent.get("urgency"), competitor_insights
            )

            url_slug = svc.lower().replace(" ", "-")
            ad_group = {
                "name": f"{svc} — {locations[0] if locations else 'All Areas'}",
                "theme": svc,
                "match_strategy": "EXACT + PHRASE (SKAG-style tightly themed)",
                "keywords": svc_keywords[:20],
                "negatives": all_negatives,
                "ads": [{
                    "type": "RESPONSIVE_SEARCH_AD",
                    "headlines": headlines,
                    "descriptions": descriptions,
                    "final_urls": [f"{website}/{url_slug}"] if website else [],
                    "display_path": [svc[:15].replace(" ", "-"), locations[0][:15] if locations else "NearYou"],
                }],
            }
            ad_groups.append(ad_group)

        extensions = self._generate_expert_extensions(
            business_profile, services, offers, usps, competitor_insights
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
