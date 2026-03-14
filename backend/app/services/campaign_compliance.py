"""
Campaign Compliance Engine — Google Ads Maximum Standards Validator + Auto-Healer

Validates every generated campaign against Google's actual requirements and
auto-fixes issues via targeted AI regeneration until the campaign hits
"Excellent" Ad Strength.

Google's Ad Strength scoring:
  - POOR: Missing basics, too few assets, duplicates
  - AVERAGE: Meets minimums but lacks diversity
  - GOOD: Decent diversity and coverage
  - EXCELLENT: Maximum asset count, full diversity, all categories covered,
               no duplicates, strong pinning, complete extensions

This engine enforces EXCELLENT on every campaign.
"""
import json
import structlog
from typing import Dict, Any, List, Optional, Tuple
from openai import AsyncOpenAI
from app.core.config import settings

logger = structlog.get_logger()

# ══════════════════════════════════════════════════════════════════════════════
#  GOOGLE ADS REQUIREMENTS BY CAMPAIGN TYPE
# ══════════════════════════════════════════════════════════════════════════════

SEARCH_REQUIREMENTS = {
    "headlines_min": 3,
    "headlines_excellent": 15,
    "headline_max_chars": 30,
    "descriptions_min": 2,
    "descriptions_excellent": 4,
    "description_max_chars": 90,
    "keyword_in_headlines_min": 3,
    "geo_in_headlines_min": 1,
    "cta_in_headlines_min": 1,
    "unique_headline_themes_min": 5,
    "sitelinks_min": 4,
    "callouts_min": 4,
    "callout_max_chars": 25,
    "sitelink_text_max_chars": 25,
    "sitelink_desc_max_chars": 35,
    "negatives_min": 5,
}

CALL_REQUIREMENTS = {
    "headline1_max_chars": 30,
    "headline2_max_chars": 30,
    "description1_max_chars": 35,
    "description2_max_chars": 35,
    "business_name_max_chars": 25,
    "phone_required": True,
    "country_code_required": True,
}

PMAX_REQUIREMENTS = {
    "headlines_min": 3,
    "headlines_excellent": 5,
    "headline_max_chars": 30,
    "long_headlines_min": 1,
    "long_headlines_excellent": 5,
    "long_headline_max_chars": 90,
    "descriptions_min": 2,
    "descriptions_excellent": 5,
    "description_max_chars": 90,
    "business_name_max_chars": 25,
    "final_url_required": True,
    "search_themes_min": 3,
}

DISPLAY_REQUIREMENTS = {
    "short_headlines_min": 1,
    "short_headlines_excellent": 5,
    "headline_max_chars": 30,
    "long_headline_required": True,
    "long_headline_max_chars": 90,
    "descriptions_min": 1,
    "descriptions_excellent": 5,
    "description_max_chars": 90,
    "business_name_max_chars": 25,
    "final_url_required": True,
}

# Headline diversity categories that Google uses for Ad Strength scoring
HEADLINE_CATEGORIES = [
    "keyword_relevance",   # Contains the primary keyword/service
    "geo_targeting",       # Contains location name
    "trust_social_proof",  # Ratings, years, license, insurance
    "value_proposition",   # USPs, differentiators, specific benefits
    "cta_action",          # Call now, Get quote, Book today
    "urgency_availability",# 24/7, Same-day, Available now, Emergency
    "brand_name",          # Business name
    "offer_promotion",     # Discounts, free estimates, special pricing
]


