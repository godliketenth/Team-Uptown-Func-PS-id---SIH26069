import * as React from "react";
import * as maplibregl from "maplibre-gl";
import { ChevronDown, Info } from "lucide-react";
import Supercluster, { type ClusterProperties, type PointFeature } from "supercluster";
import type { MapEvent } from "@/lib/types";
import {
  EVENT_COLORS,
  EVENT_GLYPHS,
  SEVERITY_COLORS,
  STATUS_COLORS,
  WARNING_COLORS,
  WARNING_LABELS,
  WARNING_PIN_SIZE,
} from "@/lib/domain";
import { WaitingState } from "@/components/ui/empty";
import { MOCK_MAP_VIEW, isMockMode } from "@/lib/mock";
import { buildMapStyle } from "@/lib/mapStyle";
import { getTheme, useTheme } from "@/hooks/useTheme";

const INDIA_BOUNDS: [number, number, number, number] = [67.0, 6.0, 98.5, 37.5];
const CLUSTER_MAX_ZOOM = 6;

/**
 * Framing India for a pane that is much wider than it is tall.
 *
 * `fitBounds` is a *contain* fit: it takes the smaller of the zoom that fits
 * the width and the zoom that fits the height. India's bounding box is roughly
 * square, the map pane is about 2:1, so the height governs and every bit of
 * slack lands horizontally — the country ends up filling the pane top to bottom
 * but only about 40% of its width, with Saudi Arabia and the Philippines
 * padding out the sides of a console about Indian weather.
 *
 * A *cover* fit is worse in the other direction: it would crop away more than
 * half of India's latitude.
 *
 * So take the contain zoom and move it a fraction of the way toward the width
 * zoom. India then fills the pane horizontally and gives up a little of the
 * empty ocean north and south. On a pane that is taller than it is wide the
 * width zoom is already the smaller of the two, the bias term is zero, and
 * this degrades to exactly the old behaviour.
 */
const FRAME_BIAS = 0.55;
const TILE_SIZE = 512;

/** Mercator northing for a latitude, in radians. */
function mercatorY(lat: number): number {
  return Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
}

function frameIndia(width: number, height: number): { center: [number, number]; zoom: number } {
  const [west, south, east, north] = INDIA_BOUNDS;

  // The bounds as a fraction of the whole world, so a zoom can be solved for.
  const spanX = (east - west) / 360;
  const spanY = (mercatorY(north) - mercatorY(south)) / (2 * Math.PI);

  // Leave a margin so the country never touches the edge of the pane.
  const margin = 0.94;
  const zoomFor = (px: number, span: number) => Math.log2((px * margin) / (span * TILE_SIZE));

  const zoomX = zoomFor(width, spanX);
  const zoomY = zoomFor(height, spanY);
  const contain = Math.min(zoomX, zoomY);
  const zoom = contain + FRAME_BIAS * Math.max(0, zoomX - contain);

  // Centre on the middle of the bounds in Mercator, not in raw degrees — the
  // latter sits noticeably south of centre at these latitudes.
  const midY = (mercatorY(north) + mercatorY(south)) / 2;
  const centerLat = (360 / Math.PI) * Math.atan(Math.exp(midY)) - 90;

  return { center: [(west + east) / 2, centerLat], zoom };
}

interface Props {
  events: MapEvent[];
  loading: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  focus?: { lat: number; lon: number; zoom?: number } | null;
}

type ClusterPoint = PointFeature<{ event: MapEvent }>;

