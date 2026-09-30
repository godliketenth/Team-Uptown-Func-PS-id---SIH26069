import { useQuery } from "@tanstack/react-query";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { EmptyState, WaitingState } from "@/components/ui/empty";
import { api } from "@/lib/api";
import { fmtDateTime, shortId } from "@/lib/utils";
import { AdminPage } from "./AdminPage";
import { livePoll } from "@/lib/live";
import { EVENT_COLORS, STATUS_COLORS } from "@/lib/domain";

const ACTION_HUE: Record<string, string> = {
  "event.verified": STATUS_COLORS.VERIFIED,
  "event.rejected": STATUS_COLORS.REJECTED,
  "event.resolved": STATUS_COLORS.RESOLVED,
  "source.update": EVENT_COLORS.RAIN,
  "auth.login": STATUS_COLORS.DETECTED,
};

export function AdminAudit() {
  const { data, isLoading } = useQuery({
    queryKey: ["audit-logs"],
    queryFn: () => api.auditLogs(200),
    refetchInterval: livePoll(10000),
  });

  const items = data?.items ?? [];

  return (
    <AdminPage
      title="Audit Log"
      subtitle="Every operator action against the platform, newest first."
      actions={<span className="num text-[14px] text-[var(--text-dim)]">{data?.total ?? 0}</span>}
    >
      {isLoading ? (
        <WaitingState title="Loading audit log" detail="" />
      ) : items.length === 0 ? (
        <EmptyState title="No operator actions yet" detail="Sign-ins and verdicts land here." />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>When</Th>
              <Th>Actor</Th>
              <Th>Action</Th>
              <Th>Target</Th>
              <Th>Details</Th>
            </tr>
          </thead>
          <tbody>
            {items.map((l) => (
              <Tr key={l.id}>
                <Td className="num whitespace-nowrap text-[var(--text-faint)]">
                  {fmtDateTime(l.created_at)}
                </Td>
                <Td className="num text-[var(--text-dim)]">{l.actor_email ?? "system"}</Td>
                <Td>
                  <Badge color={ACTION_HUE[l.action] ?? STATUS_COLORS.DETECTED}>{l.action}</Badge>
                </Td>
                <Td className="num text-[var(--text-faint)]">
                  {l.target_type ? `${l.target_type}/${shortId(l.target_id ?? "", 8)}` : "—"}
                </Td>
                <Td className="num max-w-[460px] truncate text-[12.5px] text-[var(--text-dim)]">
                  {l.details ? JSON.stringify(l.details) : ""}
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </AdminPage>
  );
}
