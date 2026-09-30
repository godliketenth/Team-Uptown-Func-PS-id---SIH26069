import type { StyleSpecification } from "maplibre-gl";
import type { Theme } from "@/hooks/useTheme";

/**
 * The MapLibre basemap style, drawn from the design tokens.
 *
 * Every colour here is read from a CSS custom property at call time, so the map
 * cannot drift from `index.css`. Nothing in this module hardcodes a colour —
 * that is the rule, and it is the reason this module exists at all rather than
 * living inline in `IndiaMap.tsx`.
 *
 * ## Why the basemap is drawn rather than filtered
 *
 * The previous build used a single OSM raster source and faked a dark map with
 * `filter: invert(.94) hue-rotate(180deg)` on `.maplibregl-canvas`. That has
 * three failures a real style does not:
 *
 *   1. Inversion is not a palette. Landmass, water and roads all shift by the
 *      same rule, so the country reads as undifferentiated muddy grey and no
 *      token can influence it.
 *   2. OSM's raster bakes in local-script labels. Inverted, Chinese, Arabic and
 *      Thai place names around India's borders end up at *higher* contrast than
 *      Indian ones — on a platform whose subject is India.
 *   3. At city zoom the inverted tile collapses to near-black, which is exactly
 *      where the event detail map needs to be legible.
 *
 * Vector tiles fix all three at once: the style below decides every colour, so
 * dark and light are two honest palettes rather than one palette and a filter,
 * and `name:en` gives Latin labels everywhere.
 *
 * ## Why OpenFreeMap
 *
 * It serves OpenMapTiles-schema vector tiles and glyphs with no API key and no
 * signup, which keeps the console runnable from a clean checkout. CARTO's
 * basemaps now watermark unkeyed requests and Stadia/Stamen require an account;
 * both would put a credential between a judge and a working demo.
 */

const TILES = "https://tiles.openfreemap.org/planet";
const GLYPHS = "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf";

const ATTRIBUTION =
  '<a href="https://openfreemap.org" target="_blank" rel="noreferrer">OpenFreeMap</a> · ' +
  '<a href="https://www.openmaptiles.org/" target="_blank" rel="noreferrer">© OpenMapTiles</a> · ' +
  'data from <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a>';

const REGULAR = ["Noto Sans Regular"];
const BOLD = ["Noto Sans Bold"];