export function IndiaMap({ events, loading, selectedId, onSelect, focus }: Props) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const mapRef = React.useRef<maplibregl.Map | null>(null);
  const markersRef = React.useRef<Map<string, maplibregl.Marker>>(new Map());
  const seenRef = React.useRef<Set<string>>(new Set());
  const onSelectRef = React.useRef(onSelect);
  const [ready, setReady] = React.useState(false);
  const [viewTick, setViewTick] = React.useState(0);
  const { theme } = useTheme();

  onSelectRef.current = onSelect;

  React.useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: buildMapStyle(getTheme()),
      // Mock mode pins an explicit centre and zoom so that two screenshots are
      // comparable; live, the framing is derived from the pane so the country
      // fills it at any window size.
      ...(isMockMode()
        ? { center: MOCK_MAP_VIEW.center, zoom: MOCK_MAP_VIEW.zoom }
        : frameIndia(
            containerRef.current.clientWidth,
            containerRef.current.clientHeight,
          )),
      minZoom: 3.2,
      maxZoom: 13,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    map.on("load", () => setReady(true));
    // Re-cluster whenever the viewport changes.
    map.on("moveend", () => setViewTick((t) => t + 1));
    map.on("zoomend", () => setViewTick((t) => t + 1));
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Repainting the basemap on a theme change. Markers are DOM elements owned by
  // MapLibre's Marker, not style layers, so `setStyle` leaves every pin in
  // place and nothing needs to be re-clustered.
  React.useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.setStyle(buildMapStyle(theme));
  }, [theme, ready]);

  React.useEffect(() => {
    const map = mapRef.current;
    if (!map || !focus) return;
    // Jump rather than fly in mock mode: an in-flight animation makes a
    // screenshot depend on when it was taken.
    if (isMockMode()) {
      map.jumpTo({ center: [focus.lon, focus.lat], zoom: focus.zoom ?? 8 });
      return;
    }
    map.flyTo({ center: [focus.lon, focus.lat], zoom: focus.zoom ?? 8, duration: 900 });
  }, [focus]);

  const index = React.useMemo(() => {
    const cluster = new Supercluster<{ event: MapEvent }>({
      radius: 52,
      maxZoom: CLUSTER_MAX_ZOOM,
    });
    cluster.load(
      events
        .filter((e) => Number.isFinite(e.center_longitude) && Number.isFinite(e.center_latitude))
        .map((e) => ({
          type: "Feature" as const,
          properties: { event: e },
          geometry: {
            type: "Point" as const,
            coordinates: [e.center_longitude, e.center_latitude],
          },
        })),
    );
    return cluster;
  }, [events]);

  // Render markers for whatever the current viewport clusters into.
  React.useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;

    const bounds = map.getBounds();
    const zoom = Math.round(map.getZoom());
    const clusters = index.getClusters(
      [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()],
      zoom,
    );

    const nextKeys = new Set<string>();

    for (const feature of clusters) {
      const [lon, lat] = feature.geometry.coordinates;
      const isCluster = Boolean((feature.properties as ClusterProperties).cluster);
      const key = isCluster
        ? `c-${(feature.properties as ClusterProperties).cluster_id}-${zoom}`
        : `e-${(feature as ClusterPoint).properties.event.id}`;
      nextKeys.add(key);

      if (markersRef.current.has(key)) {
        if (!isCluster) {
          const el = markersRef.current.get(key)!.getElement();
          applyEventStyle(el, (feature as ClusterPoint).properties.event, selectedId);
        }
        continue;
      }

      const el = document.createElement("div");
      if (isCluster) {
        const props = feature.properties as ClusterProperties;
        const leaves = index.getLeaves(props.cluster_id, 30) as ClusterPoint[];
        buildClusterElement(el, props.point_count, leaves);
        el.addEventListener("click", () => {
          const target = Math.min(index.getClusterExpansionZoom(props.cluster_id), 12);
          map.flyTo({ center: [lon, lat], zoom: target, duration: 600 });
        });
      } else {
        const event = (feature as ClusterPoint).properties.event;
        const isNew = !seenRef.current.has(event.id);
        seenRef.current.add(event.id);
        buildEventElement(el, event, isNew);
        applyEventStyle(el, event, selectedId);
        el.addEventListener("click", (ev) => {
          ev.stopPropagation();
          onSelectRef.current(event.id);
        });
      }

      const marker = new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat([lon, lat])
        .addTo(map);
      markersRef.current.set(key, marker);
    }

    for (const [key, marker] of markersRef.current) {
      if (!nextKeys.has(key)) {
        marker.remove();
        markersRef.current.delete(key);
      }
    }
  }, [index, ready, viewTick, selectedId]);

  const showWaiting = loading && events.length === 0;

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />
      {showWaiting && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-[var(--surface-base)]/75 backdrop-blur-sm">
          <WaitingState />
        </div>
      )}
      {!showWaiting && events.length === 0 && (
        <div className="pointer-events-none absolute inset-x-0 top-4 z-10 flex justify-center">
          <div className="panel rise rounded-full px-4 py-2 text-[13px] text-[var(--text-dim)]">
            No events match the current filters
          </div>
        </div>
      )}
      <MapLegend />
    </div>
  );
}

