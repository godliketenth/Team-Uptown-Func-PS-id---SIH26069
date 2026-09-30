import { cn } from "@/lib/utils";
import { EVENT_COLORS } from "@/lib/domain";
import type { EventType } from "@/lib/types";

/** Tracked tags (#IMD and the rest of the watchlist) get the accent treatment;
    incidental tags stay quiet so the watchlist reads at a glance. */
export function HashtagChip({
  tag,
  tracked = false,
  count,
  eventType,
  onClick,
  active,
  className,
}: {
  tag: string;
  tracked?: boolean;
  count?: number;
  eventType?: EventType | null;
  onClick?: () => void;
  active?: boolean;
  className?: string;
}) {
  const hue = eventType ? EVENT_COLORS[eventType] : "var(--color-accent)";
  const Tag = onClick ? "button" : "span";
  return (
    <Tag
      onClick={onClick}
      className={cn(
        "num inline-flex items-center gap-1.5 rounded-full border px-3 py-[4px] text-[12.5px] leading-[18px] transition-all duration-150",
        onClick &&
          "cursor-pointer hover:brightness-125 hover:-translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]/60",
        className,
      )}
      style={{
        color: tracked ? hue : "var(--text-faint)",
        borderColor: tracked
          ? `color-mix(in oklab, ${hue} 40%, transparent)`
          : "var(--surface-line)",
        backgroundColor: active
          ? `color-mix(in oklab, ${hue} 22%, transparent)`
          : tracked
            ? `color-mix(in oklab, ${hue} 10%, transparent)`
            : "transparent",
      }}
      title={tracked ? "Tracked weather hashtag" : "Incidental hashtag"}
    >
      #{tag}
      {count !== undefined && <span className="opacity-70">{count}</span>}
    </Tag>
  );
}
