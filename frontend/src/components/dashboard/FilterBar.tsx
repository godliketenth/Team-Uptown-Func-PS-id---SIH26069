import { RotateCcw } from "lucide-react";
import { MultiSelect, NativeSelect } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import {
  DISTRICTS_BY_STATE,
  EVENT_COLORS,
  EVENT_LABELS,
  EVENT_STATUSES,
  EVENT_TYPES,
  STATUS_COLORS,
  STATUS_LABELS,
} from "@/lib/domain";
import { useFilters, type RangeKey } from "@/store/filters";
import type { EventStatus, EventType } from "@/lib/types";

/**
 * Date, event, location and verification-status filters.
 *
 * All five are always present. They previously shared one row with the wordmark
 * and the user menu and were dropped by breakpoint to make room — status below
 * 1024px, state below 1280px, district below 1536px — which meant that on a
 * 1440px laptop there was no way to filter by district. Location-wise filtering
 * is a requirement of the platform, not a nice-to-have, so the row scrolls
 * horizontally when it runs out of space rather than discarding controls.
 */

const RANGES: { value: RangeKey; label: string }[] = [
  { value: "1h", label: "Last hour" },
  { value: "6h", label: "Last 6 hours" },
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "all", label: "All time" },
];

export function FilterBar() {
  const {
    range,
    eventTypes,
    statuses,
    state,
    district,
    setRange,
    setEventTypes,
    setStatuses,
    setState,
    setDistrict,
    reset,
  } = useFilters();

  const districts = state ? (DISTRICTS_BY_STATE[state] ?? []) : [];
  const dirty =
    range !== "24h" || eventTypes.length > 0 || statuses.length > 0 || state !== "" || district !== "";

  return (
    <div className="scroll-thin flex min-w-0 flex-1 items-center gap-2 overflow-x-auto">
      <NativeSelect
        className="w-[124px] shrink-0"
        value={range}
        onChange={(v) => setRange(v as RangeKey)}
        options={RANGES}
      />
      <MultiSelect
        className="w-[128px] shrink-0"
        label="Event type"
        values={eventTypes}
        onChange={(v) => setEventTypes(v as EventType[])}
        options={EVENT_TYPES.map((t) => ({
          value: t,
          label: EVENT_LABELS[t],
          color: EVENT_COLORS[t],
        }))}
      />
      <MultiSelect
        className="w-[118px] shrink-0"
        label="Status"
        values={statuses}
        onChange={(v) => setStatuses(v as EventStatus[])}
        options={EVENT_STATUSES.map((s) => ({
          value: s,
          label: STATUS_LABELS[s],
          color: STATUS_COLORS[s],
        }))}
      />
      <NativeSelect
        className="w-[146px] shrink-0"
        value={state}
        onChange={setState}
        placeholder="All states"
        options={Object.keys(DISTRICTS_BY_STATE)
          .sort()
          .map((s) => ({ value: s, label: s }))}
      />
      <NativeSelect
        className="w-[156px] shrink-0"
        value={district}
        onChange={setDistrict}
        placeholder={state ? "All districts" : "All districts"}
        options={districts.map((d) => ({ value: d, label: d }))}
      />
      {dirty && (
        <Button variant="ghost" size="sm" onClick={reset} title="Clear all filters" className="shrink-0">
          <RotateCcw className="h-3 w-3" />
          Clear
        </Button>
      )}
    </div>
  );
}
