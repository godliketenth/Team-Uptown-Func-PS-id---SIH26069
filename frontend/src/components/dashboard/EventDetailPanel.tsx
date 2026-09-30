import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as maplibregl from "maplibre-gl";
import { Check, ExternalLink, X } from "lucide-react";
import { Sheet, SheetHeader } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { EventTypeBadge, SeverityBadge, StatusBadge, WarningBadge } from "@/components/ui/badge";
import { EvidencePanel } from "./EvidencePanel";
import { api } from "@/lib/api";
import { EVENT_COLORS, LANGUAGE_LABELS, SOURCE_LABELS, atLeast } from "@/lib/domain";
import { fmtCoord, fmtDateTime, fmtPct, relativeTime, shortId } from "@/lib/utils";
import { useAuth } from "@/store/auth";
import { WaitingState } from "@/components/ui/empty";
import { HashtagChip } from "@/components/ui/hashtag";
import { MediaStrip } from "@/components/ui/media";
import { CredibilityFlagList, RiskBadge } from "@/components/ui/credibility";
import { livePoll } from "@/lib/live";
import { buildMapStyle } from "@/lib/mapStyle";
import { getTheme, useTheme } from "@/hooks/useTheme";

export function EventDetailPanel({
  eventId,
  onClose,
}: {
  eventId: string | null;
  onClose: () => void;
}) {
  const user = useAuth((s) => s.user);
  const qc = useQueryClient();
  const [reason, setReason] = React.useState("");

  const { data: event, isLoading } = useQuery({
    queryKey: ["event", eventId],
    queryFn: () => api.event(eventId!),
    enabled: !!eventId,
    refetchInterval: livePoll(5000),
  });

  const { data: reports } = useQuery({
    queryKey: ["event-reports", eventId],
    queryFn: () => api.eventReports(eventId!, 50),
    enabled: !!eventId,
  });

  const decide = useMutation({
    mutationFn: ({ action }: { action: "verify" | "reject" }) =>
      action === "verify" ? api.verify(eventId!, reason) : api.reject(eventId!, reason),
    onSuccess: () => {
      setReason("");
      qc.invalidateQueries({ queryKey: ["event", eventId] });
      qc.invalidateQueries({ queryKey: ["events"] });
      qc.invalidateQueries({ queryKey: ["map-events"] });
      qc.invalidateQueries({ queryKey: ["verification-queue"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
    },
  });

  const canDecide = atLeast(user?.role, "VERIFIER");

  return (
    <Sheet open={!!eventId} onClose={onClose}>
      {!event || isLoading ? (
        <div className="flex h-full items-center justify-center">
          <WaitingState title="Loading event" detail="Fetching evidence and contributing reports." />
        </div>
      ) : (
        <>
          <SheetHeader
            title={
              <div className="flex flex-wrap items-center gap-1.5">
                <EventTypeBadge type={event.event_type} />
                <WarningBadge level={event.warning_level} />
                <StatusBadge status={event.status} />
                <SeverityBadge severity={event.severity} />
              </div>
            }
            subtitle={
              <span className="num">
                EVT-{shortId(event.id)} · {fmtCoord(event.center_latitude)},{" "}
                {fmtCoord(event.center_longitude)}
              </span>
            }
            onClose={onClose}
          >
            <div className="mt-2 flex items-center justify-between">
              <div className="text-[15.5px] font-medium">
                {event.district ?? "Unresolved district"}
                <span className="text-[var(--text-faint)]">{event.state ? `, ${event.state}` : ""}</span>
              </div>
              <a
                href={`/events/${event.id}`}
                className="flex items-center gap-1 text-[12.5px] text-[var(--text-faint)] hover:text-[var(--color-accent)]"
              >
                <ExternalLink className="h-3 w-3" /> permalink
              </a>
            </div>
            <div className="num mt-1 text-[12.5px] text-[var(--text-faint)]">
              started {fmtDateTime(event.start_time)} · updated {relativeTime(event.last_updated)}
            </div>
          </SheetHeader>

          <div className="scroll-thin flex-1 overflow-y-auto">
            <MiniMap
              lat={event.center_latitude}
              lon={event.center_longitude}
              color={EVENT_COLORS[event.event_type]}
              reports={reports?.items ?? []}
            />

            <Section title="Evidence">
              <EvidencePanel event={event} />
            </Section>

            <Section title={`Contributing reports (${reports?.total ?? 0})`}>
              <div className="space-y-1.5">
                {(reports?.items ?? []).slice(0, 25).map((r) => (
                  <div
                    key={r.id}
                    className="rounded-[var(--r-md)] border border-[var(--hairline-soft)] bg-[var(--veil-2)] px-2.5 py-2 transition-colors hover:bg-[var(--veil-1)]"
                  >
                    <div className="flex items-center gap-1.5">
                      <span className="text-[12px] uppercase tracking-wider text-[var(--text-faint)]">
                        {SOURCE_LABELS[r.source_type]}
                      </span>
                      {r.language && r.language !== "en" && (
                        <span className="num rounded-full border border-[var(--hairline)] px-1.5 text-[12px] text-[var(--text-dim)]">
                          {LANGUAGE_LABELS[r.language] ?? r.language.toUpperCase()}
                        </span>
                      )}
                      {r.duplicate_of_report_id && (
                        <span className="rounded-full border border-[var(--color-st-resolved)]/45 bg-[var(--color-st-resolved)]/10 px-1.5 text-[12px] uppercase text-[var(--color-st-resolved)]">
                          duplicate
                        </span>
                      )}
                      <span className="num ml-auto text-[12px] text-[var(--text-faint)]">
                        {relativeTime(r.observed_at)}
                      </span>
                    </div>
                    <div className="mt-1.5 text-[13.5px] leading-relaxed text-[var(--text-ink)]">
                      {r.raw_text}
                    </div>

                    {r.hashtags && r.hashtags.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {r.hashtags.map((t) => (
                          <HashtagChip
                            key={t}
                            tag={t}
                            tracked={(r.tracked_hashtags ?? []).includes(t)}
                            eventType={r.predicted_event_type}
                          />
                        ))}
                      </div>
                    )}

                    <MediaStrip media={r.media} className="mt-1.5" />
                    <CredibilityFlagList flags={r.credibility_flags} className="mt-1.5" />

                    <div className="num mt-1.5 flex flex-wrap items-center gap-2 text-[12px] text-[var(--text-faint)]">
                      <span>RPT-{shortId(r.id, 6)}</span>
                      {r.author && <span className="text-[var(--text-dim)]">@{r.author}</span>}
                      <span>
                        {fmtCoord(r.latitude)}, {fmtCoord(r.longitude)}
                      </span>
                      <RiskBadge risk={r.misinformation_risk} className="ml-auto" />
                      <span>reliability {fmtPct(r.reliability_score)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Section>

            <Section title="Status history">
              <ol className="space-y-1.5">
                {event.status_history.map((h) => (
                  <li key={h.id} className="flex gap-2">
                    <span className="num mt-[3px] shrink-0 text-[12px] text-[var(--text-faint)]">
                      {fmtDateTime(h.created_at)}
                    </span>
                    <span className="min-w-0 text-[13px] text-[var(--text-dim)]">
                      <span className="text-[var(--text-ink)]">
                        {h.old_status ? `${h.old_status} → ` : ""}
                        {h.new_status}
                      </span>
                      <span className="text-[var(--text-faint)]">
                        {" "}
                        · {h.changed_by ?? "system"}
                        {h.reason ? ` · ${h.reason}` : ""}
                      </span>
                    </span>
                  </li>
                ))}
              </ol>
            </Section>
          </div>

          {canDecide && (
            <div className="shrink-0 border-t border-[var(--hairline)] bg-[var(--veil-2)] p-3.5">
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Reason (recorded in the audit log)"
                className="mb-2.5 h-9 w-full rounded-[var(--r-sm)] border border-[var(--hairline)] bg-[var(--veil-1)] px-3 text-[14px] text-[var(--text-ink)] transition-colors placeholder:text-[var(--text-faint)] focus:border-[var(--color-accent)]/45 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/30"
              />
              <div className="flex gap-2">
                <Button
                  variant="verify"
                  size="lg"
                  className="flex-1"
                  disabled={decide.isPending}
                  onClick={() => decide.mutate({ action: "verify" })}
                >
                  <Check className="h-3.5 w-3.5" /> Verify
                </Button>
                <Button
                  variant="reject"
                  size="lg"
                  className="flex-1"
                  disabled={decide.isPending}
                  onClick={() => decide.mutate({ action: "reject" })}
                >
                  <X className="h-3.5 w-3.5" /> Reject
                </Button>
              </div>
              {decide.isError && (
                <div className="mt-1.5 text-[12.5px] text-[var(--color-st-rejected)]">
                  {(decide.error as Error).message}
                </div>
              )}
            </div>
          )}
          {!canDecide && (
            <div className="shrink-0 border-t border-[var(--hairline)] bg-[var(--veil-2)] px-4 py-2.5 text-[12.5px] text-[var(--text-faint)]">
              Sign in with a verifier account to action this event.
            </div>
          )}
        </>
      )}
    </Sheet>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="divider-x px-4 py-3.5">
      <div className="label mb-2.5">{title}</div>
      {children}
    </div>
  );
}

function MiniMap({
  lat,
  lon,
  color,
  reports,
}: {
  lat: number;
  lon: number;
  color: string;
  reports: { id: string; latitude: number | null; longitude: number | null }[];
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const mapRef = React.useRef<maplibregl.Map | null>(null);
  const { theme } = useTheme();

  React.useEffect(() => {
    if (!ref.current) return;
    const map = new maplibregl.Map({
      container: ref.current,
      // `recede` pushes the basemap further back than on the main map: this one
      // sits at city zoom behind a dense scatter of report pins, and the pins
      // are the content.
      style: buildMapStyle(getTheme(), { recede: true }),
      center: [lon, lat],
      zoom: 9,
      interactive: false,
      attributionControl: false,
    });
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [lat, lon]);

  React.useEffect(() => {
    mapRef.current?.setStyle(buildMapStyle(theme, { recede: true }));
  }, [theme]);

  React.useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const markers: maplibregl.Marker[] = [];
    const center = document.createElement("div");
    center.style.cssText =
      `width:13px;height:13px;border-radius:9999px;background:${color};` +
      `border:2px solid var(--pin-base);` +
      `box-shadow:0 0 14px -2px ${color}, 0 0 0 1px ${color}`;
    markers.push(new maplibregl.Marker({ element: center }).setLngLat([lon, lat]).addTo(map));

    for (const r of reports) {
      if (r.latitude === null || r.longitude === null) continue;
      const el = document.createElement("div");
      el.style.cssText =
        `width:5px;height:5px;border-radius:9999px;background:${color};` +
        `border:1px solid var(--pin-base);opacity:.9`;
      markers.push(new maplibregl.Marker({ element: el }).setLngLat([r.longitude, r.latitude]).addTo(map));
    }
    return () => markers.forEach((m) => m.remove());
  }, [reports, color, lat, lon]);

  return <div ref={ref} className="h-40 w-full divider-x" />;
}
