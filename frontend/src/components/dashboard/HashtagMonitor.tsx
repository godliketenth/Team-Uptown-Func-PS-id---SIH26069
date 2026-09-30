import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { HashtagChip } from "@/components/ui/hashtag";
import { EmptyState } from "@/components/ui/empty";
import { useFilters } from "@/store/filters";
import { livePoll } from "@/lib/live";

/**
 * Live hashtag watchlist. #IMD and the rest of the tracked set are what the
 * collectors key on, so the dashboard shows which of them are actually
 * carrying traffic right now.
 */
export function HashtagMonitor({ hours }: { hours: number }) {
  const setEventTypes = useFilters((s) => s.setEventTypes);
  const eventTypes = useFilters((s) => s.eventTypes);

  const { data } = useQuery({
    queryKey: ["hashtags", hours],
    queryFn: () => api.hashtags({ hours, limit: 18 }),
    refetchInterval: livePoll(10000),
  });

  const rows = data?.rows ?? [];
  if (rows.length === 0) {
    return <EmptyState title="No hashtags yet" />;
  }

  return (
    <div className="scroll-thin h-full overflow-y-auto px-5 py-4">
      <div className="flex flex-wrap gap-2">
        {rows.map((r) => (
          <HashtagChip
            key={r.hashtag}
            tag={r.hashtag}
            tracked={r.tracked}
            count={r.report_count}
            eventType={r.top_event_type}
            active={r.top_event_type ? eventTypes.includes(r.top_event_type) : false}
            onClick={
              r.top_event_type
                ? () => {
                    const t = r.top_event_type!;
                    setEventTypes(
                      eventTypes.includes(t)
                        ? eventTypes.filter((x) => x !== t)
                        : [...eventTypes, t],
                    );
                  }
                : undefined
            }
          />
        ))}
      </div>
      <div className="num mt-3.5 text-[12px] text-[var(--text-faint)]">
        {data?.total_tagged_reports ?? 0} tagged reports in the last {hours}h
      </div>
    </div>
  );
}
