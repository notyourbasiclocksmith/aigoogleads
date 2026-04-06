"""
Pipeline A/B Tracker
=====================

Tracks which pipeline agent prompt variants produce better campaigns,
enabling A/B testing of the pipeline itself (not just ads).

Records variant configs (ad copy angle, keyword strategy, headline style,
description style) alongside QA scores and real-world campaign performance.
Uses an 80/20 exploit/explore split to converge on winning configs while
still testing new combinations.

No AI calls -- pure tracking and statistical analysis.
"""

import random
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

logger = structlog.get_logger()

# ---- Valid variant options (for validation & random generation) ----

VARIANT_OPTIONS = {
    "ad_copy_angle": ["urgency", "premium", "price_anchoring"],
    "keyword_strategy": ["broad_then_narrow", "narrow_focused"],
    "headline_style": ["question", "statement", "cta_first"],
    "description_style": ["problem_solution", "feature_benefit", "social_proof"],
}

MIN_RUNS_FOR_VALIDITY = 5


# ---- SQLAlchemy model ----

class PipelineABVariant(Base):
    __tablename__ = "pipeline_ab_variants"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
    )
    conversation_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), nullable=True
    )
    campaign_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    variant_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    qa_score: Mapped[float] = mapped_column(Float, nullable=False)
    real_ctr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    real_conversions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    real_roas: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    performance_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# ---- Tracker service ----

class PipelineABTracker:
    """Tracks pipeline variant performance and decides which variant to use next."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_pipeline_run(
        self,
        tenant_id: str,
        conversation_id: Optional[str],
        variant_config: Dict[str, str],
        qa_score: float,
        campaign_id: Optional[str] = None,
    ) -> PipelineABVariant:
        """Save which prompt variants were used and the resulting QA score."""
        record = PipelineABVariant(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            variant_config=variant_config,
            qa_score=qa_score,
            campaign_id=campaign_id,
        )
        self.db.add(record)
        await self.db.flush()

        logger.info(
            "pipeline_ab_run_recorded",
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            variant_config=variant_config,
            qa_score=qa_score,
        )
        return record

    async def get_winning_variants(
        self, tenant_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Return the variant config that produces the highest average QA score.

        Only considers configs with at least MIN_RUNS_FOR_VALIDITY runs.
        Returns None if no config has enough data yet.

        Response format:
            {
                "variant_config": {...},
                "avg_qa_score": float,
                "run_count": int,
                "avg_real_ctr": float | None,
                "avg_real_roas": float | None,
            }
        """
        # Group by the JSON variant_config, compute stats
        stmt = (
            select(
                PipelineABVariant.variant_config,
                func.avg(PipelineABVariant.qa_score).label("avg_qa"),
                func.count(PipelineABVariant.id).label("run_count"),
                func.avg(PipelineABVariant.real_ctr).label("avg_ctr"),
                func.avg(PipelineABVariant.real_roas).label("avg_roas"),
            )
            .where(PipelineABVariant.tenant_id == tenant_id)
            .group_by(PipelineABVariant.variant_config)
            .having(func.count(PipelineABVariant.id) >= MIN_RUNS_FOR_VALIDITY)
            .order_by(func.avg(PipelineABVariant.qa_score).desc())
            .limit(1)
        )

        result = await self.db.execute(stmt)
        row = result.first()

        if row is None:
            logger.info(
                "pipeline_ab_no_winner_yet",
                tenant_id=tenant_id,
                reason="insufficient_data",
            )
            return None

        winner = {
            "variant_config": row.variant_config,
            "avg_qa_score": float(row.avg_qa),
            "run_count": int(row.run_count),
            "avg_real_ctr": float(row.avg_ctr) if row.avg_ctr is not None else None,
            "avg_real_roas": float(row.avg_roas) if row.avg_roas is not None else None,
        }

        logger.info(
            "pipeline_ab_winner_found",
            tenant_id=tenant_id,
            avg_qa_score=winner["avg_qa_score"],
            run_count=winner["run_count"],
        )
        return winner

    async def should_use_variant(self, tenant_id: str) -> Dict[str, str]:
        """
        Decide which variant config to use for the next pipeline run.

        80% of the time: use the winning variant (exploit).
        20% of the time: use a random variant (explore).

        If no winner exists yet, always returns a random variant.
        """
        winner = await self.get_winning_variants(tenant_id)

        if winner is not None and random.random() < 0.80:
            logger.info(
                "pipeline_ab_exploit",
                tenant_id=tenant_id,
                variant_config=winner["variant_config"],
            )
            return winner["variant_config"]

        # Explore: random combination
        variant = _random_variant_config()
        logger.info(
            "pipeline_ab_explore",
            tenant_id=tenant_id,
            variant_config=variant,
        )
        return variant

    async def record_campaign_performance(
        self,
        campaign_id: str,
        metrics: Dict[str, Any],
    ) -> int:
        """
        Update real-world performance metrics for a campaign's variant record.

        Called after 7+ days of campaign data is available.
        `metrics` may contain: ctr, conversions, roas.

        Returns the number of rows updated.
        """
        stmt = (
            select(PipelineABVariant)
            .where(PipelineABVariant.campaign_id == campaign_id)
        )
        result = await self.db.execute(stmt)
        records: List[PipelineABVariant] = list(result.scalars().all())

        if not records:
            logger.warning(
                "pipeline_ab_no_records_for_campaign",
                campaign_id=campaign_id,
            )
            return 0

        now = datetime.now(timezone.utc)
        updated = 0

        for record in records:
            if "ctr" in metrics:
                record.real_ctr = float(metrics["ctr"])
            if "conversions" in metrics:
                record.real_conversions = int(metrics["conversions"])
            if "roas" in metrics:
                record.real_roas = float(metrics["roas"])
            record.performance_updated_at = now
            updated += 1

        await self.db.flush()

        logger.info(
            "pipeline_ab_performance_updated",
            campaign_id=campaign_id,
            rows_updated=updated,
            metrics_keys=list(metrics.keys()),
        )
        return updated


# ---- Helpers ----

def _random_variant_config() -> Dict[str, str]:
    """Generate a random variant config from all valid options."""
    return {
        key: random.choice(options)
        for key, options in VARIANT_OPTIONS.items()
    }
