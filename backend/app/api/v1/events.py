from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Float, cast, column, func, select, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Event,
    EventStatus,
    EventStatusHistory,
    EventType,
    Report,
    Source,
    WarningLevel,
)
from app.db.session import get_session
from app.schemas.common import Page
from app.schemas.events import (
    AdvisoryOut,
    EvidenceBreakdown,
    EventDetail,
    EventOut,
    StatusHistoryOut,
)
from app.schemas.reports import ReportSummary
from app.services.pipeline import advisory as advisory_mod
from app.services.pipeline.credibility import FLAG_LABELS, REVIEW_RISK
from app.services.pipeline.normalize import TRACKED_HASHTAGS

router = APIRouter(prefix="/events", tags=["events"])

OPEN_STATUSES = [
    EventStatus.DETECTED,
    EventStatus.CORROBORATING,
    EventStatus.NEEDS_REVIEW,
    EventStatus.VERIFIED,
]


def build_filters(
    date_from: datetime | None,
    date_to: datetime | None,
    event_type: list[EventType] | None,
    state: str | None,
    district: str | None,
    status: list[EventStatus] | None,
    min_evidence: float | None = None,
    warning_level: list[WarningLevel] | None = None,
) -> list:
    filters = []
    if date_from:
        filters.append(Event.last_updated >= date_from)
    if date_to:
        filters.append(Event.start_time <= date_to)
    if event_type:
        filters.append(Event.event_type.in_(event_type))
    if state:
        filters.append(Event.state == state)
    if district:
        filters.append(Event.district == district)
    if status:
        filters.append(Event.status.in_(status))
    if min_evidence is not None:
        filters.append(Event.evidence_score >= min_evidence)
    if warning_level:
        filters.append(Event.warning_level.in_(warning_level))
    return filters


