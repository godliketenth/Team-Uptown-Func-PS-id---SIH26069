import * as React from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EVENT_COLORS, EVENT_LABELS, EVENT_TYPES } from "@/lib/domain";
import type { TimelineOut } from "@/lib/types";
import { WaitingState } from "@/components/ui/empty";
import { useChartTheme } from "@/lib/chartTheme";

/**
 * Reports per hour, stacked by event type.
 *
 * Memoised on `data` and `loading`. The dashboard polls four endpoints on a
 * five-second cadence and every one of them re-renders the page; without this
 * the chart rebuilt its whole SVG each time, which read as a flicker across the
 * bottom of the screen. Recharts has no internal guard against that — it is the
 * caller's job to hand it stable props.
 */
function TimelineChartInner({ data, loading }: { data?: TimelineOut; loading: boolean }) {
  const chart = useChartTheme();

  // Hooks before any early return.
  const rows = React.useMemo(
    () =>
      (data?.buckets ?? []).map((b) => ({
        t: new Date(b.bucket).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }),
        ...b.counts,
      })),
    [data],
  );
  const empty = React.useMemo(
    () => (data?.buckets ?? []).every((b) => b.total === 0),
    [data],
  );

  if (loading && !data) return <WaitingState title="Building timeline" detail="" />;
  if (!data) return null;

  return (
    <div className="relative h-full w-full">
      {empty && (
        <div className="absolute inset-0 z-10 flex items-center justify-center">
          <span className="text-[13px] text-[var(--text-faint)]">
            No reports in this window yet
          </span>
        </div>
      )}
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows} margin={{ top: 8, right: 10, left: 2, bottom: 0 }}>
          <defs>
            {EVENT_TYPES.map((t) => (
              <linearGradient key={t} id={`grad-${t}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={EVENT_COLORS[t]} stopOpacity={0.62} />
                <stop offset="100%" stopColor={EVENT_COLORS[t]} stopOpacity={0.06} />
              </linearGradient>
            ))}
          </defs>
          <XAxis
            dataKey="t"
            tick={chart.tick}
            axisLine={chart.axisLine}
            tickLine={false}
            minTickGap={28}
          />
          <YAxis
            tick={chart.tick}
            axisLine={false}
            tickLine={false}
            width={34}
            allowDecimals={false}
            tickMargin={4}
          />
          <Tooltip
            contentStyle={chart.tooltipContent}
            labelStyle={chart.tooltipLabel}
            itemStyle={chart.tooltipItem}
            formatter={(value, name) => [
              value as number,
              EVENT_LABELS[name as keyof typeof EVENT_LABELS] ?? String(name),
            ]}
          />
          {EVENT_TYPES.map((t) => (
            <Area
              key={t}
              type="monotone"
              dataKey={t}
              stackId="1"
              stroke={EVENT_COLORS[t]}
              strokeWidth={1.4}
              fill={`url(#grad-${t})`}
              isAnimationActive={false}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export const TimelineChart = React.memo(TimelineChartInner);
