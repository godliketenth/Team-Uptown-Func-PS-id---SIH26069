from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import EventStatus, EventType, Severity, WarningLevel
from app.schemas.reports import ReportSummary


class StatusHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    old_status: str | None
    new_status: str
    changed_by: str | None
    reason: str | None
    created_at: datetime


class EvidenceBreakdown(BaseModel):
    """Why an event holds the status it holds. Never hide this behind a badge."""

    report_count: int
    source_count: int
    distinct_source_types: list[str]
    evidence_score: float
    weather_corroboration: float
    duplicate_count: int
    independent_citizen_reports: int
    with_media: int
    flagged_report_count: int
    avg_misinformation_risk: float
    top_flags: list[dict]
    top_hashtags: list[dict]
    top_contributing_sources: list[dict]


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: EventType
    status: EventStatus
    center_latitude: float
    center_longitude: float
    state: str | None
    district: str | None
    start_time: datetime
    last_updated: datetime
    report_count: int
    source_count: int
    evidence_score: float
    corroboration_score: float
    flagged_report_count: int
    severity: Severity
    warning_level: WarningLevel
    warning_reasons: dict | None
    created_at: datetime


class EventDetail(EventOut):
    evidence: EvidenceBreakdown
    status_history: list[StatusHistoryOut]
    sample_reports: list[ReportSummary]


class MapEvent(BaseModel):
    """Deliberately small: this is polled every 5 seconds."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: EventType
    status: EventStatus
    severity: Severity
    center_latitude: float
    center_longitude: float
    report_count: int
    source_count: int
    evidence_score: float
    flagged_report_count: int
    warning_level: WarningLevel
    last_updated: datetime
    district: str | None
    state: str | None


class MapReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    latitude: float | None
    longitude: float | None
    predicted_event_type: str | None
    source_type: str
    reliability_score: float | None
    observed_at: datetime


class VerificationAction(BaseModel):
    reason: str | None = None


class AdvisoryOut(BaseModel):
    """Publishable advisory derived from an event. Computed on demand, never
    stored — stored derived text goes stale the moment the event moves."""

    level: str
    action: str
    headline: str
    situation: str
    expect: str
    safety: list[str]
    confidence: str
    confidence_note: str
    evidence_line: str
    issued_at: str
    validity_note: str
    hindi: dict
    disclaimer: str
    plain_text: str
