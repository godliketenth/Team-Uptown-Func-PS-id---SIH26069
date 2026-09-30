import { cn } from "@/lib/utils";

export function Table({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("w-full overflow-auto scroll-thin", className)}>
      <table className="w-full border-collapse text-[14px]">{children}</table>
    </div>
  );
}

export function Th({
  children,
  className,
  onClick,
}: {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
}) {
  return (
    <th
      onClick={onClick}
      className={cn(
        "sticky top-0 z-10 divider-x bg-[color-mix(in_oklab,var(--surface-panel)_92%,transparent)] px-5 py-4 text-left text-[12px] font-bold uppercase tracking-[0.1em] text-[var(--text-faint)] backdrop-blur-md",
        onClick && "cursor-pointer select-none transition-colors hover:text-[var(--text-ink)]",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <td
      className={cn(
        "border-b border-[var(--hairline-soft)] px-5 py-4 align-middle",
        className,
      )}
    >
      {children}
    </td>
  );
}

export function Tr({
  children,
  onClick,
  active,
  className,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  active?: boolean;
  className?: string;
}) {
  // A clickable row must be reachable and operable without a pointer, so it
  // takes focus and responds to Enter/Space like the button it behaves as.
  return (
    <tr
      onClick={onClick}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      tabIndex={onClick ? 0 : undefined}
      role={onClick ? "button" : undefined}
      aria-pressed={onClick ? Boolean(active) : undefined}
      className={cn(
        "transition-colors duration-150",
        onClick &&
          "cursor-pointer focus-visible:outline focus-visible:-outline-offset-2 focus-visible:outline-2 focus-visible:outline-[var(--color-accent)]",
        "hover:bg-[var(--veil-1)]",
        active &&
          "bg-[color-mix(in_oklab,var(--color-accent)_12%,transparent)] hover:bg-[color-mix(in_oklab,var(--color-accent)_16%,transparent)]",
        className,
      )}
    >
      {children}
    </tr>
  );
}
