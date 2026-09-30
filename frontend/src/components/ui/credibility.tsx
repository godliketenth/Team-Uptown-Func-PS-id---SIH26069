import { AlertTriangle, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { Meter } from "@/components/ui/panel";
import type { CredibilityFlags } from "@/lib/types";

const RISK_HIGH = 0.5;
const RISK_SOME = 0.2;

export function riskColor(risk: number) {
  if (risk >= RISK_HIGH) return "var(--color-st-rejected)";
  if (risk >= RISK_SOME) return "var(--color-st-review)";
  return "var(--color-st-verified)";
}

/** Compact "this report looks suspect" marker for dense lists. */
export function RiskBadge({
  risk,
  className,
}: {
  risk: number | null | undefined;
  className?: string;
}) {
  if (risk === null || risk === undefined) return null;
  const flagged = risk >= RISK_HIGH;
  const color = riskColor(risk);
  return (
    <span
      className={cn(
        "num inline-flex items-center gap-1 rounded-full border px-1.5 py-[2px] text-[14px] uppercase leading-[14px]",
        className,
      )}
      style={{
        color,
        borderColor: `color-mix(in oklab, ${color} 45%, transparent)`,
        backgroundColor: `color-mix(in oklab, ${color} 12%, transparent)`,
      }}
      title={flagged ? "Flagged for review" : "Within normal credibility range"}
    >
      {flagged ? <AlertTriangle className="h-2.5 w-2.5" /> : <ShieldCheck className="h-2.5 w-2.5" />}
      risk {Math.round(risk * 100)}%
    </span>
  );
}

/** The named reasons a report was flagged. Never show the score alone. */
export function CredibilityFlagList({
  flags,
  className,
}: {
  flags: CredibilityFlags | null | undefined;
  className?: string;
}) {
  if (!flags || flags.flags.length === 0) return null;
  return (
    <div className={cn("flex flex-wrap gap-1", className)}>
      {flags.flags.map((f) => (
        <span
          key={f.code}
          className="rounded-full border border-[var(--color-st-review)]/35 bg-[var(--color-st-review)]/12 px-2 py-[2px] text-[14px] leading-[14px] text-[var(--color-st-review)]"
          title={`contributes ${Math.round(f.weight * 100)}% to the risk score`}
        >
          {f.label}
        </span>
      ))}
    </div>
  );
}

export function RiskMeter({ risk, label }: { risk: number; label?: string }) {
  const color = riskColor(risk);
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-[15px] text-[var(--text-dim)]">
          {label ?? "Misinformation risk"}
        </span>
        <span className="num text-[15px] font-semibold" style={{ color }}>
          {Math.round(risk * 100)}%
        </span>
      </div>
      <Meter value={risk} color={color} className="mt-1" />
    </div>
  );
}
