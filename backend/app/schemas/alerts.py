from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import (
    AlertStatus,
    AuthorityLevel,
    DeliveryChannel,
    DeliveryStatus,
    EventType,
    SourceStatus,
    WarningLevel,
)


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    level: WarningLevel
    status: AlertStatus
    event_type: EventType
    state: str | None
    district: str | None
    center_latitude: float | None
    center_longitude: float | None
    headline: str
    action: str
    evidence_snapshot: dict | None
    raised_at: datetime
    escalated_at: datetime | None
    previous_level: str | None
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    closed_at: datetime | None
    closed_reason: str | None


class AlertAction(BaseModel):
    note: str | None = None


class AlertSummary(BaseModel):
    active: int
    acknowledged: int
    closed_last_24h: int
    by_level: dict[str, int]
    by_state: list[dict]
    oldest_unacknowledged_minutes: float | None


class AuthorityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    level: AuthorityLevel
    state: str | None
    district: str | None
    contact_email: str | None
    webhook_url: str | None
    phone: str | None
    event_types: list[str] | None
    min_level: WarningLevel
    status: SourceStatus
    created_at: datetime


class AuthorityUpdate(BaseModel):
    status: SourceStatus | None = None
    min_level: WarningLevel | None = None
    webhook_url: str | None = None
    contact_email: str | None = None
    event_types: list[str] | None = None


class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alert_id: uuid.UUID
    authority_id: uuid.UUID
    authority_name: str | None = None
    channel: DeliveryChannel
    status: DeliveryStatus
    target: str | None
    response_code: int | None
    last_error: str | None
    attempts: int
    queued_at: datetime
    sent_at: datetime | None


class DeliveryStats(BaseModel):
    pending: int
    sent: int
    simulated: int
    failed: int
    authorities_active: int
    by_channel: dict[str, int]
