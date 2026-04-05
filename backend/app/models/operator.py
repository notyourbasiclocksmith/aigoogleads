"""
Operator Chat models — Conversations, Messages, Proposed Actions, Execution Logs.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Boolean, Integer, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base


def _uuid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


class OperatorConversation(Base):
    __tablename__ = "operator_conversations"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(String(20), nullable=False)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    messages = relationship("OperatorMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="OperatorMessage.created_at")


class OperatorMessage(Base):
    __tablename__ = "operator_messages"

    id = Column(String(36), primary_key=True, default=_uuid)
    conversation_id = Column(String(36), ForeignKey("operator_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user | assistant | system
    content = Column(Text, nullable=True)
    structured_payload = Column(JSON, nullable=True)  # findings, actions, tables, etc.
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    conversation = relationship("OperatorConversation", back_populates="messages")
    proposed_actions = relationship("ProposedAction", back_populates="message", cascade="all, delete-orphan")


class ProposedAction(Base):
    __tablename__ = "proposed_actions"

    id = Column(String(36), primary_key=True, default=_uuid)
    conversation_id = Column(String(36), ForeignKey("operator_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String(36), ForeignKey("operator_messages.id", ondelete="CASCADE"), nullable=False)
    action_type = Column(String(50), nullable=False)
    label = Column(String(300), nullable=False)
    reasoning = Column(Text, nullable=True)
    expected_impact = Column(String(500), nullable=True)
    risk_level = Column(String(20), nullable=False, default="medium")  # low | medium | high
    action_payload = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="proposed")  # proposed | approved | rejected | executed | failed
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    executed_by = Column(String(36), nullable=True)

    message = relationship("OperatorMessage", back_populates="proposed_actions")
    execution_logs = relationship("ActionExecutionLog", back_populates="proposed_action", cascade="all, delete-orphan")


class ActionExecutionLog(Base):
    __tablename__ = "action_execution_logs"

    id = Column(String(36), primary_key=True, default=_uuid)
    proposed_action_id = Column(String(36), ForeignKey("proposed_actions.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False)
    customer_id = Column(String(20), nullable=False)
    request_payload = Column(JSON, nullable=True)
    response_payload = Column(JSON, nullable=True)
    before_state = Column(JSON, nullable=True)
    after_state = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False)  # success | failed | partial
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    proposed_action = relationship("ProposedAction", back_populates="execution_logs")
