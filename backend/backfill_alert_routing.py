"""Route alerts that were raised before the authority registry existed.

Third time this pattern has appeared (warning levels, then alerts, now
deliveries): anything derived from an event is only recomputed when a report
attaches, so rows created earlier need an explicit backfill.

Scoped to alerts that are still live — routing a stood-down alert would tell a
district to prepare for something already over.
"""
import asyncio

from sqlalchemy import select

from app.db.models import Alert, AlertStatus
from app.db.session import SessionLocal, engine
from app.services.pipeline.routing import route

LIVE = (AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED)


async def main() -> None:
    queued = 0
    async with SessionLocal() as session:
        alerts = (
            await session.execute(select(Alert).where(Alert.status.in_(LIVE)))
        ).scalars().all()
        for alert in alerts:
            queued += await route(session, alert)
        await session.commit()
    print(f"routing backfill: {len(alerts)} live alerts, {queued} deliveries queued")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
