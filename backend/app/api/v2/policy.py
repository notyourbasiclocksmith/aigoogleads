"""Module 5 — Policy Compliance API Routes"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.v2.policy_rule import PolicyRule
from app.models.v2.policy_scan_result import PolicyScanResult
from app.services.v2.policy_engine import scan_ad_content, scan_campaign_draft, get_active_rules

router = APIRouter()


class ScanTextRequest(BaseModel):
    tenant_id: str
    texts: List[str]
    entity_type: str = "ad"
    entity_ref: str = "manual_scan"
    strict_mode: bool = False


class ScanCampaignRequest(BaseModel):
    tenant_id: str
    campaign_data: dict
    strict_mode: bool = False


@router.post("/scan")
async def scan_text_endpoint(req: ScanTextRequest, db: AsyncSession = Depends(get_db)):
    result = await scan_ad_content(
        db, req.tenant_id, req.entity_type, req.entity_ref, req.texts, req.strict_mode
    )
    return {
        "passed": result.passed,
        "warnings": result.warnings_json,
        "entity_ref": result.entity_ref,
    }


@router.post("/scan-campaign")
async def scan_campaign_endpoint(req: ScanCampaignRequest, db: AsyncSession = Depends(get_db)):
    results = await scan_campaign_draft(db, req.tenant_id, req.campaign_data, req.strict_mode)
    all_passed = all(r["passed"] for r in results) if results else True
    return {"passed": all_passed, "results": results}


@router.get("/rules")
async def list_rules(tenant_id: Optional[str] = None, strict_mode: bool = False, db: AsyncSession = Depends(get_db)):
    if tenant_id:
        rules = await get_active_rules(db, tenant_id, strict_mode)
    else:
        stmt = select(PolicyRule).where(PolicyRule.is_global == True)
        result = await db.execute(stmt)
        rules = list(result.scalars().all())
    return [
        {
            "id": r.id, "category": r.category, "pattern": r.pattern,
            "severity": r.severity, "description": r.description, "enabled": r.enabled,
        }
        for r in rules
    ]


@router.get("/scan-history")
async def scan_history(tenant_id: str, limit: int = 20, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(PolicyScanResult)
        .where(PolicyScanResult.tenant_id == tenant_id)
        .order_by(PolicyScanResult.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    scans = result.scalars().all()
    return [
        {
            "id": s.id, "entity_type": s.entity_type, "entity_ref": s.entity_ref,
            "passed": s.passed, "warnings": s.warnings_json,
            "created_at": s.created_at.isoformat(),
        }
        for s in scans
    ]
