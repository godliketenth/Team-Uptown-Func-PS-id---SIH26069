import { Meter } from "@/components/ui/panel";
import { HashtagChip } from "@/components/ui/hashtag";
import { WarningBadge } from "@/components/ui/badge";
import { WARNING_COLORS } from "@/lib/domain";
import { RiskMeter } from "@/components/ui/credibility";
import { EVENT_COLORS, SOURCE_LABELS, SOURCE_TRUST, STATUS_COLORS } from "@/lib/domain";
import { fmtPct } from "@/lib/utils";
import type { EventDetail } from "@/lib/types";

/**
 * The platform's core credibility surface, reused by the dashboard slide-over
 * and the admin verification drawer. A status is never presented on its own -
 * always next to the evidence that produced it.
 */
export function EvidencePanel({ event }: { event: EventDetail }) {
  const ev = event.evidence;
  const hue = EVENT_COLORS[event.event_type];
  const statusHue = STATUS_COLORS[event.status];

  return (
    <div className="space-y-7">
      {event.warning_reasons && (
        <div
          className="rounded-[var(--r-md)] border px-3 py-2.5"
          style={{
            borderColor: `color-mix(in oklab, ${WARNING_COLORS[event.warning_level]} 32%, transparent)`,
            backgroundColor: `color-mix(in oklab, ${WARNING_COLORS[event.warning_level]} 8%, transparent)`,
          }}
        >
          <div className="flex items-center justify-between gap-2">
            <WarningBadge level={event.warning_level} />
            <span className="label-caps">IMD scale</span>
          </div>
          <ul className="mt-2 space-y-0.5">
            {event.warning_reasons.reasons.map((r) => (
              <li key={r} className="text-[15px] leading-snug text-[var(--text-dim)]">
                · {r}
              </li>
            ))}
          </ul>
          {event.warning_reasons.capped_by && (
            <div className="mt-1.5 text-[14.5px] leading-snug text-[var(--color-st-review)]">
              Held down: {event.warning_reasons.capped_by}
            </div>
          )}
          <div className="mt-2 text-[14px] leading-relaxed text-[var(--text-faint)]">
            Colour and action follow IMD's four-level bulletin scale. The thresholds
            that trigger it are derived from reported evidence, not forecast intensity.
          </div>
        </div>
      )}

      <div className="grid grid-cols-5 gap-1.5">
        <Figure label="Reports" value={ev.report_count} />
        <Figure label="Sources" value={ev.source_count} />
        <Figure label="Dupes" value={ev.duplicate_count} />
        <Figure label="Media" value={ev.with_media} />
        <Figure
          label="Flagged"
          value={ev.flagged_report_count}
          color={ev.flagged_report_count > 0 ? "var(--color-st-rejected)" : undefined}
        />
      </div>

      <div className="space-y-2">
        <Bar
          label="Evidence score"
          hint="Mean reliability across contributing reports"
          value={ev.evidence_score}
          color={statusHue}
        />
        <Bar
          label="Weather corroboration"
          hint="Agreement with observed Open-Meteo conditions"
          value={ev.weather_corroboration}
          color={hue}
        />
        <Bar
          label="Source diversity"
          hint={`${ev.distinct_source_types.length} of 6 source categories reporting`}
          value={ev.distinct_source_types.length / 6}
          color={EVENT_COLORS.RAIN}
        />
        <RiskMeter risk={ev.avg_misinformation_risk} label="Mean misinformation risk" />
      </div>

      {ev.top_flags.length > 0 && (
        <div>
          <div className="label mb-3 text-[15px]">Credibility flags raised</div>
          <div className="space-y-1">
            {ev.top_flags.map((f) => (
              <div
                key={f.code}
                className="flex items-center gap-2 rounded-[var(--r-sm)] border border-[var(--color-st-review)]/25 bg-[var(--color-st-review)]/[0.07] px-2.5 py-1.5"
              >
                <span className="min-w-0 flex-1 truncate text-[15px] text-[var(--color-st-review)]">
                  {f.label}
                </span>
                <span className="num shrink-0 text-[14.5px] text-[var(--text-dim)]">
                  {f.report_count}r
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {ev.top_hashtags.length > 0 && (
        <div>
          <div className="label mb-3 text-[15px]">Hashtags carrying this event</div>
          <div className="flex flex-wrap gap-1">
            {ev.top_hashtags.map((h) => (
              <HashtagChip
                key={h.hashtag}
                tag={h.hashtag}
                tracked={h.tracked}
                count={h.report_count}
                eventType={event.event_type}
              />
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="label mb-3 text-[15px]">Contributing sources</div>
        {ev.top_contributing_sources.length === 0 ? (
          <div className="text-[15px] text-[var(--text-faint)]">No attributed sources yet.</div>
        ) : (
          <div className="space-y-1">
            {ev.top_contributing_sources.map((s) => (
              <div
                key={`${s.name}-${s.source_type}`}
                className="flex items-center gap-2 rounded-[var(--r-sm)] border border-[var(--hairline-soft)] bg-[var(--veil-2)] px-2.5 py-1.5 transition-colors hover:bg-[var(--veil-1)]"
              >
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{
                    backgroundColor: `color-mix(in oklab, var(--color-accent) ${
                      SOURCE_TRUST[s.source_type] * 100
                    }%, var(--surface-line))`,
                    boxShadow: `0 0 8px -2px color-mix(in oklab, var(--color-accent) ${
                      SOURCE_TRUST[s.source_type] * 100
                    }%, transparent)`,
                  }}
                />
                <span className="min-w-0 flex-1 truncate text-[15px] text-[var(--text-ink)]">
                  {s.name}
                </span>
                <span className="shrink-0 text-[14px] uppercase tracking-wider text-[var(--text-faint)]">
                  {SOURCE_LABELS[s.source_type]}
                </span>
                <span className="num shrink-0 text-[14.5px] text-[var(--text-dim)]">
                  {s.report_count}r · {fmtPct(s.avg_reliability)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <p className="rounded-[var(--r-sm)] border border-[var(--hairline-soft)] bg-[var(--veil-2)] px-2.5 py-2 text-[14.5px] leading-relaxed text-[var(--text-faint)]">
        Status advances automatically as independent sources accumulate
        (1 → detected, 2 → corroborating, 3+ → needs review). A human verdict is
        never overwritten by the pipeline. Flags come from the credibility stage
        and name the specific signal that raised them.
      </p>
    </div>
  );
}

function Figure({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color?: string;
}) {
  return (
    <div className="rounded-[var(--r-sm)] border border-[var(--hairline-soft)] bg-[var(--veil-2)] px-2 py-2">
      <div className="text-[15.5px] text-[var(--text-faint)]">{label}</div>
      <div
        className="num mt-1 text-[22px] font-semibold leading-none tracking-[-0.02em]"
        style={{ color: color ?? "var(--text-ink)" }}
      >
        {value}
      </div>
    </div>
  );
}

function Bar({
  label,
  hint,
  value,
  color,
}: {
  label: string;
  hint: string;
  value: number;
  color: string;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-[15.5px] text-[var(--text-dim)]">{label}</span>
        <span className="num text-[15.5px] font-semibold tracking-[-0.02em]" style={{ color }}>
          {fmtPct(value)}
        </span>
      </div>
      <Meter value={value} color={color} className="mt-1.5" />
      <div className="mt-1 text-[14px] leading-snug text-[var(--text-faint)]">{hint}</div>
    </div>
  );
}
