import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, FileText, X } from "lucide-react";
import { Panel, SectionLabel, Stat } from "@/components/ui/panel";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { Badge, EventTypeBadge, WarningBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/select";
import { EmptyState, WaitingState } from "@/components/ui/empty";
import { api } from "@/lib/api";
import { STATUS_COLORS, WARNING_COLORS } from "@/lib/domain";
import { fmtDateTime, relativeTime, shortId } from "@/lib/utils";
import { useAuth } from "@/store/auth";
import { atLeast } from "@/lib/domain";
import type { AlertStatus } from "@/lib/types";
import { AdvisoryPanel } from "@/components/dashboard/AdvisoryPanel";
import { Sheet, SheetHeader } from "@/components/ui/sheet";
import { AdminPage } from "./AdminPage";
import { livePoll } from "@/lib/live";

const STATUS_LABEL: Record<AlertStatus, string> = {
  ACTIVE: "Active",
  ACKNOWLEDGED: "Acknowledged",
  CLOSED: "Closed",
};

const STATUS_HUE: Record<AlertStatus, string> = {
  ACTIVE: STATUS_COLORS.REJECTED,
  ACKNOWLEDGED: STATUS_COLORS.NEEDS_REVIEW,
  CLOSED: STATUS_COLORS.RESOLVED,
};

/**
 * The alert queue — where the platform asks someone to act.
 *
 * Ordered most severe first, then oldest, because that is the order an
 * operator works down. Acknowledging means *seen*; closing means *no longer
 * applies*, and only a verifier can do the second.
 */
export function AdminAlerts() {
  const qc = useQueryClient();
  const user = useAuth((s) => s.user);
  const canClose = atLeast(user?.role, "VERIFIER");
  const [statusFilter, setStatusFilter] = React.useState("live");
  const [note, setNote] = React.useState("");
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [advisoryFor, setAdvisoryFor] = React.useState<string | null>(null);

  const { data: summary } = useQuery({
    queryKey: ["alert-summary"],
    queryFn: api.alertSummary,
    refetchInterval: livePoll(5000),
  });

  const { data, isLoading } = useQuery({
    queryKey: ["alerts", statusFilter],
    queryFn: () =>
      api.alerts(
        statusFilter === "live"
          ? { live_only: true, limit: 200 }
          : { status: [statusFilter.toUpperCase()], limit: 200 },
      ),
    refetchInterval: livePoll(5000),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["alerts"] });
    qc.invalidateQueries({ queryKey: ["alert-summary"] });
  };

  const ack = useMutation({
    mutationFn: (id: string) => api.acknowledgeAlert(id, note || undefined),
    onSuccess: () => {
      setNote("");
      invalidate();
    },
    onSettled: () => setBusyId(null),
  });

  const close = useMutation({
    mutationFn: (id: string) => api.closeAlert(id, note || undefined),
    onSuccess: () => {
      setNote("");
      invalidate();
    },
    onSettled: () => setBusyId(null),
  });

  const items = data?.items ?? [];
  const oldest = summary?.oldest_unacknowledged_minutes;

  return (
    <AdminPage
      title="Alert Queue"
      subtitle="Events that crossed a response threshold. Most severe first, then oldest."
      actions={
        <div className="flex items-center gap-2">
          <NativeSelect
            className="w-[150px]"
            value={statusFilter}
            onChange={setStatusFilter}
            options={[
              { value: "live", label: "Live (open)" },
              { value: "active", label: "Active only" },
              { value: "acknowledged", label: "Acknowledged" },
              { value: "closed", label: "Closed" },
            ]}
          />
          <span className="num text-[14px] text-[var(--text-dim)]">{data?.total ?? 0}</span>
        </div>
      }
    >
      <div className="scroll-thin flex-1 overflow-y-auto p-4">
        <div className="grid grid-cols-4 gap-3.5">
          <Panel className="lift p-4">
            <Stat
              label="Awaiting action"
              value={summary?.active ?? 0}
              hint="not yet acknowledged"
              color={summary?.active ? STATUS_COLORS.REJECTED : undefined}
            />
          </Panel>
          <Panel className="lift p-4">
            <Stat
              label="Acknowledged"
              value={summary?.acknowledged ?? 0}
              hint="seen, still open"
              color={STATUS_COLORS.NEEDS_REVIEW}
            />
          </Panel>
          <Panel className="lift p-4">
            <Stat
              label="Red warnings"
              value={summary?.by_level?.RED ?? 0}
              hint="take action"
              color={WARNING_COLORS.RED}
            />
          </Panel>
          <Panel className="lift p-4">
            <Stat
              label="Oldest unactioned"
              value={oldest === null || oldest === undefined ? "—" : `${Math.round(oldest)}m`}
              hint="time to first acknowledgement"
              color={oldest !== null && oldest !== undefined && oldest > 30 ? STATUS_COLORS.REJECTED : undefined}
            />
          </Panel>
        </div>

        {summary && summary.by_state.length > 0 && (
          <Panel className="mt-3.5 flex flex-col">
            <SectionLabel
              right={
                <span className="num text-[12.5px] text-[var(--text-faint)]">open alerts</span>
              }
            >
              Where action is needed
            </SectionLabel>
            <div className="flex flex-wrap gap-1.5 p-3">
              {summary.by_state.map((s) => (
                <span
                  key={s.state}
                  className="rounded-full border border-[var(--hairline)] bg-[var(--veil-1)] px-2.5 py-1 text-[13px] text-[var(--text-dim)]"
                >
                  {s.state} <span className="num text-[var(--text-ink)]">{s.count}</span>
                </span>
              ))}
            </div>
          </Panel>
        )}

        <Panel className="mt-3.5 flex flex-col">
          <SectionLabel
            right={
              canClose ? (
                <input
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Note applied to the next action…"
                  className="h-7 w-[260px] rounded-[var(--r-sm)] border border-[var(--hairline)] bg-[var(--veil-1)] px-2.5 text-[13px] text-[var(--text-ink)] placeholder:text-[var(--text-faint)] focus:border-[var(--color-accent)]/45 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/30"
                />
              ) : undefined
            }
          >
            Alerts
          </SectionLabel>

          {isLoading ? (
            <WaitingState title="Loading alerts" detail="" />
          ) : items.length === 0 ? (
            <EmptyState
              title="No alerts in this view"
              detail="Alerts are raised when an event reaches ORANGE or RED on the IMD scale."
            />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Level</Th>
                  <Th>Alert</Th>
                  <Th>Type</Th>
                  <Th>Status</Th>
                  <Th className="text-right">Evidence</Th>
                  <Th>Raised</Th>
                  <Th className="text-right">Action</Th>
                </tr>
              </thead>
              <tbody>
                {items.map((a) => {
                  const snap = (a.evidence_snapshot ?? {}) as Record<string, number>;
                  const busy = busyId === a.id;
                  return (
                    <Tr key={a.id}>
                      <Td>
                        <WarningBadge level={a.level} showAction={false} />
                        {a.previous_level && (
                          <div className="num mt-1 text-[12px] text-[var(--color-st-review)]">
                            ↑ from {a.previous_level}
                          </div>
                        )}
                      </Td>
                      <Td className="max-w-[360px]">
                        <div className="text-[var(--text-ink)]">{a.headline}</div>
                        <div className="num mt-0.5 text-[12px] text-[var(--text-faint)]">
                          {a.action} · EVT-{shortId(a.event_id)}
                        </div>
                        {a.closed_reason && (
                          <div className="mt-0.5 text-[12px] text-[var(--text-faint)]">
                            closed: {a.closed_reason}
                          </div>
                        )}
                      </Td>
                      <Td>
                        <EventTypeBadge type={a.event_type} />
                      </Td>
                      <Td>
                        <Badge color={STATUS_HUE[a.status]} dot>
                          {STATUS_LABEL[a.status]}
                        </Badge>
                        {a.acknowledged_by && (
                          <div className="num mt-1 text-[12px] text-[var(--text-faint)]">
                            {a.acknowledged_by}
                          </div>
                        )}
                      </Td>
                      <Td className="num text-right text-[var(--text-dim)]">
                        {snap.report_count ?? "—"}r · {snap.source_count ?? "—"}s
                      </Td>
                      <Td className="num text-[var(--text-faint)]">
                        <div>{relativeTime(a.raised_at)}</div>
                        <div className="text-[12px]">{fmtDateTime(a.raised_at)}</div>
                      </Td>
                      <Td className="text-right">
                        <div className="flex justify-end gap-1.5">
                          <Button
                            size="sm"
                            variant="ghost"
                            title="Draft public advisory"
                            onClick={() => setAdvisoryFor(a.id)}
                          >
                            <FileText className="h-3 w-3" /> Advisory
                          </Button>
                          {a.status === "ACTIVE" && (
                            <Button
                              size="sm"
                              disabled={busy}
                              onClick={() => {
                                setBusyId(a.id);
                                ack.mutate(a.id);
                              }}
                            >
                              <Check className="h-3 w-3" /> Ack
                            </Button>
                          )}
                          {a.status !== "CLOSED" && canClose && (
                            <Button
                              size="sm"
                              variant="reject"
                              disabled={busy}
                              onClick={() => {
                                setBusyId(a.id);
                                close.mutate(a.id);
                              }}
                            >
                              <X className="h-3 w-3" /> Close
                            </Button>
                          )}
                        </div>
                      </Td>
                    </Tr>
                  );
                })}
              </tbody>
            </Table>
          )}
          {!canClose && (
            <div className="border-t border-[var(--hairline-soft)] px-5 py-2.5 text-[12.5px] text-[var(--text-faint)]">
              Standing an alert down requires a verifier account — signed in as {user?.role}.
            </div>
          )}
        </Panel>
      </div>

      <Sheet open={Boolean(advisoryFor)} onClose={() => setAdvisoryFor(null)}>
        {advisoryFor && (
          <>
            <SheetHeader
              title={<span className="text-[15.5px] font-semibold">Public advisory</span>}
              subtitle="Template-generated and deterministic — review before issuing."
              onClose={() => setAdvisoryFor(null)}
            />
            <div className="scroll-thin flex-1 overflow-y-auto p-4">
              <AdvisoryPanel alertId={advisoryFor} />
            </div>
          </>
        )}
      </Sheet>
    </AdminPage>
  );
}
