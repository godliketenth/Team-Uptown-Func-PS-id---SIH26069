import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { connectLiveStream } from "./lib/live";
import { MOCK_TOKEN, isMockMode } from "./lib/mock";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // No retries in mock mode: a missing fixture should surface immediately
      // rather than after three identical failures.
      retry: isMockMode() ? false : 1,
      refetchOnWindowFocus: false,
      // Updates arrive over the live stream (see lib/live.ts); polling stays
      // as the fallback when it drops. Showing the previous page while the
      // next one loads avoids the console flashing on every refresh.
      placeholderData: (prev: unknown) => prev,
      // Frozen data never goes stale, so nothing refetches behind a screenshot.
      staleTime: isMockMode() ? Infinity : 2000,
    },
  },
});

if (isMockMode()) {
  // Sign in as the recorded user so the admin console is reachable with no
  // backend at all — the clearest proof that the freeze is real.
  try {
    localStorage.setItem("nwap.token", MOCK_TOKEN);
  } catch {
    /* private window; the app still renders the public dashboard */
  }
}

// Opened once for the life of the tab, outside React, so StrictMode's double
// mount in development cannot open two connections. A no-op in mock mode.
connectLiveStream(queryClient);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
