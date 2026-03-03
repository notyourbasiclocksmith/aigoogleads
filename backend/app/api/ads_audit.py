from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import List

from app.core.database import get_db
from app.core.deps import require_tenant, CurrentUser
from app.models.campaign import Campaign
from app.models.ad_group import AdGroup
from app.models.keyword import Keyword
from app.models.conversion import Conversion
from app.models.integration_google_ads import IntegrationGoogleAds

router = APIRouter()


@router.post("/run")
async def run_audit(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    return await _perform_audit(user, db)


@router.get("")
async def get_audit(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    return await _perform_audit(user, db)


async def _perform_audit(user: CurrentUser, db: AsyncSession):
    issues = []

    # Check account connections
    accts = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.tenant_id == user.tenant_id,
            IntegrationGoogleAds.is_active == True,
        )
    )
    accounts = accts.scalars().all()
    if not accounts:
        issues.append({
            "severity": "critical",
            "category": "setup",
            "title": "No Google Ads accounts connected",
            "description": "Connect at least one Google Ads account to begin.",
            "fix": "Go to Settings > Integrations to connect your account.",
        })
        return {"health_score": 0, "issues": issues, "structure": {}}

    # Count entities
    campaign_count = await db.execute(
        select(func.count()).select_from(Campaign).where(Campaign.tenant_id == user.tenant_id)
    )
    total_campaigns = campaign_count.scalar() or 0

    ad_group_count = await db.execute(
        select(func.count()).select_from(AdGroup).where(AdGroup.tenant_id == user.tenant_id)
    )
    total_ad_groups = ad_group_count.scalar() or 0

    keyword_count = await db.execute(
        select(func.count()).select_from(Keyword).where(Keyword.tenant_id == user.tenant_id)
    )
    total_keywords = keyword_count.scalar() or 0

    # Check conversions
    conv_result = await db.execute(
        select(Conversion).where(
            Conversion.tenant_id == user.tenant_id,
            Conversion.is_primary == True,
        )
    )
    primary_conversions = conv_result.scalars().all()
    if not primary_conversions:
        issues.append({
            "severity": "high",
            "category": "tracking",
            "title": "No primary conversion actions found",
            "description": "Without conversion tracking, optimization is severely limited.",
            "fix": "Set up conversion actions in your Google Ads account.",
        })

    # Check for broad match without negatives
    broad_kws = await db.execute(
        select(func.count()).select_from(Keyword).where(
            and_(Keyword.tenant_id == user.tenant_id, Keyword.match_type == "BROAD")
        )
    )
    broad_count = broad_kws.scalar() or 0
    if broad_count > 0 and total_keywords > 0 and (broad_count / total_keywords) > 0.5:
        issues.append({
            "severity": "medium",
            "category": "structure",
            "title": "Heavy reliance on broad match keywords",
            "description": f"{broad_count} of {total_keywords} keywords use broad match, which can lead to wasted spend.",
            "fix": "Consider tightening match types or adding comprehensive negative keywords.",
        })

    # Check quality scores
    low_qs = await db.execute(
        select(func.count()).select_from(Keyword).where(
            and_(
                Keyword.tenant_id == user.tenant_id,
                Keyword.quality_score.isnot(None),
                Keyword.quality_score < 5,
            )
        )
    )
    low_qs_count = low_qs.scalar() or 0
    if low_qs_count > 5:
        issues.append({
            "severity": "medium",
            "category": "quality",
            "title": f"{low_qs_count} keywords with low Quality Score (<5)",
            "description": "Low Quality Scores increase CPC and reduce ad position.",
            "fix": "Improve ad relevance and landing page experience for these keywords.",
        })

    # Calculate health score
    critical = sum(1 for i in issues if i["severity"] == "critical")
    high = sum(1 for i in issues if i["severity"] == "high")
    medium = sum(1 for i in issues if i["severity"] == "medium")
    health_score = max(0, 100 - (critical * 30) - (high * 15) - (medium * 5))

    return {
        "health_score": health_score,
        "issues": issues,
        "structure": {
            "accounts": len(accounts),
            "campaigns": total_campaigns,
            "ad_groups": total_ad_groups,
            "keywords": total_keywords,
            "primary_conversions": len(primary_conversions),
        },
    }
