from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import ProcessingState, SourceType


class MediaItem(BaseModel):
    url: str
    type: str = "image"


class ReportCreate(BaseModel):
    """Citizen submission payload."""

    text: str = Field(..., min_length=3, max_length=2000)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    city: str | None = None
    observed_at: datetime | None = None
    media: list[MediaItem] | None = None
    reporter_handle: str | None = None


class ReportAccepted(BaseModel):
    raw_event_id: uuid.UUID
    status: str = "accepted"
    detail: str = "Report accepted; enrichment pipeline runs asynchronously."


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    raw_event_id: uuid.UUID | None
    source_id: uuid.UUID | None
    source_type: SourceType
    external_id: str | None
    raw_text: str
    normalized_text: str | None
    language: str | None
    hashtags: list[str] | None
    tracked_hashtags: list[str] | None
    mentions: list[str] | None
    urls: list[str] | None
    author: str | None
    latitude: float | None
    longitude: float | None
    city: str | None
    district: str | None
    state: str | None
    location_confidence: float
    observed_at: datetime
    event_type_scores: dict | None
    predicted_event_type: str | None
    weather_corroboration: dict | None
    reliability_score: float | None
    insufficient_evidence: bool
    misinformation_risk: float | None
    credibility_flags: dict | None
    duplicate_of_report_id: uuid.UUID | None
    dedup_method: str | None
    event_id: uuid.UUID | None
    media: list | None
    processing_state: ProcessingState
    created_at: datetime


class ReportSummary(BaseModel):
    """Trimmed shape for lists, map layers and event detail panels."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_type: SourceType
    raw_text: str
    language: str | None
    hashtags: list[str] | None
    tracked_hashtags: list[str] | None
    author: str | None
    media: list | None
    latitude: float | None
    longitude: float | None
    city: str | None
    district: str | None
    state: str | None
    observed_at: datetime
    predicted_event_type: str | None
    reliability_score: float | None
    misinformation_risk: float | None
    credibility_flags: dict | None
    duplicate_of_report_id: uuid.UUID | None
    event_id: uuid.UUID | None
    processing_state: ProcessingState
