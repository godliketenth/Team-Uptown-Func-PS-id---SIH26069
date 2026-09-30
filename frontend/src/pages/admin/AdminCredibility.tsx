import { useQuery } from "@tanstack/react-query";
import { Panel, SectionLabel, Stat } from "@/components/ui/panel";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { EventTypeBadge } from "@/components/ui/badge";
import { HashtagChip } from "@/components/ui/hashtag";
import { CredibilityFlagList, RiskBadge, riskColor } from "@/components/ui/credibility";
import { MediaStrip } from "@/components/ui/media";
import { EmptyState, WaitingState } from "@/components/ui/empty";
import { api } from "@/lib/api";
import { SOURCE_LABELS } from "@/lib/domain";
import { fmtPct, relativeTime, shortId } from "@/lib/utils";
import { AdminPage } from "./AdminPage";
import { livePoll } from "@/lib/live";

/**
 * The "identify fake or misleading reports" surface. Every row names the
 * signals that raised it, so a reviewer argues with a specific claim rather
 * than with a score.
 */
export function AdminCredibility() {
  const { data: roll, isLoading } = useQuery({
    queryKey: ["credibility"],
    queryFn: () => api.credibility(24),
    refetchInterval: livePoll(8000),
  });

  const { data: flagged } = useQuery({
    queryKey: ["flagged-reports"],
    queryFn: () => api.reports({ flagged_only: true, include_duplicates: true, limit: 150 }),
    refetchInterval: livePoll(8000),
  });

  if (isLoading || !roll) {
    return (
      <AdminPage title="Credibility">
        <WaitingState title="Scoring intake" detail="" />
      </AdminPage>
    );
  }

  const items = flagged?.items ?? [];
  const maxFlag = Math.max(1, ...roll.flags.map((f) => f.report_count));

  return (
    <AdminPage
      title="Credibility"
      subtitle="Automated fake / misleading detection across the last 24 hours of intake."
      actions={
        <span className="num text-[14px]" style={{ color: riskColor(roll.avg_risk) }}>
          {roll.flagged_reports} flagged · {fmtPct(roll.flagged_rate)} of intake
        </span>
      }
    >
      <div className="scroll-thin flex-1 overflow-y-auto p-4">
        <div className="grid grid-cols-4 gap-3.5">
          <Panel className="lift p-4">
            <Stat label="Reports assessed" value={roll.total_reports} hint="last 24h" />
          </Panel>
          <Panel className="lift p-4">
            <Stat
              label="Flagged for review"
              value={roll.flagged_reports}
              hint={`${fmtPct(roll.flagged_rate)} of intake`}
              color={riskColor(roll.avg_risk)}
            />
          </Panel>
          <Panel className="lift p-4">
            <Stat
              label="Mean risk"
              value={fmtPct(roll.avg_risk)}
              hint="0% = fully corroborated"
              color={riskColor(roll.avg_risk)}
            />
          </Panel>
          <Panel className="lift p-4">
            <Stat
              label="Distinct signals"
              value={roll.flags.length}
              hint="rules currently firing"
            />
          </Panel>
        </div>

        <Panel className="mt-3.5 flex flex-col">
          <SectionLabel
            right={
              <span className="num text-[12.5px] text-[var(--text-faint)]">
                reports raising each signal
              </span>
            }
          >
            Why reports get flagged
          </SectionLabel>
          <div className="space-y-1.5 p-3">
            {roll.flags.length === 0 ? (
              <div className="text-[13px] text-[var(--text-faint)]">
                Nothing flagged in this window.
              </div>
            ) : (
              roll.flags.map((f) => (
                <div key={f.code} className="flex items-center gap-3">
                  <span className="w-[230px] shrink-0 truncate text-[13px] text-[var(--text-ink)]">
                    {f.label}
                  </span>
                  <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-[var(--veil-1)] ring-1 ring-inset ring-[var(--hairline-soft)]">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-[var(--color-st-review)]/55 to-[var(--color-st-review)] shadow-[0_0_10px_-2px_var(--color-st-review)] transition-[width] duration-500"
                      style={{ width: `${(f.report_count / maxFlag) * 100}%` }}
                    />
                  </div>
                  <span className="num w-10 shrink-0 text-right text-[12.5px] text-[var(--text-dim)]">
                    {f.report_count}
                  </span>
                  <span className="num w-[210px] shrink-0 text-[12px] text-[var(--text-faint)]">
                    {f.code}
                  </span>
                </div>
              ))
            )}
          </div>
        </Panel>

        <Panel className="mt-3.5 flex flex-col">
          <SectionLabel
            right={
              <span className="num text-[12.5px] text-[var(--text-faint)]">
                {flagged?.total ?? 0} reports
              </span>
            }
          >
            Flagged reports
          </SectionLabel>
          {items.length === 0 ? (
            <EmptyState title="Nothing flagged right now" />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Report</Th>
                  <Th>Source</Th>
                  <Th>Claimed</Th>
                  <Th>Location</Th>
                  <Th className="text-right">Risk</Th>
                  <Th>Observed</Th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <Tr key={r.id}>
                    <Td className="max-w-[460px]">
                      <div className="truncate text-[var(--text-ink)]">{r.raw_text}</div>
                      {r.hashtags && r.hashtags.length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {r.hashtags.slice(0, 5).map((t) => (
                            <HashtagChip
                              key={t}
                              tag={t}
                              tracked={(r.tracked_hashtags ?? []).includes(t)}
                              eventType={r.predicted_event_type}
                            />
                          ))}
                        </div>
                      )}
                      <CredibilityFlagList flags={r.credibility_flags} className="mt-1" />
                      <MediaStrip media={r.media} className="mt-1" />
                      <div className="num mt-1 text-[12px] text-[var(--text-faint)]">
                        RPT-{shortId(r.id, 6)}
                        {r.author ? ` · @${r.author}` : ""}
                      </div>
                    </Td>
                    <Td className="text-[var(--text-dim)]">{SOURCE_LABELS[r.source_type]}</Td>
                    <Td>
                      {r.predicted_event_type ? (
                        <EventTypeBadge type={r.predicted_event_type} />
                      ) : (
                        <span className="text-[var(--text-faint)]">—</span>
                      )}
                    </Td>
                    <Td className="text-[var(--text-dim)]">{r.district ?? "—"}</Td>
                    <Td className="text-right">
                      <RiskBadge risk={r.misinformation_risk} />
                    </Td>
                    <Td className="num text-[var(--text-faint)]">
                      {relativeTime(r.observed_at)}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>
      </div>
    </AdminPage>
  );
}
