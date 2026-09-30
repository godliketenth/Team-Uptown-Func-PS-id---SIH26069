import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Panel, SectionLabel, Stat } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { WaitingState } from "@/components/ui/empty";
import { api } from "@/lib/api";
import { fmtDateTime, fmtPct } from "@/lib/utils";
import { AdminPage } from "./AdminPage";
import { livePoll } from "@/lib/live";
import { useChartTheme } from "@/lib/chartTheme";
import { STATUS_COLORS } from "@/lib/domain";

/* The ingest pipeline is a sequence, so its bars read as a progression from
   "just arrived" (warm stone) to "assigned to an event" (the verified green
   already used for a settled report elsewhere in the console). */
const STAGE_COLORS: Record<string, string> = {
  RECEIVED: "#7A6F62",
  NORMALIZED: "#9E9285",
  ENRICHED: "#4A90D9",
  CLASSIFIED: "#8E5FC4",
  DEDUPLICATED: "#E8A83A",
  EVENT_ASSIGNED: "#45B87C",
};

export function AdminHealth() {
  const chart = useChartTheme();
  const { data, isLoading } = useQuery({
    queryKey: ["system-health"],
    queryFn: api.systemHealth,
    refetchInterval: livePoll(4000),
  });

  const { data: byState } = useQuery({
    queryKey: ["by-state"],
    queryFn: () => api.byState(24),
    refetchInterval: livePoll(15000),
  });

  if (isLoading || !data) {
    return (
      <AdminPage title="System Health">
        <WaitingState title="Reading pipeline telemetry" detail="" />
      </AdminPage>
    );
  }

  const healthy = data.status === "healthy";

  return (
    <AdminPage
      title="System Health"
      subtitle="Collector, bus and pipeline telemetry."
      actions={
        <Badge color={healthy ? STATUS_COLORS.VERIFIED : STATUS_COLORS.REJECTED}>{data.status}</Badge>
      }
    >
      <div className="scroll-thin flex-1 overflow-y-auto p-4">
        <div className="grid grid-cols-4 gap-3.5">
          <Panel className="lift p-4">
            <Stat
              label="Scheduler"
              value={data.scheduler_running ? "running" : "stopped"}
              hint={
                data.seconds_since_tick !== null
                  ? `last tick ${data.seconds_since_tick.toFixed(1)}s ago`
                  : "no tick yet"
              }
              color={data.scheduler_running ? STATUS_COLORS.VERIFIED : STATUS_COLORS.REJECTED}
            />
          </Panel>
          <Panel className="lift p-4">
            <Stat
              label="Bus throughput"
              value={data.bus.processed}
              hint={
                /* With Kafka the backlog is the consumer-group lag, which is
                   unavailable until partitions are assigned — an em dash is
                   honest there, a zero would not be. */
                `${data.bus.pending ?? "—"} ${
                  data.bus.transport === "kafka" ? "lag" : "pending"
                } · ${data.bus.published} published · ${data.bus.transport}`
              }
            />
          </Panel>
          <Panel className="lift p-4">
            <Stat
              label="Error rate"
              value={fmtPct(data.error_rate)}
              hint={`${data.bus.failed} failed`}
              color={data.error_rate > 0.1 ? STATUS_COLORS.REJECTED : STATUS_COLORS.VERIFIED}
            />
          </Panel>
          <Panel className="lift p-4">
            <Stat
              label="Corroboration"
              value={data.open_meteo_enabled ? "Open-Meteo live" : "offline"}
              hint={data.open_meteo_enabled ? "real observations in use" : "neutral 0.5 fallback"}
              color={data.open_meteo_enabled ? "#4A90D9" : STATUS_COLORS.DETECTED}
            />
          </Panel>
        </div>

        <div className="mt-3.5 grid grid-cols-3 gap-3.5">
          <Panel className="col-span-2 flex h-[256px] flex-col">
            <SectionLabel right={<span className="num text-[12.5px] text-[var(--text-faint)]">reports per stage</span>}>
              Pipeline stages
            </SectionLabel>
            <div className="min-h-0 flex-1 p-2">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={data.pipeline_stages.map((s) => ({
                    stage: s.stage.replace("_", " ").toLowerCase(),
                    count: s.count,
                    key: s.stage,
                  }))}
                  margin={{ top: 8, right: 8, left: -20, bottom: 0 }}
                >
                  <XAxis
                    dataKey="stage"
                    tick={chart.tick}
                    axisLine={chart.axisLine}
                    tickLine={false}
                  />
                  <YAxis
                    tick={chart.tick}
                    axisLine={false}
                    tickLine={false}
                    allowDecimals={false}
                  />
                  <Tooltip
                    cursor={chart.cursorFill}
                    contentStyle={chart.tooltipContent}
                    labelStyle={chart.tooltipLabel}
                    itemStyle={chart.tooltipItem}
                  />
                  <Bar dataKey="count" isAnimationActive={false} radius={[5, 5, 0, 0]}>
                    {data.pipeline_stages.map((s) => (
                      <Cell key={s.stage} fill={STAGE_COLORS[s.stage] ?? "#4A90D9"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Panel>

          <Panel className="flex h-[256px] flex-col">
            <SectionLabel>Storage</SectionLabel>
            <div className="grid grid-cols-2 gap-4 p-4">
              <Stat label="Raw events" value={data.raw_events_total} />
              <Stat label="Reports" value={data.reports_total} />
              <Stat label="Events" value={data.events_total} />
              <Stat label="Lake objects" value={data.raw_lake.objects} />
            </div>
            <div className="mt-auto border-t border-[var(--hairline-soft)] px-3.5 py-2.5">
              <div className="label flex items-center justify-between">
                <span>Raw lake root</span>
                <span
                  className="rounded-full border px-1.5 py-[1px] text-[12px] font-semibold normal-case tracking-normal"
                  style={
                    data.raw_lake.backend === "s3"
                      ? {
                          color: STATUS_COLORS.VERIFIED,
                          borderColor: `color-mix(in oklab, ${STATUS_COLORS.VERIFIED} 32%, transparent)`,
                          backgroundColor: `color-mix(in oklab, ${STATUS_COLORS.VERIFIED} 13%, transparent)`,
                        }
                      : {
                          color: "var(--text-dim)",
                          borderColor: "var(--hairline)",
                          backgroundColor: "var(--veil-1)",
                        }
                  }
                  title={
                    data.raw_lake.backend === "s3"
                      ? `S3-compatible object store at ${data.raw_lake.endpoint ?? "configured endpoint"}`
                      : "Local filesystem — set S3_ENDPOINT_URL to use object storage"
                  }
                >
                  {data.raw_lake.backend === "s3" ? "object store" : "local disk"}
                </span>
              </div>
              <div className="num mt-0.5 truncate text-[12.5px] text-[var(--text-dim)]">
                {data.raw_lake.root}
              </div>
              <div className="num text-[12px] text-[var(--text-faint)]">
                {data.raw_lake.partitions} partitions
              </div>
            </div>
          </Panel>
        </div>

        <div className="mt-3.5 grid grid-cols-2 gap-3.5">
          <Panel className="flex flex-col">
            <SectionLabel right={<span className="num text-[12.5px] text-[var(--text-faint)]">last 24h</span>}>
              Activity by state
            </SectionLabel>
            <div className="scroll-thin max-h-[260px] overflow-y-auto">
              {(byState ?? []).slice(0, 12).map((row) => (
                <div
                  key={row.state}
                  className="flex items-center gap-2 border-b border-[var(--hairline-soft)] px-3.5 py-2 transition-colors hover:bg-[var(--veil-1)]"
                >
                  <span className="min-w-0 flex-1 truncate text-[13px] text-[var(--text-ink)]">
                    {row.state}
                  </span>
                  <span className="num w-10 shrink-0 text-right text-[12.5px] text-[var(--text-dim)]">
                    {row.event_count}e
                  </span>
                  <span className="num w-10 shrink-0 text-right text-[12.5px] text-[var(--text-faint)]">
                    {row.report_count}r
                  </span>
                  <span className="w-[86px] shrink-0 text-right text-[12px] uppercase tracking-wider text-[var(--text-faint)]">
                    {row.dominant_event_type?.replace("_", " ").toLowerCase() ?? "—"}
                  </span>
                </div>
              ))}
            </div>
          </Panel>

          <Panel className="flex flex-col">
            <SectionLabel>Last pipeline error</SectionLabel>
            <div className="p-3">
              {data.bus.last_error ? (
                <pre className="num whitespace-pre-wrap break-all text-[12.5px] leading-relaxed text-[var(--color-st-rejected)]">
                  {data.bus.last_error}
                </pre>
              ) : (
                <div className="text-[13px] text-[var(--text-faint)]">
                  No pipeline errors recorded since startup.
                </div>
              )}
              {data.last_tick_at && (
                <div className="num mt-3 text-[12.5px] text-[var(--text-faint)]">
                  last ingest tick · {fmtDateTime(data.last_tick_at)}
                </div>
              )}
            </div>
          </Panel>
        </div>
      </div>
    </AdminPage>
  );
}
