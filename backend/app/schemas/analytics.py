from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SummaryCounts(BaseModel):
    total_events: int
    active_events: int
    verified_events: int
    needs_review_events: int
    rejected_events: int
    total_reports: int
    reports_last_hour: int
    duplicate_reports: int
    dedup_rate: float
    active_sources: int
    events_by_type: dict[str, int]
    events_by_status: dict[str, int]
    events_by_severity: dict[str, int]
    reports_by_source_type: dict[str, int]
    avg_evidence_score: float


class TimelineBucket(BaseModel):
    bucket: datetime
    counts: dict[str, int]
    total: int


class TimelineOut(BaseModel):
    buckets: list[TimelineBucket]
    event_types: list[str]


class HashtagRow(BaseModel):
    hashtag: str
    report_count: int
    tracked: bool
    top_event_type: str | None


class HashtagsOut(BaseModel):
    window_hours: int
    total_tagged_reports: int
    rows: list[HashtagRow]


class CredibilityRow(BaseModel):
    code: str
    label: str
    report_count: int


class CredibilityOut(BaseModel):
    window_hours: int
    total_reports: int
    flagged_reports: int
    flagged_rate: float
    avg_risk: float
    flags: list[CredibilityRow]


class StateRow(BaseModel):
    state: str
    event_count: int
    report_count: int
    verified_count: int
    avg_evidence_score: float
    dominant_event_type: str | None


class DistrictRisk(BaseModel):
    district: str
    state: str | None
    event_count: int
    alert_count: int
    red_alerts: int
    dominant_hazard: str | None
    hazard_counts: dict[str, int]
    avg_evidence: float
    verified: int
    rejected: int


class HourBucket(BaseModel):
    hour_ist: int
    counts: dict[str, int]
    total: int


class DetectionStats(BaseModel):
    measured: int
    median_minutes: float | None
    p90_minutes: float | None
    note: str


class PreparednessOut(BaseModel):
    window_days: int
    data_span_hours: float
    coverage_note: str
    districts: list[DistrictRisk]
    hazard_totals: dict[str, int]
    hour_of_day: list[HourBucket]
    detection: DetectionStats
