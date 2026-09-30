export type EventType =
  | "RAIN"
  | "FLOOD"
  | "THUNDERSTORM"
  | "HEATWAVE"
  | "FOG"
  | "DUST_STORM"
  | "STRONG_WIND";

export type EventStatus =
  | "DETECTED"
  | "CORROBORATING"
  | "NEEDS_REVIEW"
  | "VERIFIED"
  | "REJECTED"
  | "RESOLVED";

export type Severity = "LOW" | "MODERATE" | "HIGH" | "SEVERE";

/** IMD-style warning scale: vocabulary and actions follow IMD, thresholds are ours. */
export type WarningLevel = "GREEN" | "YELLOW" | "ORANGE" | "RED";

export interface WarningReasons {
  level: WarningLevel;
  action: string;
  color: string;
  reasons: string[];
  capped_by: string | null;
}

export type SourceType =
  | "GOVERNMENT"
  | "WEATHER_API"
  | "CITIZEN"
  | "SOCIAL"
  | "WEB_RSS"
  | "SATELLITE";

export type SourceStatus = "ACTIVE" | "PAUSED" | "ERROR";

export type UserRole = "PUBLIC_USER" | "ANALYST" | "VERIFIER" | "ADMIN";

export type ProcessingState =
  | "RECEIVED"
  | "NORMALIZED"
  | "ENRICHED"
  | "CLASSIFIED"
  | "DEDUPLICATED"
  | "EVENT_ASSIGNED";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface WeatherEvent {
  id: string;
  event_type: EventType;
  status: EventStatus;
  center_latitude: number;
  center_longitude: number;
  state: string | null;
  district: string | null;
  start_time: string;
  last_updated: string;
  report_count: number;
  source_count: number;
  evidence_score: number;
  corroboration_score: number;
  flagged_report_count: number;
  severity: Severity;
  warning_level: WarningLevel;
  warning_reasons: WarningReasons | null;
  created_at: string;
}

export interface MapEvent {
  id: string;
  event_type: EventType;
  status: EventStatus;
  severity: Severity;
  center_latitude: number;
  center_longitude: number;
  report_count: number;
  source_count: number;
  evidence_score: number;
  flagged_report_count: number;
  warning_level: WarningLevel;
  last_updated: string;
  district: string | null;
  state: string | null;
}

export interface CredibilityFlag {
  code: string;
  label: string;
  weight: number;
}

export interface CredibilityFlags {
  risk: number;
  needs_review: boolean;
  flags: CredibilityFlag[];
}

export interface MediaItem {
  url: string;
  type: string;
}

export interface ReportSummary {
  id: string;
  source_type: SourceType;
  raw_text: string;
  language: string | null;
  hashtags: string[] | null;
  tracked_hashtags: string[] | null;
  author: string | null;
  media: MediaItem[] | null;
  misinformation_risk: number | null;
  credibility_flags: CredibilityFlags | null;
  latitude: number | null;
  longitude: number | null;
  city: string | null;
  district: string | null;
  state: string | null;
  observed_at: string;
  predicted_event_type: EventType | null;
  reliability_score: number | null;
  duplicate_of_report_id: string | null;
  event_id: string | null;
  processing_state: ProcessingState;
}

export interface EvidenceBreakdown {
  report_count: number;
  source_count: number;
  distinct_source_types: SourceType[];
  evidence_score: number;
  weather_corroboration: number;
  duplicate_count: number;
  independent_citizen_reports: number;
  with_media: number;
  flagged_report_count: number;
  avg_misinformation_risk: number;
  top_flags: { code: string; label: string; report_count: number }[];
  top_hashtags: { hashtag: string; report_count: number; tracked: boolean }[];
  top_contributing_sources: {
    name: string;
    source_type: SourceType;
    report_count: number;
    avg_reliability: number;
  }[];
}

export interface StatusHistory {
  id: string;
  old_status: string | null;
  new_status: string;
  changed_by: string | null;
  reason: string | null;
  created_at: string;
}

export interface EventDetail extends WeatherEvent {
  evidence: EvidenceBreakdown;
  status_history: StatusHistory[];
  sample_reports: ReportSummary[];
}

