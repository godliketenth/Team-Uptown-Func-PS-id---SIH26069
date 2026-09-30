from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_analyst, require_verifier
from app.db.models import AuditLog, Event, EventStatus, User
from app.db.session import get_session
from app.schemas.common import Page
from app.schemas.events import EventOut, VerificationAction
from app.services.pipeline.event_engine import record_status_change, recompute_event

router = APIRouter(prefix="/verification", tags=["verification"])


@router.get("/queue", response_model=Page[EventOut])
async def verification_queue(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    # Reading the queue is an operations action, not a public one: it reveals
    # which events the platform currently distrusts, ahead of any human
    # judgement. `require_analyst` matches the other read endpoints on the
    # admin console; acting on the queue still requires a verifier.
    _user: User = Depends(require_analyst),
) -> Page[EventOut]:
    """Weakest evidence first - that is where a human adds the most value."""
    filters = [Event.status == EventStatus.NEEDS_REVIEW]
    total = (await session.execute(select(func.count(Event.id)).where(*filters))).scalar() or 0
    rows = (
        await session.execute(
            select(Event)
            .where(*filters)
            .order_by(Event.evidence_score.asc(), Event.last_updated.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return Page[EventOut](
        items=[EventOut.model_validate(e) for e in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


async def _decide(
    session: AsyncSession,
    event_id: uuid.UUID,
    new_status: EventStatus,
    action: VerificationAction,
    user: User,
) -> Event:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.status in (EventStatus.REJECTED, EventStatus.RESOLVED):
        raise HTTPException(
            status_code=409, detail=f"Event is already {event.status.value} and cannot be re-decided"
        )

    previous = event.status
    await record_status_change(
        session,
        event,
        new_status,
        changed_by=user.email,
        reason=action.reason or f"manual {new_status.value.lower()}",
    )
    session.add(
        AuditLog(
            actor_id=user.id,
            actor_email=user.email,
            action=f"event.{new_status.value.lower()}",
            target_type="event",
            target_id=str(event.id),
            details={
                "from": previous.value,
                "to": new_status.value,
                "reason": action.reason,
                "evidence_score": event.evidence_score,
                "report_count": event.report_count,
                "source_count": event.source_count,
            },
        )
    )
    # The verdict changes the warning level (a rejection drops it to GREEN,
    # a verification lifts it to at least ORANGE), so re-derive it here.
    await recompute_event(session, event)
    await session.commit()
    await session.refresh(event)
    return event


@router.post("/{event_id}/verify", response_model=EventOut)
async def verify_event(
    event_id: uuid.UUID,
    action: VerificationAction,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_verifier),
) -> EventOut:
    event = await _decide(session, event_id, EventStatus.VERIFIED, action, user)
    return EventOut.model_validate(event)


@router.post("/{event_id}/reject", response_model=EventOut)
async def reject_event(
    event_id: uuid.UUID,
    action: VerificationAction,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_verifier),
) -> EventOut:
    event = await _decide(session, event_id, EventStatus.REJECTED, action, user)
    return EventOut.model_validate(event)


@router.post("/{event_id}/resolve", response_model=EventOut)
async def resolve_event(
    event_id: uuid.UUID,
    action: VerificationAction,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_verifier),
) -> EventOut:
    event = await _decide(session, event_id, EventStatus.RESOLVED, action, user)
    return EventOut.model_validate(event)
