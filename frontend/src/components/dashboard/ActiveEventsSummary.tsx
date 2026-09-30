import { EVENT_COLORS, EVENT_GLYPHS, EVENT_LABELS, EVENT_TYPES } from "@/lib/domain";
import { useFilters } from "@/store/filters";
import type { SummaryCounts } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Count per event type, doubling as a one-click type filter.
 *
 * One column, not two. At the current type size the two-column grid truncated
 * half the labels — "Thunde…", "Dust St…" — and a filter you cannot read the
 * name of is not a filter.
 */
export function ActiveEventsSummary({ summary }: { summary?: SummaryCounts }) {
  const { eventTypes, setEventTypes } = useFilters();

  const toggle = (t: string) =>
    setEventTypes(
      eventTypes.includes(t as never)
        ? (eventTypes.filter((x) => x !== t) as never)
        : ([...eventTypes, t] as never),
    );

  return (
    <div className="flex flex-col gap-1.5 p-3.5">
      {EVENT_TYPES.map((t) => {
        const count = summary?.events_by_type?.[t] ?? 0;
        const active = eventTypes.includes(t);
        return (
          <button
            key={t}
            onClick={() => toggle(t)}
            className={cn(
              "flex cursor-pointer items-center gap-3 rounded-[var(--r-md)] border px-4 py-3.5 text-left transition-all duration-150",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]/60",
              active
                ? "border-[var(--hairline)] bg-[var(--veil-1)]"
                : "border-transparent hover:border-[var(--hairline-soft)] hover:bg-[var(--veil-2)]",
            )}
            title={`Filter to ${EVENT_LABELS[t]}`}
            aria-pressed={active}
          >
            <span
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[14px] transition-all"
              style={{
                backgroundColor: `color-mix(in oklab, ${EVENT_COLORS[t]} ${active ? 38 : 16}%, transparent)`,
                color: EVENT_COLORS[t],
                boxShadow: active ? `0 0 12px -3px ${EVENT_COLORS[t]}` : "none",
              }}
            >
              {EVENT_GLYPHS[t]}
            </span>
            <span
              className={cn(
                "min-w-0 flex-1 truncate text-[15.5px]",
                active ? "text-[var(--text-ink)]" : "text-[var(--text-dim)]",
              )}
            >
              {EVENT_LABELS[t]}
            </span>
            <span
              className="num text-[19px] font-bold tracking-[-0.01em]"
              style={{ color: count > 0 ? EVENT_COLORS[t] : "var(--text-faint)" }}
            >
              {count}
            </span>
          </button>
        );
      })}
    </div>
  );
}