export interface SummaryCounts {
  total_events: number;
  active_events: number;
  verified_events: number;
  needs_review_events: number;
  rejected_events: number;
  total_reports: number;
  reports_last_hour: number;
  duplicate_reports: number;
  dedup_rate: number;
  active_sources: number;
  events_by_type: Record<EventType, number>;
  events_by_status: Record<EventStatus, number>;
  events_by_severity: Record<string, number>;
  reports_by_source_type: Record<string, number>;
  avg_evidence_score: number;
}

export interface TimelineBucket {
  bucket: string;
  counts: Record<EventType, number>;
  total: number;
}

export interface TimelineOut {
  buckets: TimelineBucket[];
  event_types: EventType[];
}

export interface HashtagRow {
  hashtag: string;
  report_count: number;
  tracked: boolean;
  top_event_type: EventType | null;
}

export interface HashtagsOut {
  window_hours: number;
  total_tagged_reports: number;
  rows: HashtagRow[];
}

export interface CredibilityOut {
  window_hours: number;
  total_reports: number;
  flagged_reports: number;
  flagged_rate: number;
  avg_risk: number;
  flags: { code: string; label: string; report_count: number }[];
}

export type AlertStatus = "ACTIVE" | "ACKNOWLEDGED" | "CLOSED";

export interface AlertItem {
  id: string;
  event_id: string;
  level: WarningLevel;
  status: AlertStatus;
  event_type: EventType;
  state: string | null;
  district: string | null;
  center_latitude: number | null;
  center_longitude: number | null;
  headline: string;
  action: string;
  evidence_snapshot: Record<string, unknown> | null;
  raised_at: string;
  escalated_at: string | null;
  previous_level: string | null;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  closed_at: string | null;
  closed_reason: string | null;
}

export interface AlertSummary {
  active: number;
  acknowledged: number;
  closed_last_24h: number;
  by_level: Record<WarningLevel, number>;
  by_state: { state: string; count: number }[];
  oldest_unacknowledged_minutes: number | null;
}

export interface Advisory {
  level: WarningLevel;
  action: string;
  headline: string;
  situation: string;
  expect: string;
  safety: string[];
  confidence: "high" | "medium" | "low";
  confidence_note: string;
  evidence_line: string;
  issued_at: string;
  validity_note: string;
  hindi: { headline: string; action: string };
  disclaimer: string;
  plain_text: string;
}

export interface DistrictRisk {
  district: string;
  state: string | null;
  event_count: number;
  alert_count: number;
  red_alerts: number;
  dominant_hazard: EventType | null;
  hazard_counts: Record<string, number>;
  avg_evidence: number;
  verified: number;
  rejected: number;
}

export interface PreparednessOut {
  window_days: number;
  data_span_hours: number;
  coverage_note: string;
  districts: DistrictRisk[];
  hazard_totals: Record<EventType, number>;
  hour_of_day: { hour_ist: number; counts: Record<EventType, number>; total: number }[];
  detection: {
    measured: number;
    median_minutes: number | null;
    p90_minutes: number | null;
    note: string;
  };
}

export interface StateRow {
  state: string;
  event_count: number;
  report_count: number;
  verified_count: number;
  avg_evidence_score: number;
  dominant_event_type: EventType | null;
}

export interface SourceHealth {
  id: string;
  name: string;
  source_type: SourceType;
  status: SourceStatus;
  poll_interval_seconds: number;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error_message: string | null;
  created_at: string;
  raw_events_total: number;
  raw_events_last_hour: number;
  reports_total: number;
}

export interface SystemHealth {
  status: string;
  scheduler_running: boolean;
  last_tick_at: string | null;
  seconds_since_tick: number | null;
  bus: {
    transport: "in-process" | "kafka";
    published: number;
    processed: number;
    failed: number;
    pending: number | null;
    last_tick_at: string | null;
    last_error: string | null;
  };
  pipeline_stages: { stage: ProcessingState; count: number }[];
  raw_events_total: number;
  reports_total: number;
  events_total: number;
  error_rate: number;
  raw_lake: {
    backend: "local" | "s3";
    root: string;
    endpoint?: string;
    partitions: number;
    objects: number;
  };
  open_meteo_enabled: boolean;
}

export interface AuditLog {
  id: string;
  actor_id: string | null;
  actor_email: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface AuthUser {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  created_at: string;
}
