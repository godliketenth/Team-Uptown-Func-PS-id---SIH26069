import * as React from "react";

const KEY = "nwap.theme";
export type Theme = "dark" | "light";

/**
 * Theme lives in a module-level store rather than in component state.
 *
 * The toggle is rendered once, in the top bar, but the theme is now read in
 * more than one place: the map has to rebuild its basemap style when the mode
 * changes, and the charts re-read their axis colours. With per-component
 * `useState` each caller had its own copy and only the one holding the toggle
 * ever saw a change.
 */

function initial(): Theme {
  try {
    return (localStorage.getItem(KEY) as Theme) ?? "dark";
  } catch {
    // Private windows and blocked site data throw; dark is the operational
    // default and a theme preference must never break the console.
    return "dark";
  }
}

let current: Theme = initial();
const listeners = new Set<() => void>();

function apply(theme: Theme) {
  const root = document.documentElement;
  root.classList.toggle("light", theme === "light");
  root.classList.toggle("dark", theme === "dark");
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* preference is a convenience, not a requirement */
  }
}

apply(current);

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function getSnapshot(): Theme {
  return current;
}

/** The theme right now. For imperative consumers such as the MapLibre
    constructor, which needs a value at the moment it builds a style rather
    than a subscription. */
export function getTheme(): Theme {
  return current;
}

export function setTheme(theme: Theme) {
  if (theme === current) return;
  current = theme;
  apply(theme);
  for (const fn of listeners) fn();
}

/** Dark is the operational default; the toggle is a convenience, not the norm. */
export function useTheme() {
  const theme = React.useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  return {
    theme,
    toggle: () => setTheme(theme === "dark" ? "light" : "dark"),
  };
}
