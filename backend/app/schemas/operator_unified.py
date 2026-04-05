"""
Unified Operator Schemas — shared request/response models for all channels.
"""
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from enum import Enum


class OperatorMode(str, Enum):
    auto = "auto"
    google_ads = "google_ads"
    meta_ads = "meta_ads"
    gbp = "gbp"
    image = "image"


class SystemName(str, Enum):
    google_ads = "google_ads"
    meta_ads = "meta_ads"
    gbp = "gbp"
    image = "image"


# ── Requests ───────────────────────────────────────────────

class UnifiedChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=5000)
    mode: OperatorMode = OperatorMode.auto
    customer_id: Optional[str] = None  # Google Ads customer ID if explicit
    date_range: str = "LAST_30_DAYS"


class UnifiedNewConversationRequest(BaseModel):
    mode: OperatorMode = OperatorMode.auto
    title: Optional[str] = None


class UnifiedApproveRequest(BaseModel):
    action_ids: List[str] = Field(..., min_length=1)


class UnifiedRejectRequest(BaseModel):
    action_ids: List[str] = Field(..., min_length=1)


# ── Response Sub-models ────────────────────────────────────

class UnifiedFinding(BaseModel):
    system: str
    type: str
    title: str
    description: str
    severity: str = "medium"
    data: Optional[List[Any]] = None


class UnifiedProposedAction(BaseModel):
    id: str
    system: str
    action_type: str
    label: str
    reasoning: Optional[str] = None
    risk_level: str = "medium"
    requires_confirmation: bool = True
    expected_impact: Optional[str] = None
    payload: Dict[str, Any] = {}
    preview: Optional[Dict[str, Any]] = None
    status: str = "proposed"


class UnifiedExecutionResult(BaseModel):
    action_id: str
    system: str
    action_type: str
    status: str  # success | failed | partial_success
    summary: str = ""
    details: Optional[Dict[str, Any]] = None
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ConnectedSystemStatus(BaseModel):
    name: str
    connected: bool
    error: Optional[str] = None


# ── Responses ──────────────────────────────────────────────

class UnifiedChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    mode: str
    systems_used: List[str] = []
    summary: str = ""
    findings: List[UnifiedFinding] = []
    recommended_actions: List[UnifiedProposedAction] = []
    questions: List[str] = []
    message: Optional[str] = None
    connected_systems: List[ConnectedSystemStatus] = []


class UnifiedApproveResponse(BaseModel):
    status: str
    succeeded: int = 0
    failed: int = 0
    results: List[UnifiedExecutionResult] = []


class ConversationSummary(BaseModel):
    conversation_id: str
    title: str
    mode: str
    created_at: str
    updated_at: str
