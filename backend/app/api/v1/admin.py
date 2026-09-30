from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import require_admin, require_analyst
from app.db.models import (
    AlertDelivery,
    AuditLog,
    Authority,
    DeliveryStatus,
    Event,
    ProcessingState,
    RawEvent,
    Report,
    Source,
    SourceStatus,
    User,
)
from app.db.session import get_session
from app.schemas.alerts import AuthorityOut, AuthorityUpdate, DeliveryStats
from app.schemas.admin import (
    AuditLogOut,
    PipelineStage,
    SourceHealth,
    SourceOut,
    SourceUpdate,
    SystemHealth,
)
from app.schemas.common import Page
from app.services import bus
from app.services.ingestion.lake import lake_stats
from app.services.pipeline.corroborate import CACHE_STATS


def _cache_summary() -> dict:
    total = CACHE_STATS["hits"] + CACHE_STATS["misses"]
    return {
        "hits": CACHE_STATS["hits"],
        "misses": CACHE_STATS["misses"],
        "hit_rate": round(CACHE_STATS["hits"] / total, 4) if total else 0.0,
    }
from app.services.scheduler import scheduler

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/sources", response_model=list[SourceHealth])
async def list_sources(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_analyst),
) -> list[SourceHealth]:
    hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

    raw_counts = dict(
        (sid, (int(total), int(recent)))
        for sid, total, recent in (
            await session.execute(
                select(
                    RawEvent.source_id,
                    func.count(RawEvent.id),
                    func.count(RawEvent.id).filter(RawEvent.collected_at >= hour_ago),
                ).group_by(RawEvent.source_id)
            )
        ).all()
    )
    report_counts = dict(
        (sid, int(total))
        for sid, total in (
            await session.execute(
                select(Report.source_id, func.count(Report.id)).group_by(Report.source_id)
            )
        ).all()
    )

    sources = (
        await session.execute(select(Source).order_by(Source.source_type, Source.name))
    ).scalars().all()
    return [
        SourceHealth(
            **SourceOut.model_validate(s).model_dump(),
            raw_events_total=raw_counts.get(s.id, (0, 0))[0],
            raw_events_last_hour=raw_counts.get(s.id, (0, 0))[1],
            reports_total=report_counts.get(s.id, 0),
        )
        for s in sources
    ]


@router.patch("/sources/{source_id}", response_model=SourceOut)
async def update_source(
    source_id: uuid.UUID,
    payload: SourceUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_admin),
) -> SourceOut:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    changes: dict = {}
    if payload.status is not None and payload.status != source.status:
        changes["status"] = [source.status.value, payload.status.value]
        source.status = payload.status
    if payload.poll_interval_seconds is not None:
        changes["poll_interval_seconds"] = [
            source.poll_interval_seconds,
            payload.poll_interval_seconds,
        ]
        source.poll_interval_seconds = payload.poll_interval_seconds
    if payload.name is not None:
        changes["name"] = [source.name, payload.name]
        source.name = payload.name

    if changes:
        session.add(
            AuditLog(
                actor_id=user.id,
                actor_email=user.email,
                action="source.update",
                target_type="source",
                target_id=str(source.id),
                details=changes,
            )
        )
    await session.commit()
    await session.refresh(source)
    return SourceOut.model_validate(source)


@router.get("/system-health", response_model=SystemHealth)
async def system_health(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_analyst),
) -> SystemHealth:
    stage_rows = (
        await session.execute(
            select(Report.processing_state, func.count()).group_by(Report.processing_state)
        )
    ).all()
    by_stage = {s.value: int(c) for s, c in stage_rows}

    raw_total = (await session.execute(select(func.count(RawEvent.id)))).scalar() or 0
    reports_total = (await session.execute(select(func.count(Report.id)))).scalar() or 0
    events_total = (await session.execute(select(func.count(Event.id)))).scalar() or 0

    # Refresh broker lag on read, not only on the scheduler tick — otherwise
    # the number is stale by up to one tick interval, which is exactly when an
    # operator is looking at it (during a surge).
    await bus.refresh_lag()
    bus_stats = bus.stats.as_dict()
    attempted = bus_stats["processed"] + bus_stats["failed"]
    last_tick = bus.stats.last_tick_at
    since_tick = (
        round((datetime.now(timezone.utc) - last_tick).total_seconds(), 2) if last_tick else None
    )

    degraded = (
        not scheduler.running
        or (since_tick is not None and since_tick > settings.scheduler_interval_seconds * 4)
        or (attempted and bus_stats["failed"] / attempted > 0.10)
    )

    return SystemHealth(
        status="degraded" if degraded else "healthy",
        scheduler_running=scheduler.running,
        last_tick_at=last_tick,
        seconds_since_tick=since_tick,
        bus=bus_stats,
        pipeline_stages=[
            PipelineStage(stage=stage.value, count=by_stage.get(stage.value, 0))
            for stage in ProcessingState
        ],
        raw_events_total=int(raw_total),
        reports_total=int(reports_total),
        events_total=int(events_total),
        error_rate=round(bus_stats["failed"] / attempted, 4) if attempted else 0.0,
        raw_lake=lake_stats() | {"corroboration_cache": _cache_summary()},
        open_meteo_enabled=settings.open_meteo_enabled,
    )


