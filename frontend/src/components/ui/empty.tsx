import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

/** The generator needs a few seconds before the first events exist. Never show
    a blank panel in that window — show that the pipeline is running. */
export function WaitingState({
  title = "Waiting for data",
  detail = "The ingestion scheduler is collecting from sources. First events appear within a few seconds.",
  className,
}: {
  title?: string;
  detail?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rise flex h-full flex-col items-center justify-center gap-3.5 px-6 text-center",
        className,
      )}
    >
      <div className="relative flex h-11 w-11 items-center justify-center">
        <span className="absolute inset-0 rounded-full bg-[var(--color-accent)]/10 blur-md" />
        <span className="absolute inset-0 rounded-full border border-[var(--color-accent)]/25" />
        <Loader2 className="relative h-4 w-4 animate-spin text-[var(--color-accent)]" />
      </div>
      <div>
        <div className="text-[14px] font-medium text-[var(--text-ink)]">{title}</div>
        {detail && (
          <div className="mx-auto mt-1.5 max-w-[290px] text-[13px] leading-relaxed text-[var(--text-faint)]">
            {detail}
          </div>
        )}
      </div>
      <div className="h-[3px] w-32 overflow-hidden rounded-full bg-[var(--veil-1)]">
        <div className="sweep h-full w-1/4 rounded-full bg-gradient-to-r from-transparent via-[var(--color-accent)] to-transparent" />
      </div>
    </div>
  );
}

export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="rise flex h-full flex-col items-center justify-center gap-1.5 px-6 text-center">
      <div className="text-[14px] font-medium text-[var(--text-dim)]">{title}</div>
      {detail && (
        <div className="max-w-[290px] text-[13px] leading-relaxed text-[var(--text-faint)]">
          {detail}
        </div>
      )}
    </div>
  );
}
