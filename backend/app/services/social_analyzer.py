"""
Social Media & Business Analysis Service

Crawls website + all social profiles, sends collected data to OpenAI for
structured business intelligence analysis. Produces a comprehensive report
that enriches the BusinessProfile with actionable insights for Google Ads.
"""
import json
import re
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
import structlog

from app.core.config import settings

logger = structlog.get_logger()

ANALYSIS_PROMPT = """You are a senior digital marketing strategist analyzing a local service business.
You have been given crawled data from a business's website and social media profiles.
Analyze everything and produce a structured JSON report.

BUSINESS INFO PROVIDED:
- Business Name: {business_name}
- Industry: {industry}
- Phone: {phone}
- Website URL: {website_url}

WEBSITE CONTENT:
{website_content}

SOCIAL MEDIA PROFILES:
{social_content}

Produce a JSON object with EXACTLY these keys (no markdown, no code fences, just raw JSON):
{{
  "business_summary": "2-3 sentence summary of what this business does, their market position, and key differentiators",
  "services": ["list of specific services they offer"],
  "service_areas": ["list of cities/areas they serve"],
  "unique_selling_points": ["list of USPs and differentiators"],
  "brand_voice": {{
    "tone": "one of: professional, friendly, urgent, premium, budget, casual",
    "personality_traits": ["3-5 adjective traits"],
    "sample_phrases": ["3-5 phrases that match their voice for ad copy"]
  }},
  "target_audience": {{
    "primary": "description of primary customer",
    "demographics": "age range, income level, etc",
    "pain_points": ["list of customer pain points this business solves"],
    "buying_triggers": ["what makes customers call/buy NOW"]
  }},
  "trust_signals": ["list of trust signals found: licenses, reviews, years in business, etc"],
  "offers_and_promotions": ["current offers, discounts, financing, guarantees found"],
  "social_media_assessment": {{
    "overall_grade": "A/B/C/D/F",
    "platforms_active": ["list of platforms with activity"],
    "strengths": ["what they do well on social"],
    "weaknesses": ["what they could improve"],
    "content_themes": ["recurring topics/themes in their content"],
    "posting_frequency": "estimated posting frequency",
    "engagement_level": "high/medium/low/unknown"
  }},
  "competitor_keywords": ["10-20 keywords competitors would target for this business type and location"],
  "google_ads_recommendations": {{
    "campaign_types": ["recommended campaign types: Search, Local, Display, etc"],
    "headline_suggestions": ["5-8 compelling headline ideas based on their brand"],
    "description_suggestions": ["3-5 ad description ideas"],
    "negative_keywords": ["keywords to exclude"],
    "landing_page_suggestions": ["which pages to use as landing pages and why"],
    "budget_recommendation": "suggested daily budget range with reasoning",
    "bidding_strategy": "recommended bidding strategy with reasoning"
  }},
  "website_assessment": {{
    "overall_grade": "A/B/C/D/F",
    "strengths": ["what the website does well"],
    "weaknesses": ["what needs improvement for ads"],
    "mobile_readiness": "good/fair/poor/unknown",
    "conversion_elements": ["CTAs, forms, phone numbers found"],
    "missing_elements": ["what's missing that would help conversions"]
  }}
}}

Be specific and actionable. Use the actual business name, services, and locations in your suggestions.
If data is missing or unclear, make reasonable inferences based on the industry and available info.
Return ONLY valid JSON, no other text."""


