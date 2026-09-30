import * as React from "react";
import { Film, ImageOff, Image as ImageIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { MediaItem } from "@/lib/types";

/**
 * Photos and videos attached to a report.
 *
 * Synthetic reports carry placeholder URLs that will not resolve, so a failed
 * load degrades to a labelled tile rather than a broken image - a real
 * connector's URLs render normally through the same component.
 */
export function MediaStrip({
  media,
  className,
}: {
  media: MediaItem[] | null | undefined;
  className?: string;
}) {
  if (!media || media.length === 0) return null;
  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {media.map((m, i) => (
        <MediaTile key={`${m.url}-${i}`} item={m} />
      ))}
    </div>
  );
}

function MediaTile({ item }: { item: MediaItem }) {
  const [failed, setFailed] = React.useState(false);
  const isVideo = item.type === "video";
  const name = item.url.split("/").pop() ?? item.url;

  if (!failed && !isVideo) {
    return (
      <img
        src={item.url}
        alt={name}
        onError={() => setFailed(true)}
        className="h-16 w-24 rounded-[var(--r-sm)] border border-[var(--hairline)] object-cover shadow-[var(--shadow-sm)]"
      />
    );
  }

  const Icon = isVideo ? Film : failed ? ImageOff : ImageIcon;
  return (
    <div
      className="flex h-16 w-24 flex-col items-center justify-center gap-1 rounded-[var(--r-sm)] border border-[var(--hairline)] bg-[var(--veil-1)] px-1"
      title={item.url}
    >
      <Icon className="h-3.5 w-3.5 text-[var(--text-faint)]" />
      <span className="num w-full truncate text-center text-[11px] text-[var(--text-faint)]">
        {isVideo ? "video" : "image"}
      </span>
    </div>
  );
}
