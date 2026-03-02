"""
Competitive Intelligence Engine

1) SERP Ad Scanner — capture visible ad copy, domains, extensions
2) Auction Insights — from tenant account
3) Landing Page Comparator — extract offers, CTAs, trust signals
4) Market Messaging Summary — dominant themes, overused angles, opportunity gaps
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from collections import Counter
import httpx
from bs4 import BeautifulSoup
import structlog

from app.models.serp_scan import SerpScan
from app.models.auction_insight import AuctionInsight
from app.models.competitor_profile import CompetitorProfile

logger = structlog.get_logger()


class CompetitorIntelService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def get_market_summary(self) -> Dict[str, Any]:
        serp_themes = await self._analyze_serp_themes()
        top_competitors = await self._get_top_competitors()
        messaging_heatmap = await self._build_messaging_heatmap()
        opportunity_gaps = self._find_opportunity_gaps(serp_themes, messaging_heatmap)

        return {
            "dominant_themes": serp_themes.get("dominant", []),
            "overused_angles": serp_themes.get("overused", []),
            "opportunity_gaps": opportunity_gaps,
            "top_competitors": top_competitors,
            "messaging_heatmap": messaging_heatmap,
            "differentiation_strategy": self._suggest_differentiation(serp_themes, opportunity_gaps),
        }

    async def _analyze_serp_themes(self) -> Dict[str, Any]:
        result = await self.db.execute(
            select(SerpScan)
            .where(SerpScan.tenant_id == self.tenant_id)
            .order_by(desc(SerpScan.scanned_at))
            .limit(50)
        )
        scans = result.scalars().all()

        all_headlines = []
        all_descriptions = []
        domain_count = Counter()

        for scan in scans:
            ads = scan.ads_json if isinstance(scan.ads_json, list) else []
            for ad in ads:
                headlines = ad.get("headlines", [])
                descriptions = ad.get("descriptions", [])
                domain = ad.get("domain", "")
                all_headlines.extend(headlines)
                all_descriptions.extend(descriptions)
                if domain:
                    domain_count[domain] += 1

        theme_words = Counter()
        for h in all_headlines:
            words = h.lower().split()
            for w in words:
                if len(w) > 3:
                    theme_words[w] += 1

        dominant = [w for w, c in theme_words.most_common(10)]
        overused = [w for w, c in theme_words.most_common(20) if c > len(scans) * 0.5]

        return {
            "dominant": dominant,
            "overused": overused,
            "top_domains": domain_count.most_common(10),
            "total_ads_analyzed": sum(len(s.ads_json) if isinstance(s.ads_json, list) else 0 for s in scans),
        }

    async def _get_top_competitors(self) -> List[Dict[str, Any]]:
        result = await self.db.execute(
            select(
                AuctionInsight.competitor_domain,
                func.avg(AuctionInsight.impression_share).label("avg_is"),
                func.avg(AuctionInsight.overlap_rate).label("avg_overlap"),
                func.avg(AuctionInsight.outranking_share).label("avg_outranking"),
                func.count().label("data_points"),
            )
            .where(AuctionInsight.tenant_id == self.tenant_id)
            .group_by(AuctionInsight.competitor_domain)
            .order_by(desc("avg_is"))
            .limit(10)
        )
        rows = result.all()
        return [
            {
                "domain": r.competitor_domain,
                "avg_impression_share": round(r.avg_is, 2),
                "avg_overlap_rate": round(r.avg_overlap, 2),
                "avg_outranking_share": round(r.avg_outranking, 2),
                "data_points": r.data_points,
            }
            for r in rows
        ]

    async def _build_messaging_heatmap(self) -> Dict[str, Any]:
        result = await self.db.execute(
            select(CompetitorProfile).where(CompetitorProfile.tenant_id == self.tenant_id)
        )
        profiles = result.scalars().all()

        theme_count = Counter()
        for p in profiles:
            themes = p.messaging_themes_json if isinstance(p.messaging_themes_json, list) else []
            for t in themes:
                theme = t if isinstance(t, str) else t.get("theme", "")
                if theme:
                    theme_count[theme] += 1

        return {
            "themes": [{"theme": t, "frequency": c} for t, c in theme_count.most_common(20)],
            "total_competitors_analyzed": len(profiles),
        }

    def _find_opportunity_gaps(self, serp_themes: Dict, messaging_heatmap: Dict) -> List[str]:
        gaps = []
        overused = set(serp_themes.get("overused", []))

        potential_angles = [
            "warranty", "guarantee", "same day", "emergency",
            "financing", "veteran", "family-owned", "certified",
            "eco-friendly", "transparent pricing", "no hidden fees",
            "satisfaction guaranteed", "background checked",
        ]

        dominant = set(serp_themes.get("dominant", []))
        for angle in potential_angles:
            if angle.split()[0] not in dominant and angle not in overused:
                gaps.append(angle)

        return gaps[:8]

    def _suggest_differentiation(self, serp_themes: Dict, gaps: List[str]) -> List[str]:
        suggestions = []
        if gaps:
            suggestions.append(f"Leverage underused messaging angles: {', '.join(gaps[:3])}")

        overused = serp_themes.get("overused", [])
        if overused:
            suggestions.append(f"Avoid overused terms competitors saturate: {', '.join(overused[:3])}")

        suggestions.extend([
            "Emphasize unique trust signals (certifications, years in business, review count)",
            "Test urgency-based messaging if competitors focus on price",
            "Use specific service area names instead of generic 'near me'",
        ])

        return suggestions[:5]

    async def analyze_landing_page(self, url: str) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return {"url": url, "status": "error", "error": f"HTTP {resp.status_code}"}

            soup = BeautifulSoup(resp.text, "lxml")
            text = soup.get_text(separator=" ", strip=True)[:5000]

            return {
                "url": url,
                "title": soup.title.string.strip() if soup.title and soup.title.string else "",
                "ctas": self._extract_ctas(soup),
                "offers": self._extract_offers(text),
                "trust_signals": self._extract_trust_signals(text),
                "phone_visible": bool(self._extract_phones(text)),
                "form_present": bool(soup.find("form")),
                "word_count": len(text.split()),
            }
        except Exception as e:
            return {"url": url, "status": "error", "error": str(e)}

    def _extract_ctas(self, soup: BeautifulSoup) -> List[str]:
        ctas = []
        buttons = soup.find_all(["button", "a"], class_=lambda x: x and ("btn" in x or "button" in x or "cta" in x))
        for btn in buttons[:10]:
            text = btn.get_text(strip=True)
            if 2 < len(text) < 50:
                ctas.append(text)
        return ctas

    def _extract_offers(self, text: str) -> List[str]:
        import re
        offers = []
        patterns = [r'\$\d+\s*off', r'\d+%\s*(?:off|discount)', r'free\s+\w+', r'special\s+offer']
        for p in patterns:
            matches = re.findall(p, text.lower())
            offers.extend(matches)
        return list(set(offers))[:5]

    def _extract_trust_signals(self, text: str) -> List[str]:
        import re
        signals = []
        patterns = [r'licensed', r'insured', r'certified', r'bbb', r'guarantee', r'\d+\+?\s*years']
        for p in patterns:
            if re.search(p, text.lower()):
                signals.append(p.replace(r'\d+\+?\s*', '').replace('\\', ''))
        return signals

    def _extract_phones(self, text: str) -> List[str]:
        import re
        return re.findall(r'[\(]?\d{3}[\)]?[-.\s]?\d{3}[-.\s]?\d{4}', text)
