"""
Module 5 — Policy Compliance & Claims Safety Engine
Scans ad text against configurable rules to prevent policy violations.
"""
import re
import uuid
from typing import List, Dict, Any
from datetime import datetime, timezone
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.v2.policy_rule import PolicyRule
from app.models.v2.tenant_policy_override import TenantPolicyOverride
from app.models.v2.policy_scan_result import PolicyScanResult

logger = structlog.get_logger()

# ── Default global rules seeded on first scan if table empty ──
DEFAULT_RULES: List[Dict[str, str]] = [
    # Prohibited content
    {"category": "prohibited", "pattern": r"\b(weapons?|firearms?|guns?|ammunition)\b", "severity": "error", "description": "Weapons-related content is prohibited"},
    {"category": "prohibited", "pattern": r"\b(drugs?|narcotics?|cocaine|heroin|meth)\b", "severity": "error", "description": "Drug-related content is prohibited"},
    {"category": "prohibited", "pattern": r"\b(adult|xxx|porn|escort)\b", "severity": "error", "description": "Adult content is prohibited"},
    # Misleading claims
    {"category": "misleading", "pattern": r"\bguaranteed?\b", "severity": "warning", "description": "Guarantee claims require substantiation"},
    {"category": "misleading", "pattern": r"\b#1\b|number one|best in", "severity": "warning", "description": "Superlative/ranking claims need proof"},
    {"category": "misleading", "pattern": r"\bfree\b(?!.*terms)", "severity": "warning", "description": "Free offers must include terms/conditions"},
    {"category": "misleading", "pattern": r"\b(lowest price|cheapest)\b", "severity": "warning", "description": "Price comparison claims need substantiation"},
    {"category": "misleading", "pattern": r"\b(instant|immediate) results?\b", "severity": "warning", "description": "Instant results claims may be misleading"},
    # Trademark-sensitive (configurable per tenant)
    {"category": "trademark", "pattern": r"", "severity": "info", "description": "Placeholder — tenant configures competitor names"},
    # Strict mode rules
    {"category": "strict_superlative", "pattern": r"\b(best|greatest|finest|top-rated|premier|leading|unmatched|unbeatable)\b", "severity": "warning", "description": "Superlative term detected (strict mode)"},
    {"category": "strict_price", "pattern": r"\$\d+|\d+%\s*off|save \$", "severity": "warning", "description": "Price claim detected — verify landing page support (strict mode)"},
]


async def _ensure_global_rules(db: AsyncSession):
    result = await db.execute(select(PolicyRule).where(PolicyRule.is_global == True).limit(1))
    if result.scalars().first():
        return
    for rule_def in DEFAULT_RULES:
        if not rule_def["pattern"]:
            continue
        rule = PolicyRule(
            id=str(uuid.uuid4()),
            category=rule_def["category"],
            pattern=rule_def["pattern"],
            severity=rule_def["severity"],
            description=rule_def["description"],
            is_global=True,
            enabled=True,
        )
        db.add(rule)


async def get_active_rules(db: AsyncSession, tenant_id: str, strict_mode: bool = False) -> List[PolicyRule]:
    """Get all applicable rules for a tenant, applying overrides."""
    await _ensure_global_rules(db)

    stmt = select(PolicyRule).where(PolicyRule.enabled == True)
    if not strict_mode:
        stmt = stmt.where(~PolicyRule.category.in_(["strict_superlative", "strict_price"]))
    result = await db.execute(stmt)
    rules = list(result.scalars().all())

    # Apply tenant overrides
    override_stmt = select(TenantPolicyOverride).where(TenantPolicyOverride.tenant_id == tenant_id)
    override_result = await db.execute(override_stmt)
    overrides = {o.rule_id: o.enabled for o in override_result.scalars().all()}

    return [r for r in rules if overrides.get(r.id, r.enabled)]


def scan_text(text: str, rules: List[PolicyRule]) -> List[Dict[str, Any]]:
    """Scan a single text string against all rules. Returns list of violations."""
    warnings = []
    for rule in rules:
        if not rule.pattern:
            continue
        try:
            matches = re.findall(rule.pattern, text, re.IGNORECASE)
            if matches:
                warnings.append({
                    "rule_id": rule.id,
                    "category": rule.category,
                    "severity": rule.severity,
                    "description": rule.description,
                    "matched": matches[:5],
                })
        except re.error:
            logger.warning("Invalid regex pattern in policy rule", rule_id=rule.id, pattern=rule.pattern)
    return warnings


async def scan_ad_content(
    db: AsyncSession,
    tenant_id: str,
    entity_type: str,
    entity_ref: str,
    texts: List[str],
    strict_mode: bool = False,
) -> PolicyScanResult:
    """Scan ad content (headlines, descriptions, etc.) and store result."""
    rules = await get_active_rules(db, tenant_id, strict_mode)
    all_warnings = []
    for text in texts:
        all_warnings.extend(scan_text(text, rules))

    passed = not any(w["severity"] == "error" for w in all_warnings)

    result = PolicyScanResult(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_ref=entity_ref,
        warnings_json=all_warnings,
        passed=passed,
    )
    db.add(result)
    return result


async def scan_campaign_draft(
    db: AsyncSession,
    tenant_id: str,
    campaign_data: dict,
    strict_mode: bool = False,
) -> List[Dict[str, Any]]:
    """Scan an entire campaign draft, returning all warnings grouped by element."""
    results = []
    campaign_name = campaign_data.get("name", "draft")

    for ag in campaign_data.get("ad_groups", []):
        for ad in ag.get("ads", []):
            texts = ad.get("headlines", []) + ad.get("descriptions", [])
            scan_result = await scan_ad_content(
                db, tenant_id,
                entity_type="ad",
                entity_ref=f"{campaign_name}/{ag.get('name', 'group')}/{ad.get('type', 'rsa')}",
                texts=texts,
                strict_mode=strict_mode,
            )
            if scan_result.warnings_json:
                results.append({
                    "entity_ref": scan_result.entity_ref,
                    "passed": scan_result.passed,
                    "warnings": scan_result.warnings_json,
                })
    return results
