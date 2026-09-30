from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import SourceStatus, SourceType, UserRole


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    source_type: SourceType
    status: SourceStatus
    poll_interval_seconds: int
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_error_message: str | None
    created_at: datetime


class SourceHealth(SourceOut):
    raw_events_total: int
    raw_events_last_hour: int
    reports_total: int


class SourceUpdate(BaseModel):
    status: SourceStatus | None = None
    poll_interval_seconds: int | None = None
    name: str | None = None


class PipelineStage(BaseModel):
    stage: str
    count: int


class SystemHealth(BaseModel):
    status: str
    scheduler_running: bool
    last_tick_at: datetime | None
    seconds_since_tick: float | None
    bus: dict
    pipeline_stages: list[PipelineStage]
    raw_events_total: int
    reports_total: int
    events_total: int
    error_rate: float
    raw_lake: dict
    open_meteo_enabled: bool


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_email: str | None
    action: str
    target_type: str | None
    target_id: str | None
    details: dict | None
    created_at: datetime


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    email: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None
    role: UserRole
    created_at: datetime
