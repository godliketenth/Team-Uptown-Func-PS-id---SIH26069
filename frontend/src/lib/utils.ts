import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function shortId(id: string, len = 8) {
  return id.replace(/-/g, "").slice(0, len).toUpperCase();
}

export function fmtCoord(v: number | null | undefined, digits = 3) {
  return v === null || v === undefined ? "—" : v.toFixed(digits);
}

export function fmtPct(v: number | null | undefined) {
  return v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`;
}

export function fmtTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function fmtDateTime(iso: string) {
  const d = new Date(iso);
  return `${d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" })} ${d.toLocaleTimeString(
    "en-GB",
    { hour: "2-digit", minute: "2-digit" },
  )}`;
}

export function relativeTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.max(0, Math.round(diff / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}


/**
 * A data hue, safe to use as text on either ground.
 *
 * The event and status scales are tuned as pin fills, which means mid
 * lightness — fine as white-on-colour or on a dark ground, and far below
 * contrast minimums as coloured text on light paper. This mixes the hue toward
 * ink by an amount the theme decides: nothing in dark mode, about a third in
 * light. Use it wherever a scale colour is applied to `color`, never to
 * `background`.
 */
export function textHue(color: string): string {
  return `color-mix(in oklab, ${color} var(--hue-strength), var(--hue-shade))`;
}
