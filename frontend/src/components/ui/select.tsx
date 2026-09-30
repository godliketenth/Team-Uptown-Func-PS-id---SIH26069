import * as React from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

const triggerCls =
  "flex h-9 cursor-pointer items-center gap-1.5 rounded-[var(--r-sm)] border border-[var(--hairline)] bg-[var(--veil-1)] px-2.5 text-[14px] text-[var(--text-dim)] transition-colors hover:text-[var(--text-ink)] hover:brightness-125 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/40";

export function NativeSelect({
  value,
  onChange,
  options,
  placeholder,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  placeholder?: string;
  className?: string;
}) {
  return (
    <div className={cn("relative", className)}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(triggerCls, "w-full appearance-none pr-7")}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2 top-2 h-3.5 w-3.5 text-[var(--text-faint)]" />
    </div>
  );
}

/** Popover multi-select with a coloured dot per option. */
export function MultiSelect({
  label,
  values,
  onChange,
  options,
  className,
}: {
  label: string;
  values: string[];
  onChange: (v: string[]) => void;
  options: { value: string; label: string; color?: string }[];
  className?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const toggle = (v: string) =>
    onChange(values.includes(v) ? values.filter((x) => x !== v) : [...values, v]);

  return (
    <div ref={ref} className={cn("relative", className)}>
      <button type="button" className={cn(triggerCls, "w-full justify-between")} onClick={() => setOpen((o) => !o)}>
        <span className="truncate">
          {label}
          {values.length > 0 && (
            <span className="num ml-1 text-[var(--color-accent)]">({values.length})</span>
          )}
        </span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[var(--text-faint)]" />
      </button>
      {open && (
        <div className="rise absolute z-50 mt-1.5 max-h-72 w-56 overflow-y-auto rounded-[var(--r-md)] border border-[var(--hairline)] bg-[color-mix(in_oklab,var(--surface-raised)_94%,transparent)] p-1.5 shadow-[var(--shadow-lg)] backdrop-blur-xl scroll-thin">
          {values.length > 0 && (
            <button
              className="mb-1 w-full rounded-[var(--r-xs)] px-2 py-1.5 text-left text-[12.5px] uppercase tracking-wider text-[var(--text-faint)] transition-colors hover:bg-[var(--veil-1)] hover:text-[var(--text-dim)]"
              onClick={() => onChange([])}
            >
              Clear selection
            </button>
          )}
          {options.map((o) => {
            const active = values.includes(o.value);
            return (
              <button
                key={o.value}
                className="flex w-full items-center gap-2 rounded-[var(--r-xs)] px-2 py-1.5 text-left text-[14px] text-[var(--text-dim)] transition-colors hover:bg-[var(--veil-1)] hover:text-[var(--text-ink)]"
                onClick={() => toggle(o.value)}
              >
                <span className="flex h-3 w-3 shrink-0 items-center justify-center">
                  {active && <Check className="h-3 w-3 text-[var(--color-accent)]" />}
                </span>
                {o.color && (
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: o.color, boxShadow: `0 0 6px ${o.color}` }}
                  />
                )}
                <span className="truncate">{o.label}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
