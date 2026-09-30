import type {
  Advisory,
  PreparednessOut,
  AlertItem,
  AlertSummary,
  AuditLog,
  AuthUser,
  CredibilityOut,
  HashtagsOut,
  EventDetail,
  EventStatus,
  EventType,
  MapEvent,
  Page,
  ReportSummary,
  SourceHealth,
  StateRow,
  SummaryCounts,
  SystemHealth,
  TimelineOut,
  WeatherEvent,
} from "./types";

import { isMockMode, mockResponse } from "./mock";

const TOKEN_KEY = "nwap.token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (isMockMode()) {
    const method = (init.method ?? "GET").toUpperCase();
    if (method !== "GET") {
      // Mutations are accepted and do nothing. The frozen dataset must not
      // move, but a click that throws would look like a broken console.
      console.info(`[mock] ${method} ${path} — ignored, dataset is frozen`);
      return undefined as T;
    }
    const recorded = await mockResponse<T>(path);
    if (recorded !== undefined) return recorded;
    // Say which path is missing rather than failing vaguely — it is the one
    // thing you need to know to re-record.
    throw new ApiError(404, `[mock] no fixture recorded for ${path}`);
  }

  const token = getToken();
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401) clearToken();
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** Repeats a key per value the way FastAPI expects list query params. */
function qs(params: object) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      if (value.length === 0) continue;
      value.forEach((v) => search.append(key, String(v)));
    } else {
      search.append(key, String(value));
    }
  }
  const str = search.toString();
  return str ? `?${str}` : "";
}

export interface EventFilters {
  date_from?: string;
  date_to?: string;
  event_type?: EventType[];
  status?: EventStatus[];
  state?: string;
  district?: string;
}

export const api = {
  events: (filters: EventFilters & { limit?: number; sort?: string; order?: string }) =>
    request<Page<WeatherEvent>>(`/events${qs(filters)}`),

  event: (id: string) => request<EventDetail>(`/events/${id}`),

  eventReports: (id: string, limit = 100) =>
    request<Page<ReportSummary>>(`/events/${id}/reports${qs({ limit })}`),

  mapEvents: (filters: EventFilters & { limit?: number }) =>
    request<MapEvent[]>(`/map/events${qs(filters)}`),

  reports: (params: Record<string, unknown>) =>
    request<Page<ReportSummary>>(`/reports${qs(params)}`),

  submitReport: (body: Record<string, unknown>) =>
    request<{ raw_event_id: string; status: string; detail: string }>("/reports", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  summary: () => request<SummaryCounts>("/analytics/summary"),

  timeline: (params: { hours?: number; bucket_minutes?: number; state?: string; event_type?: EventType[] }) =>
    request<TimelineOut>(`/analytics/timeline${qs(params)}`),

  hashtags: (params: { hours?: number; limit?: number; tracked_only?: boolean } = {}) =>
    request<HashtagsOut>(`/analytics/hashtags${qs(params)}`),

  credibility: (hours = 24) =>
    request<CredibilityOut>(`/analytics/credibility${qs({ hours })}`),

  preparedness: (days = 7, limit = 20) =>
    request<PreparednessOut>(`/analytics/preparedness${qs({ days, limit })}`),

  byState: (hours = 24) => request<StateRow[]>(`/analytics/by-state${qs({ hours })}`),

  verificationQueue: (limit = 100) =>
    request<Page<WeatherEvent>>(`/verification/queue${qs({ limit })}`),

  verify: (id: string, reason?: string) =>
    request<WeatherEvent>(`/verification/${id}/verify`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  reject: (id: string, reason?: string) =>
    request<WeatherEvent>(`/verification/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  alerts: (params: Record<string, unknown> = {}) =>
    request<Page<AlertItem>>(`/alerts${qs(params)}`),

  alertSummary: () => request<AlertSummary>("/alerts/summary"),

  alertAdvisory: (id: string) => request<Advisory>(`/alerts/${id}/advisory`),

  eventAdvisory: (id: string) => request<Advisory>(`/events/${id}/advisory`),

  acknowledgeAlert: (id: string, note?: string) =>
    request<AlertItem>(`/alerts/${id}/acknowledge`, {
      method: "POST",
      body: JSON.stringify({ note }),
    }),

  closeAlert: (id: string, note?: string) =>
    request<AlertItem>(`/alerts/${id}/close`, {
      method: "POST",
      body: JSON.stringify({ note }),
    }),

  sources: () => request<SourceHealth[]>("/admin/sources"),

  updateSource: (id: string, body: Record<string, unknown>) =>
    request<SourceHealth>(`/admin/sources/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  systemHealth: () => request<SystemHealth>("/admin/system-health"),

  auditLogs: (limit = 100) => request<Page<AuditLog>>(`/admin/audit-logs${qs({ limit })}`),

  login: (email: string, password: string) =>
    request<{ access_token: string; token_type: string; role: string; email: string }>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
    ),

  me: () => request<AuthUser>("/auth/me"),
};
