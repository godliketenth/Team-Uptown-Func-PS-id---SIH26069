import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import {
  EventTypeBadge,
  SeverityBadge,
  StatusBadge,
  WarningBadge,
} from "@/components/ui/badge";
import { EvidencePanel } from "@/components/dashboard/EvidencePanel";
import { EmptyState, WaitingState } from "@/components/ui/empty";
import { PanelTitle } from "@/components/ui/panel";
import { api } from "@/lib/api";
import { WARNING_COLORS, atLeast } from "@/lib/domain";
import {
  fmtCoord,
  fmtDateTime,
  fmtPct,
  relativeTime,
  shortId,
} from "@/lib/utils";
import { useAuth } from "@/store/auth";
import { livePoll } from "@/lib/live";
import { cn } from "@/lib/utils";
import type { WeatherEvent } from "@/lib/types";

/**
 * Verify — the decision.
 *
 * One question: is this reported event real. There is no map on this screen,
 * which is the point. Deciding is a reading task — you compare an event's
 * evidence against its corroboration and its sources — and a map of the whole
 * country tells you nothing about whether 33 reports from Bengaluru are a real
 * thunderstorm or one rumour repeated. The queue stays on the left so the next
 * decision is always one keystroke away, and the evidence that produced the
 * status sits beside it rather than behind a slide-over.
 *
 * Weakest evidence first: that is where a human verdict changes the outcome.
 */
export function Verify() {
  const [picked, setPicked] = React.useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["verification-queue"],
    queryFn: () => api.verificationQueue(200),
    refetchInterval: livePoll(5000),
  });

  const items = React.useMemo(() => data?.items ?? [], [data]);

  // Derived, not stored. The queue refetches every few seconds and an event
  // leaves it the moment it is decided, so a selection held in state goes
  // stale on its own; falling back to the head of the queue means deciding one
  // event advances you to the next without any synchronising effect.
  const selected = React.useMemo(() => {
    if (picked && items.some((i) => i.id === picked)) return picked;
    return items[0]?.id ?? null;
  }, [picked, items]);

  // j/k walk the queue. A verifier working a backlog should not have to move
  // their hand to the mouse between decisions.
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (e.key !== "j" && e.key !== "k") return;
      e.preventDefault();
      const idx = items.findIndex((i) => i.id === selected);
      const next = e.key === "j" ? idx + 1 : idx - 1;
      if (next >= 0 && next < items.length) setPicked(items[next].id);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [items, selected]);

  return (
    <AppShell>
      <div className="flex min-h-0 flex-1">
        <section className="flex w-[380px] shrink-0 flex-col divider-y xl:w-[430px]">
          <PanelTitle
            right={
              <span className="num text-[13px] text-[var(--text-faint)]">
                {data?.total ?? 0} pending
              </span>
            }
          >
            Awaiting a verdict
          </PanelTitle>

          {isLoading ? (
            <WaitingState title="Loading queue" detail="" />
          ) : items.length === 0 ? (
            <EmptyState
              title="Queue is clear"
              detail="Events arrive here once three independent sources report the same thing."
            />
          ) : (
            <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
              {items.map((e) => (
                <QueueRow
                  key={e.id}
                  event={e}
                  selected={selected === e.id}
                  onSelect={() => setPicked(e.id)}
                />
              ))}
            </div>
          )}

          <div className="shrink-0 border-t border-[var(--hairline-soft)] px-4 py-2">
            <span className="text-[14px] text-[var(--text-faint)]">
              Press <kbd className="num text-[var(--text-dim)]">j</kbd> and{" "}
              <kbd className="num text-[var(--text-dim)]">k</kbd> to move
              through the queue
            </span>
          </div>
        </section>

        <section className="min-w-0 flex-1">
          {selected ? (
            <Decision key={selected} eventId={selected} />
          ) : (
            <EmptyState
              title="Select an event"
              detail="Its evidence will appear here."
            />
          )}
        </section>
      </div>
    </AppShell>
  );
}

/**
 * A queue row.
 *
 * The left edge states the warning level, so the column can be read as a
 * severity profile without reading a single word. Evidence is shown as a
 * percentage rather than a meter here: at this row height a meter is a
 * decoration, and the number is what gets compared.
 */
