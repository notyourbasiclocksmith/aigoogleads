from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Optional, List

from app.core.database import get_db
from app.core.deps import require_tenant, CurrentUser
from app.models.serp_scan import SerpScan
from app.models.auction_insight import AuctionInsight
from app.models.competitor_profile import CompetitorProfile

router = APIRouter()


class SerpScanRequest(BaseModel):
    keywords: List[str]
    geo: Optional[str] = None
    device: str = "desktop"


@router.get("/serp-results")
async def get_serp_results(
    keyword: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    query = select(SerpScan).where(SerpScan.tenant_id == user.tenant_id)
    if keyword:
        query = query.where(SerpScan.keyword.ilike(f"%{keyword}%"))
    query = query.order_by(desc(SerpScan.scanned_at)).limit(limit)

    result = await db.execute(query)
    scans = result.scalars().all()
    return [
        {
            "id": s.id,
            "keyword": s.keyword,
            "geo": s.geo,
            "device": s.device,
            "scanned_at": s.scanned_at.isoformat() if s.scanned_at else None,
            "ads": s.ads_json,
            "organic_results": s.results_json,
        }
        for s in scans
    ]


@router.post("/serp-scan")
async def trigger_serp_scan(
    req: SerpScanRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    from app.jobs.tasks import run_serp_scan_task
    run_serp_scan_task.delay(user.tenant_id, req.keywords, req.geo, req.device)
    return {"status": "scan_queued", "keywords": len(req.keywords)}


@router.get("/auction-insights")
async def get_auction_insights(
    campaign_id: Optional[str] = None,
    days: int = Query(30, ge=7, le=90),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date, timedelta
    start_date = date.today() - timedelta(days=days)

    query = select(AuctionInsight).where(
        AuctionInsight.tenant_id == user.tenant_id,
        AuctionInsight.date >= start_date,
    )
    if campaign_id:
        query = query.where(AuctionInsight.campaign_id == campaign_id)
    query = query.order_by(desc(AuctionInsight.date)).limit(200)

    result = await db.execute(query)
    insights = result.scalars().all()

    # Aggregate by competitor
    competitors = {}
    for i in insights:
        if i.competitor_domain not in competitors:
            competitors[i.competitor_domain] = {
                "domain": i.competitor_domain,
                "avg_impression_share": 0,
                "avg_overlap_rate": 0,
                "avg_outranking_share": 0,
                "avg_top_of_page_rate": 0,
                "data_points": 0,
            }
        c = competitors[i.competitor_domain]
        c["avg_impression_share"] += i.impression_share
        c["avg_overlap_rate"] += i.overlap_rate
        c["avg_outranking_share"] += i.outranking_share
        c["avg_top_of_page_rate"] += i.top_of_page_rate
        c["data_points"] += 1

    for c in competitors.values():
        n = c["data_points"]
        c["avg_impression_share"] = round(c["avg_impression_share"] / n, 2)
        c["avg_overlap_rate"] = round(c["avg_overlap_rate"] / n, 2)
        c["avg_outranking_share"] = round(c["avg_outranking_share"] / n, 2)
        c["avg_top_of_page_rate"] = round(c["avg_top_of_page_rate"] / n, 2)

    return list(competitors.values())


@router.get("/profiles")
async def get_competitor_profiles(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CompetitorProfile).where(CompetitorProfile.tenant_id == user.tenant_id)
        .order_by(desc(CompetitorProfile.last_updated_at))
    )
    profiles = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "domain": p.domain,
            "landing_pages": p.landing_pages_json,
            "messaging_themes": p.messaging_themes_json,
            "last_updated": p.last_updated_at.isoformat() if p.last_updated_at else None,
        }
        for p in profiles
    ]


@router.get("/market-summary")
async def get_market_summary(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    from app.services.competitor_intel_service import CompetitorIntelService
    svc = CompetitorIntelService(db, user.tenant_id)
    summary = await svc.get_market_summary()
    return summary