@router.get("/audit-logs", response_model=Page[AuditLogOut])
async def audit_logs(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_analyst),
    action: str | None = None,
    target_type: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Page[AuditLogOut]:
    filters = []
    if action:
        filters.append(AuditLog.action == action)
    if target_type:
        filters.append(AuditLog.target_type == target_type)

    total = (await session.execute(select(func.count(AuditLog.id)).where(*filters))).scalar() or 0
    rows = (
        await session.execute(
            select(AuditLog)
            .where(*filters)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return Page[AuditLogOut](
        items=[AuditLogOut.model_validate(r) for r in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# Authority registry (Phase 2.3)
# ---------------------------------------------------------------------------
@router.get("/authorities", response_model=list[AuthorityOut])
async def list_authorities(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_analyst),
) -> list[AuthorityOut]:
    rows = (
        await session.execute(
            select(Authority).order_by(Authority.level, Authority.state, Authority.name)
        )
    ).scalars().all()
    return [AuthorityOut.model_validate(a) for a in rows]


@router.patch("/authorities/{authority_id}", response_model=AuthorityOut)
async def update_authority(
    authority_id: uuid.UUID,
    payload: AuthorityUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_admin),
) -> AuthorityOut:
    authority = await session.get(Authority, authority_id)
    if authority is None:
        raise HTTPException(status_code=404, detail="Authority not found")

    changes: dict = {}
    for field in ("status", "min_level", "webhook_url", "contact_email", "event_types"):
        value = getattr(payload, field)
        if value is None:
            continue
        current = getattr(authority, field)
        current_repr = current.value if hasattr(current, "value") else current
        new_repr = value.value if hasattr(value, "value") else value
        if current_repr != new_repr:
            changes[field] = [current_repr, new_repr]
            setattr(authority, field, value)

    if changes:
        session.add(
            AuditLog(
                actor_id=user.id,
                actor_email=user.email,
                action="authority.update",
                target_type="authority",
                target_id=str(authority.id),
                details=changes,
            )
        )
    await session.commit()
    await session.refresh(authority)
    return AuthorityOut.model_validate(authority)


@router.get("/delivery-stats", response_model=DeliveryStats)
async def delivery_stats(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_analyst),
) -> DeliveryStats:
    counts = (
        await session.execute(
            select(
                func.count(AlertDelivery.id).filter(AlertDelivery.status == DeliveryStatus.PENDING),
                func.count(AlertDelivery.id).filter(AlertDelivery.status == DeliveryStatus.SENT),
                func.count(AlertDelivery.id).filter(AlertDelivery.status == DeliveryStatus.SIMULATED),
                func.count(AlertDelivery.id).filter(AlertDelivery.status == DeliveryStatus.FAILED),
            )
        )
    ).one()
    active = (
        await session.execute(
            select(func.count(Authority.id)).where(Authority.status == SourceStatus.ACTIVE)
        )
    ).scalar() or 0
    by_channel = {
        ch.value: int(n)
        for ch, n in (
            await session.execute(
                select(AlertDelivery.channel, func.count(AlertDelivery.id)).group_by(
                    AlertDelivery.channel
                )
            )
        ).all()
    }
    return DeliveryStats(
        pending=int(counts[0] or 0),
        sent=int(counts[1] or 0),
        simulated=int(counts[2] or 0),
        failed=int(counts[3] or 0),
        authorities_active=int(active),
        by_channel=by_channel,
    )
