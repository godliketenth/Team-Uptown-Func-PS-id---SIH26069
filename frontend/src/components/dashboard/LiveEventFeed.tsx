import * as React from "react";
import { EventTypeBadge, StatusBadge, WarningBadge } from "@/components/ui/badge";
import { EmptyState, WaitingState } from "@/components/ui/empty";
import { cn, relativeTime, shortId } from "@/lib/utils";
import type { WeatherEvent } from "@/lib/types";

export function LiveEventFeed({
  events,
  loading,
  selectedId,
  onSelect,
}: {
  events: WeatherEvent[];
  loading: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  // Anything not present on the previous poll is flashed once.
  const seenRef = React.useRef<Set<string>>(new Set());
  const [fresh, setFresh] = React.useState<Set<string>>(new Set());

  React.useEffect(() => {
    const incoming = new Set<string>();
    for (const e of events) {
      if (!seenRef.current.has(e.id)) incoming.add(e.id);
      seenRef.current.add(e.id);
    }
    if (incoming.size === 0) return;
    setFresh(incoming);
    const timer = setTimeout(() => setFresh(new Set()), 2600);
    return () => clearTimeout(timer);
  }, [events]);

  if (loading && events.length === 0) {
    return <WaitingState detail="First reports are being normalized, classified and clustered." />;
  }
  if (events.length === 0) {
    return <EmptyState title="No events in range" detail="Widen the time range or clear filters." />;
  }

  return (
    <div className="scroll-thin h-full overflow-y-auto p-3.5">
      {events.map((e) => (
        <button
          key={e.id}
          onClick={() => onSelect(e.id)}
          className={cn(
            "mb-3 block w-full cursor-pointer rounded-[var(--r-lg)] border px-4 py-4 text-left transition-all duration-150",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]/60",
            selectedId === e.id
              ? "border-[var(--color-accent)]/35 bg-[color-mix(in_oklab,var(--color-accent)_12%,transparent)]"
              : "border-[var(--hairline-soft)] bg-[var(--veil-2)] hover:border-[var(--hairline)] hover:bg-[var(--veil-1)]",
            fresh.has(e.id) && "feed-new",
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <EventTypeBadge type={e.event_type} />
            <span className="num text-[12px] text-[var(--text-faint)]">
              {relativeTime(e.last_updated)}
            </span>
          </div>
          <div className="mt-3 truncate text-[15px] font-bold text-[var(--text-ink)]">
            {e.district ?? "Unresolved district"}
            <span className="text-[var(--text-faint)]">{e.state ? `, ${e.state}` : ""}</span>
          </div>
          <div className="mt-3 flex items-center gap-2.5">
            <WarningBadge level={e.warning_level} showAction={false} />
            <StatusBadge status={e.status} />
            <span className="num ml-auto text-[12px] text-[var(--text-dim)]">
              {e.report_count}r · {e.source_count}s · {Math.round(e.evidence_score * 100)}%
            </span>
          </div>
          <div className="num mt-2 text-[13px] text-[var(--text-faint)]">EVT-{shortId(e.id)}</div>
        </button>
      ))}
    </div>
  );
}
