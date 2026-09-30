"""Re-run geocoding on reports the old 65-city table could not place.

Phase 4.2 replaced a hand-written city table with a 9,093-name gazetteer, and
`resolve_location` only runs at ingest — so rows collected before the change
keep the answer the old code gave. This is the fourth time a derived column
has needed a backfill after the logic behind it changed (warning levels,
alerts, deliveries, now locations); the pattern is worth naming rather than
rediscovering.

Deliberately narrow. It touches:

  * reports with no location at all, which are all unclustered, so writing a
    location to them cannot move an existing event; and
  * reports from the live news feed, which is where the gazetteer's false
    positives would show up and where a wrong location is most visible.

It does not re-geocode clustered synthetic reports. Those resolved correctly
from their own `city_hint`, and moving a report that an event was built from
would silently change that event's centre — a worse outcome than a stale row.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import or_, select

from app.db.models import RawEvent, Report
from app.db.session import SessionLocal
from app.services.pipeline.event_engine import point_expr
from app.services.pipeline.geo import resolve_location


async def main() -> int:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Report, RawEvent.payload)
                .join(RawEvent, RawEvent.id == Report.raw_event_id)
                .where(
                    Report.event_id.is_(None),
                    or_(
                        Report.latitude.is_(None),
                        RawEvent.payload["provider"].astext == "google-news-rss",
                    ),
                )
            )
        ).all()

        print(f"examining {len(rows):,} candidate reports")
        resolved = corrected = cleared = 0

        for report, payload in rows:
            text = report.normalized_text or report.raw_text or ""
            hint = (payload or {}).get("city_hint")
            geo = resolve_location(text, city_hint=hint)

            before = (report.latitude, report.city, report.state)
            if geo.method == "unresolved":
                # The gazetteer now rejects what it used to accept wrongly.
                # Clearing is the honest write: no location beats a confident
                # wrong one.
                if report.latitude is not None:
                    report.latitude = report.longitude = None
                    report.city = report.district = report.state = None
                    report.geom = None
                    cleared += 1
                continue

            report.latitude = geo.latitude
            report.longitude = geo.longitude
            report.city = geo.city
            report.district = geo.district
            report.state = geo.state
            report.geom = point_expr(geo.latitude, geo.longitude)

            if before[0] is None:
                resolved += 1
            elif before[1:] != (geo.city, geo.state):
                corrected += 1

        await session.commit()

    print(f"  newly located : {resolved:,}")
    print(f"  corrected     : {corrected:,}")
    print(f"  cleared (was wrong, now unresolvable): {cleared:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
