"""
Intent Router — classifies user messages into target systems.

Uses keyword heuristics first, falls back to Claude classification if ambiguous.
Deterministic enough for production, smart enough for natural language.
"""
import re
from typing import List, Set

# Keyword maps — order matters, first match wins for strong signals
_GOOGLE_ADS_SIGNALS = {
    "google ads", "google ad", "gads", "search ads", "ppc", "keywords",
    "keyword", "search terms", "search term", "ad groups", "ad group",
    "quality score", "negative keyword", "cpc", "cpa", "roas",
    "responsive search", "rsa", "display ads", "shopping ads",
}

_META_ADS_SIGNALS = {
    "meta ads", "meta ad", "facebook ads", "facebook ad", "instagram ads",
    "instagram ad", "fb ads", "fb ad", "meta campaign", "facebook campaign",
    "instagram campaign", "adset", "ad set", "meta creative", "facebook page",
    "meta audience", "lookalike", "custom audience",
}

_GBP_SIGNALS = {
    "google business", "gbp", "reviews", "review", "google reviews",
    "local", "google profile", "business profile", "post to google",
    "gbp post", "local presence", "reply to review", "google listing",
    "business info", "google maps", "local seo", "reputation",
}

_IMAGE_SIGNALS = {
    "generate image", "create image", "make image", "ad image",
    "social image", "dalle", "stability", "flux", "image for",
    "promo image", "creative image", "photo for",
}

# Mixed / cross-channel signals
_CROSS_CHANNEL_SIGNALS = {
    "audit my marketing", "audit everything", "cross-channel",
    "all channels", "full audit", "marketing audit", "overall",
    "across all", "why are leads down", "leads down",
    "what should i do", "this week", "improve everything",
    "where am i wasting", "wasting money", "wasted spend",
}

# Action-type signals that hint at specific systems
_CAMPAIGN_CREATE_SIGNALS = {
    "create a campaign", "new campaign", "launch campaign",
    "build a campaign", "set up campaign", "start campaign",
}

_PROMO_SIGNALS = {
    "promo", "promotion", "spring promo", "seasonal", "sale",
    "offer", "discount", "special",
}


def classify_intent(message: str, mode: str = "auto") -> List[str]:
    """
    Classify which systems a user message needs.

    Returns list of system names: google_ads, meta_ads, gbp, image
    In explicit mode, returns only that system (unless message clearly needs another).
    """
    if mode != "auto":
        # Explicit mode — use that system, but add image if image generation is requested
        systems = [mode]
        lower = message.lower()
        if mode != "image" and _has_signal(lower, _IMAGE_SIGNALS):
            systems.append("image")
        return systems

    lower = message.lower()
    systems: Set[str] = set()

    # Check for cross-channel signals first
    if _has_signal(lower, _CROSS_CHANNEL_SIGNALS):
        systems.update(["google_ads", "meta_ads", "gbp"])

    # Check each system
    if _has_signal(lower, _GOOGLE_ADS_SIGNALS):
        systems.add("google_ads")
    if _has_signal(lower, _META_ADS_SIGNALS):
        systems.add("meta_ads")
    if _has_signal(lower, _GBP_SIGNALS):
        systems.add("gbp")
    if _has_signal(lower, _IMAGE_SIGNALS):
        systems.add("image")

    # Promo/campaign creation — suggest multiple if no specific system detected
    if not systems and _has_signal(lower, _PROMO_SIGNALS):
        systems.update(["google_ads", "meta_ads", "gbp", "image"])
    if not systems and _has_signal(lower, _CAMPAIGN_CREATE_SIGNALS):
        systems.update(["google_ads", "meta_ads"])

    # Generic paid media queries
    if not systems:
        paid_words = {"spend", "budget", "cost", "roi", "performance", "campaign", "campaigns", "ads", "ad"}
        if _has_signal(lower, paid_words):
            systems.update(["google_ads", "meta_ads"])

    # Generic content/social queries
    if not systems:
        content_words = {"post", "content", "social", "creative"}
        if _has_signal(lower, content_words):
            systems.update(["gbp", "image"])

    # Fallback: if still empty, use all major systems
    if not systems:
        systems.update(["google_ads", "meta_ads", "gbp"])

    return sorted(systems)


def _has_signal(text: str, signals: set) -> bool:
    """Check if any signal phrase appears in text."""
    for signal in signals:
        if signal in text:
            return True
    return False
