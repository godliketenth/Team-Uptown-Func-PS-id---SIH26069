import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/** Right-side slide-over. Detail never takes over the whole screen - the map
    stays visible behind it. */
export function Sheet({
  open,
  onClose,
  children,
  width = "clamp(360px, 33vw, 520px)",
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  width?: string;
}) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <>
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px] transition-opacity duration-300",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onClose}
      />
      <aside
        className={cn(
          "fixed right-0 top-0 z-50 flex h-full flex-col overflow-hidden border-l border-[var(--hairline)]",
          "bg-[color-mix(in_oklab,var(--surface-panel)_92%,transparent)] backdrop-blur-2xl",
          "shadow-[var(--shadow-lg)] transition-transform duration-300 [transition-timing-function:cubic-bezier(0.2,0.7,0.3,1)]",
          open ? "translate-x-0" : "translate-x-full",
        )}
        style={{ width }}
        role="dialog"
        aria-modal="true"
      >
        {children}
      </aside>
    </>
  );
}

export function SheetHeader({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  onClose: () => void;
  children?: React.ReactNode;
}) {
  return (
    <div className="shrink-0 divider-x bg-[var(--veil-2)] px-4 py-3.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">{title}</div>
          {subtitle && <div className="mt-1 text-[13px] text-[var(--text-faint)]">{subtitle}</div>}
        </div>
        <button
          onClick={onClose}
          className="cursor-pointer rounded-[var(--r-sm)] p-1.5 text-[var(--text-faint)] transition-colors hover:bg-[var(--veil-1)] hover:text-[var(--text-ink)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]/60"
          aria-label="Close panel"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      {children}
    </div>
  );
}
