"""
Ahrefs-Powered Keyword Intelligence Service
=============================================

Pulls REAL search volume, CPC, keyword difficulty, and competitor paid keywords
from the Ahrefs API to feed into the campaign pipeline's Keyword Research Agent.

Instead of Claude "imagining" keywords, this service provides ground truth:
1. Seed keyword expansion with real volume/CPC data
2. Related terms and search suggestions
3. Competitor paid keyword spying
4. Volume trend analysis (seasonal keywords)

The Keyword Research Agent then uses this data to make intelligent decisions
about which keywords to bid on, what match types to use, and what to exclude.

NOTE: Ahrefs CPC values are in USD cents (integer). We convert to dollars
in the output for consistency with Google Ads reporting.
"""

import asyncio
import httpx
import structlog
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.core.config import settings

logger = structlog.get_logger()

# Ahrefs API base — v3 endpoints
AHREFS_API_BASE = "https://api.ahrefs.com/v3"

# Default timeout for Ahrefs API calls (30 seconds)
AHREFS_TIMEOUT = 30.0

# Retry config
MAX_RETRIES = 2
RETRY_BACKOFF = [1.0, 3.0]  # seconds between retries


class AhrefsKeywordService:
    """Pulls real keyword data from Ahrefs to power the campaign pipeline."""

    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or getattr(settings, "AHREFS_API_KEY", "")
        self.available = bool(self.api_token)
        # Shared client for connection pooling
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create a shared httpx client for connection pooling."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=AHREFS_TIMEOUT)
        return self._client

    async def close(self):
        """Close the shared httpx client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── PUBLIC API ──────────────────────────────────────────────

    async def enrich_keyword_research(
        self,
        services: List[str],
        locations: List[str],
        business_website: str = "",
        competitor_domains: Optional[List[str]] = None,
        country: str = "us",
    ) -> Dict[str, Any]:
        """
        Full keyword intelligence package for the campaign pipeline.

        Returns:
        {
            "seed_keywords": [...],        # Real volume/CPC for service keywords
            "expanded_keywords": [...],     # Related terms with metrics
            "search_suggestions": [...],    # Autocomplete-style suggestions
            "competitor_keywords": [...],   # What competitors bid on (paid)
            "volume_trends": {...},         # Seasonal volume data
            "summary": {                   # Quick stats for the agent
                "total_keywords_found": N,
                "avg_cpc": $X.XX,
                "avg_volume": N,
                "high_value_keywords": N,
            }
        }
        """
        if not self.available:
            logger.info("Ahrefs API key not configured — returning empty enrichment")
            return self._empty_result()

        # Normalize country to uppercase (Ahrefs requires ISO 3166-1 alpha-2)
        country = country.upper()

        results: Dict[str, Any] = {
            "seed_keywords": [],
            "expanded_keywords": [],
            "search_suggestions": [],
            "competitor_keywords": [],
            "volume_trends": {},
            "summary": {},
        }

        try:
            # Build seed queries from services + locations
            seed_queries = self._build_seed_queries(services, locations)

            # Run parallel Ahrefs calls
            tasks = [
                self._get_keyword_overview(seed_queries, country),
                self._get_matching_terms(services, country),
                self._get_search_suggestions(services, country),
            ]

            # Add competitor spying if we have domains
            if competitor_domains:
                for domain in competitor_domains[:3]:  # Max 3 competitors
                    tasks.append(self._get_competitor_keywords(domain, country))

            # Also spy on our own organic keywords for cross-pollination
            if business_website:
                tasks.append(self._get_organic_keywords(business_website, country))

            gathered = await asyncio.gather(*tasks, return_exceptions=True)

            # Unpack results
            idx = 0
            if not isinstance(gathered[idx], Exception):
                results["seed_keywords"] = gathered[idx] or []
            idx += 1

            if not isinstance(gathered[idx], Exception):
                results["expanded_keywords"] = gathered[idx] or []
            idx += 1

            if not isinstance(gathered[idx], Exception):
                results["search_suggestions"] = gathered[idx] or []
            idx += 1

            # Competitor keywords
            comp_kws = []
            if competitor_domains:
                for i in range(min(3, len(competitor_domains))):
                    if idx < len(gathered) and not isinstance(gathered[idx], Exception):
                        comp_kws.extend(gathered[idx] or [])
                    idx += 1
            results["competitor_keywords"] = comp_kws

            # Own organic keywords (for ideas)
            if business_website and idx < len(gathered):
                if not isinstance(gathered[idx], Exception):
                    organic = gathered[idx] or []
                    # Add organic keywords as potential paid targets
                    results["expanded_keywords"].extend([
                        {**kw, "source": "own_organic"} for kw in organic
                    ])

            # Build summary stats
            all_kws = (
                results["seed_keywords"]
                + results["expanded_keywords"]
                + results["search_suggestions"]
            )
            if all_kws:
                cpcs = [kw.get("cpc") or 0 for kw in all_kws if kw.get("cpc")]
                volumes = [kw.get("volume") or 0 for kw in all_kws if kw.get("volume")]
                results["summary"] = {
                    "total_keywords_found": len(all_kws),
                    "avg_cpc": round(sum(cpcs) / len(cpcs), 2) if cpcs else 0,
                    "avg_volume": round(sum(volumes) / len(volumes)) if volumes else 0,
                    "high_value_keywords": len([
                        kw for kw in all_kws
                        if (kw.get("volume") or 0) >= 50 and (kw.get("cpc") or 0) >= 0.50
                    ]),
                    "competitor_keywords_found": len(results["competitor_keywords"]),
                }

        except Exception as e:
            logger.error("Ahrefs enrichment failed", error=str(e))
        finally:
            await self.close()

        return results

    # ── AHREFS API CALLS ────────────────────────────────────────

    async def _get_keyword_overview(
        self, keywords: List[str], country: str
    ) -> List[Dict]:
        """Get search volume, CPC, difficulty for a list of keywords."""
        if not keywords:
            return []

        # Batch keywords (Ahrefs supports comma-separated)
        keyword_str = ",".join(keywords[:100])  # Max 100 per request

        data = await self._api_call(
            "/keywords-explorer/overview",
            params={
                "select": "keyword,volume,cpc,difficulty,global_volume,clicks,traffic_potential",
                "keywords": keyword_str,
                "country": country,
            },
        )

        if not data or not isinstance(data, dict) or "keywords" not in data:
            return []

        return [
            {
                "keyword": kw.get("keyword", ""),
                "volume": kw.get("volume") or 0,
                "cpc": self._cents_to_dollars(kw.get("cpc")),
                "difficulty": kw.get("difficulty") or 0,
                "global_volume": kw.get("global_volume") or 0,
                "clicks": kw.get("clicks") or 0,
                "traffic_potential": kw.get("traffic_potential") or 0,
                "source": "ahrefs_overview",
            }
            for kw in data["keywords"]
        ]

    async def _get_matching_terms(
        self, services: List[str], country: str
    ) -> List[Dict]:
        """Expand services into matching keyword terms with real metrics."""
        all_terms = []

        for service in services[:5]:  # Max 5 services
            data = await self._api_call(
                "/keywords-explorer/matching-terms",
                params={
                    "select": "keyword,volume,cpc,difficulty",
                    "keywords": service,
                    "country": country,
                    "limit": 30,
                    "order_by": "volume:desc",
                },
            )

            if data and isinstance(data, dict) and "keywords" in data:
                for kw in data["keywords"]:
                    all_terms.append({
                        "keyword": kw.get("keyword", ""),
                        "volume": kw.get("volume") or 0,
                        "cpc": self._cents_to_dollars(kw.get("cpc")),
                        "difficulty": kw.get("difficulty") or 0,
                        "parent_service": service,
                        "source": "ahrefs_matching",
                    })

        return all_terms

    async def _get_search_suggestions(
        self, services: List[str], country: str
    ) -> List[Dict]:
        """Get autocomplete-style keyword suggestions."""
        all_suggestions = []

        for service in services[:5]:
            data = await self._api_call(
                "/keywords-explorer/search-suggestions",
                params={
                    "select": "keyword,volume,cpc,difficulty",
                    "keywords": service,
                    "country": country,
                    "limit": 20,
                },
            )

            if data and isinstance(data, dict) and "keywords" in data:
                for kw in data["keywords"]:
                    all_suggestions.append({
                        "keyword": kw.get("keyword", ""),
                        "volume": kw.get("volume") or 0,
                        "cpc": self._cents_to_dollars(kw.get("cpc")),
                        "difficulty": kw.get("difficulty") or 0,
                        "parent_service": service,
                        "source": "ahrefs_suggestion",
                    })

        return all_suggestions

    async def _get_competitor_keywords(
        self, domain: str, country: str
    ) -> List[Dict]:
        """
        Spy on what organic keywords a competitor ranks for that have CPC > 0
        (meaning advertisers bid on them = commercially valuable).
        """
        data = await self._api_call(
            "/site-explorer/organic-keywords",
            params={
                "select": "keyword,volume,cpc,best_position,sum_traffic",
                "target": domain,
                "country": country,
                "mode": "subdomains",
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "limit": 50,
                "order_by": "sum_traffic:desc",
                "where": {
                    "and": [
                        {"field": "best_position", "is": ["lte", 10]},
                        {"field": "cpc", "is": ["gt", 0]},
                    ]
                },
            },
        )

        if not data or not isinstance(data, dict) or "keywords" not in data:
            return []

        competitor_kws = []
        for kw in data["keywords"]:
            competitor_kws.append({
                "keyword": kw.get("keyword", ""),
                "volume": kw.get("volume") or 0,
                "cpc": self._cents_to_dollars(kw.get("cpc")),
                "competitor_domain": domain,
                "competitor_position": kw.get("best_position") or 0,
                "competitor_traffic": kw.get("sum_traffic") or 0,
                "source": "competitor_spy",
            })

        return competitor_kws

    async def _get_organic_keywords(
        self, website: str, country: str
    ) -> List[Dict]:
        """Get our own organic keywords — good candidates for paid campaigns."""
        # Strip protocol
        domain = website.replace("https://", "").replace("http://", "").rstrip("/")

        data = await self._api_call(
            "/site-explorer/organic-keywords",
            params={
                "select": "keyword,volume,cpc,best_position,sum_traffic",
                "target": domain,
                "country": country,
                "mode": "subdomains",
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "limit": 50,
                "order_by": "sum_traffic:desc",
                "where": {
                    "and": [
                        {"field": "best_position", "is": ["gte", 4]},
                        {"field": "cpc", "is": ["gt", 0]},
                    ]
                },
            },
        )

        if not data or not isinstance(data, dict) or "keywords" not in data:
            return []

        return [
            {
                "keyword": kw.get("keyword", ""),
                "volume": kw.get("volume") or 0,
                "cpc": self._cents_to_dollars(kw.get("cpc")),
                "organic_position": kw.get("best_position") or 0,
                "organic_traffic": kw.get("sum_traffic") or 0,
                "source": "own_organic",
            }
            for kw in data["keywords"]
        ]

    # ── HTTP HELPER ─────────────────────────────────────────────

    async def _api_call(
        self, endpoint: str, params: Dict[str, Any]
    ) -> Optional[Dict]:
        """Make an authenticated call to the Ahrefs API with retry logic."""
        url = f"{AHREFS_API_BASE}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
        }

        # Handle JSON-style `where` filter — Ahrefs accepts it as a JSON string param
        if "where" in params and isinstance(params["where"], dict):
            import json
            params["where"] = json.dumps(params["where"])

        for attempt in range(MAX_RETRIES + 1):
            try:
                client = await self._get_client()
                resp = await client.get(url, params=params, headers=headers)

                if resp.status_code == 200:
                    result = resp.json()
                    if isinstance(result, dict):
                        return result
                    logger.warning("Ahrefs returned non-dict response",
                        endpoint=endpoint, type=type(result).__name__)
                    return None
                elif resp.status_code == 429:
                    # Rate limit — retry with backoff
                    if attempt < MAX_RETRIES:
                        wait = RETRY_BACKOFF[attempt] if attempt < len(RETRY_BACKOFF) else 5.0
                        logger.warning("Ahrefs rate limit hit, retrying",
                            endpoint=endpoint, attempt=attempt + 1, wait=wait)
                        await asyncio.sleep(wait)
                        continue
                    logger.warning("Ahrefs rate limit exhausted after retries", endpoint=endpoint)
                    return None
                elif resp.status_code >= 500:
                    # Server error — retry
                    if attempt < MAX_RETRIES:
                        wait = RETRY_BACKOFF[attempt] if attempt < len(RETRY_BACKOFF) else 5.0
                        logger.warning("Ahrefs server error, retrying",
                            endpoint=endpoint, status=resp.status_code, attempt=attempt + 1)
                        await asyncio.sleep(wait)
                        continue
                    logger.warning("Ahrefs server error after retries",
                        endpoint=endpoint, status=resp.status_code, body=resp.text[:200])
                    return None
                else:
                    logger.warning(
                        "Ahrefs API error",
                        endpoint=endpoint,
                        status=resp.status_code,
                        body=resp.text[:300],
                    )
                    return None

            except httpx.TimeoutException:
                if attempt < MAX_RETRIES:
                    logger.warning("Ahrefs API timeout, retrying",
                        endpoint=endpoint, attempt=attempt + 1)
                    await asyncio.sleep(RETRY_BACKOFF[attempt] if attempt < len(RETRY_BACKOFF) else 5.0)
                    continue
                logger.warning("Ahrefs API timeout after retries", endpoint=endpoint)
                return None
            except Exception as e:
                logger.error("Ahrefs API call failed", endpoint=endpoint, error=str(e))
                return None

        return None

    # ── HELPERS ──────────────────────────────────────────────────

    @staticmethod
    def _cents_to_dollars(cpc_cents: Any) -> float:
        """Convert Ahrefs CPC (in USD cents) to dollars."""
        if cpc_cents is None:
            return 0.0
        try:
            return round(float(cpc_cents) / 100, 2)
        except (TypeError, ValueError):
            return 0.0

    def _build_seed_queries(
        self, services: List[str], locations: List[str]
    ) -> List[str]:
        """Build seed keyword queries from services x locations."""
        seeds = []

        # Plain service terms
        for svc in services:
            seeds.append(svc.lower())
            seeds.append(f"{svc.lower()} near me")

        # Service + location combos
        for svc in services:
            for loc in locations[:3]:  # Top 3 locations
                seeds.append(f"{svc.lower()} in {loc.lower()}")
                seeds.append(f"{loc.lower()} {svc.lower()}")

        # Emergency variants
        for svc in services:
            seeds.append(f"emergency {svc.lower()}")
            seeds.append(f"24/7 {svc.lower()}")

        return seeds[:100]  # Cap at 100

    def _empty_result(self) -> Dict[str, Any]:
        """Return empty structure when Ahrefs is unavailable."""
        return {
            "seed_keywords": [],
            "expanded_keywords": [],
            "search_suggestions": [],
            "competitor_keywords": [],
            "volume_trends": {},
            "summary": {
                "total_keywords_found": 0,
                "avg_cpc": 0,
                "avg_volume": 0,
                "high_value_keywords": 0,
                "competitor_keywords_found": 0,
                "ahrefs_available": False,
            },
        }
