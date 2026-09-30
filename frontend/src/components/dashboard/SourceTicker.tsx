import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { SOURCE_LABELS } from "@/lib/domain";
import { relativeTime } from "@/lib/utils";
import type { SummaryCounts } from "@/lib/types";
import { useAuth } from "@/store/auth";
import { livePoll } from "@/lib/live";

/**
 * Source health at a glance. Signed-in analysts get real per-source status from
 * /admin/sources; the public view falls back to report volume per source type,
 * which needs no privilege.
 */
export function SourceTicker({ summary }: { summary?: SummaryCounts }) {
  const user = useAuth((s) => s.user);

  const { data: sources } = useQuery({
    queryKey: ["sources"],
    queryFn: api.sources,
    enabled: !!user,
    refetchInterval: livePoll(15000),
  });

  if (sources) {
    return (
      <div className="scroll-thin flex h-full flex-col gap-0.5 overflow-y-auto px-2 py-1.5">
        {sources.map((s) => {
          const color =
            s.status === "ACTIVE"
              ? "var(--color-st-verified)"
              : s.status === "PAUSED"
                ? "var(--color-st-unassessed)"
                : "var(--color-st-rejected)";
          return (
            <div
              key={s.id}
              className="flex items-center gap-2.5 rounded-[var(--r-sm)] px-3 py-2 transition-colors hover:bg-[var(--veil-1)]"
            >
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ backgroundColor: color, boxShadow: `0 0 6px ${color}` }}
              />
              <span className="min-w-0 flex-1 truncate text-[13.5px] text-[var(--text-dim)]">
                {s.name}
              </span>
              <span className="num shrink-0 text-[12px] text-[var(--text-faint)]">
                {s.raw_events_last_hour}/h
              </span>
              <span className="num w-[58px] shrink-0 text-right text-[12px] text-[var(--text-faint)]">
                {s.last_success_at ? relativeTime(s.last_success_at) : "—"}
              </span>
            </div>
          );
        })}
      </div>
    );
  }

  const bySource = summary?.reports_by_source_type ?? {};
  const total = Object.values(bySource).reduce((a, b) => a + b, 0) || 1;
  return (
    <div className="scroll-thin flex h-full flex-col gap-px overflow-y-auto">
      {Object.entries(SOURCE_LABELS).map(([key, label]) => {
        const count = bySource[key] ?? 0;
        return (
          <div
            key={key}
            className="flex items-center gap-2.5 rounded-[var(--r-sm)] px-3 py-2 transition-colors hover:bg-[var(--veil-1)]"
          >
            <span
              className="h-1.5 w-1.5 shrink-0 rounded-full"
              style={{
                backgroundColor: count > 0 ? "var(--color-st-verified)" : "var(--color-st-unassessed)",
                boxShadow: count > 0 ? "0 0 6px var(--color-st-verified)" : "none",
              }}
            />
            <span className="min-w-0 flex-1 truncate text-[13.5px] text-[var(--text-dim)]">{label}</span>
            <div className="h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-[var(--veil-1)]">
              <div
                className="h-full rounded-full bg-[var(--color-accent)] shadow-[0_0_8px_-2px_var(--color-accent)]"
                style={{ width: `${(count / total) * 100}%` }}
              />
            </div>
            <span className="num w-9 shrink-0 text-right text-[12px] text-[var(--text-faint)]">
              {count}
            </span>
          </div>
        );
      })}
    </div>
  );
}
