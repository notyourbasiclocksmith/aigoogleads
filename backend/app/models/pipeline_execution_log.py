"""
Pipeline Execution Log — records every pipeline, auto-scaler, and A/B test run
for developer/analyst review.

Tracks:
- What service ran (campaign_pipeline, budget_scaler, ab_generator, audit)
- Full input context + output results
- Per-agent timing within multi-agent pipelines
- Ahrefs data used (if any)
- Campaign association for filtering
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Float, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


def _uuid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


class PipelineExecutionLog(Base):
    __tablename__ = "pipeline_execution_logs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(String(20), nullable=True)
    campaign_id = Column(String(30), nullable=True, index=True)
    conversation_id = Column(UUID(as_uuid=False), nullable=True, index=True)

    # What ran
    service_type = Column(String(50), nullable=False, index=True)
    # campaign_pipeline | budget_scaler | ab_generator | post_audit | ahrefs_enrichment | feedback_eval

    # Status
    status = Column(String(20), nullable=False, default="running")
    # running | completed | failed | partial

    # Timing
    started_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Input context (what was fed into the service)
    input_summary = Column(JSONB, nullable=True)
    # e.g., {"user_prompt": "...", "services": [...], "locations": [...]}

    # Per-agent breakdown (for multi-agent pipeline)
    agent_results = Column(JSONB, nullable=True)
    # e.g., [{"agent": "Strategist", "duration_ms": 2300, "tokens_used": 1500, "status": "done"},
    #         {"agent": "Keyword Research", "duration_ms": 4100, "tokens_used": 3800, "status": "done"}, ...]

    # Ahrefs data used
    ahrefs_data = Column(JSONB, nullable=True)
    # e.g., {"keywords_found": 120, "avg_cpc": 5.40, "competitor_keywords": 45, "api_calls": 6}

    # Output result
    output_summary = Column(JSONB, nullable=True)
    # e.g., {"ad_groups": 4, "total_keywords": 85, "qa_score": 92, "budget_daily": 75}

    # Full output (for deep analysis — can be large)
    output_full = Column(JSONB, nullable=True)

    # Error info
    error_message = Column(Text, nullable=True)

    # Metadata
    model_used = Column(String(50), nullable=True)  # claude-opus-4-6, etc.
    total_tokens = Column(Integer, nullable=True)
    total_cost_cents = Column(Integer, nullable=True)  # Estimated API cost in cents

    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
