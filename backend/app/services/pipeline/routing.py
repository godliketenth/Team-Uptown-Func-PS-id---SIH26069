"""Phase 2.3 — routing alerts to the authorities who must act on them.

Matching is hierarchical and deliberately conservative: it is far worse to
leave a district uninformed than to tell one authority twice, so a DISTRICT,
its STATE and the NATIONAL desk can all be matched by the same alert.

On what is real: **webhook delivery genuinely posts over HTTP**. Email and SMS
have no transport configured in this build, so they are recorded as SIMULATED
with the exact payload that would have been sent — never as SENT, and never as
FAILED, because "we cannot send" is not the same as "we tried and it broke".
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Alert,
    AlertDelivery,
    Authority,
    AuthorityLevel,
    DeliveryChannel,
    DeliveryStatus,
    SourceStatus,
)
from app.services.pipeline.warning import ORDER

log = logging.getLogger(__name__)

WEBHOOK_TIMEOUT = 6.0
MAX_ATTEMPTS = 3
BATCH = 25


def _rank(level) -> int:
    from app.db.models import WarningLevel

    return ORDER.index(WarningLevel(level.value if hasattr(level, "value") else level))


def matches(authority: Authority, alert: Alert) -> bool:
    """Does this authority need to know about this alert?"""
    if authority.status != SourceStatus.ACTIVE:
        return False
    if _rank(alert.level) < _rank(authority.min_level):
        return False
    if authority.event_types and alert.event_type.value not in authority.event_types:
        return False

    if authority.level == AuthorityLevel.NATIONAL:
        return True
    if authority.level == AuthorityLevel.STATE:
        return bool(authority.state) and authority.state == alert.state
    # DISTRICT — both must line up, since district names repeat across states.
    return (
        bool(authority.district)
        and authority.district == alert.district
        and (not authority.state or authority.state == alert.state)
    )


def build_payload(alert: Alert, authority: Authority) -> dict:
    return {
        "alert_id": str(alert.id),
        "event_id": str(alert.event_id),
        "level": alert.level.value,
        "action": alert.action,
        "headline": alert.headline,
        "event_type": alert.event_type.value,
        "state": alert.state,
        "district": alert.district,
        "location": {"lat": alert.center_latitude, "lon": alert.center_longitude},
        "raised_at": alert.raised_at.isoformat() if alert.raised_at else None,
        "evidence": alert.evidence_snapshot,
        "addressed_to": {"authority": authority.name, "level": authority.level.value},
        "source": "NWAP — National Weather Analytics Platform",
    }


def channels_for(authority: Authority) -> list[tuple[DeliveryChannel, str]]:
    out: list[tuple[DeliveryChannel, str]] = []
    if authority.webhook_url:
        out.append((DeliveryChannel.WEBHOOK, authority.webhook_url))
    if authority.contact_email:
        out.append((DeliveryChannel.EMAIL, authority.contact_email))
    if authority.phone:
        out.append((DeliveryChannel.SMS, authority.phone))
    return out


async def route(session: AsyncSession, alert: Alert) -> int:
    """Queue a delivery per (matching authority × channel). Idempotent:
    re-routing the same alert will not duplicate an existing delivery."""
    authorities = (await session.execute(select(Authority))).scalars().all()
    existing = {
        (d.authority_id, d.channel)
        for d in (
            await session.execute(
                select(AlertDelivery).where(AlertDelivery.alert_id == alert.id)
            )
        ).scalars().all()
    }

    queued = 0
    for authority in authorities:
        if not matches(authority, alert):
            continue
        for channel, target in channels_for(authority):
            if (authority.id, channel) in existing:
                continue
            session.add(
                AlertDelivery(
                    alert_id=alert.id,
                    authority_id=authority.id,
                    channel=channel,
                    status=DeliveryStatus.PENDING,
                    target=target,
                    payload=build_payload(alert, authority),
                )
            )
            queued += 1

    if queued:
        log.info("queued %s deliveries for alert %s (%s)", queued, alert.id, alert.level.value)
    return queued


async def dispatch_pending(session: AsyncSession, limit: int = BATCH) -> dict:
    """Attempt queued deliveries. Called on a scheduler tick."""
    pending = (
        await session.execute(
            select(AlertDelivery)
            .where(
                AlertDelivery.status == DeliveryStatus.PENDING,
                AlertDelivery.attempts < MAX_ATTEMPTS,
            )
            .order_by(AlertDelivery.queued_at)
            .limit(limit)
        )
    ).scalars().all()

    sent = simulated = failed = 0
    if not pending:
        return {"sent": 0, "simulated": 0, "failed": 0}

    async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
        for delivery in pending:
            delivery.attempts += 1
            now = datetime.now(timezone.utc)

            if delivery.channel is DeliveryChannel.WEBHOOK:
                try:
                    resp = await client.post(delivery.target, json=delivery.payload)
                    delivery.response_code = resp.status_code
                    if 200 <= resp.status_code < 300:
                        delivery.status = DeliveryStatus.SENT
                        delivery.sent_at = now
                        delivery.last_error = None
                        sent += 1
                    else:
                        delivery.last_error = f"HTTP {resp.status_code}"
                        if delivery.attempts >= MAX_ATTEMPTS:
                            delivery.status = DeliveryStatus.FAILED
                            failed += 1
                except Exception as exc:
                    delivery.last_error = f"{type(exc).__name__}: {exc}"[:400]
                    if delivery.attempts >= MAX_ATTEMPTS:
                        delivery.status = DeliveryStatus.FAILED
                        failed += 1
            else:
                # No SMTP or SMS gateway is configured in this build. Record
                # exactly what would have gone out rather than claiming it did.
                delivery.status = DeliveryStatus.SIMULATED
                delivery.sent_at = now
                delivery.last_error = "no transport configured — payload recorded, not sent"
                simulated += 1

    await session.commit()
    if sent or failed:
        log.info("deliveries: sent=%s failed=%s simulated=%s", sent, failed, simulated)
    return {"sent": sent, "simulated": simulated, "failed": failed}
