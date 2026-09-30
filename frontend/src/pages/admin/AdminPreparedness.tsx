import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { Panel, SectionLabel, Stat } from "@/components/ui/panel";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { EventTypeBadge } from "@/components/ui/badge";
import { WaitingState } from "@/components/ui/empty";
import { api } from "@/lib/api";
import { EVENT_COLORS, EVENT_TYPES, WARNING_COLORS } from "@/lib/domain";
import { fmtPct } from "@/lib/utils";
import { AdminPage } from "./AdminPage";
import { livePoll } from "@/lib/live";

/**
 * The historical view a disaster-management body plans against.
 *
 * Deliberately states its own limits: with less than a year of data, seasonal
 * and monsoon-cycle analysis is not possible, and the coverage note says so
 * rather than implying otherwise.
 */
export function AdminPreparedness() {
  const { data, isLoading } = useQuery({
    queryKey: ["preparedness"],
    queryFn: () => api.preparedness(7, 15),
    refetchInterval: livePoll(30000),
  });

  if (isLoading || !data) {
    return (
      <AdminPage title="Preparedness">
        <WaitingState title="Building risk profile" detail="" />
      </AdminPage>
    );
  }

  const peakHour = data.hour_of_day.reduce(
    (best, h) => (h.total > best.total ? h : best),
    data.hour_of_day[0],
  );
  const maxHour = Math.max(1, ...data.hour_of_day.map((h) => h.total));

  return (
    <AdminPage
      title="Preparedness"
      subtitle="Which districts are hit repeatedly, by what hazard, and how fast we flag it."
    >
      <div className="scroll-thin flex-1 overflow-y-auto p-4">
        <div className="mb-3.5 flex gap-2 rounded-[var(--r-md)] border border-[var(--hairline)] bg-[var(--veil-2)] px-3 py-2.5">
          <Info className="mt-px h-3.5 w-3.5 shrink-0 text-[var(--text-faint)]" />
          <span className="text-[13px] leading-relaxed text-[var(--text-dim)]">
            {data.coverage_note}
          </span>
        </div>

        <div className="grid grid-cols-4 gap-3.5">
          <Panel className="lift p-4">
            <Stat
              label="Districts affected"
              value={data.districts.length}
              hint={`over ${Math.round(data.data_span_hours)}h`}
            />
          </Panel>
          <Panel className="lift p-4">
            <Stat
              label="Highest burden"
              value={data.districts[0]?.district ?? "—"}
              hint={`${data.districts[0]?.red_alerts ?? 0} red alerts`}
              color={data.districts[0]?.red_alerts ? WARNING_COLORS.RED : undefined}
            />
          </Panel>
          <Panel className="lift p-4">
            <Stat
              label="Peak reporting hour"
              value={`${String(peakHour?.hour_ist ?? 0).padStart(2, "0")}:00`}
              hint="IST, across all hazards"
            />
          </Panel>
          <Panel className="lift p-4">
            <Stat
              label="Detection lead"
              value={
                data.detection.median_minutes === null
                  ? "—"
                  : `${Math.round(data.detection.median_minutes)}m`
              }
              hint={`median, n=${data.detection.measured}`}
            />
          </Panel>
        </div>

        <Panel className="mt-3.5 flex flex-col">
          <SectionLabel
            right={
              <span className="num text-[12.5px] text-[var(--text-faint)]">
                events per hour of day · IST
              </span>
            }
          >
            When hazards are reported
          </SectionLabel>
          <div className="p-4">
            <div className="flex h-28 items-stretch gap-[3px]">
              {data.hour_of_day.map((h) => (
                <div key={h.hour_ist} className="group flex h-full flex-1 flex-col justify-end gap-px">
                  {EVENT_TYPES.filter((t) => h.counts[t] > 0).map((t) => (
                    <div
                      key={t}
                      style={{
                        height: `${(h.counts[t] / maxHour) * 100}%`,
                        backgroundColor: EVENT_COLORS[t],
                      }}
                      className="w-full shrink-0 rounded-[1px] opacity-85 transition-opacity group-hover:opacity-100"
                      title={`${String(h.hour_ist).padStart(2, "0")}:00 — ${t} ${h.counts[t]}`}
                    />
                  ))}
                </div>
              ))}
            </div>
            <div className="num mt-1.5 flex justify-between text-[12px] text-[var(--text-faint)]">
              {[0, 4, 8, 12, 16, 20, 23].map((h) => (
                <span key={h}>{String(h).padStart(2, "0")}</span>
              ))}
            </div>
            <div className="mt-2.5 flex flex-wrap gap-x-3 gap-y-1">
              {EVENT_TYPES.filter((t) => data.hazard_totals[t] > 0).map((t) => (
                <span key={t} className="flex items-center gap-1.5">
                  <span
                    className="h-2 w-2 rounded-[1px]"
                    style={{ backgroundColor: EVENT_COLORS[t] }}
                  />
                  <span className="text-[12.5px] capitalize text-[var(--text-dim)]">
                    {t.replace("_", " ").toLowerCase()}
                  </span>
                  <span className="num text-[12.5px] text-[var(--text-faint)]">
                    {data.hazard_totals[t]}
                  </span>
                </span>
              ))}
            </div>
          </div>
        </Panel>

        <Panel className="mt-3.5 flex flex-col">
          <SectionLabel
            right={
              <span className="num text-[12.5px] text-[var(--text-faint)]">
                ranked by alert burden
              </span>
            }
          >
            District risk profile
          </SectionLabel>
          <Table>
            <thead>
              <tr>
                <Th>District</Th>
                <Th>Dominant hazard</Th>
                <Th>Hazard mix</Th>
                <Th className="text-right">Events</Th>
                <Th className="text-right">Alerts</Th>
                <Th className="text-right">Red</Th>
                <Th className="text-right">Evidence</Th>
              </tr>
            </thead>
            <tbody>
              {data.districts.map((d) => {
                const total = Object.values(d.hazard_counts).reduce((a, b) => a + b, 0) || 1;
                return (
                  <Tr key={`${d.district}-${d.state}`}>
                    <Td>
                      <div className="text-[var(--text-ink)]">{d.district}</div>
                      <div className="text-[12px] text-[var(--text-faint)]">{d.state}</div>
                    </Td>
                    <Td>
                      {d.dominant_hazard ? (
                        <EventTypeBadge type={d.dominant_hazard} />
                      ) : (
                        <span className="text-[var(--text-faint)]">—</span>
                      )}
                    </Td>
                    <Td>
                      <div className="flex h-2 w-[140px] overflow-hidden rounded-full bg-[var(--veil-1)]">
                        {EVENT_TYPES.filter((t) => d.hazard_counts[t]).map((t) => (
                          <div
                            key={t}
                            style={{
                              width: `${(d.hazard_counts[t] / total) * 100}%`,
                              backgroundColor: EVENT_COLORS[t],
                            }}
                            title={`${t} ${d.hazard_counts[t]}`}
                          />
                        ))}
                      </div>
                    </Td>
                    <Td className="num text-right text-[var(--text-ink)]">{d.event_count}</Td>
                    <Td className="num text-right text-[var(--text-dim)]">{d.alert_count}</Td>
                    <Td className="num text-right">
                      <span style={{ color: d.red_alerts ? WARNING_COLORS.RED : undefined }}>
                        {d.red_alerts}
                      </span>
                    </Td>
                    <Td className="num text-right text-[var(--text-dim)]">
                      {fmtPct(d.avg_evidence)}
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
          <div className="border-t border-[var(--hairline-soft)] px-5 py-2.5 text-[12.5px] text-[var(--text-faint)]">
            {data.detection.note}
          </div>
        </Panel>
      </div>
    </AdminPage>
  );
}
