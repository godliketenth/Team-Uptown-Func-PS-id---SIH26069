"""One-off backfill for `events.warning_level` and the alerts derived from it.

`recompute_event` only runs when a new report attaches, so events that existed
before the column was added keep the migration's GREEN default until something
happens to them. This recomputes every event from its stored evidence, using
the same `assess()` the pipeline uses, so there is one source of truth.

Safe to re-run.
"""
import asyncio

from sqlalchemy import select

from datetime import datetime, timedelta, timezone

from app.db.models import Event, EventStatus, WarningLevel
from app.db.session import SessionLocal, engine
from app.services.pipeline.alerting import evaluate as evaluate_alert
from app.services.pipeline.warning import assess

# Only still-live, recently-active events get an alert backfilled. Raising a
# warning for something that stopped being reported hours ago would be noise,
# not information.
ALERT_BACKFILL_WINDOW = timedelta(hours=3)
OPEN_STATUSES = (
    EventStatus.DETECTED,
    EventStatus.CORROBORATING,
    EventStatus.NEEDS_REVIEW,
    EventStatus.VERIFIED,
)

BATCH = 500


async def main() -> None:
    changed = 0
    alerted = 0
    total = 0
    cutoff = datetime.now(timezone.utc) - ALERT_BACKFILL_WINDOW
    async with SessionLocal() as session:
        events = (await session.execute(select(Event))).scalars().all()
        total = len(events)
        for i, event in enumerate(events, 1):
            result = assess(
                status=event.status.value,
                report_count=event.report_count,
                source_count=event.source_count,
                evidence_score=event.evidence_score,
                corroboration_score=event.corroboration_score,
                flagged_report_count=event.flagged_report_count,
            )
            new_level = WarningLevel(result.level.value)
            if event.warning_level != new_level or event.warning_reasons is None:
                event.warning_level = new_level
                event.warning_reasons = result.as_dict()
                changed += 1

            if event.status in OPEN_STATUSES and event.last_updated >= cutoff:
                if await evaluate_alert(session, event) is not None:
                    alerted += 1
            if i % BATCH == 0:
                await session.commit()
                print(f"  {i}/{total} processed, {changed} updated", end="\r")
        await session.commit()
    print(f"\nbackfill complete: {changed} of {total} events updated, "
          f"{alerted} with a live alert")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
