/**
 * Shared Recharts styling, derived from the design tokens.
 *
 * Every chart in the console takes its axis, grid and tooltip props from here.
 * Nothing in this module hardcodes a hex value: each colour is read from a CSS
 * custom property at render time, which is what makes a chart follow the theme
 * toggle instead of staying dark on a light page.
 *
 * Charts previously styled themselves inline — `TimelineChart` and
 * `AdminHealth` each carried their own axis colours and tooltip chrome, with
 * literal `#64748b` and `rgba(21,27,37,.94)` values that no longer existed
 * anywhere else in the system.
 */

import * as React from "react";
import { useTheme } from "@/hooks/useTheme";

function token(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

export const MONO = "IBM Plex Mono, ui-monospace, monospace";
export const SANS = "IBM Plex Sans, ui-sans-serif, system-ui, sans-serif";

/** Tick styling for either axis. Always mono — figures are figures. */
export function axisTick() {
  return {
    fill: token("--text-faint", "#7e7263"),
    fontSize: 12,
    fontFamily: MONO,
  } as const;
}

export function axisLine() {
  return { stroke: token("--hairline", "rgba(255,240,218,.085)") } as const;
}

export function gridStroke() {
  return token("--hairline-soft", "rgba(255,240,218,.05)");
}

/** The floating tooltip surface, matched to `.panel` in `index.css`. */
export function tooltipContentStyle() {
  return {
    background: token("--surface-panel", "#1e1a14"),
    border: `1px solid ${token("--hairline", "rgba(255,240,218,.085)")}`,
    borderRadius: Number.parseInt(token("--r-md", "11px"), 10),
    fontSize: 13.5,
    fontFamily: SANS,
    color: token("--text-ink", "#f2ede4"),
    boxShadow: token("--shadow-lg", "0 18px 48px -12px rgba(12,7,2,.75)"),
    padding: "8px 10px",
  } as const;
}

export function tooltipLabelStyle() {
  return {
    color: token("--text-dim", "#b0a392"),
    fontFamily: MONO,
    fontSize: 12.5,
    marginBottom: 3,
  } as const;
}

export function tooltipItemStyle() {
  return { padding: 0, fontSize: 13.5 } as const;
}

/** Cursor line/fill shown under the pointer. */
export function tooltipCursor() {
  return { stroke: token("--hairline", "rgba(255,240,218,.085)"), strokeWidth: 1 } as const;
}

export function tooltipCursorFill() {
  return { fill: token("--veil-1", "rgba(255,238,214,.045)") } as const;
}


/**
 * The whole theme as one memoised bundle.
 *
 * Every helper above builds a fresh object each time it is called. Passed
 * straight into Recharts as `tick={axisTick()}` that is a new prop identity on
 * every render, so Recharts rebuilt its entire SVG whenever anything on the
 * page re-rendered — and the dashboard polls four endpoints on a five-second
 * cadence, so the chart was tearing itself down and rebuilding several times a
 * second. That is what the flicker was.
 *
 * Memoising on the theme gives Recharts stable props: the chart now re-renders
 * when its data changes or the mode is toggled, and not otherwise.
 */
export function useChartTheme() {
  const { theme } = useTheme();
  return React.useMemo(
    () => ({
      // Carried through so the dependency below is a real one: these values are
      // read off the document root, so the mode is genuinely what they depend
      // on, but a linter cannot see that through `getComputedStyle`.
      theme,
      tick: axisTick(),
      axisLine: axisLine(),
      grid: gridStroke(),
      tooltipContent: tooltipContentStyle(),
      tooltipLabel: tooltipLabelStyle(),
      tooltipItem: tooltipItemStyle(),
      cursor: tooltipCursor(),
      cursorFill: tooltipCursorFill(),
    }),
    [theme],
  );
}
