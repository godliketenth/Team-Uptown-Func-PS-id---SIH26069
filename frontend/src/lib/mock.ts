/**
 * `?mock=1` — freeze the console against a fixed dataset.
 *
 * This platform ingests continuously and pushes updates over SSE, which is
 * correct for an operations console and hostile to UI work: every screenshot
 * differs, every comparison drifts, and a layout bug is indistinguishable from
 * new data arriving. Mock mode makes the screen a pure function of the code.
 *
 * Three things happen when it is on:
 *
 *   1. Every `/api/v1` call is served from `fixtures/api.json` — real responses
 *      captured from a running backend, not hand-written objects that drift
 *      from the actual schema.
 *   2. The live SSE stream is never opened, and polling is disabled, so
 *      nothing refetches behind you.
 *   3. The map starts at a fixed centre and zoom instead of fitting bounds to
 *      the container, which otherwise changes with window size.
 *
 * It needs **no backend running at all** — that is the point, and the easiest
 * way to prove the freeze is real.
 *
 * Turn it on with `?mock=1`, off with `?mock=0`. The flag is remembered for
 * the tab so client-side navigation keeps it.
 *
 * Re-record the fixtures with `npm run capture-fixtures` (backend must be up).
 */

const FLAG = "nwap.mock";

function readFlag(): boolean {
  try {
    const param = new URLSearchParams(window.location.search).get("mock");
    if (param === "1" || param === "true") {
      sessionStorage.setItem(FLAG, "1");
      return true;
    }
    if (param === "0" || param === "false") {
      sessionStorage.removeItem(FLAG);
      return false;
    }
    return sessionStorage.getItem(FLAG) === "1";
  } catch {
    // Private windows and blocked site data throw on sessionStorage; mock mode
    // is a developer convenience and must never break the real app.
    return false;
  }
}

// Read once at module load. A flag that changes mid-session would defeat the
// purpose of freezing anything.
const MOCK = readFlag();

export function isMockMode(): boolean {
  return MOCK;
}

/** Fixed view for the India map, so the framing never depends on window size. */
export const MOCK_MAP_VIEW = { center: [82.5, 22.6] as [number, number], zoom: 4.05 };

type Fixtures = Record<string, unknown>;
let cache: Promise<Fixtures> | null = null;

function fixtures(): Promise<Fixtures> {
  // Dynamic import so the ~2MB of captured responses is a separate chunk that
  // normal (non-mock) sessions never download.
  if (!cache) cache = import("../fixtures/api.json").then((m) => m.default as Fixtures);
  return cache;
}

/**
 * The recorded response for an API path, or `undefined` if nothing matches.
 *
 * Tries the exact path first, so a recorded URL renders exactly what was
 * captured. Falls back to the same pathname with different query parameters,
 * which is what makes filtering and pagination still render something sensible
 * rather than an error — the data stays frozen, which is the whole point.
 */
export async function mockResponse<T>(path: string): Promise<T | undefined> {
  const data = await fixtures();
  if (path in data) return data[path] as T;

  const pathname = path.split("?")[0];
  if (pathname in data) return data[pathname] as T;

  const sameRoute = Object.keys(data).find((k) => k.split("?")[0] === pathname);
  if (sameRoute) return data[sameRoute] as T;

  // Per-resource routes carry an id in the path, so an exact match only ever
  // works for the one id that happened to be recorded. Every other event in
  // the frozen dataset would spin on "Loading event" forever — which defeats
  // the point of a mode whose whole job is to be demoable with no backend.
  //
  // Fall back to the recorded response for the same *route shape*: the
  // evidence shown belongs to a different event than the one selected, and in
  // mock mode that is the correct trade. The dataset is frozen scenery, not
  // ground truth.
  const shape = routeShape(pathname);
  if (shape) {
    const match = Object.keys(data).find((k) => routeShape(k.split("?")[0]) === shape);
    if (match) return data[match] as T;
  }

  return undefined;
}

/**
 * Collapse an id inside a path to a placeholder, so `/events/<uuid>/reports`
 * and `/events/<other-uuid>/reports` compare equal.
 */
function routeShape(pathname: string): string | null {
  const parts = pathname.split("/");
  let sawId = false;
  const shaped = parts.map((part) => {
    // UUIDs and long opaque ids, not the short literal segments of a route.
    if (/^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(part) || /^[0-9a-f]{16,}$/i.test(part)) {
      sawId = true;
      return ":id";
    }
    return part;
  });
  return sawId ? shaped.join("/") : null;
}

/**
 * Mock mode signs you in as the recorded user without a real token, so the
 * admin console is reachable with no backend. The value is a marker, not a
 * credential — nothing verifies it, because nothing is called.
 */
export const MOCK_TOKEN = "mock-session-no-backend";