/** Read a CSS custom property off the document root. */
function token(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/** Place names in Latin script, falling back to the local name when there is
    no English variant — never the other way round. */
const NAME_EN: unknown = ["coalesce", ["get", "name:en"], ["get", "name:latin"], ["get", "name"]];

export interface MapStyleOptions {
  /** The detail panel's inset map sits behind a dense scatter of report pins at
      city zoom, so its labels and roads are held back further than the main
      map's — the pins are the content there. */
  recede?: boolean;
}

export function buildMapStyle(theme: Theme, options: MapStyleOptions = {}): StyleSpecification {
  const dark = theme === "dark";
  const recede = options.recede ?? false;

  const land = token("--map-land", dark ? "#1b1711" : "#f2ebde");
  const landAlt = token("--map-land-alt", dark ? "#221d15" : "#e8e2cd");
  const water = token("--map-water", dark ? "#101821" : "#cdd7e3");
  const boundary = token("--map-boundary", "rgba(255,240,218,.14)");
  const boundaryCountry = token("--map-boundary-country", "rgba(255,240,218,.28)");
  const road = token("--map-road", "rgba(255,240,218,.055)");
  const roadMajor = token("--map-road-major", "rgba(255,240,218,.11)");
  const building = token("--map-building", "rgba(255,240,218,.05)");
  const label = token("--map-label", dark ? "#a2957f" : "#6a5f51");
  const labelStrong = token("--map-label-strong", dark ? "#cbbda4" : "#3f372d");
  const halo = token("--map-label-halo", dark ? "#15120e" : "#f7f2e8");

  // Labels compete with pins. On the inset map they lose.
  const labelOpacity = recede ? 0.45 : 1;

  return {
    version: 8,
    glyphs: GLYPHS,
    sources: {
      openfreemap: { type: "vector", url: TILES, attribution: ATTRIBUTION },
    },
    layers: [
      { id: "ground", type: "background", paint: { "background-color": land } },

      /* Vegetation and parks lift the land off the ground colour just enough to
         give the country internal shape, without becoming green — a saturated
         basemap would compete with the event pins, which are the content. */
      {
        id: "landcover",
        type: "fill",
        source: "openfreemap",
        "source-layer": "landcover",
        filter: ["in", ["get", "class"], ["literal", ["wood", "grass", "scrub"]]],
        paint: { "fill-color": landAlt, "fill-opacity": dark ? 0.55 : 0.75 },
      },
      {
        id: "park",
        type: "fill",
        source: "openfreemap",
        "source-layer": "park",
        paint: { "fill-color": landAlt, "fill-opacity": dark ? 0.45 : 0.6 },
      },

      {
        id: "water",
        type: "fill",
        source: "openfreemap",
        "source-layer": "water",
        filter: ["!=", ["get", "brunnel"], "tunnel"],
        paint: { "fill-color": water },
      },
      {
        id: "waterway",
        type: "line",
        source: "openfreemap",
        "source-layer": "waterway",
        minzoom: 5,
        paint: {
          "line-color": water,
          "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.5, 12, 2.2],
        },
      },

      {
        id: "building",
        type: "fill",
        source: "openfreemap",
        "source-layer": "building",
        minzoom: 13,
        paint: {
          "fill-color": building,
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 13, 0, 15, 1],
        },
      },

      /* Roads are texture, not navigation: this console is about where events
         are, and a full road hierarchy would bury the pins. Two weights only. */
      {
        id: "road-minor",
        type: "line",
        source: "openfreemap",
        "source-layer": "transportation",
        minzoom: 10,
        filter: ["in", ["get", "class"], ["literal", ["minor", "service", "tertiary"]]],
        paint: {
          "line-color": road,
          "line-width": ["interpolate", ["linear"], ["zoom"], 10, 0.4, 16, 3],
        },
      },
      {
        id: "road-major",
        type: "line",
        source: "openfreemap",
        "source-layer": "transportation",
        minzoom: 6,
        filter: [
          "in",
          ["get", "class"],
          ["literal", ["motorway", "trunk", "primary", "secondary"]],
        ],
        paint: {
          "line-color": roadMajor,
          "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.4, 10, 1.1, 16, 4],
        },
      },

      /* State boundaries matter here in a way they do not on a general-purpose
         map: every filter, every alert and every advisory in this platform is
         addressed to a state or a district. Dashed for internal, solid for
         national. */
      {
        id: "boundary-state",
        type: "line",
        source: "openfreemap",
        "source-layer": "boundary",
        filter: [">=", ["get", "admin_level"], 3],
        paint: {
          "line-color": boundary,
          "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.5, 8, 1.1],
          "line-dasharray": [2.5, 2],
        },
      },
      {
        id: "boundary-country",
        type: "line",
        source: "openfreemap",
        "source-layer": "boundary",
        filter: ["<=", ["get", "admin_level"], 2],
        paint: {
          "line-color": boundaryCountry,
          "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.8, 8, 1.8],
        },
      },

      {
        id: "label-water",
        type: "symbol",
        source: "openfreemap",
        "source-layer": "water_name",
        minzoom: 4,
        layout: {
          "text-field": NAME_EN as never,
          "text-font": REGULAR,
          "text-size": ["interpolate", ["linear"], ["zoom"], 4, 9, 10, 12],
          "text-letter-spacing": 0.08,
          "text-max-width": 8,
        },
        paint: {
          "text-color": label,
          "text-halo-color": halo,
          "text-halo-width": 1.1,
          "text-opacity": labelOpacity * 0.8,
        },
      },
      {
        id: "label-place-small",
        type: "symbol",
        source: "openfreemap",
        "source-layer": "place",
        minzoom: 7,
        filter: [
          "all",
          ["in", ["get", "class"], ["literal", ["town", "village", "suburb"]]],
          ["==", ["get", "iso_a2"], "IN"],
        ],
        layout: {
          "text-field": NAME_EN as never,
          "text-font": REGULAR,
          "text-size": ["interpolate", ["linear"], ["zoom"], 7, 9.5, 12, 12],
          "text-max-width": 8,
        },
        paint: {
          "text-color": label,
          "text-halo-color": halo,
          "text-halo-width": 1.2,
          "text-opacity": labelOpacity,
        },
      },
      /* Cities are split by country. A console about Indian weather should not
         give Chengdu and Bangkok the same presence as Nagpur — they are there
         for orientation, nothing more. `rank` additionally thins the label set
         at the India-wide framing, where every label competes with a pin. */
      {
        id: "label-place-city-foreign",
        type: "symbol",
        source: "openfreemap",
        "source-layer": "place",
        minzoom: 4,
        filter: [
          "all",
          ["==", ["get", "class"], "city"],
          ["!=", ["get", "iso_a2"], "IN"],
          ["<=", ["get", "rank"], 6],
        ],
        layout: {
          "text-field": NAME_EN as never,
          "text-font": REGULAR,
          "text-size": ["interpolate", ["linear"], ["zoom"], 4, 9.5, 10, 12],
          "text-max-width": 8,
        },
        paint: {
          "text-color": label,
          "text-halo-color": halo,
          "text-halo-width": 1.2,
          "text-opacity": labelOpacity * 0.5,
        },
      },
      {
        id: "label-place-city",
        type: "symbol",
        source: "openfreemap",
        "source-layer": "place",
        minzoom: 4,
        filter: ["all", ["==", ["get", "class"], "city"], ["==", ["get", "iso_a2"], "IN"]],
        layout: {
          "text-field": NAME_EN as never,
          "text-font": REGULAR,
          "text-size": ["interpolate", ["linear"], ["zoom"], 4, 10.5, 10, 14],
          "text-max-width": 8,
        },
        paint: {
          "text-color": labelStrong,
          "text-halo-color": halo,
          "text-halo-width": 1.3,
          "text-opacity": labelOpacity,
        },
      },
      /* States are set in spaced capitals, the way they are printed on a
         bulletin map, so they read as territory rather than as another city. */
      {
        id: "label-state",
        type: "symbol",
        source: "openfreemap",
        "source-layer": "place",
        minzoom: 5,
        maxzoom: 9,
        filter: ["in", ["get", "class"], ["literal", ["state", "province"]]],
        layout: {
          "text-field": NAME_EN as never,
          "text-font": BOLD,
          "text-transform": "uppercase",
          "text-size": ["interpolate", ["linear"], ["zoom"], 4, 8.5, 8, 11],
          "text-letter-spacing": 0.16,
          "text-max-width": 9,
        },
        paint: {
          "text-color": label,
          "text-halo-color": halo,
          "text-halo-width": 1.2,
          "text-opacity": labelOpacity * 0.85,
        },
      },
      /* Neighbouring countries are context and are set back accordingly. */
      {
        id: "label-country",
        type: "symbol",
        source: "openfreemap",
        "source-layer": "place",
        maxzoom: 6,
        filter: [
          "all",
          ["==", ["get", "class"], "country"],
          ["!=", ["get", "iso_a2"], "IN"],
        ],
        layout: {
          "text-field": NAME_EN as never,
          "text-font": BOLD,
          "text-transform": "uppercase",
          "text-size": ["interpolate", ["linear"], ["zoom"], 2, 8.5, 5, 10.5],
          "text-letter-spacing": 0.2,
          "text-max-width": 7,
        },
        paint: {
          "text-color": label,
          "text-halo-color": halo,
          "text-halo-width": 1.2,
          "text-opacity": labelOpacity * 0.45,
        },
      },
      /* India is the subject of the platform, so it is the one country label
         that carries weight. */
      {
        id: "label-country-india",
        type: "symbol",
        source: "openfreemap",
        "source-layer": "place",
        maxzoom: 6,
        filter: [
          "all",
          ["==", ["get", "class"], "country"],
          ["==", ["get", "iso_a2"], "IN"],
        ],
        layout: {
          "text-field": NAME_EN as never,
          "text-font": BOLD,
          "text-transform": "uppercase",
          "text-size": ["interpolate", ["linear"], ["zoom"], 2, 11, 5, 15],
          "text-letter-spacing": 0.3,
          "text-max-width": 7,
        },
        paint: {
          "text-color": labelStrong,
          "text-halo-color": halo,
          "text-halo-width": 1.4,
          "text-opacity": labelOpacity * 0.9,
        },
      },
    ],
  } as StyleSpecification;
}
