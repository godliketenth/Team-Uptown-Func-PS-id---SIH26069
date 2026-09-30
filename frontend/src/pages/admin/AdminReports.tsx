import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { Badge, EventTypeBadge } from "@/components/ui/badge";
import { HashtagChip } from "@/components/ui/hashtag";
import { MediaStrip } from "@/components/ui/media";
import { RiskBadge } from "@/components/ui/credibility";
import { NativeSelect } from "@/components/ui/select";
import { EmptyState, WaitingState } from "@/components/ui/empty";
import { api } from "@/lib/api";
import {
  EVENT_LABELS,
  EVENT_TYPES,
  LANGUAGE_LABELS,
  SOURCE_LABELS,
  STATUS_COLORS,
} from "@/lib/domain";
import { fmtCoord, fmtPct, relativeTime, shortId } from "@/lib/utils";
import { AdminPage } from "./AdminPage";
import { livePoll } from "@/lib/live";

export function AdminReports() {
  const [sourceType, setSourceType] = React.useState("");
  const [eventType, setEventType] = React.useState("");
  const [showDupes, setShowDupes] = React.useState(true);
  const [flaggedOnly, setFlaggedOnly] = React.useState(false);
  const [hashtag, setHashtag] = React.useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["admin-reports", sourceType, eventType, showDupes, flaggedOnly, hashtag],
    queryFn: () =>
      api.reports({
        limit: 200,
        source_type: sourceType || undefined,
        predicted_event_type: eventType || undefined,
        include_duplicates: showDupes,
        flagged_only: flaggedOnly || undefined,
        hashtag: hashtag.trim() ? hashtag.trim().replace(/^#/, "") : undefined,
      }),
    refetchInterval: livePoll(8000),
  });

  const items = data?.items ?? [];

  return (
    <AdminPage
      title="Reports"
      subtitle="Individual normalized observations, including the ones dedup collapsed."
      actions={
        <div className="flex items-center gap-2">
          <NativeSelect
            className="w-[130px]"
            value={sourceType}
            onChange={setSourceType}
            placeholder="All sources"
            options={Object.entries(SOURCE_LABELS).map(([v, l]) => ({ value: v, label: l }))}
          />
          <NativeSelect
            className="w-[130px]"
            value={eventType}
            onChange={setEventType}
            placeholder="All event types"
            options={EVENT_TYPES.map((t) => ({ value: t, label: EVENT_LABELS[t] }))}
          />
          <input
            value={hashtag}
            onChange={(e) => setHashtag(e.target.value)}
            placeholder="#hashtag"
            className="num h-8 w-[118px] rounded-[var(--r-sm)] border border-[var(--hairline)] bg-[var(--veil-1)] px-2.5 text-[13px] text-[var(--text-ink)] transition-colors placeholder:text-[var(--text-faint)] focus:border-[var(--color-accent)]/45 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/30"
          />
          <label className="flex cursor-pointer items-center gap-1.5 text-[13px] text-[var(--text-dim)]">
            <input
              type="checkbox"
              checked={showDupes}
              onChange={(e) => setShowDupes(e.target.checked)}
              className="accent-[var(--color-accent)]"
            />
            duplicates
          </label>
          <label className="flex cursor-pointer items-center gap-1.5 text-[13px] text-[var(--text-dim)]">
            <input
              type="checkbox"
              checked={flaggedOnly}
              onChange={(e) => setFlaggedOnly(e.target.checked)}
              className="accent-[var(--color-st-rejected)]"
            />
            flagged only
          </label>
          <span className="num text-[14px] text-[var(--text-dim)]">{data?.total ?? 0}</span>
        </div>
      }
    >
      {isLoading ? (
        <WaitingState title="Loading reports" detail="" />
      ) : items.length === 0 ? (
        <EmptyState title="No reports match" />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Report</Th>
              <Th>Source</Th>
              <Th>Classified</Th>
              <Th>Location</Th>
              <Th className="text-right">Reliability</Th>
              <Th className="text-right">Risk</Th>
              <Th>Stage</Th>
              <Th>Observed</Th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <Tr key={r.id}>
                <Td className="max-w-[420px]">
                  <div className="truncate text-[var(--text-ink)]">{r.raw_text}</div>
                  {r.hashtags && r.hashtags.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {r.hashtags.slice(0, 6).map((t) => (
                        <HashtagChip
                          key={t}
                          tag={t}
                          tracked={(r.tracked_hashtags ?? []).includes(t)}
                          eventType={r.predicted_event_type}
                          onClick={() => setHashtag(t)}
                        />
                      ))}
                    </div>
                  )}
                  <MediaStrip media={r.media} className="mt-1" />
                  <div className="num mt-0.5 flex items-center gap-2 text-[12px] text-[var(--text-faint)]">
                    <span>RPT-{shortId(r.id, 6)}</span>
                    {r.author && <span className="text-[var(--text-dim)]">@{r.author}</span>}
                    {r.language && r.language !== "en" && (
                      <span className="text-[var(--color-accent)]">
                        {LANGUAGE_LABELS[r.language] ?? r.language.toUpperCase()}
                      </span>
                    )}
                    {r.duplicate_of_report_id && (
                      <span className="text-[var(--color-st-resolved)]">
                        dup → {shortId(r.duplicate_of_report_id, 6)}
                      </span>
                    )}
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
                <Td>
                  <div className="text-[var(--text-dim)]">{r.district ?? "—"}</div>
                  <div className="num text-[12px] text-[var(--text-faint)]">
                    {fmtCoord(r.latitude)}, {fmtCoord(r.longitude)}
                  </div>
                </Td>
                <Td className="num text-right text-[var(--text-ink)]">
                  {fmtPct(r.reliability_score)}
                </Td>
                <Td className="text-right">
                  <RiskBadge risk={r.misinformation_risk} />
                </Td>
                <Td>
                  <Badge
                    color={
                      r.processing_state === "EVENT_ASSIGNED"
                        ? STATUS_COLORS.VERIFIED
                        : r.processing_state === "DEDUPLICATED"
                          ? STATUS_COLORS.DETECTED
                          : STATUS_COLORS.NEEDS_REVIEW
                    }
                  >
                    {r.processing_state.replace("_", " ")}
                  </Badge>
                </Td>
                <Td className="num text-[var(--text-faint)]">{relativeTime(r.observed_at)}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </AdminPage>
  );
}
