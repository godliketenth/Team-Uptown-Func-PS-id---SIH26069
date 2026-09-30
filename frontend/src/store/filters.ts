import { create } from "zustand";
import type { EventStatus, EventType } from "@/lib/types";

export type RangeKey = "1h" | "6h" | "24h" | "7d" | "all";

interface FilterState {
  range: RangeKey;
  eventTypes: EventType[];
  statuses: EventStatus[];
  state: string;
  district: string;
  setRange: (r: RangeKey) => void;
  setEventTypes: (v: EventType[]) => void;
  setStatuses: (v: EventStatus[]) => void;
  setState: (v: string) => void;
  setDistrict: (v: string) => void;
  selectDistrict: (district: string, state: string) => void;
  reset: () => void;
}

const RANGE_HOURS: Record<RangeKey, number | null> = {
  "1h": 1,
  "6h": 6,
  "24h": 24,
  "7d": 168,
  all: null,
};

export const useFilters = create<FilterState>((set) => ({
  range: "24h",
  eventTypes: [],
  statuses: [],
  state: "",
  district: "",
  setRange: (range) => set({ range }),
  setEventTypes: (eventTypes) => set({ eventTypes }),
  setStatuses: (statuses) => set({ statuses }),
  // Changing state invalidates whatever district was chosen under the old one.
  setState: (state) => set({ state, district: "" }),
  setDistrict: (district) => set({ district }),
  // Picking a district from the ungrouped, country-wide list also settles the
  // state it belongs to, so the two controls never disagree. Set together,
  // because `setState` deliberately clears the district.
  selectDistrict: (district, state) => set({ district, state }),
  reset: () => set({ range: "24h", eventTypes: [], statuses: [], state: "", district: "" }),
}));

export function rangeToDateFrom(range: RangeKey): string | undefined {
  const hours = RANGE_HOURS[range];
  if (hours === null) return undefined;
  return new Date(Date.now() - hours * 3600_000).toISOString();
}

/** The single place filter state becomes API query params. */
export function useApiFilters() {
  const { range, eventTypes, statuses, state, district } = useFilters();
  return {
    date_from: rangeToDateFrom(range),
    event_type: eventTypes,
    status: statuses,
    state: state || undefined,
    district: district || undefined,
  };
}
