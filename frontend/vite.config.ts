import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // MapLibre ships its worker as a separate entry the dep optimizer cannot
  // pre-bundle; excluding it keeps `npm run dev` output clean.
  optimizeDeps: { exclude: ["maplibre-gl"] },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    // 5180, not Vite's default 5173: that port is commonly already taken by
    // another project, and a console that silently starts somewhere else is
    // a demo-day surprise. strictPort makes the collision fail loudly instead.
    port: 5180,
    strictPort: true,
    // Bind every interface. Left to itself Vite bound only to IPv6 `[::1]` on
    // this machine, so `curl localhost` succeeded while Chrome — resolving to
    // 127.0.0.1 — got "This site can't be reached". A demo that works in the
    // terminal and not in the browser is the worst possible failure mode.
    host: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