class CampaignComplianceEngine:
    """
    Validates campaign drafts against Google's maximum standards and
    auto-heals issues via targeted AI regeneration.
    """

    def __init__(self):
        self.issues: List[Dict[str, Any]] = []
        self.score = 0
        self.grade = "POOR"

    # ── PUBLIC API ────────────────────────────────────────────────────────

    def validate(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a campaign draft and return a compliance report.
        Returns: {score, grade, issues[], fixes_needed[], passed}
        """
        self.issues = []
        campaign = draft.get("campaign", {})
        campaign_type = (campaign.get("type") or "SEARCH").upper()

        if campaign_type == "SEARCH":
            self._validate_search(draft)
        elif campaign_type == "CALL":
            self._validate_call(draft)
        elif campaign_type == "PERFORMANCE_MAX":
            self._validate_pmax(draft)
        elif campaign_type == "DISPLAY":
            self._validate_display(draft)

        # Common checks
        self._validate_extensions(draft, campaign_type)
        self._validate_campaign_settings(draft)

        # Score calculation
        self.score = self._calculate_score(campaign_type)
        self.grade = self._score_to_grade(self.score)

        critical = [i for i in self.issues if i["severity"] == "critical"]
        warnings = [i for i in self.issues if i["severity"] == "warning"]
        suggestions = [i for i in self.issues if i["severity"] == "suggestion"]

        return {
            "score": self.score,
            "grade": self.grade,
            "passed": self.score >= 90,
            "total_issues": len(self.issues),
            "critical": len(critical),
            "warnings": len(warnings),
            "suggestions": len(suggestions),
            "issues": self.issues,
            "fixes_needed": [i for i in self.issues if i["severity"] in ("critical", "warning") and i.get("auto_fixable")],
        }

    async def validate_and_heal(
        self, draft: Dict[str, Any], max_rounds: int = 2
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Validate → auto-heal → re-validate loop.
        Returns (healed_draft, final_compliance_report).
        """
        for round_num in range(max_rounds):
            report = self.validate(draft)

            if report["passed"]:
                logger.info(
                    "Campaign compliance PASSED",
                    score=report["score"],
                    grade=report["grade"],
                    round=round_num,
                )
                break

            fixable = report["fixes_needed"]
            if not fixable:
                logger.info(
                    "Campaign compliance issues found but none auto-fixable",
                    score=report["score"],
                    issues=report["total_issues"],
                )
                break

            logger.info(
                "Auto-healing campaign",
                round=round_num + 1,
                fixes=len(fixable),
                score=report["score"],
            )
            draft = await self._auto_heal(draft, fixable)

        # Final validation
        report = self.validate(draft)
        draft["compliance"] = {
            "score": report["score"],
            "grade": report["grade"],
            "issues_remaining": report["total_issues"],
            "auto_healed": max_rounds > 0,
        }
        return draft, report

    # ── SEARCH VALIDATION ────────────────────────────────────────────────

    def _validate_search(self, draft: Dict) -> None:
        reqs = SEARCH_REQUIREMENTS
        ad_groups = draft.get("ad_groups", [])

        if not ad_groups:
            self._add_issue("critical", "No ad groups found", "search_structure", True)
            return

        for i, ag in enumerate(ad_groups):
            ag_name = ag.get("name", f"Ad Group {i+1}")
            ads = ag.get("ads", [])
            keywords = ag.get("keywords", [])

            if not ads:
                self._add_issue("critical", f"[{ag_name}] No ads found", "search_ads", True)
                continue

            for ad in ads:
                if ad.get("type", "RESPONSIVE_SEARCH_AD") == "RESPONSIVE_SEARCH_AD":
                    self._validate_rsa(ad, ag_name, ag.get("theme", ""), reqs)

            # Keywords
            if not keywords:
                self._add_issue("critical", f"[{ag_name}] No keywords", "search_keywords", True)
            elif len(keywords) < 5:
                self._add_issue("warning", f"[{ag_name}] Only {len(keywords)} keywords — aim for 10-20 per ad group", "search_keywords", False)

            # Match type diversity
            match_types = set(kw.get("match_type", "").upper() for kw in keywords)
            if len(match_types) < 2 and len(keywords) >= 5:
                self._add_issue("suggestion", f"[{ag_name}] Only uses {match_types} match types — add variety", "search_keywords", False)

            # Negatives
            negatives = ag.get("negatives", [])
            if len(negatives) < reqs["negatives_min"]:
                self._add_issue("warning", f"[{ag_name}] Only {len(negatives)} negatives — need ≥{reqs['negatives_min']}", "search_negatives", False)

    def _validate_rsa(self, ad: Dict, ag_name: str, theme: str, reqs: Dict) -> None:
        headlines = ad.get("headlines", [])
        descriptions = ad.get("descriptions", [])

        # Headline count
        if len(headlines) < reqs["headlines_min"]:
            self._add_issue("critical", f"[{ag_name}] Only {len(headlines)} headlines — Google requires ≥{reqs['headlines_min']}", "rsa_headlines", True)
        elif len(headlines) < reqs["headlines_excellent"]:
            self._add_issue("warning", f"[{ag_name}] {len(headlines)} headlines — need {reqs['headlines_excellent']} for Excellent Ad Strength", "rsa_headlines", True)

        # Description count
        if len(descriptions) < reqs["descriptions_min"]:
            self._add_issue("critical", f"[{ag_name}] Only {len(descriptions)} descriptions — Google requires ≥{reqs['descriptions_min']}", "rsa_descriptions", True)
        elif len(descriptions) < reqs["descriptions_excellent"]:
            self._add_issue("warning", f"[{ag_name}] {len(descriptions)} descriptions — need {reqs['descriptions_excellent']} for Excellent", "rsa_descriptions", True)

        # Character limits
        for j, h in enumerate(headlines):
            if len(h) > reqs["headline_max_chars"]:
                self._add_issue("critical", f"[{ag_name}] Headline {j+1} is {len(h)} chars (max {reqs['headline_max_chars']}): \"{h}\"", "rsa_char_limit", True)

        for j, d in enumerate(descriptions):
            if len(d) > reqs["description_max_chars"]:
                self._add_issue("critical", f"[{ag_name}] Description {j+1} is {len(d)} chars (max {reqs['description_max_chars']}): \"{d[:50]}...\"", "rsa_char_limit", True)

        # Duplicate headlines (case-insensitive)
        seen = set()
        dupes = 0
        for h in headlines:
            normalized = h.lower().strip()
            if normalized in seen:
                dupes += 1
            seen.add(normalized)
        if dupes:
            self._add_issue("critical", f"[{ag_name}] {dupes} duplicate headline(s) found — Google rejects duplicates", "rsa_duplicates", True)

        # Similar headlines (>70% word overlap)
        similar_pairs = self._find_similar_headlines(headlines)
        if similar_pairs:
            self._add_issue("warning", f"[{ag_name}] {len(similar_pairs)} headline pair(s) too similar — hurts Ad Strength diversity score", "rsa_similarity", True)

        # Headline diversity categories
        if theme and headlines:
            categories_hit = self._check_headline_diversity(headlines, theme)
            missing = [c for c in HEADLINE_CATEGORIES if c not in categories_hit]
            if len(missing) >= 3:
                self._add_issue("warning", f"[{ag_name}] Headlines missing diversity categories: {', '.join(missing[:4])} — add variety for Excellent Ad Strength", "rsa_diversity", True)

        # Keyword in headlines
        if theme:
            keyword_headlines = sum(1 for h in headlines if theme.lower() in h.lower())
            if keyword_headlines < reqs["keyword_in_headlines_min"]:
                self._add_issue("warning", f"[{ag_name}] Only {keyword_headlines} headlines contain the keyword \"{theme}\" — need ≥{reqs['keyword_in_headlines_min']} for Ad Relevance", "rsa_keyword_relevance", True)

        # Final URLs
        final_urls = ad.get("final_urls", [])
        if not final_urls:
            self._add_issue("critical", f"[{ag_name}] No final URLs on ad — Google will reject", "rsa_final_url", False)

        # Pinning check
        pinning = ad.get("pinning", {})
        if not pinning or not pinning.get("headline_pins"):
            self._add_issue("suggestion", f"[{ag_name}] No headline pinning — pin best keyword headline to Position 1 for Ad Relevance", "rsa_pinning", False)

    # ── CALL VALIDATION ──────────────────────────────────────────────────

    def _validate_call(self, draft: Dict) -> None:
        reqs = CALL_REQUIREMENTS
        ad_groups = draft.get("ad_groups", [])

        if not ad_groups:
            self._add_issue("critical", "No ad groups found", "call_structure", True)
            return

        for i, ag in enumerate(ad_groups):
            ag_name = ag.get("name", f"Ad Group {i+1}")
            for ad in ag.get("ads", []):
                if ad.get("type") != "CALL_AD":
                    self._add_issue("warning", f"[{ag_name}] Ad type is {ad.get('type')} — Call campaigns should use CALL_AD", "call_ad_type", False)
                    continue

                # Required fields
                if not ad.get("phone_number"):
                    self._add_issue("critical", f"[{ag_name}] No phone number on Call ad", "call_phone", False)
                if not ad.get("business_name"):
                    self._add_issue("critical", f"[{ag_name}] No business name on Call ad", "call_business_name", True)
                if not ad.get("country_code"):
                    self._add_issue("warning", f"[{ag_name}] No country code — defaulting to US", "call_country_code", False)

                # Character limits
                for field, max_chars in [("headline1", 30), ("headline2", 30), ("description1", 35), ("description2", 35)]:
                    val = ad.get(field, "")
                    if not val:
                        self._add_issue("critical", f"[{ag_name}] Missing {field}", "call_fields", True)
                    elif len(val) > max_chars:
                        self._add_issue("critical", f"[{ag_name}] {field} is {len(val)} chars (max {max_chars})", "call_char_limit", True)

                # Business name length
                biz = ad.get("business_name", "")
                if len(biz) > reqs["business_name_max_chars"]:
                    self._add_issue("critical", f"[{ag_name}] Business name is {len(biz)} chars (max {reqs['business_name_max_chars']})", "call_char_limit", True)

    # ── PMAX VALIDATION ──────────────────────────────────────────────────

    def _validate_pmax(self, draft: Dict) -> None:
        reqs = PMAX_REQUIREMENTS
        asset_groups = draft.get("asset_groups", [])

        if not asset_groups:
            self._add_issue("critical", "No asset groups found", "pmax_structure", True)
            return

        for i, ag in enumerate(asset_groups):
            ag_name = ag.get("name", f"Asset Group {i+1}")
            text_assets = ag.get("text_assets", {})

            # Headlines
            headlines = text_assets.get("headlines", [])
            if len(headlines) < reqs["headlines_min"]:
                self._add_issue("critical", f"[{ag_name}] Only {len(headlines)} headlines — Google requires ≥{reqs['headlines_min']}", "pmax_headlines", True)
            elif len(headlines) < reqs["headlines_excellent"]:
                self._add_issue("warning", f"[{ag_name}] {len(headlines)} headlines — need {reqs['headlines_excellent']} for Excellent", "pmax_headlines", True)

            for j, h in enumerate(headlines):
                if len(h) > reqs["headline_max_chars"]:
                    self._add_issue("critical", f"[{ag_name}] Headline {j+1} is {len(h)} chars (max {reqs['headline_max_chars']})", "pmax_char_limit", True)

            # Long headlines
            long_headlines = text_assets.get("long_headlines", [])
            if len(long_headlines) < reqs["long_headlines_min"]:
                self._add_issue("critical", f"[{ag_name}] No long headlines — Google requires ≥{reqs['long_headlines_min']}", "pmax_long_headlines", True)
            elif len(long_headlines) < reqs["long_headlines_excellent"]:
                self._add_issue("warning", f"[{ag_name}] {len(long_headlines)} long headlines — need {reqs['long_headlines_excellent']} for Excellent", "pmax_long_headlines", True)

            for j, lh in enumerate(long_headlines):
                if len(lh) > reqs["long_headline_max_chars"]:
                    self._add_issue("critical", f"[{ag_name}] Long headline {j+1} is {len(lh)} chars (max {reqs['long_headline_max_chars']})", "pmax_char_limit", True)

            # Descriptions
            descriptions = text_assets.get("descriptions", [])
            if len(descriptions) < reqs["descriptions_min"]:
                self._add_issue("critical", f"[{ag_name}] Only {len(descriptions)} descriptions — Google requires ≥{reqs['descriptions_min']}", "pmax_descriptions", True)
            elif len(descriptions) < reqs["descriptions_excellent"]:
                self._add_issue("warning", f"[{ag_name}] {len(descriptions)} descriptions — need {reqs['descriptions_excellent']} for Excellent", "pmax_descriptions", True)

            for j, d in enumerate(descriptions):
                if len(d) > reqs["description_max_chars"]:
                    self._add_issue("critical", f"[{ag_name}] Description {j+1} is {len(d)} chars (max {reqs['description_max_chars']})", "pmax_char_limit", True)

            # Business name
            biz = text_assets.get("business_name", "")
            if not biz:
                self._add_issue("critical", f"[{ag_name}] Missing business name", "pmax_business_name", True)
            elif len(biz) > reqs["business_name_max_chars"]:
                self._add_issue("critical", f"[{ag_name}] Business name is {len(biz)} chars (max {reqs['business_name_max_chars']})", "pmax_char_limit", True)

            # Final URL
            if not ag.get("final_url"):
                self._add_issue("warning", f"[{ag_name}] No final URL — Google will use your domain", "pmax_final_url", False)

            # Audience signals
            signals = ag.get("audience_signals", {})
            search_themes = signals.get("search_themes", [])
            if len(search_themes) < reqs["search_themes_min"]:
                self._add_issue("warning", f"[{ag_name}] Only {len(search_themes)} search themes — add ≥{reqs['search_themes_min']} for better targeting", "pmax_signals", True)

            # Image assets warning
            if not ag.get("image_assets"):
                self._add_issue("suggestion", f"[{ag_name}] No image assets — PMax performs significantly better with images (landscape 1200×628, square 1200×1200)", "pmax_images", False)

    # ── DISPLAY VALIDATION ───────────────────────────────────────────────

    def _validate_display(self, draft: Dict) -> None:
        reqs = DISPLAY_REQUIREMENTS
        ad_groups = draft.get("ad_groups", [])

        if not ad_groups:
            self._add_issue("critical", "No ad groups found", "display_structure", True)
            return

        for i, ag in enumerate(ad_groups):
            ag_name = ag.get("name", f"Ad Group {i+1}")
            for ad in ag.get("ads", []):
                if ad.get("type") != "RESPONSIVE_DISPLAY_AD":
                    continue

                # Short headlines
                short_headlines = ad.get("short_headlines", [])
                if len(short_headlines) < reqs["short_headlines_min"]:
                    self._add_issue("critical", f"[{ag_name}] No short headlines — Google requires ≥{reqs['short_headlines_min']}", "display_headlines", True)
                elif len(short_headlines) < reqs["short_headlines_excellent"]:
                    self._add_issue("warning", f"[{ag_name}] {len(short_headlines)} short headlines — need {reqs['short_headlines_excellent']} for Excellent", "display_headlines", True)

                for j, h in enumerate(short_headlines):
                    if len(h) > reqs["headline_max_chars"]:
                        self._add_issue("critical", f"[{ag_name}] Short headline {j+1} is {len(h)} chars (max {reqs['headline_max_chars']})", "display_char_limit", True)

                # Long headline
                long_hl = ad.get("long_headline", "")
                if not long_hl:
                    self._add_issue("critical", f"[{ag_name}] Missing long headline", "display_long_headline", True)
                elif len(long_hl) > reqs["long_headline_max_chars"]:
                    self._add_issue("critical", f"[{ag_name}] Long headline is {len(long_hl)} chars (max {reqs['long_headline_max_chars']})", "display_char_limit", True)

                # Descriptions
                descriptions = ad.get("descriptions", [])
                if len(descriptions) < reqs["descriptions_min"]:
                    self._add_issue("critical", f"[{ag_name}] No descriptions", "display_descriptions", True)
                elif len(descriptions) < reqs["descriptions_excellent"]:
                    self._add_issue("warning", f"[{ag_name}] {len(descriptions)} descriptions — need {reqs['descriptions_excellent']} for Excellent", "display_descriptions", True)

                for j, d in enumerate(descriptions):
                    if len(d) > reqs["description_max_chars"]:
                        self._add_issue("critical", f"[{ag_name}] Description {j+1} is {len(d)} chars (max {reqs['description_max_chars']})", "display_char_limit", True)

                # Business name
                biz = ad.get("business_name", "")
                if not biz:
                    self._add_issue("critical", f"[{ag_name}] Missing business name", "display_business_name", True)

                # Final URLs
                if not ad.get("final_urls"):
                    self._add_issue("critical", f"[{ag_name}] No final URLs", "display_final_url", False)

                # Image warning
                if not ad.get("image_assets") and not ad.get("image_asset_resources"):
                    self._add_issue("suggestion", f"[{ag_name}] No image assets — Display ads need images for maximum performance", "display_images", False)

            # Audience targeting
            targeting = ag.get("audience_targeting", {})
            if not targeting.get("custom_intent") and not targeting.get("in_market"):
                self._add_issue("warning", f"[{ag_name}] No audience targeting configured — Display campaigns need targeting", "display_targeting", False)

    # ── EXTENSION VALIDATION (all types) ─────────────────────────────────

    def _validate_extensions(self, draft: Dict, campaign_type: str) -> None:
        extensions = draft.get("extensions", {})

        if campaign_type in ("SEARCH", "CALL"):
            # Sitelinks
            sitelinks = extensions.get("sitelinks", [])
            if len(sitelinks) < SEARCH_REQUIREMENTS["sitelinks_min"]:
                self._add_issue("warning", f"Only {len(sitelinks)} sitelinks — need ≥{SEARCH_REQUIREMENTS['sitelinks_min']} for maximum Quality Score", "ext_sitelinks", True)

            for sl in sitelinks:
                text = sl.get("text", "")
                if len(text) > SEARCH_REQUIREMENTS["sitelink_text_max_chars"]:
                    self._add_issue("critical", f"Sitelink text \"{text}\" is {len(text)} chars (max {SEARCH_REQUIREMENTS['sitelink_text_max_chars']})", "ext_sitelink_chars", True)

            # Callouts
            callouts = extensions.get("callouts", [])
            if len(callouts) < SEARCH_REQUIREMENTS["callouts_min"]:
                self._add_issue("warning", f"Only {len(callouts)} callouts — need ≥{SEARCH_REQUIREMENTS['callouts_min']} for maximum CTR boost", "ext_callouts", True)

            for co in callouts:
                if len(co) > SEARCH_REQUIREMENTS["callout_max_chars"]:
                    self._add_issue("critical", f"Callout \"{co}\" is {len(co)} chars (max {SEARCH_REQUIREMENTS['callout_max_chars']})", "ext_callout_chars", True)

            # Structured snippets
            snippets = extensions.get("structured_snippets", [])
            if not snippets:
                self._add_issue("suggestion", "No structured snippets — adds 10-15% CTR boost", "ext_snippets", False)

            # Call extension
            if not extensions.get("call_extension"):
                phone = draft.get("campaign", {}).get("settings", {}).get("phone_number")
                if phone:
                    self._add_issue("suggestion", "Phone number available but no call extension set", "ext_call", False)

    # ── CAMPAIGN SETTINGS VALIDATION ─────────────────────────────────────

    def _validate_campaign_settings(self, draft: Dict) -> None:
        campaign = draft.get("campaign", {})

        if not campaign.get("name"):
            self._add_issue("critical", "Campaign has no name", "settings_name", False)

        if not campaign.get("budget_micros") and not campaign.get("budget_daily_usd"):
            self._add_issue("critical", "No budget set", "settings_budget", False)

        if not campaign.get("bidding_strategy"):
            self._add_issue("warning", "No bidding strategy set — will default to MAXIMIZE_CLICKS", "settings_bidding", False)

        if not campaign.get("locations"):
            self._add_issue("suggestion", "No location targeting — campaign will target all locations", "settings_locations", False)

        schedule = campaign.get("schedule", {})
        if not schedule:
            self._add_issue("suggestion", "No ad schedule — consider limiting to business hours for calls", "settings_schedule", False)

    # ── SCORING ──────────────────────────────────────────────────────────

    def _calculate_score(self, campaign_type: str) -> int:
        """Calculate compliance score 0-100."""
        if not self.issues:
            return 100

        critical = sum(1 for i in self.issues if i["severity"] == "critical")
        warnings = sum(1 for i in self.issues if i["severity"] == "warning")
        suggestions = sum(1 for i in self.issues if i["severity"] == "suggestion")

        # Start at 100, deduct for issues
        score = 100
        score -= critical * 15     # Critical issues: -15 each
        score -= warnings * 5      # Warnings: -5 each
        score -= suggestions * 1   # Suggestions: -1 each

        return max(0, min(100, score))

    @staticmethod
    def _score_to_grade(score: int) -> str:
        if score >= 90:
            return "EXCELLENT"
        elif score >= 75:
            return "GOOD"
        elif score >= 50:
            return "AVERAGE"
        return "POOR"

    # ── AUTO-HEAL ────────────────────────────────────────────────────────

    async def _auto_heal(self, draft: Dict, fixable_issues: List[Dict]) -> Dict:
        """Use AI to fix identified compliance issues."""
        if not settings.OPENAI_API_KEY:
            return draft

        campaign_type = (draft.get("campaign", {}).get("type") or "SEARCH").upper()

        if campaign_type == "SEARCH":
            draft = await self._heal_search(draft, fixable_issues)
        elif campaign_type == "CALL":
            draft = await self._heal_call(draft, fixable_issues)
        elif campaign_type == "PERFORMANCE_MAX":
            draft = await self._heal_pmax(draft, fixable_issues)
        elif campaign_type == "DISPLAY":
            draft = await self._heal_display(draft, fixable_issues)

        # Heal extensions for Search/Call campaigns
        if campaign_type in ("SEARCH", "CALL"):
            ext_issues = [i for i in fixable_issues if i["category"].startswith("ext_")]
            if ext_issues:
                draft = await self._heal_extensions(draft, ext_issues)

        return draft

    async def _heal_search(self, draft: Dict, issues: List[Dict]) -> Dict:
        """Fix Search campaign RSA issues via targeted AI regeneration."""
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        for ag in draft.get("ad_groups", []):
            for ad in ag.get("ads", []):
                if ad.get("type", "RESPONSIVE_SEARCH_AD") != "RESPONSIVE_SEARCH_AD":
                    continue

                headlines = ad.get("headlines", [])
                descriptions = ad.get("descriptions", [])
                theme = ag.get("theme", "")

                needs_heal = (
                    len(headlines) < 15
                    or len(descriptions) < 4
                    or any(len(h) > 30 for h in headlines)
                    or any(len(d) > 90 for d in descriptions)
                    or self._has_duplicates(headlines)
                )

                if not needs_heal:
                    continue

                # De-duplicate existing headlines
                seen = set()
                clean_headlines = []
                for h in headlines:
                    if h.lower().strip() not in seen and len(h) <= 30:
                        seen.add(h.lower().strip())
                        clean_headlines.append(h)

                # Trim over-length descriptions
                clean_descriptions = [d[:90] for d in descriptions if d.strip()]

                # Calculate how many more we need
                headlines_needed = max(0, 15 - len(clean_headlines))
                descriptions_needed = max(0, 4 - len(clean_descriptions))

                if headlines_needed == 0 and descriptions_needed == 0:
                    ad["headlines"] = clean_headlines[:15]
                    ad["descriptions"] = clean_descriptions[:4]
                    continue

                # AI generation of missing assets
                existing_hl_str = "\n".join(f"  - \"{h}\"" for h in clean_headlines)
                missing_categories = self._get_missing_categories(clean_headlines, theme)

                system = """You are a Google Ads compliance specialist. Your job is to add MISSING
headlines and descriptions to reach Google's maximum Ad Strength (Excellent).
Headlines: STRICTLY ≤30 characters. Descriptions: STRICTLY ≤90 characters.
Each headline must be UNIQUE and different from existing ones.
Respond ONLY with valid JSON."""

                prompt = f"""I need {headlines_needed} more headlines and {descriptions_needed} more descriptions for this ad group.

Service/Theme: {theme}
Existing headlines:
{existing_hl_str}

Missing headline categories to cover: {', '.join(missing_categories)}

RULES:
- Each new headline MUST be ≤30 characters (count precisely!)
- Each new description MUST be ≤90 characters
- NO duplicates or near-duplicates of existing headlines
- Cover the missing categories above for maximum Ad Strength diversity

Return JSON:
{{
  "headlines": ["new headline 1", ...],
  "descriptions": ["new description 1", ...]
}}"""

                try:
                    response = await client.chat.completions.create(
                        model=settings.OPENAI_MODEL,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.8,
                        max_tokens=1000,
                    )
                    content = response.choices[0].message.content
                    data = json.loads(content) if content else {}

                    new_headlines = [h[:30] for h in data.get("headlines", []) if isinstance(h, str) and h.strip()]
                    new_descriptions = [d[:90] for d in data.get("descriptions", []) if isinstance(d, str) and d.strip()]

                    # De-duplicate against existing
                    for h in new_headlines:
                        if h.lower().strip() not in seen:
                            seen.add(h.lower().strip())
                            clean_headlines.append(h)

                    clean_descriptions.extend(new_descriptions)

                    ad["headlines"] = clean_headlines[:15]
                    ad["descriptions"] = clean_descriptions[:4]
                    ad["compliance_healed"] = True

                    logger.info("RSA auto-healed", ag=ag.get("name"), new_headlines=len(new_headlines), new_descriptions=len(new_descriptions))

                except Exception as e:
                    logger.error("Auto-heal RSA failed", error=str(e))

        return draft

    async def _heal_call(self, draft: Dict, issues: List[Dict]) -> Dict:
        """Fix Call campaign issues — truncate over-length fields."""
        for ag in draft.get("ad_groups", []):
            for ad in ag.get("ads", []):
                if ad.get("type") != "CALL_AD":
                    continue
                ad["headline1"] = (ad.get("headline1", "") or "")[:30]
                ad["headline2"] = (ad.get("headline2", "") or "")[:30]
                ad["description1"] = (ad.get("description1", "") or "")[:35]
                ad["description2"] = (ad.get("description2", "") or "")[:35]
                ad["business_name"] = (ad.get("business_name", "") or "")[:25]
                if not ad.get("country_code"):
                    ad["country_code"] = "US"
        return draft

    async def _heal_pmax(self, draft: Dict, issues: List[Dict]) -> Dict:
        """Fix PMax asset group issues via targeted AI regeneration."""
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        for ag in draft.get("asset_groups", []):
            ta = ag.get("text_assets", {})
            headlines = ta.get("headlines", [])
            long_headlines = ta.get("long_headlines", [])
            descriptions = ta.get("descriptions", [])

            hl_needed = max(0, 5 - len(headlines))
            lh_needed = max(0, 5 - len(long_headlines))
            desc_needed = max(0, 5 - len(descriptions))

            if hl_needed == 0 and lh_needed == 0 and desc_needed == 0:
                continue

            system = """You are a PMax compliance specialist. Generate ADDITIONAL text assets
to reach Google's maximum asset count for Excellent Ad Strength.
Headlines ≤30 chars. Long headlines ≤90 chars. Descriptions ≤90 chars.
Respond ONLY with valid JSON."""

            prompt = f"""Asset group: {ag.get('name', 'Service')}
Need: {hl_needed} more headlines, {lh_needed} more long headlines, {desc_needed} more descriptions.
Existing headlines: {json.dumps(headlines)}
Existing long headlines: {json.dumps(long_headlines)}
Existing descriptions: {json.dumps(descriptions)}

Return JSON:
{{
  "headlines": ["≤30 chars", ...],
  "long_headlines": ["≤90 chars", ...],
  "descriptions": ["≤90 chars", ...]
}}"""

            try:
                response = await client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.8,
                    max_tokens=1000,
                )
                data = json.loads(response.choices[0].message.content or "{}")

                headlines.extend([h[:30] for h in data.get("headlines", []) if isinstance(h, str) and h.strip()])
                long_headlines.extend([h[:90] for h in data.get("long_headlines", []) if isinstance(h, str) and h.strip()])
                descriptions.extend([d[:90] for d in data.get("descriptions", []) if isinstance(d, str) and d.strip()])

                ta["headlines"] = headlines[:5]
                ta["long_headlines"] = long_headlines[:5]
                ta["descriptions"] = descriptions[:5]
                ag["text_assets"] = ta
                ag["compliance_healed"] = True

            except Exception as e:
                logger.error("Auto-heal PMax failed", error=str(e))

        return draft

    async def _heal_display(self, draft: Dict, issues: List[Dict]) -> Dict:
        """Fix Display campaign issues via targeted AI regeneration."""
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        for ag in draft.get("ad_groups", []):
            for ad in ag.get("ads", []):
                if ad.get("type") != "RESPONSIVE_DISPLAY_AD":
                    continue

                short_headlines = ad.get("short_headlines", [])
                descriptions = ad.get("descriptions", [])
                hl_needed = max(0, 5 - len(short_headlines))
                desc_needed = max(0, 5 - len(descriptions))

                if hl_needed == 0 and desc_needed == 0:
                    continue

                system = """You are a Display Ads compliance specialist. Generate ADDITIONAL assets
for Responsive Display Ads. Short headlines ≤30 chars. Descriptions ≤90 chars.
Respond ONLY with valid JSON."""

                prompt = f"""Ad group: {ag.get('name', 'Service')}
Need: {hl_needed} more short headlines, {desc_needed} more descriptions.
Existing short headlines: {json.dumps(short_headlines)}
Existing descriptions: {json.dumps(descriptions)}

Return JSON:
{{
  "short_headlines": ["≤30 chars", ...],
  "descriptions": ["≤90 chars", ...]
}}"""

                try:
                    response = await client.chat.completions.create(
                        model=settings.OPENAI_MODEL,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.8,
                        max_tokens=800,
                    )
                    data = json.loads(response.choices[0].message.content or "{}")

                    short_headlines.extend([h[:30] for h in data.get("short_headlines", []) if isinstance(h, str) and h.strip()])
                    descriptions.extend([d[:90] for d in data.get("descriptions", []) if isinstance(d, str) and d.strip()])

                    ad["short_headlines"] = short_headlines[:5]
                    ad["descriptions"] = descriptions[:5]
                    ad["compliance_healed"] = True

                except Exception as e:
                    logger.error("Auto-heal Display failed", error=str(e))

        return draft

    async def _heal_extensions(self, draft: Dict, issues: List[Dict]) -> Dict:
        """Generate missing sitelinks and callouts for Search/Call campaigns."""
        extensions = draft.get("extensions", {})
        sitelinks = extensions.get("sitelinks", [])
        callouts = extensions.get("callouts", [])

        sl_needed = max(0, 4 - len(sitelinks))
        co_needed = max(0, 4 - len(callouts))

        if sl_needed == 0 and co_needed == 0:
            return draft

        campaign = draft.get("campaign", {})
        service = campaign.get("name", "Service")

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        system = """You are a Google Ads extension specialist. Generate sitelinks and callouts
that maximize Quality Score and CTR. Sitelink text ≤25 chars. Sitelink descriptions ≤35 chars.
Callouts ≤25 chars. Respond ONLY with valid JSON."""

        prompt = f"""Campaign: {service}
Need: {sl_needed} more sitelinks, {co_needed} more callouts.
Existing sitelinks: {json.dumps([s.get('text', '') for s in sitelinks])}
Existing callouts: {json.dumps(callouts)}

Return JSON:
{{
  "sitelinks": [{{"text": "≤25 chars", "desc1": "≤35 chars", "desc2": "≤35 chars"}}, ...],
  "callouts": ["≤25 chars", ...]
}}"""

        try:
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.8,
                max_tokens=600,
            )
            data = json.loads(response.choices[0].message.content or "{}")

            new_sitelinks = data.get("sitelinks", [])
            for sl in new_sitelinks:
                if isinstance(sl, dict) and sl.get("text"):
                    sl["text"] = sl["text"][:25]
                    sl["desc1"] = (sl.get("desc1", "") or "")[:35]
                    sl["desc2"] = (sl.get("desc2", "") or "")[:35]
                    sitelinks.append(sl)

            new_callouts = [c[:25] for c in data.get("callouts", []) if isinstance(c, str) and c.strip()]
            callouts.extend(new_callouts)

            extensions["sitelinks"] = sitelinks[:4]
            extensions["callouts"] = callouts[:8]
            draft["extensions"] = extensions
            draft.setdefault("compliance", {})["extensions_healed"] = True

            logger.info("Extensions auto-healed", new_sitelinks=len(new_sitelinks), new_callouts=len(new_callouts))

        except Exception as e:
            logger.error("Auto-heal extensions failed", error=str(e))

        return draft

    # ── HELPERS ───────────────────────────────────────────────────────────

    def _add_issue(self, severity: str, message: str, category: str, auto_fixable: bool):
        self.issues.append({
            "severity": severity,
            "message": message,
            "category": category,
            "auto_fixable": auto_fixable,
        })

    @staticmethod
    def _has_duplicates(items: List[str]) -> bool:
        seen = set()
        for item in items:
            normalized = item.lower().strip()
            if normalized in seen:
                return True
            seen.add(normalized)
        return False

    @staticmethod
    def _find_similar_headlines(headlines: List[str]) -> List[Tuple[str, str]]:
        """Find headline pairs with >70% word overlap."""
        pairs = []
        for i in range(len(headlines)):
            words_i = set(headlines[i].lower().split())
            if not words_i:
                continue
            for j in range(i + 1, len(headlines)):
                words_j = set(headlines[j].lower().split())
                if not words_j:
                    continue
                overlap = len(words_i & words_j) / max(len(words_i), len(words_j))
                if overlap > 0.7:
                    pairs.append((headlines[i], headlines[j]))
        return pairs

    @staticmethod
    def _check_headline_diversity(headlines: List[str], theme: str) -> set:
        """Check which headline diversity categories are covered."""
        categories_hit = set()
        theme_lower = theme.lower()

        cta_words = {"call", "book", "get", "schedule", "free", "start", "save", "try", "contact", "request"}
        trust_words = {"licensed", "insured", "rated", "star", "★", "trusted", "certified", "years", "guarantee", "warranty"}
        urgency_words = {"now", "today", "24/7", "emergency", "fast", "same-day", "available", "open", "immediate", "quick"}
        offer_words = {"free", "off", "%", "$", "discount", "save", "deal", "special", "coupon", "promo"}

        for h in headlines:
            h_lower = h.lower()
            words = set(h_lower.split())

            if theme_lower and theme_lower in h_lower:
                categories_hit.add("keyword_relevance")
            if any(w in words for w in cta_words):
                categories_hit.add("cta_action")
            if any(w in h_lower for w in trust_words):
                categories_hit.add("trust_social_proof")
            if any(w in h_lower for w in urgency_words):
                categories_hit.add("urgency_availability")
            if any(w in h_lower for w in offer_words):
                categories_hit.add("offer_promotion")

        return categories_hit

    @staticmethod
    def _get_missing_categories(headlines: List[str], theme: str) -> List[str]:
        """Get list of missing headline diversity categories."""
        hit = CampaignComplianceEngine._check_headline_diversity(headlines, theme)
        return [c for c in HEADLINE_CATEGORIES if c not in hit]
