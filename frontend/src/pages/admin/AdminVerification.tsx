import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { EventTypeBadge, SeverityBadge, StatusBadge } from "@/components/ui/badge";
import { Meter } from "@/components/ui/panel";
import { EmptyState, WaitingState } from "@/components/ui/empty";
import { EventDetailPanel } from "@/components/dashboard/EventDetailPanel";
import { api } from "@/lib/api";
import { STATUS_COLORS } from "@/lib/domain";
import { fmtCoord, fmtPct, relativeTime, shortId } from "@/lib/utils";
import { AdminPage } from "./AdminPage";
import { livePoll } from "@/lib/live";

export function AdminVerification() {
  const [selected, setSelected] = React.useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["verification-queue"],
    queryFn: () => api.verificationQueue(200),
    refetchInterval: livePoll(5000),
  });

  const items = data?.items ?? [];

  return (
    <AdminPage
      title="Verification Queue"
      subtitle="Events awaiting a human verdict, weakest evidence first — that is where review adds the most."
      actions={
        <span className="num text-xs text-[var(--text-dim)]">
          {data?.total ?? 0} pending
        </span>
      }
    >
      {isLoading ? (
        <WaitingState title="Loading queue" detail="" />
      ) : items.length === 0 ? (
        <EmptyState
          title="Queue is clear"
          detail="Events escalate here once three independent sources report the same thing."
        />
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
              <Th className="w-[140px]">Evidence</Th>
              <Th className="text-right">Corroboration</Th>
              <Th>Updated</Th>
            </tr>
          </thead>
          <tbody>
            {items.map((e) => (
              <Tr key={e.id} onClick={() => setSelected(e.id)} active={selected === e.id}>
                <Td>
                  <EventTypeBadge type={e.event_type} />
                  <div className="num mt-1 text-[9px] text-[var(--text-faint)]">
                    EVT-{shortId(e.id)}
                  </div>
                </Td>
                <Td>
                  <div className="text-[var(--text-ink)]">{e.district ?? "—"}</div>
                  <div className="num text-[9px] text-[var(--text-faint)]">
                    {fmtCoord(e.center_latitude)}, {fmtCoord(e.center_longitude)}
                  </div>
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
                    <span className="num w-8 shrink-0 text-right text-[10px] text-[var(--text-dim)]">
                      {fmtPct(e.evidence_score)}
                    </span>
                  </div>
                </Td>
                <Td className="num text-right text-[var(--text-dim)]">
                  {fmtPct(e.corroboration_score)}
                </Td>
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
