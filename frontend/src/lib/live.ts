import type { QueryClient } from "@tanstack/react-query";
import { getToken } from "./api";
import { isMockMode } from "./mock";

/**
 * Live updates over server-sent events.
 *
 * The dashboard used to poll every 5 seconds, which is wrong twice: an alert
 * could sit unseen for five seconds, and most of those requests re-fetched
 * data that had not changed.
 *
 * A frame only ever says *what kind of thing changed*. The refetch still goes
 * through the ordinary authenticated endpoints, so the stream cannot show a
 * viewer anything their own queries would not.
 *
 * Read with `fetch` rather than `EventSource` because `EventSource` cannot set
 * an Authorization header, and the alternative — a token in the query string —
 * writes a credential into every proxy log between here and the server.
 */

let streamUp = false;
let stopped = false;

export function isLive() {
  return streamUp;
}

/**
 * Polling interval to use for a query, given the stream.
 *
 * Polling is not removed, it is demoted. If the stream drops — a proxy timeout,
 * a laptop waking from sleep, a backend restart — a console that silently stops
 * updating is far worse than one that quietly polls. Passed as a function so
 * TanStack re-evaluates it when the connection state changes.
 */
export function livePoll(ms: number): () => number | false {
  // Mock mode freezes the data; a poll would refetch the same fixture forever
  // and re-render for no reason.
  if (isMockMode()) return () => false;
  return () => (streamUp ? false : ms);
}

/** Which cached queries a given frame invalidates. */
function invalidate(qc: QueryClient, kind: string) {
  if (kind === "heartbeat" || kind === "hello") return;
  if (kind === "alert") {
    // An alert changes the queue, its badge, and the event behind it.
    qc.invalidateQueries({ queryKey: ["alerts"] });
    qc.invalidateQueries({ queryKey: ["alert-summary"] });
    qc.invalidateQueries({ queryKey: ["events"] });
    return;
  }
  // An ingest tick can move almost anything on screen. Invalidating broadly is
  // right here: TanStack only refetches queries that are actually mounted, so
  // this costs requests for what the user is looking at and nothing else.
  qc.invalidateQueries();
}

/**
 * Opens the stream and keeps it open. Returns a function that closes it.
 * Reconnects with backoff, because a dropped connection that never comes back
 * would leave the console frozen.
 */
export function connectLiveStream(qc: QueryClient): () => void {
  if (isMockMode()) {
    console.info("[mock] live stream not opened — dataset is frozen");
    return () => {};
  }
  stopped = false;
  const controller = new AbortController();
  let attempt = 0;

  const run = async () => {
    while (!stopped) {
      try {
        const token = getToken();
        if (!token) {
          // Not signed in yet; wait rather than hammering a 401.
          await sleep(2000);
          continue;
        }
        const res = await fetch("/api/v1/stream", {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (!res.ok || !res.body) throw new Error(`stream HTTP ${res.status}`);

        streamUp = true;
        attempt = 0;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // SSE frames are separated by a blank line. Anything after the last
          // separator is a partial frame and stays in the buffer.
          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";
          for (const frame of frames) {
            const kind =
              frame.match(/^event:\s*(.+)$/m)?.[1]?.trim() ?? "change";
            invalidate(qc, kind);
          }
        }
      } catch {
        // Falls through to the backoff below; the polling fallback covers the
        // gap in the meantime.
      }
      streamUp = false;
      if (stopped) return;
      attempt += 1;
      await sleep(Math.min(1000 * 2 ** Math.min(attempt, 4), 15000));
    }
  };

  void run();

  return () => {
    stopped = true;
    streamUp = false;
    controller.abort();
  };
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
