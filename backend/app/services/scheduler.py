"""Ingestion scheduler.

One APScheduler job per concern:
  * ingest_tick     - poll every ACTIVE source, append to raw_events, publish
                      onto the in-process bus (every SCHEDULER_INTERVAL_SECONDS)
  * housekeeping    - resolve events nobody has reported on for hours
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.config import settings
from app.db.models import Source, SourceStatus, SourceType
from app.db.session import SessionLocal
from app.services import bus, notify
from app.services.ingestion.connectors import (
    NewsRssConnector,
    OpenMeteoConnector,
    SatelliteConnector,
    StubConnector,
)
from app.services.pipeline.corroborate import dominant_condition
from app.services.pipeline.event_engine import resolve_stale_events
from app.services.pipeline.routing import dispatch_pending
from app.services.pipeline.geo import CITIES, HOT_CITIES
from app.services.pipeline.runner import store_raw_event

log = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")

_stub = StubConnector()
_open_meteo = OpenMeteoConnector()
_satellite = SatelliteConnector()
_news_rss = NewsRssConnector()


async def ingest_tick() -> None:
    """Collect one round from every source that is active and due."""
    bus.mark_tick()
    await bus.refresh_lag()
    now = datetime.now(timezone.utc)

    async with SessionLocal() as session:
        sources = (await session.execute(select(Source))).scalars().all()

        # A source contributes only when it is ACTIVE *and* its configured poll
        # interval has elapsed. Without this the interval shown in the admin
        # table would be decorative, and a 30-minute satellite cycle would fire
        # as often as an 8-second citizen stream.
        due_by_type: dict[SourceType, list[Source]] = {}
        for src in sources:
            if src.status == SourceStatus.ACTIVE and _is_due(src, now):
                due_by_type.setdefault(src.source_type, []).append(src)
        due_types = set(due_by_type)

        hints = await _condition_hints()

        collected: list = []
        polled: set[SourceType] = set()

        live_rss_due = [
            src
            for src in due_by_type.get(SourceType.WEB_RSS, [])
            if src.name == _news_rss.name
        ]

        simulated_due = due_types - {SourceType.WEATHER_API, SourceType.SATELLITE}
        if simulated_due:
            try:
                collected.extend(await _stub.poll(hints, allowed_sources=simulated_due))
                polled |= simulated_due
            except Exception as exc:
                log.exception("stub connector failed")
                _mark_failure(
                    [s for t in simulated_due for s in due_by_type[t]], str(exc), now
                )

        if SourceType.WEATHER_API in due_types:
            try:
                collected.extend(await _open_meteo.poll())
                polled.add(SourceType.WEATHER_API)
            except Exception as exc:
                log.warning("open-meteo connector failed: %s", exc)
                _mark_failure(due_by_type[SourceType.WEATHER_API], str(exc), now)

        if live_rss_due:
            try:
                collected.extend(await _news_rss.poll())
                for src in live_rss_due:
                    src.last_success_at = now
                    src.last_error_message = None
            except Exception as exc:
                log.warning("news rss connector failed: %s", exc)
                _mark_failure(live_rss_due, str(exc), now)

        if SourceType.SATELLITE in due_types:
            try:
                collected.extend(await _satellite.poll())
                polled.add(SourceType.SATELLITE)
            except Exception as exc:
                log.warning("satellite connector failed: %s", exc)
                _mark_failure(due_by_type[SourceType.SATELLITE], str(exc), now)

        published = 0
        for item in collected:
            candidates = due_by_type.get(item.source_type)
            if not candidates:
                continue
            if item.source_name:
                named = [s for s in candidates if s.name == item.source_name]
                if not named:
                    continue
                source = named[0]
            else:
                # Spread across every due source of that type, so an event
                # genuinely accumulates independent sources.
                source = random.choice(
                    [s for s in candidates if s.name != _news_rss.name] or candidates
                )
            raw = await store_raw_event(
                session=session,
                source_id=source.id,
                source_type=item.source_type,
                external_id=item.external_id,
                payload=item.payload,
                collected_at=item.collected_at,
            )
            await session.commit()
            if bus.publish_nowait(raw.id):
                published += 1

        # A poll that completed is a success even when it yielded nothing - a
        # clear sky is a valid satellite reading. Marking it here is what stops
        # a silent source being treated as perpetually overdue.
        for source_type in polled:
            for src in due_by_type[source_type]:
                src.last_success_at = now
                src.last_error_message = None

        await session.commit()

    if published:
        # One message per tick, not per report: a tick that ingested 40 rows
        # should cost the client one refetch, not forty.
        notify.publish("ingest", published=published, collected=len(collected))

    log.info(
        "ingest tick: due=%s collected=%s published=%s",
        sorted(t.value for t in due_types),
        len(collected),
        published,
    )


def _is_due(source: Source, now: datetime) -> bool:
    """True when this source has never run, or its interval has elapsed.

    A satellite on a 30-minute cycle and a citizen stream on an 8-second one
    genuinely behave differently; honouring the field is what makes the admin
    table mean something.
    """
    if source.last_success_at is None:
        return True
    elapsed = (now - source.last_success_at).total_seconds()
    return elapsed >= max(1, source.poll_interval_seconds)


async def _condition_hints() -> dict[str, str]:
    """What weather is actually happening in the busiest cities right now.

    Keeps most synthetic traffic anchored to reality, so corroboration and the
    credibility flags carry real information instead of firing on everything.
    Readings are cached per (0.1 degree, hour), so this costs a handful of
    calls per hour, not per tick.
    """
    now = datetime.now(timezone.utc)
    hints: dict[str, str] = {}
    for city in HOT_CITIES:
        lat, lon, _district, _state = CITIES[city]
        try:
            condition = await dominant_condition(lat, lon, now, city)
        except Exception:
            condition = None
        if condition:
            hints[city] = condition
    return hints


def _mark_failure(sources: list[Source], message: str, now: datetime) -> None:
    for src in sources:
        src.last_failure_at = now
        src.last_error_message = message[:500]


async def dispatch_alerts() -> None:
    """Work the alert delivery queue. Separate from ingestion so a slow or
    unreachable webhook can never stall data collection."""
    async with SessionLocal() as session:
        try:
            await dispatch_pending(session)
        except Exception:
            log.exception("alert dispatch failed")


async def housekeeping() -> None:
    async with SessionLocal() as session:
        resolved = await resolve_stale_events(session)
        await session.commit()
        if resolved:
            log.info("housekeeping resolved %s stale events", resolved)


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        ingest_tick,
        "interval",
        seconds=settings.scheduler_interval_seconds,
        id="ingest_tick",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.add_job(
        dispatch_alerts,
        "interval",
        seconds=15,
        id="dispatch_alerts",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        housekeeping, "interval", minutes=5, id="housekeeping", max_instances=1, coalesce=True
    )
    scheduler.start()
    log.info("scheduler started (interval=%ss)", settings.scheduler_interval_seconds)


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
