"""Alert queue — the operator-facing output of the rules engine."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_analyst, require_verifier
from app.db.models import (
    Alert,
    AlertDelivery,
    AlertStatus,
    AuditLog,
    Authority,
    Event,
    User,
    WarningLevel,
)
from app.db.session import get_session
from app.schemas.alerts import AlertAction, AlertOut, AlertSummary, DeliveryOut
from app.schemas.events import AdvisoryOut
from app.services.pipeline import advisory as advisory_mod
from app.schemas.common import Page
from app.services.pipeline.warning import ORDER

router = APIRouter(prefix="/alerts", tags=["alerts"])

LIVE = (AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED)


@router.get("", response_model=Page[AlertOut])
async def list_alerts(
    session: AsyncSession = Depends(get_session),
    status: list[AlertStatus] | None = Query(None),
    level: list[WarningLevel] | None = Query(None),
    state: str | None = None,
    district: str | None = None,
    live_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Page[AlertOut]:
    filters = []
    if status:
        filters.append(Alert.status.in_(status))
    if live_only:
        filters.append(Alert.status.in_(LIVE))
    if level:
        filters.append(Alert.level.in_(level))
    if state:
        filters.append(Alert.state == state)
    if district:
        filters.append(Alert.district == district)

    total = (await session.execute(select(func.count(Alert.id)).where(*filters))).scalar() or 0
    rows = (
        await session.execute(
            select(Alert)
            .where(*filters)
            # Most severe first, then oldest — the queue an operator works down.
            .order_by(Alert.level.desc(), Alert.raised_at.asc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return Page[AlertOut](
        items=[AlertOut.model_validate(a) for a in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/summary", response_model=AlertSummary)
async def alert_summary(session: AsyncSession = Depends(get_session)) -> AlertSummary:
    now = datetime.now(timezone.utc)
    counts = (
        await session.execute(
            select(
                func.count(Alert.id).filter(Alert.status == AlertStatus.ACTIVE),
                func.count(Alert.id).filter(Alert.status == AlertStatus.ACKNOWLEDGED),
                func.count(Alert.id).filter(
                    Alert.status == AlertStatus.CLOSED,
                    Alert.closed_at >= now - timedelta(hours=24),
                ),
                func.min(Alert.raised_at).filter(Alert.status == AlertStatus.ACTIVE),
            )
        )
    ).one()
    active, acknowledged, closed_24h, oldest = counts

    by_level = {
        lvl.value: int(n)
        for lvl, n in (
            await session.execute(
                select(Alert.level, func.count(Alert.id))
                .where(Alert.status.in_(LIVE))
                .group_by(Alert.level)
            )
        ).all()
    }
    by_state = [
        {"state": st, "count": int(n)}
        for st, n in (
            await session.execute(
                select(Alert.state, func.count(Alert.id))
                .where(Alert.status.in_(LIVE), Alert.state.is_not(None))
                .group_by(Alert.state)
                .order_by(func.count(Alert.id).desc())
                .limit(10)
            )
        ).all()
    ]

    return AlertSummary(
        active=int(active or 0),
        acknowledged=int(acknowledged or 0),
        closed_last_24h=int(closed_24h or 0),
        by_level={lvl.value: by_level.get(lvl.value, 0) for lvl in ORDER},
        by_state=by_state,
        oldest_unacknowledged_minutes=(
            round((now - oldest).total_seconds() / 60, 1) if oldest else None
        ),
    )


@router.get("/{alert_id}", response_model=AlertOut)
async def get_alert(
    alert_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> AlertOut:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertOut.model_validate(alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge(
    alert_id: uuid.UUID,
    payload: AlertAction,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_analyst),
) -> AlertOut:
    """Acknowledge means *seen*, not *resolved* — the alert stays live."""
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status == AlertStatus.CLOSED:
        raise HTTPException(status_code=409, detail="Alert is already closed")
    if alert.status == AlertStatus.ACKNOWLEDGED:
        return AlertOut.model_validate(alert)

    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledged_by = user.email
    session.add(
        AuditLog(
            actor_id=user.id,
            actor_email=user.email,
            action="alert.acknowledge",
            target_type="alert",
            target_id=str(alert.id),
            details={"level": alert.level.value, "note": payload.note},
        )
    )
    await session.commit()
    await session.refresh(alert)
    return AlertOut.model_validate(alert)


@router.post("/{alert_id}/close", response_model=AlertOut)
async def close(
    alert_id: uuid.UUID,
    payload: AlertAction,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_verifier),
) -> AlertOut:
    """Manually stand an alert down. The engine reopens one if the event
    climbs back above the threshold, which is the intended behaviour."""
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status == AlertStatus.CLOSED:
        raise HTTPException(status_code=409, detail="Alert is already closed")

    alert.status = AlertStatus.CLOSED
    alert.closed_at = datetime.now(timezone.utc)
    alert.closed_reason = payload.note or f"closed manually by {user.email}"
    session.add(
        AuditLog(
            actor_id=user.id,
            actor_email=user.email,
            action="alert.close",
            target_type="alert",
            target_id=str(alert.id),
            details={"level": alert.level.value, "reason": alert.closed_reason},
        )
    )
    await session.commit()
    await session.refresh(alert)
    return AlertOut.model_validate(alert)


# ---------------------------------------------------------------------------
# Authority registry and delivery (Phase 2.3)
# ---------------------------------------------------------------------------
@router.get("/{alert_id}/deliveries", response_model=list[DeliveryOut])
async def alert_deliveries(
    alert_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_analyst),
) -> list[DeliveryOut]:
    """Who was told about this alert, on which channel, and whether it landed."""
    if await session.get(Alert, alert_id) is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    rows = (
        await session.execute(
            select(AlertDelivery, Authority.name)
            .join(Authority, Authority.id == AlertDelivery.authority_id)
            .where(AlertDelivery.alert_id == alert_id)
            .order_by(AlertDelivery.queued_at)
        )
    ).all()
    out = []
    for delivery, name in rows:
        item = DeliveryOut.model_validate(delivery)
        item.authority_name = name
        out.append(item)
    return out


@router.get("/{alert_id}/advisory", response_model=AdvisoryOut)
async def alert_advisory(
    alert_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> AdvisoryOut:
    """The advisory an operator would issue for this alert."""
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    event = await session.get(Event, alert.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Underlying event not found")
    built = advisory_mod.build(event)
    return AdvisoryOut(**built.as_dict(), plain_text=built.as_text())
