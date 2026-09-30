import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { EventTypeBadge, SeverityBadge, StatusBadge } from "@/components/ui/badge";
import { Meter } from "@/components/ui/panel";
import { NativeSelect } from "@/components/ui/select";
import { EmptyState, WaitingState } from "@/components/ui/empty";
import { EventDetailPanel } from "@/components/dashboard/EventDetailPanel";
import { api } from "@/lib/api";
import { EVENT_STATUSES, STATUS_COLORS, STATUS_LABELS } from "@/lib/domain";
import { fmtDateTime, fmtPct, relativeTime, shortId } from "@/lib/utils";
import type { EventStatus } from "@/lib/types";
import { AdminPage } from "./AdminPage";
import { livePoll } from "@/lib/live";

const SORTS = [
  { value: "last_updated", label: "Last updated" },
  { value: "start_time", label: "Start time" },
  { value: "report_count", label: "Report count" },
  { value: "evidence_score", label: "Evidence score" },
];

export function AdminEvents() {
  const [selected, setSelected] = React.useState<string | null>(null);
  const [status, setStatus] = React.useState("");
  const [sort, setSort] = React.useState("last_updated");

  const { data, isLoading } = useQuery({
    queryKey: ["admin-events", status, sort],
    queryFn: () =>
      api.events({
        limit: 300,
        sort,
        order: "desc",
        status: status ? [status as EventStatus] : undefined,
      }),
    refetchInterval: livePoll(8000),
  });

  const items = data?.items ?? [];

  return (
    <AdminPage
      title="Events"
      subtitle="Every clustered event, including resolved and rejected ones."
      actions={
        <div className="flex items-center gap-2">
          <NativeSelect
            className="w-[140px]"
            value={status}
            onChange={setStatus}
            placeholder="All statuses"
            options={EVENT_STATUSES.map((s) => ({ value: s, label: STATUS_LABELS[s] }))}
          />
          <NativeSelect className="w-[140px]" value={sort} onChange={setSort} options={SORTS} />
          <span className="num text-[14px] text-[var(--text-dim)]">{data?.total ?? 0}</span>
        </div>
      }
    >
      {isLoading ? (
        <WaitingState title="Loading events" detail="" />
      ) : items.length === 0 ? (
        <EmptyState title="No events match" />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Event</Th>
              <Th>Location</Th>
              <Th>Status</Th>
              <Th>Severity</Th>
              <Th className="text-right">Reports</Th>
              <Th className="text-right">Sources</Th>
              <Th className="w-[130px]">Evidence</Th>
              <Th>Started</Th>
              <Th>Updated</Th>
            </tr>
          </thead>
          <tbody>
            {items.map((e) => (
              <Tr key={e.id} onClick={() => setSelected(e.id)} active={selected === e.id}>
                <Td>
                  <EventTypeBadge type={e.event_type} />
                  <div className="num mt-1 text-[12px] text-[var(--text-faint)]">
                    EVT-{shortId(e.id)}
                  </div>
                </Td>
                <Td>
                  <div className="text-[var(--text-ink)]">{e.district ?? "—"}</div>
                  <div className="text-[12px] text-[var(--text-faint)]">{e.state ?? ""}</div>
                </Td>
                <Td>
                  <StatusBadge status={e.status} />
                </Td>
                <Td>
                  <SeverityBadge severity={e.severity} />
                </Td>
                <Td className="num text-right text-[var(--text-ink)]">{e.report_count}</Td>
                <Td className="num text-right text-[var(--text-dim)]">{e.source_count}</Td>
                <Td>
                  <div className="flex items-center gap-2">
                    <Meter value={e.evidence_score} color={STATUS_COLORS[e.status]} />
                    <span className="num w-8 shrink-0 text-right text-[12.5px] text-[var(--text-dim)]">
                      {fmtPct(e.evidence_score)}
                    </span>
                  </div>
                </Td>
                <Td className="num text-[var(--text-faint)]">{fmtDateTime(e.start_time)}</Td>
                <Td className="num text-[var(--text-faint)]">{relativeTime(e.last_updated)}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
      <EventDetailPanel eventId={selected} onClose={() => setSelected(null)} />
    </AdminPage>
  );
}
