import * as React from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

const triggerCls =
  "flex h-9 cursor-pointer items-center gap-1.5 rounded-[var(--r-sm)] border border-[var(--hairline)] bg-[var(--veil-1)] px-2.5 text-[14px] text-[var(--text-dim)] transition-colors hover:text-[var(--text-ink)] hover:brightness-125 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/40";

export interface SelectOption {
  value: string;
  label: string;
  /** Optional heading to file this option under. When any option carries one,
      the list renders as `<optgroup>`s — which is how the district filter can
      offer every district in the country without becoming an unreadable
      alphabetical wall. */
  group?: string;
}

export function NativeSelect({
  value,
  onChange,
  options,
  placeholder,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  options: SelectOption[];
  placeholder?: string;
  className?: string;
}) {
  const grouped = options.some((o) => o.group);
  const groups: [string, SelectOption[]][] = [];
  if (grouped) {
    for (const o of options) {
      const key = o.group ?? "";
      const last = groups[groups.length - 1];
      if (last && last[0] === key) last[1].push(o);
      else groups.push([key, [o]]);
    }
  }

  return (
    <div className={cn("relative", className)}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(triggerCls, "w-full appearance-none pr-7")}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {grouped
          ? groups.map(([g, opts]) => (
              <optgroup key={g} label={g}>
                {opts.map((o) => (
                  <option key={`${g}-${o.value}`} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </optgroup>
            ))
          : options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2 top-2 h-3.5 w-3.5 text-[var(--text-faint)]" />
    </div>
  );
}

/**
 * Popover multi-select with a coloured dot per option.
 *
 * The panel is rendered into `document.body` through a portal and positioned
 * `fixed` against the trigger, rather than `absolute` inside it. That is not
 * decoration: the filter row is `overflow-x-auto` so the controls can scroll on
 * a narrow window, and `overflow-x: auto` computes to `auto` on *both* axes —
 * so an absolutely-positioned panel was clipped at the row's bottom edge and
 * became invisible and unclickable, while still being present in the DOM.
 * A portal cannot be clipped by an ancestor.
 */
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
  const [rect, setRect] = React.useState<{ top: number; left: number; width: number } | null>(null);
  const triggerRef = React.useRef<HTMLButtonElement>(null);
  const panelRef = React.useRef<HTMLDivElement>(null);

  const PANEL_W = 236;

  const place = React.useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    // Keep the panel on screen when the trigger sits near the right edge.
    const left = Math.min(r.left, window.innerWidth - PANEL_W - 12);
    setRect({ top: r.bottom + 6, left: Math.max(12, left), width: r.width });
  }, []);

  React.useLayoutEffect(() => {
    if (open) place();
  }, [open, place]);

  React.useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (triggerRef.current?.contains(t) || panelRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    // The panel is fixed, so anything that moves the trigger must move it too.
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, place]);

  const toggle = (v: string) =>
    onChange(values.includes(v) ? values.filter((x) => x !== v) : [...values, v]);

  return (
    <div className={cn("relative", className)}>
      <button
        ref={triggerRef}
        type="button"
        className={cn(triggerCls, "w-full justify-between")}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="truncate">
          {label}
          {values.length > 0 && (
            <span className="num ml-1 text-[var(--color-accent)]">({values.length})</span>
          )}
        </span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[var(--text-faint)]" />
      </button>

      {open &&
        rect &&
        createPortal(
          <div
            ref={panelRef}
            style={{ top: rect.top, left: rect.left, width: PANEL_W }}
            className="rise fixed z-[60] max-h-[min(60vh,420px)] overflow-y-auto rounded-[var(--r-md)] border border-[var(--hairline)] bg-[color-mix(in_oklab,var(--surface-raised)_96%,transparent)] p-2 shadow-[var(--shadow-lg)] backdrop-blur-xl scroll-thin"
          >
            {values.length > 0 && (
              <button
                className="mb-1 w-full rounded-[var(--r-xs)] px-2.5 py-2 text-left text-[13px] text-[var(--text-faint)] transition-colors hover:bg-[var(--veil-1)] hover:text-[var(--text-dim)]"
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
                  className="flex w-full items-center gap-2.5 rounded-[var(--r-xs)] px-2.5 py-2 text-left text-[14px] text-[var(--text-dim)] transition-colors hover:bg-[var(--veil-1)] hover:text-[var(--text-ink)]"
                  onClick={() => toggle(o.value)}
                >
                  <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center">
                    {active && <Check className="h-3.5 w-3.5 text-[var(--color-accent)]" />}
                  </span>
                  {o.color && (
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: o.color }}
                    />
                  )}
                  <span className="truncate">{o.label}</span>
                </button>
              );
            })}
          </div>,
          document.body,
        )}
    </div>
  );
}
