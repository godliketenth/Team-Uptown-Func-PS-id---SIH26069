#!/usr/bin/env python3
"""Re-record the mock-mode fixtures from a running backend.

Mock mode (`?mock=1`) serves the console from real captured responses rather
than hand-written objects, because hand-written fixtures drift from the actual
schema and then lie to you. That only holds if they are easy to re-record.

    # backend must be running on :8000
    python scripts/capture_fixtures.py

Writes frontend/src/fixtures/api.json.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://localhost:8000/api/v1"
OUT = Path(__file__).resolve().parents[1] / "frontend" / "src" / "fixtures" / "api.json"

# The paths the console actually requests. Query strings are recorded verbatim
# so a recorded URL renders exactly what was captured; mock.ts falls back to
# the same pathname for any other filter combination.
PATHS = [
    "/analytics/summary",
    "/analytics/timeline?hours=24",
    "/analytics/by-state",
    "/analytics/hashtags?hours=24",
    "/analytics/credibility?hours=24",
    "/analytics/preparedness?days=7&limit=40",
    "/map/events",
    "/map/reports",
    "/events?limit=100",
    "/events?limit=200",
    "/reports?limit=50",
    "/reports?limit=100",
    "/alerts?live_only=true&limit=200",
    "/alerts?limit=200",
    "/alerts/summary",
    "/verification/queue?limit=100",
    "/admin/sources",
    "/admin/system-health",
    "/admin/audit-logs?limit=100",
    "/admin/authorities",
    "/admin/delivery-stats",
    "/auth/me",
]


def main() -> int:
    try:
        req = urllib.request.Request(
            f"{BASE}/auth/login",
            data=json.dumps({"email": "admin@demo.in", "password": "admin123"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        token = json.load(urllib.request.urlopen(req, timeout=15))["access_token"]
    except Exception as exc:
        print(f"could not sign in — is the backend running on :8000? ({exc})")
        return 1

    def get(path: str):
        r = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {token}"})
        return json.load(urllib.request.urlopen(r, timeout=45))

    out: dict = {}
    for path in PATHS:
        try:
            out[path] = get(path)
            print(f"  recorded {path}")
        except Exception as exc:
            print(f"  SKIP     {path} ({type(exc).__name__})")

    # A representative event and alert, so the detail panels have something
    # substantial rather than the first row that happens to exist.
    events = out.get("/events?limit=100", {}).get("items", [])
    detail = next((e["id"] for e in events if e.get("report_count", 0) >= 5), None)
    if detail is None and events:
        detail = events[0]["id"]
    if detail:
        for path in (
            f"/events/{detail}",
            f"/events/{detail}/reports?limit=50",
            f"/events/{detail}/advisory",
        ):
            try:
                out[path] = get(path)
                print(f"  recorded {path}")
            except Exception as exc:
                print(f"  SKIP     {path} ({type(exc).__name__})")

    alerts = out.get("/alerts?live_only=true&limit=200", {}).get("items", [])
    if alerts:
        aid = alerts[0]["id"]
        for path in (f"/alerts/{aid}", f"/alerts/{aid}/advisory", f"/alerts/{aid}/deliveries"):
            try:
                out[path] = get(path)
                print(f"  recorded {path}")
            except Exception as exc:
                print(f"  SKIP     {path} ({type(exc).__name__})")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"\n{len(out)} responses → {OUT.relative_to(Path.cwd()) if OUT.is_relative_to(Path.cwd()) else OUT}")
    print(f"{OUT.stat().st_size / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
