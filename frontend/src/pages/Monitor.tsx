import * as React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { IndiaMap } from "@/components/dashboard/IndiaMap";
import { LiveEventFeed } from "@/components/dashboard/LiveEventFeed";
import { EventDetailPanel } from "@/components/dashboard/EventDetailPanel";
import { TimelineChart } from "@/components/dashboard/TimelineChart";
import { ActiveEventsSummary } from "@/components/dashboard/ActiveEventsSummary";
import { SourceTicker } from "@/components/dashboard/SourceTicker";
import { HashtagMonitor } from "@/components/dashboard/HashtagMonitor";
import { PanelTitle } from "@/components/ui/panel";
import { useDashboardData } from "@/hooks/useDashboardData";
import { useFilters } from "@/store/filters";
import { STATUS_COLORS } from "@/lib/domain";
import { cn, textHue } from "@/lib/utils";

/**
 * Monitor — situational awareness.
 *
 * One question: what is happening across India right now. The map is the hero
 * here and nowhere else; deciding and advising have their own screens, so this
 * one no longer has to carry a verification workflow behind a slide-over.
 */
export function Monitor() {
  const { eventId: routeEventId } = useParams();
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = React.useState<string | null>(routeEventId ?? null);
  const [focus, setFocus] = React.useState<{ lat: number; lon: number } | null>(null);

  const { events, mapEvents, summary, timeline } = useDashboardData();
  const range = useFilters((s) => s.range);
  const hashtagHours = range === "1h" ? 3 : range === "6h" ? 6 : range === "7d" ? 168 : 24;

  React.useEffect(() => {
    setSelectedId(routeEventId ?? null);
  }, [routeEventId]);

  const select = (id: string) => {
    setSelectedId(id);
    const match = (mapEvents.data ?? []).find((e) => e.id === id);
    if (match) setFocus({ lat: match.center_latitude, lon: match.center_longitude });
  };

  const close = () => {
    setSelectedId(null);
    if (routeEventId) navigate("/monitor");
  };

  const list = events.data?.items ?? [];
  const s = summary.data;

  return (
    <AppShell showFilters>
      <div className="flex min-h-0 flex-1">
        <main className="relative min-w-0 flex-1">
          <IndiaMap
            events={mapEvents.data ?? []}
            loading={mapEvents.isLoading}
            selectedId={selectedId}
            onSelect={select}
            focus={focus}
          />
          <StatStrip
            total={s?.active_events ?? 0}
            review={s?.needs_review_events ?? 0}
            verified={s?.verified_events ?? 0}
            reports={s?.reports_last_hour ?? 0}
            dedup={s?.dedup_rate ?? 0}
          />
        </main>

        <aside className="chrome hidden w-[340px] shrink-0 flex-col divider-y-l md:flex lg:w-[380px] xl:w-[420px]">
          <PanelTitle right={<span className="num text-[14px] text-[var(--text-faint)]">{s?.total_events ?? 0} total</span>}>
            Active events
          </PanelTitle>
          <ActiveEventsSummary summary={s} />

          <PanelTitle
            className="border-t border-[var(--hairline-soft)]"
            right={
              <span className="flex items-center gap-1.5">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--color-st-verified)] opacity-60" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[var(--color-st-verified)]" />
                </span>
                <span className="num text-[14px] text-[var(--text-faint)]">{list.length}</span>
              </span>
            }
          >
            Live feed
          </PanelTitle>
          <div className="min-h-0 flex-1">
            <LiveEventFeed
              events={list}
              loading={events.isLoading}
              selectedId={selectedId}
              onSelect={select}
            />
          </div>
        </aside>
      </div>

      <footer className="chrome hidden h-[224px] shrink-0 border-t border-[var(--hairline-soft)] sm:flex">
        <div className="flex min-w-0 flex-1 flex-col">
          <PanelTitle right={<span className="text-[12.5px] text-[var(--text-faint)]">reports per hour, stacked by event type</span>}>
            Reporting timeline
          </PanelTitle>
          <div className="min-h-0 flex-1">
            <TimelineChart data={timeline.data} loading={timeline.isLoading} />
          </div>
        </div>
        <div className="hidden w-[280px] shrink-0 flex-col divider-y-l lg:flex xl:w-[320px]">
          <PanelTitle>Hashtags</PanelTitle>
          <div className="min-h-0 flex-1">
            <HashtagMonitor hours={hashtagHours} />
          </div>
        </div>
        <div className="hidden w-[270px] shrink-0 flex-col divider-y-l xl:flex">
          <PanelTitle>Sources</PanelTitle>
          <div className="min-h-0 flex-1 py-1">
            <SourceTicker summary={s} />
          </div>
        </div>
      </footer>

      <EventDetailPanel eventId={selectedId} onClose={close} />
    </AppShell>
  );
}

/**
 * The headline counts, over the map.
 *
 * Deliberately not five identical cards: "needs review" is the only number
 * here that implies work, so it is the one set in the review colour and the
 * one that stays visible when the strip narrows.
 */
function StatStrip({
  total,
  review,
  verified,
  reports,
  dedup,
}: {
  total: number;
  review: number;
  verified: number;
  reports: number;
  dedup: number;
}) {
  const items = [
    { label: "Active", value: total, color: "var(--text-ink)", optional: false },
    { label: "Needs review", value: review, color: STATUS_COLORS.NEEDS_REVIEW, optional: false },
    { label: "Verified", value: verified, color: STATUS_COLORS.VERIFIED, optional: true },
    { label: "Reports/hr", value: reports, color: "var(--text-dim)", optional: true },
    { label: "Deduplicated", value: `${Math.round(dedup * 100)}%`, color: "var(--text-dim)", optional: true },
  ];
  return (
    <div className="panel rise absolute left-3 top-3 z-10 flex divide-x divide-[var(--hairline-soft)] overflow-hidden rounded-[var(--r-md)] md:left-4 md:top-4">
      {items.map((i) => (
        <div key={i.label} className={cn("px-5 py-4 md:px-7 md:py-5", i.optional && "hidden lg:block")}>
          <div className="text-[13.5px] text-[var(--text-faint)]">{i.label}</div>
          <div
            className="num mt-2.5 text-[28px] font-bold leading-none tracking-[-0.01em] md:text-[32px]"
            style={{ color: textHue(i.color) }}
          >
            {i.value}
          </div>
        </div>
      ))}
    </div>
  );
}
