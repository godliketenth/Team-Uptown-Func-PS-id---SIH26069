from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Report, Source, SourceStatus, SourceType, User
from app.db.session import get_session
from app.core.security import get_current_user_optional
from app.schemas.common import Page
from app.schemas.reports import ReportAccepted, ReportCreate, ReportOut, ReportSummary
from app.services import bus
from app.services.pipeline.credibility import REVIEW_RISK as CREDIBILITY_REVIEW_RISK
from app.services.pipeline.runner import store_raw_event

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", response_model=ReportAccepted, status_code=status.HTTP_202_ACCEPTED)
async def submit_report(
    payload: ReportCreate,
    response: Response,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user_optional),
) -> ReportAccepted:
    """Citizen submission.

    Writes to the immutable log and returns immediately; normalization,
    classification, corroboration, dedup and clustering happen on the bus.
    """
    source = (
        await session.execute(
            select(Source)
            .where(Source.source_type == SourceType.CITIZEN, Source.status == SourceStatus.ACTIVE)
            .limit(1)
        )
    ).scalars().first()

    body = {
        "text": payload.text,
        "city_hint": payload.city,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "observed_at": (payload.observed_at or datetime.now(timezone.utc)).isoformat(),
        "media": [m.model_dump() for m in payload.media] if payload.media else None,
        "reporter_handle": payload.reporter_handle,
        "author": payload.reporter_handle,
        "submitted_by": str(user.id) if user else None,
        "channel": "public_api",
    }
    raw = await store_raw_event(
        session=session,
        source_id=source.id if source else None,
        source_type=SourceType.CITIZEN,
        external_id=f"api-{uuid.uuid4().hex[:12]}",
        payload=body,
    )
    await session.commit()
    await bus.publish(raw.id)

    response.headers["Location"] = f"/api/v1/reports?raw_event_id={raw.id}"
    return ReportAccepted(raw_event_id=raw.id)


@router.get("", response_model=Page[ReportSummary])
async def list_reports(
    session: AsyncSession = Depends(get_session),
    event_id: uuid.UUID | None = None,
    raw_event_id: uuid.UUID | None = None,
    source_type: SourceType | None = None,
    predicted_event_type: str | None = None,
    state: str | None = None,
    district: str | None = None,
    hashtag: str | None = Query(None, description="Match a single hashtag, without the #"),
    author: str | None = None,
    flagged_only: bool = False,
    include_duplicates: bool = False,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Page[ReportSummary]:
    filters = []
    if event_id:
        filters.append(Report.event_id == event_id)
    if raw_event_id:
        filters.append(Report.raw_event_id == raw_event_id)
    if source_type:
        filters.append(Report.source_type == source_type)
    if predicted_event_type:
        filters.append(Report.predicted_event_type == predicted_event_type)
    if state:
        filters.append(Report.state == state)
    if district:
        filters.append(Report.district == district)
    if hashtag:
        filters.append(Report.hashtags.contains([hashtag.lstrip("#").lower()]))
    if author:
        filters.append(Report.author == author)
    if flagged_only:
        filters.append(Report.misinformation_risk >= CREDIBILITY_REVIEW_RISK)
    if not include_duplicates:
        filters.append(Report.duplicate_of_report_id.is_(None))
    if date_from:
        filters.append(Report.observed_at >= date_from)
    if date_to:
        filters.append(Report.observed_at <= date_to)

    total = (
        await session.execute(select(func.count(Report.id)).where(*filters))
    ).scalar() or 0
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


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> ReportOut:
    report = await session.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return ReportOut.model_validate(report)