function buildEventElement(el: HTMLDivElement, event: MapEvent, isNew: boolean) {
  el.className = "relative cursor-pointer";
  el.style.color = EVENT_COLORS[event.event_type];
  const size = pinSize(event);
  el.innerHTML = `
    <div class="relative flex items-center justify-center rounded-full border backdrop-blur-[2px]"
         style="width:${size}px;height:${size}px;
                transition:transform 180ms cubic-bezier(.2,.7,.3,1), box-shadow 180ms ease">
      <span style="font-size:${Math.round(size * 0.5)}px;line-height:1;opacity:.95">${EVENT_GLYPHS[event.event_type]}</span>
    </div>`;
  el.addEventListener("mouseenter", () => {
    const inner = el.firstElementChild as HTMLElement | null;
    if (inner) inner.style.transform = "scale(1.18)";
  });
  el.addEventListener("mouseleave", () => {
    const inner = el.firstElementChild as HTMLElement | null;
    if (inner) inner.style.transform = "scale(1)";
  });
  if (isNew) {
    const ripple = document.createElement("span");
    ripple.className = "pin-ripple absolute inset-0 rounded-full";
    ripple.style.color = EVENT_COLORS[event.event_type];
    el.appendChild(ripple);
  }
  el.title =
    `${event.event_type} · ${WARNING_LABELS[event.warning_level]} · ` +
    `${event.district ?? "unknown"} · ${event.report_count} reports`;
}

function applyEventStyle(el: HTMLElement, event: MapEvent, selectedId: string | null) {
  const inner = el.firstElementChild as HTMLElement | null;
  if (!inner) return;
  const hue = EVENT_COLORS[event.event_type];
  const selected = selectedId === event.id;
  // Flat fill, hard ring, no glow. A blurred halo under every pin was the
  // single loudest thing on the map and it carried no information — it made a
  // resolved fog report look as urgent as a red flood warning. Separation from
  // the basemap now comes from a hairline of the ground colour around the
  // mark, the way a printed chart separates a station circle from the terrain.
  inner.style.background = `color-mix(in oklab, ${hue} ${selected ? 92 : 72}%, var(--pin-base))`;
  // Status rides on the ring, type on the fill: two channels, two dimensions.
  inner.style.borderColor = STATUS_COLORS[event.status];
  inner.style.borderWidth =
    event.status === "VERIFIED" || event.status === "NEEDS_REVIEW" ? "2px" : "1.5px";
  inner.style.color = "var(--pin-ink)";
  inner.style.boxShadow = selected
    ? `0 0 0 2px var(--pin-base), 0 0 0 4px ${STATUS_COLORS[event.status]}`
    : `0 0 0 1.5px color-mix(in oklab, var(--pin-base) 70%, transparent)`;
  inner.style.opacity = event.status === "REJECTED" || event.status === "RESOLVED" ? "0.45" : "1";
}

function pinSize(event: MapEvent) {
  // Driven by warning level so the largest marks are the ones needing action,
  // rather than simply the ones with the most chatter.
  return WARNING_PIN_SIZE[event.warning_level] ?? 20;
}

