"""Map layers.

Kept deliberately thin: the dashboard polls these every 5 seconds, so they
return only what a pin needs. Bounding-box filtering runs through PostGIS.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event, EventStatus, EventType, Report, WarningLevel
from app.db.session import get_session
from app.schemas.events import MapEvent, MapReport

router = APIRouter(prefix="/map", tags=["map"])


def bbox_filter(column, min_lon, min_lat, max_lon, max_lat):
    if None in (min_lon, min_lat, max_lon, max_lat):
        return None
    envelope = func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
    return func.ST_Intersects(column, func.ST_GeogFromWKB(func.ST_AsBinary(envelope)))


@router.get("/events", response_model=list[MapEvent])
async def map_events(
    session: AsyncSession = Depends(get_session),
    min_lon: float | None = None,
    min_lat: float | None = None,
    max_lon: float | None = None,
    max_lat: float | None = None,
    event_type: list[EventType] | None = Query(None),
    status: list[EventStatus] | None = Query(None),
    warning_level: list[WarningLevel] | None = Query(None),
    state: str | None = None,
    district: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(2000, ge=1, le=5000),
) -> list[MapEvent]:
    filters = []
    box = bbox_filter(Event.geom, min_lon, min_lat, max_lon, max_lat)
    if box is not None:
        filters.append(box)
    if event_type:
        filters.append(Event.event_type.in_(event_type))
    if status:
        filters.append(Event.status.in_(status))
    if warning_level:
        filters.append(Event.warning_level.in_(warning_level))
    if state:
        filters.append(Event.state == state)
    if district:
        filters.append(Event.district == district)
    if date_from:
        filters.append(Event.last_updated >= date_from)
    if date_to:
        filters.append(Event.start_time <= date_to)

    rows = (
        await session.execute(
            select(Event).where(*filters).order_by(Event.last_updated.desc()).limit(limit)
        )
    ).scalars().all()
    return [MapEvent.model_validate(e) for e in rows]


@router.get("/reports", response_model=list[MapReport])
async def map_reports(
    session: AsyncSession = Depends(get_session),
    min_lon: float | None = None,
    min_lat: float | None = None,
    max_lon: float | None = None,
    max_lat: float | None = None,
    event_type: list[EventType] | None = Query(None),
    hours: int = Query(6, ge=1, le=72),
    include_duplicates: bool = False,
    limit: int = Query(3000, ge=1, le=10000),
) -> list[MapReport]:
    filters = [
        Report.latitude.is_not(None),
        Report.observed_at >= datetime.now(timezone.utc) - timedelta(hours=hours),
    ]
    box = bbox_filter(Report.geom, min_lon, min_lat, max_lon, max_lat)
    if box is not None:
        filters.append(box)
    if event_type:
        filters.append(Report.predicted_event_type.in_([e.value for e in event_type]))
    if not include_duplicates:
        filters.append(Report.duplicate_of_report_id.is_(None))

    rows = (
        await session.execute(
            select(
                Report.id,
                Report.latitude,
                Report.longitude,
                Report.predicted_event_type,
                Report.source_type,
                Report.reliability_score,
                Report.observed_at,
            )
            .where(*filters)
            .order_by(Report.observed_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        MapReport(
            id=r.id,
            latitude=r.latitude,
            longitude=r.longitude,
            predicted_event_type=r.predicted_event_type,
            source_type=r.source_type.value,
            reliability_score=r.reliability_score,
            observed_at=r.observed_at,
        )
        for r in rows
    ]
