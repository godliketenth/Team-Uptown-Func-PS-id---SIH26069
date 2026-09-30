import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, Copy, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, WarningBadge } from "@/components/ui/badge";
import { WaitingState } from "@/components/ui/empty";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const CONFIDENCE_HUE = {
  high: "var(--color-st-verified)",
  medium: "var(--color-st-review)",
  low: "var(--color-st-unassessed)",
} as const;

/**
 * The publishable advisory for an alert.
 *
 * Template-generated and deterministic on purpose — an operator signs their
 * name to this, so it must be reviewable in advance rather than invented per
 * request. The copy button exists because the realistic workflow is "paste
 * into the bulletin system, edit, issue".
 */
export function AdvisoryPanel({ alertId }: { alertId: string }) {
  const [copied, setCopied] = React.useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["advisory", alertId],
    queryFn: () => api.alertAdvisory(alertId),
  });

  const copy = async () => {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(data.plain_text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard blocked — the text is on screen to select manually */
    }
  };

  if (isLoading || !data) {
    return <WaitingState title="Composing advisory" detail="" />;
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <WarningBadge level={data.level} />
        <Badge color={CONFIDENCE_HUE[data.confidence]} dot>
          {data.confidence} confidence
        </Badge>
        <Button size="sm" className="ml-auto" onClick={copy}>
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          {copied ? "Copied" : "Copy bulletin"}
        </Button>
      </div>

      <div className="rounded-[var(--r-md)] border border-[var(--hairline)] bg-[var(--veil-2)] p-3.5">
        <div className="text-[14.5px] font-semibold text-[var(--text-ink)]">{data.headline}</div>
        <div className="num mt-1 text-[13px] text-[var(--text-dim)]" dir="auto">
          {data.hindi.headline} · {data.hindi.action}
        </div>

        <p className="mt-2.5 text-[13.5px] leading-relaxed text-[var(--text-dim)]">
          {data.situation}
        </p>

        <div className="mt-3">
          <div className="label mb-1">What to expect</div>
          <p className="text-[13.5px] leading-relaxed text-[var(--text-dim)]">{data.expect}</p>
        </div>

        <div className="mt-3">
          <div className="label mb-1.5">What to do</div>
          <ul className="space-y-1">
            {data.safety.map((s) => (
              <li
                key={s}
                className="flex gap-2 text-[13.5px] leading-relaxed text-[var(--text-ink)]"
              >
                <span className="text-[var(--color-accent)]">•</span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="mt-3 space-y-1 border-t border-[var(--hairline-soft)] pt-2.5">
          <div className={cn("text-[12.5px] leading-snug text-[var(--text-faint)]")}>
            {data.confidence_note}
          </div>
          <div className="num text-[12.5px] leading-snug text-[var(--text-faint)]">
            {data.evidence_line}
          </div>
          <div className="num text-[12.5px] text-[var(--text-faint)]">Issued {data.issued_at}</div>
        </div>
      </div>

      <div className="flex gap-2 rounded-[var(--r-sm)] border border-[var(--color-st-review)]/30 bg-[var(--color-st-review)]/[0.07] px-2.5 py-2">
        <FileText className="mt-px h-3 w-3 shrink-0 text-[var(--color-st-review)]" />
        <span className="text-[12.5px] leading-relaxed text-[var(--color-st-review)]">
          {data.disclaimer}
        </span>
      </div>
    </div>
  );
}
