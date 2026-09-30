import { cn, textHue } from "@/lib/utils";

export function Panel({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("panel rounded-[var(--r-lg)]", className)}>{children}</div>;
}

/**
 * A panel header.
 *
 * Sentence case, at reading weight. Every panel in the console used to be
 * introduced by a tracked-out uppercase label, which is template chrome rather
 * than information — it made a section called "Hashtag monitor" as loud as the
 * warning scale. Uppercase is now reserved for IMD's warning levels, where it
 * is the domain's own convention.
 */
export function PanelTitle({
  children,
  right,
  className,
}: {
  children: React.ReactNode;
  right?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex h-[52px] shrink-0 items-center justify-between gap-3 divider-x px-5",
        className,
      )}
    >
      <span className="text-[15px] font-bold text-[var(--text-ink)]">{children}</span>
      {right}
    </div>
  );
}

/** @deprecated Use `PanelTitle`. Retained while admin screens migrate. */
export function SectionLabel({
  children,
  right,
  className,
}: {
  children: React.ReactNode;
  right?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex h-[52px] shrink-0 items-center justify-between divider-x px-5",
        className,
      )}
    >
      <span className="text-[12.5px] font-medium text-[var(--text-dim)]">{children}</span>
      {right}
    </div>
  );
}

export function Stat({
  label,
  value,
  hint,
  color,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  color?: string;
}) {
  return (
    <div className="flex flex-col gap-2.5">
      <span className="text-[13px] text-[var(--text-faint)]">{label}</span>
      <span
        className="num text-[27px] font-bold leading-none tracking-[-0.01em]"
        style={{ color: color ? textHue(color) : "var(--text-ink)" }}
      >
        {value}
      </span>
      {hint && <span className="text-[12.5px] leading-snug text-[var(--text-faint)]">{hint}</span>}
    </div>
  );
}

/** A labelled 0–1 meter. Used everywhere evidence is shown. */
export function Meter({
  value,
  color,
  className,
}: {
  value: number;
  color: string;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div
      className={cn(
        "h-[9px] w-full overflow-hidden rounded-full bg-[var(--veil-1)] ring-1 ring-inset ring-[var(--hairline-soft)]",
        className,
      )}
    >
      <div
        className="h-full rounded-full transition-[width] duration-500 ease-out"
        style={{
          width: `${pct}%`,
          background: color,
        }}
      />
    </div>
  );
}
