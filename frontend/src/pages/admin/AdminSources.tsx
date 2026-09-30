import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pause, Play } from "lucide-react";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { WaitingState } from "@/components/ui/empty";
import { api } from "@/lib/api";
import { SOURCE_LABELS, STATUS_COLORS, atLeast } from "@/lib/domain";
import { relativeTime, shortId } from "@/lib/utils";
import { useAuth } from "@/store/auth";
import type { SourceStatus } from "@/lib/types";
import { AdminPage } from "./AdminPage";
import { livePoll } from "@/lib/live";

const STATUS_HUE: Record<SourceStatus, string> = {
  ACTIVE: STATUS_COLORS.VERIFIED,
  PAUSED: STATUS_COLORS.DETECTED,
  ERROR: STATUS_COLORS.REJECTED,
};

export function AdminSources() {
  const qc = useQueryClient();
  const user = useAuth((s) => s.user);
  const canEdit = atLeast(user?.role, "ADMIN");

  const { data, isLoading } = useQuery({
    queryKey: ["sources"],
    queryFn: api.sources,
    refetchInterval: livePoll(10000),
  });

  const toggle = useMutation({
    mutationFn: ({ id, status }: { id: string; status: SourceStatus }) =>
      api.updateSource(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sources"] }),
  });

  return (
    <AdminPage
      title="Sources"
      subtitle="Registered collectors. Pausing a source stops it contributing to the pipeline on the next tick."
    >
      {isLoading ? (
        <WaitingState title="Loading sources" detail="" />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Source</Th>
              <Th>Type</Th>
              <Th>Status</Th>
              <Th className="text-right">Poll</Th>
              <Th className="text-right">Raw (1h)</Th>
              <Th className="text-right">Raw total</Th>
              <Th className="text-right">Reports</Th>
              <Th>Last success</Th>
              <Th>Last error</Th>
              {canEdit && <Th className="text-right">Action</Th>}
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((s) => (
              <Tr key={s.id}>
                <Td>
                  <div className="text-[var(--text-ink)]">{s.name}</div>
                  <div className="num text-[12px] text-[var(--text-faint)]">SRC-{shortId(s.id, 6)}</div>
                </Td>
                <Td className="text-[var(--text-dim)]">{SOURCE_LABELS[s.source_type]}</Td>
                <Td>
                  <Badge color={STATUS_HUE[s.status]}>{s.status}</Badge>
                </Td>
                <Td className="num text-right text-[var(--text-dim)]">{s.poll_interval_seconds}s</Td>
                <Td className="num text-right text-[var(--text-ink)]">{s.raw_events_last_hour}</Td>
                <Td className="num text-right text-[var(--text-dim)]">{s.raw_events_total}</Td>
                <Td className="num text-right text-[var(--text-dim)]">{s.reports_total}</Td>
                <Td className="num text-[var(--text-faint)]">
                  {s.last_success_at ? relativeTime(s.last_success_at) : "—"}
                </Td>
                <Td className="max-w-[200px] truncate text-[12.5px] text-[var(--color-st-rejected)]">
                  {s.last_error_message ?? ""}
                </Td>
                {canEdit && (
                  <Td className="text-right">
                    <Button
                      size="sm"
                      variant={s.status === "ACTIVE" ? "outline" : "default"}
                      disabled={toggle.isPending}
                      onClick={() =>
                        toggle.mutate({
                          id: s.id,
                          status: s.status === "ACTIVE" ? "PAUSED" : "ACTIVE",
                        })
                      }
                    >
                      {s.status === "ACTIVE" ? (
                        <>
                          <Pause className="h-3 w-3" /> Pause
                        </>
                      ) : (
                        <>
                          <Play className="h-3 w-3" /> Resume
                        </>
                      )}
                    </Button>
                  </Td>
                )}
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
      {!canEdit && (
        <div className="border-t border-[var(--hairline-soft)] px-5 py-2.5 text-[12.5px] text-[var(--text-faint)]">
          Source configuration requires an admin account — signed in as {user?.role}.
        </div>
      )}
    </AdminPage>
  );
}