function QueueRow({
  event,
  selected,
  onSelect,
}: {
  event: WeatherEvent;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      data-selected={selected}
      className={cn(
        "edge-row rule block w-full cursor-pointer px-5 py-5 text-left",
        "focus-visible:outline focus-visible:-outline-offset-2 focus-visible:outline-2 focus-visible:outline-[var(--accent)]",
      )}
      style={{ borderLeftColor: WARNING_COLORS[event.warning_level] }}
      aria-pressed={selected}
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="truncate text-[15.5px] font-bold text-[var(--text-ink)]">
          {event.district ?? "Unresolved district"}
          {event.state && (
            <span className="text-[var(--text-faint)]">, {event.state}</span>
          )}
        </span>
        <span className="num shrink-0 text-[14px] text-[var(--text-faint)]">
          {relativeTime(event.last_updated)}
        </span>
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5">
        <EventTypeBadge type={event.event_type} />
        <StatusBadge status={event.status} />
        <SeverityBadge severity={event.severity} />
      </div>

      <div className="num mt-3 flex items-center gap-4 text-[14px] text-[var(--text-faint)]">
        <span>
          <span className="text-[var(--text-dim)]">{event.report_count}</span>{" "}
          reports
        </span>
        <span>
          <span className="text-[var(--text-dim)]">{event.source_count}</span>{" "}
          sources
        </span>
        <span>
          <span className="text-[var(--text-dim)]">
            {fmtPct(event.evidence_score)}
          </span>{" "}
          evidence
        </span>
      </div>
    </button>
  );
}

/** The decision surface for one event: evidence, then the verdict. */
function Decision({ eventId }: { eventId: string }) {
  const user = useAuth((s) => s.user);
  const qc = useQueryClient();
  const [reason, setReason] = React.useState("");

  const { data: event, isLoading } = useQuery({
    queryKey: ["event", eventId],
    queryFn: () => api.event(eventId),
    refetchInterval: livePoll(5000),
  });

  const decide = useMutation({
    mutationFn: ({ action }: { action: "verify" | "reject" }) =>
      action === "verify"
        ? api.verify(eventId, reason)
        : api.reject(eventId, reason),
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

  if (isLoading || !event) {
    return (
      <WaitingState
        title="Loading event"
        detail="Fetching evidence and contributing reports."
      />
    );
  }

  return (
    <div className="flex h-full flex-col">
      <header
        className="shrink-0 divider-x px-5 py-4"
        style={{
          borderLeft: `3px solid ${WARNING_COLORS[event.warning_level]}`,
        }}
      >
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="display text-[26px] leading-none">
            {event.district ?? "Unresolved district"}
            {event.state && (
              <span className="font-medium text-[var(--text-faint)]">
                , {event.state}
              </span>
            )}
          </h2>
          <span className="num shrink-0 text-[13px] text-[var(--text-faint)]">
            EVT-{shortId(event.id)} · {fmtCoord(event.center_latitude)},{" "}
            {fmtCoord(event.center_longitude)}
          </span>
        </div>

        <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5">
          <WarningBadge level={event.warning_level} />
          <EventTypeBadge type={event.event_type} />
          <StatusBadge status={event.status} />
          <SeverityBadge severity={event.severity} />
        </div>

        <div className="num mt-2 text-[13px] text-[var(--text-faint)]">
          started {fmtDateTime(event.start_time)} · updated{" "}
          {relativeTime(event.last_updated)}
        </div>
      </header>

      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-5 py-5">
        <div className="max-w-[860px]">
          <EvidencePanel event={event} />
        </div>
      </div>

      {canDecide && (
        <footer className="shrink-0 border-t border-[var(--hairline-soft)] bg-[var(--veil-2)] px-5 py-3.5">
          <div className="max-w-[860px]">
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why — recorded in the audit log"
              className="mb-3.5 w-full rounded-[var(--r-md)] border border-[var(--hairline)] bg-[var(--veil-1)] px-4 py-3.5 text-[15.5px] text-[var(--text-ink)] placeholder:text-[var(--text-faint)] focus-visible:border-[var(--accent)] focus-visible:outline-none"
            />
            <div className="flex gap-2.5">
              <Button
                variant="verify"
                size="lg"
                className="flex-1"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ action: "verify" })}
              >
                <Check className="h-4 w-4" /> Verify
              </Button>
              <Button
                variant="reject"
                size="lg"
                className="flex-1"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ action: "reject" })}
              >
                <X className="h-4 w-4" /> Reject
              </Button>
            </div>
          </div>
        </footer>
      )}
    </div>
  );
}
