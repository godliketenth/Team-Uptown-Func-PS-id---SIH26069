import { cn, textHue } from "@/lib/utils";
import {
  EVENT_COLORS,
  EVENT_GLYPHS,
  EVENT_LABELS,
  SEVERITY_COLORS,
  STATUS_COLORS,
  STATUS_LABELS,
  WARNING_ACTIONS,
  WARNING_COLORS,
  WARNING_LABELS,
} from "@/lib/domain";
import type { EventStatus, EventType, Severity, WarningLevel } from "@/lib/types";

/**
 * Attribute labels.
 *
 * These used to be uppercase pills with a tinted fill, a border and a glowing
 * dot — three attributes on one row meant three glowing pills, and the row's
 * actual meaning was the least visible thing on it. They are now set in
 * sentence case at text weight with a hard square mark carrying the hue. The
 * colour still does the fast work; the type stops shouting.
 *
 * The exception is `WarningBadge`, which stays loud on purpose: IMD's scale is
 * the one place in this domain where uppercase is the real vernacular, and the
 * warning level is the only attribute a district officer acts on directly.
 */
export function Badge({
  color,
  children,
  className,
  glyph,
  dot = false,
}: {
  color: string;
  children: React.ReactNode;
  className?: string;
  glyph?: string;
  dot?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 text-[13px] font-bold leading-[18px]",
        className,
      )}
      style={{ color: textHue(color) }}
    >
      {glyph && (
        <span className="text-[12px] leading-none opacity-90" aria-hidden>
          {glyph}
        </span>
      )}
      {dot && !glyph && <span className="mark" style={{ backgroundColor: color }} />}
      {children}
    </span>
  );
}

export function EventTypeBadge({ type, className }: { type: EventType; className?: string }) {
  return (
    <Badge color={EVENT_COLORS[type]} glyph={EVENT_GLYPHS[type]} className={className}>
      {EVENT_LABELS[type]}
    </Badge>
  );
}

export function StatusBadge({ status, className }: { status: EventStatus; className?: string }) {
  return (
    <Badge color={STATUS_COLORS[status]} dot className={className}>
      {STATUS_LABELS[status]}
    </Badge>
  );
}

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  const label = severity.charAt(0) + severity.slice(1).toLowerCase();
  return (
    <Badge color={SEVERITY_COLORS[severity]} className={className}>
      {label}
    </Badge>
  );
}

/**
 * The operator-facing signal: IMD's colour plus the action it implies.
 *
 * Always carries the action text, because the colour alone is the verdict and
 * the action is what a district officer actually needs. Set in condensed caps
 * — this is signage, not prose.
 */
export function WarningBadge({
  level,
  showAction = true,
  className,
}: {
  level: WarningLevel;
  showAction?: boolean;
  className?: string;
}) {
  const color = WARNING_COLORS[level];
  return (
    <span
      className={cn("inline-flex items-baseline gap-1.5 leading-[16px]", className)}
      title={`${WARNING_LABELS[level]} — ${WARNING_ACTIONS[level]}`}
    >
      <span
        className="display shrink-0 px-2 py-0.5 text-[12px] font-bold uppercase tracking-[0.08em]"
        style={{
          color: "var(--warning-ink)",
          backgroundColor: color,
        }}
      >
        {WARNING_LABELS[level]}
      </span>
      {showAction && (
        <span className="text-[13px] text-[var(--text-dim)]">{WARNING_ACTIONS[level]}</span>
      )}
    </span>
  );
}