class SocialAnalyzer:
    """Crawls business web presence and runs AI analysis."""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; IntelliAdsBot/2.0; +https://getintelliads.com)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )

    async def analyze(
        self,
        business_name: str,
        industry: str,
        phone: str,
        website_url: Optional[str],
        social_profiles: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """
        Full analysis pipeline:
        1. Crawl website pages
        2. Crawl each social profile
        3. Send everything to OpenAI for analysis
        4. Return structured results
        """
        logger.info("Starting business analysis", business=business_name)

        # Step 1: Crawl website
        website_data = []
        if website_url:
            website_data = await self._crawl_website(website_url)

        # Step 2: Crawl social profiles
        social_data = []
        for profile in social_profiles:
            platform = profile.get("platform", "unknown")
            url = profile.get("url", "")
            if url:
                data = await self._crawl_social(platform, url)
                if data:
                    social_data.append(data)

        # Step 3: AI Analysis
        analysis = await self._run_ai_analysis(
            business_name=business_name,
            industry=industry,
            phone=phone or "",
            website_url=website_url or "",
            website_data=website_data,
            social_data=social_data,
        )

        # Attach raw crawled data for storage
        analysis["_crawled"] = {
            "website_pages": len(website_data),
            "social_profiles_crawled": len(social_data),
            "website_data": website_data,
            "social_data": social_data,
        }

        logger.info(
            "Business analysis complete",
            business=business_name,
            pages_crawled=len(website_data),
            socials_crawled=len(social_data),
        )
        return analysis

    async def _crawl_website(self, website_url: str) -> List[Dict[str, Any]]:
        """Crawl main pages of a website."""
        pages = []
        base = website_url.rstrip("/")
        paths = [
            "", "/services", "/about", "/about-us", "/contact",
            "/locations", "/reviews", "/testimonials", "/pricing",
        ]

        for path in paths:
            url = f"{base}{path}"
            page = await self._fetch_page(url)
            if page:
                pages.append(page)

        # Also discover and crawl linked service pages from nav
        if pages:
            nav_links = self._extract_nav_links(pages[0].get("html", ""), base)
            for link in nav_links[:5]:
                if not any(p["url"] == link for p in pages):
                    page = await self._fetch_page(link)
                    if page:
                        pages.append(page)

        return pages

    async def _fetch_page(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch and parse a single web page."""
        try:
            resp = await self.client.get(url)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "lxml")

            # Remove noise
            for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else ""
            meta_desc = ""
            meta_tag = soup.find("meta", attrs={"name": "description"})
            if meta_tag:
                meta_desc = meta_tag.get("content", "")

            # Extract meaningful text
            body = soup.find("body")
            text = body.get_text(separator="\n", strip=True) if body else ""
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = text[:8000]

            # Extract headings
            headings = []
            for h in soup.find_all(["h1", "h2", "h3"]):
                ht = h.get_text(strip=True)
                if 3 < len(ht) < 150:
                    headings.append(ht)

            # Extract phone numbers
            phones = list(set(re.findall(r'[\(]?\d{3}[\)]?[-.\s]?\d{3}[-.\s]?\d{4}', text)))

            return {
                "url": url,
                "title": title,
                "meta_description": meta_desc,
                "text": text,
                "headings": headings[:20],
                "phones": phones[:5],
                "html": resp.text[:50000],
            }
        except Exception as e:
            logger.debug("Failed to fetch page", url=url, error=str(e))
            return None

    def _extract_nav_links(self, html: str, base_url: str) -> List[str]:
        """Extract service/about links from navigation."""
        soup = BeautifulSoup(html, "lxml")
        links = []
        domain = urlparse(base_url).netloc

        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True).lower()

            # Only internal links with relevant text
            if any(kw in text for kw in ["service", "about", "area", "location", "review", "pricing", "testimonial"]):
                if href.startswith("/"):
                    links.append(f"{base_url}{href}")
                elif domain in href:
                    links.append(href)

        return list(set(links))[:10]

    async def _crawl_social(self, platform: str, url: str) -> Optional[Dict[str, Any]]:
        """Crawl a social media profile page for public info."""
        try:
            resp = await self.client.get(url)
            if resp.status_code != 200:
                return {"platform": platform, "url": url, "content": f"[Could not access - HTTP {resp.status_code}]"}

            soup = BeautifulSoup(resp.text, "lxml")

            # Remove noise
            for tag in soup.find_all(["script", "style"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else ""

            # Get meta description (often has bio info)
            meta_desc = ""
            for meta in soup.find_all("meta"):
                prop = meta.get("property", "") or meta.get("name", "")
                if prop in ("og:description", "description", "twitter:description"):
                    meta_desc = meta.get("content", "")
                    if meta_desc:
                        break

            # Get page text (limited)
            text = soup.get_text(separator="\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text)[:4000]

            return {
                "platform": platform,
                "url": url,
                "title": title,
                "meta_description": meta_desc,
                "content": text,
            }
        except Exception as e:
            logger.debug("Failed to crawl social", platform=platform, error=str(e))
            return {"platform": platform, "url": url, "content": "[Could not access]"}

    async def _run_ai_analysis(
        self,
        business_name: str,
        industry: str,
        phone: str,
        website_url: str,
        website_data: List[Dict],
        social_data: List[Dict],
    ) -> Dict[str, Any]:
        """Send crawled data to OpenAI for structured analysis."""
        if not settings.OPENAI_API_KEY:
            logger.warning("No OpenAI API key configured, returning basic analysis")
            return self._basic_analysis(business_name, industry, website_data, social_data)

        # Build website content summary for prompt
        website_sections = []
        for page in website_data:
            section = f"--- PAGE: {page['url']} ---\nTitle: {page['title']}\nDescription: {page.get('meta_description', '')}\nHeadings: {', '.join(page.get('headings', []))}\nContent:\n{page.get('text', '')[:3000]}"
            website_sections.append(section)
        website_content = "\n\n".join(website_sections) if website_sections else "[No website data available]"

        # Build social content summary
        social_sections = []
        for profile in social_data:
            section = f"--- {profile['platform'].upper()} ({profile['url']}) ---\nTitle: {profile.get('title', '')}\nBio/Description: {profile.get('meta_description', '')}\nContent:\n{profile.get('content', '')[:2000]}"
            social_sections.append(section)
        social_content = "\n\n".join(social_sections) if social_sections else "[No social media data available]"

        # Truncate to fit token limits
        website_content = website_content[:12000]
        social_content = social_content[:8000]

        prompt = ANALYSIS_PROMPT.format(
            business_name=business_name,
            industry=industry,
            phone=phone,
            website_url=website_url,
            website_content=website_content,
            social_content=social_content,
        )

        try:
            import openai
            client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a digital marketing analyst. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=4000,
            )

            content = response.choices[0].message.content.strip()
            # Strip markdown code fences if present
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)

            analysis = json.loads(content)
            analysis["_ai_model"] = settings.OPENAI_MODEL
            analysis["_ai_status"] = "complete"
            return analysis

        except json.JSONDecodeError as e:
            logger.error("Failed to parse AI response as JSON", error=str(e))
            return {**self._basic_analysis(business_name, industry, website_data, social_data), "_ai_status": "parse_error"}
        except Exception as e:
            logger.error("AI analysis failed", error=str(e))
            return {**self._basic_analysis(business_name, industry, website_data, social_data), "_ai_status": "error", "_ai_error": str(e)}

    def _basic_analysis(
        self,
        business_name: str,
        industry: str,
        website_data: List[Dict],
        social_data: List[Dict],
    ) -> Dict[str, Any]:
        """Fallback analysis without AI — uses regex extraction."""
        all_text = " ".join(p.get("text", "") for p in website_data)
        headings = []
        phones = []
        for p in website_data:
            headings.extend(p.get("headings", []))
            phones.extend(p.get("phones", []))

        return {
            "business_summary": f"{business_name} is a {industry} business.",
            "services": headings[:10],
            "service_areas": list(set(re.findall(r'\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*),\s*([A-Z]{2})\b', all_text)))[:10],
            "unique_selling_points": [],
            "brand_voice": {"tone": "professional", "personality_traits": [], "sample_phrases": []},
            "target_audience": {"primary": "", "demographics": "", "pain_points": [], "buying_triggers": []},
            "trust_signals": [],
            "offers_and_promotions": [],
            "social_media_assessment": {
                "overall_grade": "N/A",
                "platforms_active": [s["platform"] for s in social_data],
                "strengths": [],
                "weaknesses": ["AI analysis unavailable — set OPENAI_API_KEY for full insights"],
                "content_themes": [],
                "posting_frequency": "unknown",
                "engagement_level": "unknown",
            },
            "competitor_keywords": [],
            "google_ads_recommendations": {
                "campaign_types": ["Search"],
                "headline_suggestions": [],
                "description_suggestions": [],
                "negative_keywords": [],
                "landing_page_suggestions": [],
                "budget_recommendation": "",
                "bidding_strategy": "",
            },
            "website_assessment": {
                "overall_grade": "N/A",
                "strengths": [],
                "weaknesses": [],
                "mobile_readiness": "unknown",
                "conversion_elements": phones[:3],
                "missing_elements": [],
            },
            "_ai_status": "skipped",
        }

    async def close(self):
        await self.client.aclose()
