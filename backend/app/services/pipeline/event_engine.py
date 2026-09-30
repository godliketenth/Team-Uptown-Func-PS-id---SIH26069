"""Stage 7: cluster deduplicated reports into events.

Matching rule: same predicted event type, within 15km (PostGIS ST_DWithin on
geography), seen in the last 90 minutes, on an event that is still open.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Event,
    EventStatus,
    EventStatusHistory,
    EventType,
    Report,
    Severity,
    WarningLevel,
)
from app.services.pipeline.credibility import REVIEW_RISK
from app.services.pipeline.warning import assess as assess_warning

MATCH_RADIUS_METERS = 15_000
MATCH_WINDOW = timedelta(minutes=90)
RESOLVE_AFTER = timedelta(hours=6)

OPEN_STATUSES = (
    EventStatus.DETECTED,
    EventStatus.CORROBORATING,
    EventStatus.NEEDS_REVIEW,
    EventStatus.VERIFIED,
)
# Statuses the engine is allowed to advance automatically. A human verdict
# (VERIFIED / REJECTED) is never overwritten by the pipeline.
AUTO_STATUSES = (EventStatus.DETECTED, EventStatus.CORROBORATING, EventStatus.NEEDS_REVIEW)


def point_wkt(lat: float, lon: float) -> str:
    """EWKT literal, for assigning to a Geography column."""
    return f"SRID=4326;POINT({lon} {lat})"


def point_expr(lat: float, lon: float):
    """Typed geography expression, for use inside a query.

    A bare EWKT string binds as VARCHAR and ST_DWithin(geography, varchar)
    does not exist, so every spatial predicate goes through this.
    """
    return func.ST_GeogFromText(point_wkt(lat, lon))


def report_point(report: Report):
    if report.latitude is None or report.longitude is None:
        return None
    return point_expr(report.latitude, report.longitude)


def severity_for(report_count: int) -> Severity:
    if report_count < 5:
        return Severity.LOW
    if report_count < 15:
        return Severity.MODERATE
    if report_count < 30:
        return Severity.HIGH
    return Severity.SEVERE


def status_for(source_count: int) -> EventStatus:
    """DETECTED -> CORROBORATING -> NEEDS_REVIEW as independent sources pile up."""
    if source_count >= 3:
        return EventStatus.NEEDS_REVIEW
    if source_count == 2:
        return EventStatus.CORROBORATING
    return EventStatus.DETECTED


async def record_status_change(
    session: AsyncSession,
    event: Event,
    new_status: EventStatus,
    changed_by: str = "system",
    reason: str | None = None,
) -> None:
    if event.status == new_status:
        return
    session.add(
        EventStatusHistory(
            event_id=event.id,
            old_status=event.status.value if event.status else None,
            new_status=new_status.value,
            changed_by=changed_by,
            reason=reason,
        )
    )
    event.status = new_status


async def find_matching_event(session: AsyncSession, report: Report) -> Event | None:
    point = report_point(report)
    if point is None or not report.predicted_event_type:
        return None
    stmt = (
        select(Event)
        .where(
            Event.event_type == EventType(report.predicted_event_type),
            Event.status.in_(OPEN_STATUSES),
            Event.last_updated >= report.observed_at - MATCH_WINDOW,
            func.ST_DWithin(Event.geom, point, MATCH_RADIUS_METERS),
        )
        .order_by(func.ST_Distance(Event.geom, point))
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def recompute_event(session: AsyncSession, event: Event) -> None:
    """Recompute the evidence aggregate from the event's member reports."""
    stmt = select(
        func.count(Report.id),
        func.count(func.distinct(Report.source_id)),
        func.avg(Report.reliability_score),
        func.avg(cast(Report.weather_corroboration["overall_support"].astext, Float)),
        func.max(Report.observed_at),
        func.min(Report.observed_at),
        func.count(Report.id).filter(Report.misinformation_risk >= REVIEW_RISK),
    ).where(Report.event_id == event.id, Report.duplicate_of_report_id.is_(None))
    row = (await session.execute(stmt)).one()
    (
        report_count,
        source_count,
        avg_reliability,
        avg_support,
        last_seen,
        first_seen,
        flagged,
    ) = row

    event.report_count = int(report_count or 0)
    event.source_count = int(source_count or 0)
    event.evidence_score = round(float(avg_reliability or 0.0), 4)
    event.corroboration_score = round(
        float(avg_support) if avg_support is not None else 0.5, 4
    )
    event.flagged_report_count = int(flagged or 0)
    event.severity = severity_for(event.report_count)

    # IMD-style operator signal, derived from the evidence just recomputed.
    warning = assess_warning(
        status=event.status.value,
        report_count=event.report_count,
        source_count=event.source_count,
        evidence_score=event.evidence_score,
        corroboration_score=event.corroboration_score,
        flagged_report_count=event.flagged_report_count,
    )
    event.warning_level = WarningLevel(warning.level.value)
    event.warning_reasons = warning.as_dict()

    # Raise, escalate or stand down an alert for this event. Idempotent.
    from app.services.pipeline.alerting import evaluate as evaluate_alert

    await evaluate_alert(session, event)
    if first_seen:
        event.start_time = min(event.start_time, first_seen)
    event.last_updated = last_seen or event.last_updated

    if event.status in AUTO_STATUSES:
        target = status_for(event.source_count)
        # Only ever escalate automatically.
        if AUTO_STATUSES.index(target) > AUTO_STATUSES.index(event.status):
            await record_status_change(
                session,
                event,
                target,
                reason=f"source_count reached {event.source_count}",
            )


async def assign_to_event(session: AsyncSession, report: Report) -> Event | None:
    """Attach a classified+deduplicated report to an event, creating one if needed."""
    if report.duplicate_of_report_id is not None:
        return None
    if report.latitude is None or report.longitude is None or not report.predicted_event_type:
        return None

    event = await find_matching_event(session, report)
    created = False
    if event is None:
        event = Event(
            event_type=EventType(report.predicted_event_type),
            status=EventStatus.DETECTED,
            center_latitude=report.latitude,
            center_longitude=report.longitude,
            geom=point_wkt(report.latitude, report.longitude),
            state=report.state,
            district=report.district,
            start_time=report.observed_at,
            last_updated=report.observed_at,
            report_count=0,
            source_count=0,
            evidence_score=0.0,
            severity=Severity.LOW,
        )
        session.add(event)
        await session.flush()
        created = True
        session.add(
            EventStatusHistory(
                event_id=event.id,
                old_status=None,
                new_status=EventStatus.DETECTED.value,
                changed_by="system",
                reason="first report observed",
            )
        )

    report.event_id = event.id
    await session.flush()

    if not created:
        # Drift the centroid toward the newly contributing report.
        n = max(event.report_count, 1)
        event.center_latitude = round((event.center_latitude * n + report.latitude) / (n + 1), 6)
        event.center_longitude = round((event.center_longitude * n + report.longitude) / (n + 1), 6)
        event.geom = point_wkt(event.center_latitude, event.center_longitude)
        if not event.state and report.state:
            event.state = report.state
            event.district = report.district

    await recompute_event(session, event)
    return event


async def resolve_stale_events(session: AsyncSession) -> int:
    """Close out events nobody has reported on for a while."""
    cutoff = datetime.now(timezone.utc) - RESOLVE_AFTER
    stmt = select(Event).where(
        Event.status.in_(OPEN_STATUSES), Event.last_updated < cutoff
    )
    stale = (await session.execute(stmt)).scalars().all()
    for event in stale:
        await record_status_change(
            session, event, EventStatus.RESOLVED, reason="no new reports for 6h"
        )
    return len(stale)
