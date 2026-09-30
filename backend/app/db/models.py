from __future__ import annotations

import enum
import uuid
from datetime import datetime

from geoalchemy2 import Geography
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------
class SourceType(str, enum.Enum):
    GOVERNMENT = "GOVERNMENT"
    WEATHER_API = "WEATHER_API"
    CITIZEN = "CITIZEN"
    SOCIAL = "SOCIAL"
    WEB_RSS = "WEB_RSS"
    SATELLITE = "SATELLITE"


class SourceStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ERROR = "ERROR"


class ProcessingState(str, enum.Enum):
    RECEIVED = "RECEIVED"
    NORMALIZED = "NORMALIZED"
    ENRICHED = "ENRICHED"
    CLASSIFIED = "CLASSIFIED"
    DEDUPLICATED = "DEDUPLICATED"
    EVENT_ASSIGNED = "EVENT_ASSIGNED"


class EventType(str, enum.Enum):
    RAIN = "RAIN"
    FLOOD = "FLOOD"
    THUNDERSTORM = "THUNDERSTORM"
    HEATWAVE = "HEATWAVE"
    FOG = "FOG"
    DUST_STORM = "DUST_STORM"
    STRONG_WIND = "STRONG_WIND"


class EventStatus(str, enum.Enum):
    DETECTED = "DETECTED"
    CORROBORATING = "CORROBORATING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    RESOLVED = "RESOLVED"


class WarningLevel(str, enum.Enum):
    """IMD-style four-colour warning scale. See pipeline/warning.py — the
    vocabulary and actions follow IMD; the trigger logic is ours."""

    GREEN = "GREEN"
    YELLOW = "YELLOW"
    ORANGE = "ORANGE"
    RED = "RED"


class AuthorityLevel(str, enum.Enum):
    NATIONAL = "NATIONAL"
    STATE = "STATE"
    DISTRICT = "DISTRICT"


class DeliveryChannel(str, enum.Enum):
    WEBHOOK = "WEBHOOK"
    EMAIL = "EMAIL"
    SMS = "SMS"


class DeliveryStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    # Recorded, not attempted: the channel has no transport configured.
    # Kept distinct from FAILED so "we cannot send" never looks like "we tried".
    SIMULATED = "SIMULATED"


class AlertStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    CLOSED = "CLOSED"


class Severity(str, enum.Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    SEVERE = "SEVERE"


class UserRole(str, enum.Enum):
    PUBLIC_USER = "PUBLIC_USER"
    ANALYST = "ANALYST"
    VERIFIER = "VERIFIER"
    ADMIN = "ADMIN"


def _enum(py_enum, name: str) -> Enum:
    return Enum(py_enum, name=name, native_enum=True, values_callable=lambda e: [m.value for m in e])


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


TS = DateTime(timezone=True)


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------
class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[SourceType] = mapped_column(_enum(SourceType, "source_type"), nullable=False)
    status: Mapped[SourceStatus] = mapped_column(
        _enum(SourceStatus, "source_status"), nullable=False, default=SourceStatus.ACTIVE
    )
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    last_success_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TS, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RawEvent(Base):
    """The immutable raw 'lake', as a table. Never updated after insert."""

    __tablename__ = "raw_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_type: Mapped[SourceType] = mapped_column(
        _enum(SourceType, "source_type"), nullable=False, index=True
    )
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    collected_at: Mapped[datetime] = mapped_column(TS, nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_events.id", ondelete="SET NULL"), nullable=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    source_type: Mapped[SourceType] = mapped_column(
        _enum(SourceType, "source_type"), nullable=False, index=True
    )
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Collected post metadata. Hashtags are tracked explicitly (#IMD and
    # friends) rather than being stripped away with the rest of the markup.
    # Semantic embedding for near-duplicate detection (Phase 1.2). Nullable so
    # rows written before the model existed, or while it is unavailable, stay valid.
    embedding = mapped_column(Vector(384), nullable=True)

    hashtags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tracked_hashtags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    mentions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    urls: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    author: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geom = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    district: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    location_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)

    observed_at: Mapped[datetime] = mapped_column(TS, nullable=False, index=True)

    event_type_scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    predicted_event_type: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    weather_corroboration: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reliability_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    insufficient_evidence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Fake / misleading detection: an explainable risk score plus the named
    # flags that produced it.
    misinformation_risk: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    credibility_flags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    duplicate_of_report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="SET NULL"), nullable=True
    )
    dedup_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True
    )

    media: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    processing_state: Mapped[ProcessingState] = mapped_column(
        _enum(ProcessingState, "processing_state"),
        nullable=False,
        default=ProcessingState.RECEIVED,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TS, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    event: Mapped["Event | None"] = relationship("Event", back_populates="reports", lazy="noload")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[EventType] = mapped_column(
        _enum(EventType, "event_type"), nullable=False, index=True
    )
    status: Mapped[EventStatus] = mapped_column(
        _enum(EventStatus, "event_status"), nullable=False, default=EventStatus.DETECTED, index=True
    )
    center_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    center_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geom = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=True)
    state: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    district: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    start_time: Mapped[datetime] = mapped_column(TS, nullable=False, index=True)
    last_updated: Mapped[datetime] = mapped_column(TS, nullable=False, index=True)

    report_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    corroboration_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    flagged_report_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    severity: Mapped[Severity] = mapped_column(
        _enum(Severity, "severity"), nullable=False, default=Severity.LOW
    )
    # Operator-facing risk signal on IMD's colour scale, with the evidence
    # that produced it. Severity above stays as the raw volume descriptor.
    warning_level: Mapped[WarningLevel] = mapped_column(
        _enum(WarningLevel, "warning_level"), nullable=False, default=WarningLevel.GREEN, index=True
    )
    warning_reasons: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TS, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    reports: Mapped[list[Report]] = relationship(
        "Report", back_populates="event", lazy="noload", foreign_keys=[Report.event_id]
    )
    status_history: Mapped[list["EventStatusHistory"]] = relationship(
        "EventStatusHistory", back_populates="event", lazy="noload"
    )


