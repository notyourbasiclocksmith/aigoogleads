"""
Business Intelligence Scanner Service

Crawls website + social links, extracts structured data, builds BusinessProfile JSON.
"""
import re
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup
import structlog

logger = structlog.get_logger()


class BusinessScanner:
    PAGES_TO_CRAWL = ["", "/services", "/about", "/contact", "/locations", "/reviews"]
    SOCIAL_PLATFORMS = ["facebook", "instagram", "tiktok", "youtube", "yelp", "linkedin", "twitter"]

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "IntelliAdsBot/1.0 (+https://getintelliads.com)"},
        )

    async def scan_website(self, website_url: str) -> Dict[str, Any]:
        result = {
            "pages": [],
            "services": [],
            "locations": [],
            "phone_numbers": [],
            "offers": [],
            "trust_signals": [],
            "brand_tone": "professional",
            "description": "",
            "snippets": [],
        }

        base_url = website_url.rstrip("/")
        for path in self.PAGES_TO_CRAWL:
            url = f"{base_url}{path}"
            try:
                page_data = await self._crawl_page(url)
                if page_data:
                    result["pages"].append(page_data)
                    result["services"].extend(page_data.get("extracted_services", []))
                    result["locations"].extend(page_data.get("extracted_locations", []))
                    result["phone_numbers"].extend(page_data.get("phone_numbers", []))
                    result["offers"].extend(page_data.get("offers", []))
                    result["trust_signals"].extend(page_data.get("trust_signals", []))
                    result["snippets"].extend(page_data.get("snippets", []))
            except Exception as e:
                logger.warning("Failed to crawl page", url=url, error=str(e))

        result["services"] = list(set(result["services"]))
        result["locations"] = list(set(result["locations"]))
        result["phone_numbers"] = list(set(result["phone_numbers"]))
        result["offers"] = list(set(result["offers"]))
        result["trust_signals"] = list(set(result["trust_signals"]))

        if result["pages"]:
            result["description"] = result["pages"][0].get("meta_description", "")
            result["brand_tone"] = self._detect_brand_tone(result["pages"])

        return result

    async def _crawl_page(self, url: str) -> Optional[Dict[str, Any]]:
        try:
            resp = await self.client.get(url)
            if resp.status_code != 200:
                return None
        except Exception:
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag:
            meta_desc = meta_tag.get("content", "")

        text = soup.get_text(separator=" ", strip=True)
        text_clean = re.sub(r"\s+", " ", text)[:10000]

        return {
            "url": url,
            "title": title,
            "meta_description": meta_desc,
            "text_content": text_clean,
            "extracted_services": self._extract_services(soup, text_clean),
            "extracted_locations": self._extract_locations(text_clean),
            "phone_numbers": self._extract_phones(text_clean),
            "offers": self._extract_offers(text_clean),
            "trust_signals": self._extract_trust_signals(text_clean),
            "snippets": self._extract_snippets(soup),
        }

    def _extract_services(self, soup: BeautifulSoup, text: str) -> List[str]:
        services = []
        headings = soup.find_all(["h1", "h2", "h3", "h4"])
        for h in headings:
            heading_text = h.get_text(strip=True)
            if len(heading_text) > 5 and len(heading_text) < 80:
                if any(kw in heading_text.lower() for kw in ["service", "repair", "install", "maintenance", "emergency", "solution"]):
                    services.append(heading_text)

        lists = soup.find_all("ul")
        for ul in lists:
            parent = ul.find_parent()
            if parent:
                parent_text = parent.get_text(strip=True).lower()
                if "service" in parent_text or "offer" in parent_text:
                    for li in ul.find_all("li"):
                        li_text = li.get_text(strip=True)
                        if 3 < len(li_text) < 60:
                            services.append(li_text)

        return services[:20]

    def _extract_locations(self, text: str) -> List[str]:
        locations = []
        state_pattern = r'\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*),\s*([A-Z]{2})\b'
        matches = re.findall(state_pattern, text)
        for city, state in matches:
            locations.append(f"{city}, {state}")

        zip_pattern = r'\b(\d{5}(?:-\d{4})?)\b'
        zips = re.findall(zip_pattern, text)
        locations.extend(zips[:5])

        return locations[:15]

    def _extract_phones(self, text: str) -> List[str]:
        phone_pattern = r'[\(]?\d{3}[\)]?[-.\s]?\d{3}[-.\s]?\d{4}'
        return list(set(re.findall(phone_pattern, text)))[:5]

    def _extract_offers(self, text: str) -> List[str]:
        offers = []
        offer_patterns = [
            r'\$\d+\s*off\b',
            r'\d+%\s*(?:off|discount)',
            r'free\s+(?:estimate|consultation|inspection|quote)',
            r'(?:financing|payment\s+plan)\s+available',
            r'(?:warranty|guarantee)\s+(?:included|available)',
            r'senior\s+(?:discount|citizen)',
            r'military\s+discount',
            r'coupon',
            r'special\s+offer',
        ]
        for pattern in offer_patterns:
            matches = re.findall(pattern, text.lower())
            offers.extend(matches)

        return list(set(offers))[:10]

    def _extract_trust_signals(self, text: str) -> List[str]:
        signals = []
        trust_patterns = [
            r'licensed\s*(?:&|and)\s*insured',
            r'bbb\s*(?:accredited|a\+|rated)',
            r'(?:\d+)\+?\s*years?\s*(?:of\s+)?experience',
            r'(?:\d+)\+?\s*(?:5[\-\s]?star|positive)\s*reviews?',
            r'satisfaction\s+guarantee',
            r'money[\-\s]back\s+guarantee',
            r'background[\-\s]checked',
            r'bonded\s*(?:&|and)\s*insured',
            r'certified',
            r'award[\-\s]winning',
            r'family[\-\s]owned',
            r'locally\s+owned',
        ]
        for pattern in trust_patterns:
            matches = re.findall(pattern, text.lower())
            signals.extend(matches)

        return list(set(signals))[:10]

    def _extract_snippets(self, soup: BeautifulSoup) -> List[str]:
        snippets = []
        for tag in soup.find_all(["h1", "h2", "h3"]):
            text = tag.get_text(strip=True)
            if 10 < len(text) < 100:
                snippets.append(text)

        for tag in soup.find_all("p"):
            text = tag.get_text(strip=True)
            if 30 < len(text) < 300:
                snippets.append(text)
                if len(snippets) >= 20:
                    break

        return snippets[:20]

    def _detect_brand_tone(self, pages: List[Dict]) -> str:
        all_text = " ".join(p.get("text_content", "") for p in pages).lower()

        urgent_words = ["emergency", "urgent", "24/7", "immediate", "fast", "quick", "asap"]
        premium_words = ["luxury", "premium", "exclusive", "finest", "elite", "superior"]
        budget_words = ["affordable", "cheap", "low cost", "budget", "discount", "save"]

        urgent_score = sum(1 for w in urgent_words if w in all_text)
        premium_score = sum(1 for w in premium_words if w in all_text)
        budget_score = sum(1 for w in budget_words if w in all_text)

        if urgent_score > premium_score and urgent_score > budget_score:
            return "urgent"
        if premium_score > urgent_score and premium_score > budget_score:
            return "premium"
        if budget_score > urgent_score and budget_score > premium_score:
            return "budget"
        return "professional"

    async def scan_social(self, platform: str, url: str) -> Dict[str, Any]:
        try:
            resp = await self.client.get(url)
            if resp.status_code != 200:
                return {"platform": platform, "url": url, "bio": "", "posts": []}
            soup = BeautifulSoup(resp.text, "lxml")
            text = soup.get_text(separator=" ", strip=True)[:3000]
            return {
                "platform": platform,
                "url": url,
                "bio": text[:500],
                "posts": [],
            }
        except Exception as e:
            logger.warning("Failed to scan social", platform=platform, error=str(e))
            return {"platform": platform, "url": url, "bio": "", "posts": []}

    async def close(self):
        await self.client.aclose()