function buildClusterElement(el: HTMLDivElement, count: number, leaves: ClusterPoint[]) {
  const size = count < 5 ? 30 : count < 20 ? 37 : 45;
  // Colour the cluster by whichever event type dominates inside it.
  const tally = new Map<string, number>();
  let worst = "LOW";
  for (const leaf of leaves) {
    const e = leaf.properties.event;
    tally.set(e.event_type, (tally.get(e.event_type) ?? 0) + 1);
    if (["LOW", "MODERATE", "HIGH", "SEVERE"].indexOf(e.severity) > ["LOW", "MODERATE", "HIGH", "SEVERE"].indexOf(worst)) {
      worst = e.severity;
    }
  }
  const dominant = [...tally.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? "RAIN";
  const hue = EVENT_COLORS[dominant as keyof typeof EVENT_COLORS];
  el.className = "cursor-pointer";
  el.innerHTML = `
    <div class="flex items-center justify-center rounded-full border font-semibold backdrop-blur-[2px]"
         style="width:${size}px;height:${size}px;
                background:color-mix(in oklab, ${hue} 62%, var(--pin-base));
                border-color:${SEVERITY_COLORS[worst as keyof typeof SEVERITY_COLORS]};
                border-width:1.5px;
                color:var(--pin-ink);
                font-family:'IBM Plex Mono',monospace;
                font-size:${size < 34 ? 11.5 : 13}px;
                font-variant-numeric:tabular-nums;
                letter-spacing:-.02em;
                transition:transform 180ms cubic-bezier(.2,.7,.3,1);
                box-shadow:0 0 0 1.5px color-mix(in oklab, var(--pin-base) 70%, transparent)">
      ${count}
    </div>`;
  el.addEventListener("mouseenter", () => {
    const inner = el.firstElementChild as HTMLElement | null;
    if (inner) inner.style.transform = "scale(1.12)";
  });
  el.addEventListener("mouseleave", () => {
    const inner = el.firstElementChild as HTMLElement | null;
    if (inner) inner.style.transform = "scale(1)";
  });
  el.title = `${count} events - click to zoom in`;
}

function MapLegend() {
  // Starts collapsed where the map is small enough that a fixed legend would
  // cover the country rather than annotate it.
  const [open, setOpen] = React.useState(
    () => typeof window === "undefined" || window.innerWidth >= 1280,
  );

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="panel rise absolute bottom-3 left-3 z-10 flex cursor-pointer items-center gap-1.5 rounded-full px-2.5 py-1.5 transition-colors hover:brightness-125 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]/50 md:bottom-4 md:left-4"
        aria-expanded={false}
        aria-label="Show map legend"
      >
        <Info className="h-3.5 w-3.5 text-[var(--text-dim)]" />
        <span className="label">Legend</span>
      </button>
    );
  }

  return (
    <div className="panel rise absolute bottom-3 left-3 z-10 max-w-[calc(100vw-1.5rem)] rounded-[var(--r-lg)] px-3 py-2.5 md:bottom-4 md:left-4">
      <div className="mb-2 flex items-center justify-between gap-4">
        <span className="label">Legend</span>
        <button
          onClick={() => setOpen(false)}
          className="-mr-1 cursor-pointer rounded-[var(--r-xs)] p-0.5 text-[var(--text-faint)] transition-colors hover:text-[var(--text-ink)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]/50"
          aria-expanded
          aria-label="Hide map legend"
        >
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="grid grid-cols-2 gap-x-3.5 gap-y-1.5">
        {Object.entries(EVENT_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1.5">
            <span
              className="flex h-5 w-5 items-center justify-center rounded-full border text-[11px]"
              style={{
                background: `color-mix(in oklab, ${color} 72%, var(--pin-base))`,
                borderColor: `color-mix(in oklab, ${color} 70%, transparent)`,
                color: "var(--pin-ink)",
              }}
            >
              {EVENT_GLYPHS[type as keyof typeof EVENT_GLYPHS]}
            </span>
            <span className="text-[13px] capitalize text-[var(--text-dim)]">
              {type.replace("_", " ").toLowerCase()}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-2.5 border-t border-[var(--hairline-soft)] pt-2">
        <div className="label mb-1.5">Size = warning level</div>
        <div className="mb-2 flex flex-wrap items-center gap-x-2.5 gap-y-1">
          {(["GREEN", "YELLOW", "ORANGE", "RED"] as const).map((lvl, i) => (
            <div key={lvl} className="flex items-center gap-1">
              <span
                className="rounded-full"
                style={{
                  width: 6 + i * 3,
                  height: 6 + i * 3,
                  background: WARNING_COLORS[lvl],
                }}
              />
              <span className="text-[12px] text-[var(--text-faint)]">
                {WARNING_LABELS[lvl].toLowerCase()}
              </span>
            </div>
          ))}
        </div>
        <div className="label mb-1">Ring = status</div>
        <div className="flex flex-wrap gap-x-2 gap-y-1">
          {(["NEEDS_REVIEW", "VERIFIED", "REJECTED"] as const).map((s) => (
            <div key={s} className="flex items-center gap-1">
              <span
                className="h-3 w-3 rounded-full border-2"
                style={{
                  borderColor: STATUS_COLORS[s],
                  background: "transparent",
                }}
              />
              <span className="text-[12px] text-[var(--text-faint)]">
                {s.replace("_", " ").toLowerCase()}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