class EventStatusHistory(Base):
    __tablename__ = "event_status_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    old_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_status: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # now() is the transaction timestamp, so two changes committed together
    # would tie and the lifecycle would read out of order.
    created_at: Mapped[datetime] = mapped_column(
        TS, server_default=func.clock_timestamp(), nullable=False
    )

    event: Mapped[Event] = relationship("Event", back_populates="status_history", lazy="noload")


class Alert(Base):
    """An actionable warning raised when an event crosses a response threshold.

    Deliberately a separate row rather than a flag on the event: an alert has
    its own lifecycle (raised → acknowledged → closed), its own operator, and
    must stay auditable even after the underlying event keeps changing. The
    evidence snapshot freezes what was true at the moment it was raised.
    """

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level: Mapped[WarningLevel] = mapped_column(
        _enum(WarningLevel, "warning_level"), nullable=False, index=True
    )
    status: Mapped[AlertStatus] = mapped_column(
        _enum(AlertStatus, "alert_status"), nullable=False, default=AlertStatus.ACTIVE, index=True
    )

    event_type: Mapped[EventType] = mapped_column(_enum(EventType, "event_type"), nullable=False)
    state: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    district: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    center_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    center_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    headline: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    raised_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False, index=True)
    escalated_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    previous_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    closed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TS, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Authority(Base):
    """Who gets told when an alert is raised.

    Matching is hierarchical: a NATIONAL authority receives everything, a STATE
    authority everything in its state, a DISTRICT authority only its district.
    Each can narrow further by event type and by minimum warning level.
    """

    __tablename__ = "authorities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[AuthorityLevel] = mapped_column(
        _enum(AuthorityLevel, "authority_level"), nullable=False, index=True
    )
    state: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    district: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    contact_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)

    # null = subscribe to every event type
    event_types: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    min_level: Mapped[WarningLevel] = mapped_column(
        _enum(WarningLevel, "warning_level"), nullable=False, default=WarningLevel.ORANGE
    )
    status: Mapped[SourceStatus] = mapped_column(
        _enum(SourceStatus, "source_status"), nullable=False, default=SourceStatus.ACTIVE
    )

    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TS, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AlertDelivery(Base):
    """One attempt to reach one authority about one alert.

    A row per (alert, authority, channel) so a partial failure is visible:
    "the webhook went through but the SMS did not" is operationally different
    from "nobody was told".
    """

    __tablename__ = "alert_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    authority_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("authorities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[DeliveryChannel] = mapped_column(
        _enum(DeliveryChannel, "delivery_channel"), nullable=False
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        _enum(DeliveryStatus, "delivery_status"), nullable=False, default=DeliveryStatus.PENDING, index=True
    )

    target: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    queued_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[UserRole] = mapped_column(
        _enum(UserRole, "user_role"), nullable=False, default=UserRole.PUBLIC_USER
    )
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False, index=True)
