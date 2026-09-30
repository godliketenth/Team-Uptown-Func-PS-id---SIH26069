import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useApiFilters, useFilters } from "@/store/filters";
import { livePoll } from "@/lib/live";

/** Everything on the dashboard polls on the same 5s cadence. */
export const POLL_MS = 5000;

export function useDashboardData() {
  const filters = useApiFilters();
  const range = useFilters((s) => s.range);

  const events = useQuery({
    queryKey: ["events", filters],
    queryFn: () => api.events({ ...filters, limit: 200, sort: "last_updated", order: "desc" }),
    refetchInterval: livePoll(POLL_MS),
  });

  const mapEvents = useQuery({
    queryKey: ["map-events", filters],
    queryFn: () => api.mapEvents({ ...filters, limit: 2000 }),
    refetchInterval: livePoll(POLL_MS),
  });

  const summary = useQuery({
    queryKey: ["summary"],
    queryFn: api.summary,
    refetchInterval: livePoll(POLL_MS),
  });

  const timeline = useQuery({
    queryKey: ["timeline", range, filters.state, filters.event_type],
    queryFn: () =>
      api.timeline({
        hours: range === "1h" ? 3 : range === "6h" ? 6 : range === "7d" ? 168 : 24,
        bucket_minutes: range === "1h" ? 10 : range === "6h" ? 20 : range === "7d" ? 360 : 60,
        state: filters.state,
        event_type: filters.event_type,
      }),
    refetchInterval: livePoll(POLL_MS * 2),
  });

  return { events, mapEvents, summary, timeline };
}