@router.get("", response_model=Page[EventOut])
async def list_events(
    session: AsyncSession = Depends(get_session),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    event_type: list[EventType] | None = Query(None),
    state: str | None = None,
    district: str | None = None,
    status: list[EventStatus] | None = Query(None),
    warning_level: list[WarningLevel] | None = Query(None),
    min_evidence: float | None = Query(None, ge=0, le=1),
    sort: str = Query("last_updated", pattern="^(last_updated|start_time|evidence_score|report_count|severity|warning_level)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Page[EventOut]:
    filters = build_filters(
        date_from, date_to, event_type, state, district, status, min_evidence, warning_level
    )
    total = (await session.execute(select(func.count(Event.id)).where(*filters))).scalar() or 0

    column = getattr(Event, sort)
    ordering = column.desc() if order == "desc" else column.asc()
    rows = (
        await session.execute(
            select(Event).where(*filters).order_by(ordering).limit(limit).offset(offset)
        )
    ).scalars().all()
    return Page[EventOut](
        items=[EventOut.model_validate(e) for e in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


async def build_evidence(session: AsyncSession, event: Event) -> EvidenceBreakdown:
    """The credibility story behind the status badge, assembled from members."""
    member_filter = [Report.event_id == event.id]

    agg = (
        await session.execute(
            select(
                func.count(Report.id),
                func.count(func.distinct(Report.source_id)),
                func.avg(Report.reliability_score),
                func.avg(cast(Report.weather_corroboration["overall_support"].astext, Float)),
                func.count(Report.id).filter(Report.duplicate_of_report_id.is_not(None)),
                # `media` is JSONB, and normalize writes the JSON literal
                # `null` rather than SQL NULL when a post carries no
                # attachment — so `IS NOT NULL` is true for *every* row and
                # this counted the whole event as photo-backed. Measured on a
                # live event: with_media reported 2 of 2 when the real answer
                # was 0. Overstating physical evidence in a disaster bulletin
                # is the wrong way to be wrong, so the check is on the JSON
                # type and emptiness instead.
                func.count(Report.id).filter(
                    func.jsonb_typeof(Report.media) == "array",
                    Report.media != cast("[]", JSONB),
                ),
                func.count(Report.id).filter(Report.source_type == "CITIZEN"),
                func.count(Report.id).filter(Report.misinformation_risk >= REVIEW_RISK),
                func.avg(Report.misinformation_risk),
            ).where(*member_filter)
        )
    ).one()
    (
        total,
        source_count,
        avg_rel,
        avg_corr,
        dup_count,
        with_media,
        citizen,
        flagged,
        avg_risk,
    ) = agg

    types = (
        await session.execute(
            select(func.distinct(Report.source_type)).where(*member_filter)
        )
    ).scalars().all()

    contributors = (
        await session.execute(
            select(
                func.coalesce(Source.name, "Unregistered"),
                Report.source_type,
                func.count(Report.id),
                func.avg(Report.reliability_score),
            )
            .select_from(Report)
            .join(Source, Source.id == Report.source_id, isouter=True)
            .where(*member_filter)
            .group_by(Source.name, Report.source_type)
            .order_by(func.count(Report.id).desc())
            .limit(6)
        )
    ).all()

    # Which credibility flags this event's reports tripped, and which
    # hashtags carried them - both are evidence a verifier acts on.
    flag_code = (
        func.jsonb_array_elements(Report.credibility_flags["flags"])
        .table_valued(column("value", JSONB))
        .render_derived()
    )
    # One expression object, used in both SELECT and GROUP BY - see analytics.py.
    flag_expr = flag_code.c.value["code"].astext
    flag_rows = (
        await session.execute(
            select(flag_expr, func.count(Report.id))
            .select_from(Report)
            .join(flag_code, true())
            .where(*member_filter, Report.credibility_flags.is_not(None))
            .group_by(flag_expr)
            .order_by(func.count(Report.id).desc())
            .limit(6)
        )
    ).all()

    tag = func.jsonb_array_elements_text(Report.hashtags).table_valued("value").render_derived()
    tag_rows = (
        await session.execute(
            select(tag.c.value, func.count(Report.id))
            .select_from(Report)
            .join(tag, true())
            .where(*member_filter)
            .group_by(tag.c.value)
            .order_by(func.count(Report.id).desc())
            .limit(8)
        )
    ).all()

    return EvidenceBreakdown(
        report_count=int(total or 0),
        source_count=int(source_count or 0),
        distinct_source_types=[t.value if hasattr(t, "value") else str(t) for t in types],
        evidence_score=round(float(avg_rel or 0.0), 4),
        weather_corroboration=round(float(avg_corr if avg_corr is not None else 0.5), 4),
        duplicate_count=int(dup_count or 0),
        independent_citizen_reports=int(citizen or 0),
        with_media=int(with_media or 0),
        flagged_report_count=int(flagged or 0),
        avg_misinformation_risk=round(float(avg_risk or 0.0), 4),
        top_flags=[
            {"code": c, "label": FLAG_LABELS.get(c, c), "report_count": int(n)}
            for c, n in flag_rows
            if c
        ],
        top_hashtags=[
            {"hashtag": t, "report_count": int(n), "tracked": t in TRACKED_HASHTAGS}
            for t, n in tag_rows
        ],
        top_contributing_sources=[
            {
                "name": name,
                "source_type": st.value if hasattr(st, "value") else str(st),
                "report_count": int(count),
                "avg_reliability": round(float(rel or 0.0), 4),
            }
            for name, st, count, rel in contributors
        ],
    )


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(
    event_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> EventDetail:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    history = (
        await session.execute(
            select(EventStatusHistory)
            .where(EventStatusHistory.event_id == event_id)
            .order_by(EventStatusHistory.created_at.asc())
        )
    ).scalars().all()

    samples = (
        await session.execute(
            select(Report)
            .where(Report.event_id == event_id)
            .order_by(Report.reliability_score.desc().nullslast(), Report.observed_at.desc())
            .limit(10)
        )
    ).scalars().all()

    return EventDetail(
        **EventOut.model_validate(event).model_dump(),
        evidence=await build_evidence(session, event),
        status_history=[StatusHistoryOut.model_validate(h) for h in history],
        sample_reports=[ReportSummary.model_validate(r) for r in samples],
    )


@router.get("/{event_id}/reports", response_model=Page[ReportSummary])
async def event_reports(
    event_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    include_duplicates: bool = True,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Page[ReportSummary]:
    if await session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")

    filters = [Report.event_id == event_id]
    if not include_duplicates:
        filters.append(Report.duplicate_of_report_id.is_(None))

    total = (await session.execute(select(func.count(Report.id)).where(*filters))).scalar() or 0
    rows = (
        await session.execute(
            select(Report)
            .where(*filters)
            .order_by(Report.observed_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return Page[ReportSummary](
        items=[ReportSummary.model_validate(r) for r in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/{event_id}/advisory", response_model=AdvisoryOut)
async def event_advisory(
    event_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> AdvisoryOut:
    """Publishable advisory text for this event, in English and Hindi.

    Template-based and deterministic on purpose: a model inventing safety
    instructions in a disaster bulletin would be a hazard, not a feature.
    """
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    built = advisory_mod.build(event)
    return AdvisoryOut(**built.as_dict(), plain_text=built.as_text())
