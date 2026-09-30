"""Phase 2.2 — the alert rules engine.

This is where the platform stops describing weather and starts asking someone
to do something. An alert is raised when an event crosses a response
threshold, escalated if the situation worsens, and closed when it no longer
warrants action.

Design decisions worth knowing:

* **One live alert per event.** A rising warning level escalates the existing
  alert rather than raising a second one, so a worsening situation does not
  bury an operator in duplicates.
* **Alerts never silently vanish.** When an event de-escalates or is rejected,
  the alert is *closed with a reason*, not deleted — an operator who was told
  to prepare deserves to be told it stood down.
* **The evidence is frozen at raise time.** Events keep changing; the alert
  records what was true when the call was made, so it stays auditable.
* **Acknowledgement is not resolution.** ACKNOWLEDGED means a human has seen
  it; CLOSED means it no longer applies. Conflating them would hide open work.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import notify
from app.db.models import Alert, AlertStatus, Event, WarningLevel
from app.services.pipeline.warning import ACTION, ORDER

log = logging.getLogger(__name__)

# Events at or above this level warrant a response. YELLOW is a watch — worth
# showing on the dashboard, not worth paging a district officer about.
ALERT_THRESHOLD = WarningLevel.ORANGE

EVENT_PHRASING: dict[str, str] = {
    "RAIN": "Heavy rainfall",
    "FLOOD": "Flooding",
    "THUNDERSTORM": "Thunderstorm activity",
    "HEATWAVE": "Heatwave conditions",
    "FOG": "Dense fog",
    "DUST_STORM": "Dust storm",
    "STRONG_WIND": "Strong winds",
}


def _rank(level: WarningLevel) -> int:
    return ORDER.index(level)


def meets_threshold(level: WarningLevel) -> bool:
    return _rank(level) >= _rank(ALERT_THRESHOLD)


def build_headline(event: Event) -> str:
    phrase = EVENT_PHRASING.get(event.event_type.value, event.event_type.value.title())
    where = event.district or event.state or "an unresolved location"
    if event.state and event.district and event.district != event.state:
        where = f"{event.district}, {event.state}"
    return f"{phrase} reported across {where}"


def build_snapshot(event: Event) -> dict:
    """Freeze the evidence that justified this alert."""
    return {
        "report_count": event.report_count,
        "source_count": event.source_count,
        "evidence_score": round(float(event.evidence_score or 0), 4),
        "corroboration_score": round(float(event.corroboration_score or 0), 4),
        "flagged_report_count": event.flagged_report_count,
        "severity": event.severity.value if event.severity else None,
        "status": event.status.value if event.status else None,
        "warning_reasons": event.warning_reasons,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
    }


async def get_live_alert(session: AsyncSession, event_id) -> Alert | None:
    """The alert still in play for this event, if any."""
    return (
        await session.execute(
            select(Alert)
            .where(
                Alert.event_id == event_id,
                Alert.status.in_((AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED)),
            )
            .order_by(Alert.raised_at.desc())
            .limit(1)
        )
    ).scalars().first()


async def evaluate(session: AsyncSession, event: Event) -> Alert | None:
    """Raise, escalate, or close an alert for this event.

    Called after the event's warning level is recomputed. Idempotent: running
    it repeatedly on an unchanged event does nothing.
    """
    level = event.warning_level
    live = await get_live_alert(session, event.id)
    now = datetime.now(timezone.utc)

    # --- no longer warrants action -----------------------------------------
    if not meets_threshold(level):
        if live is not None:
            live.status = AlertStatus.CLOSED
            live.closed_at = now
            live.closed_reason = (
                f"event de-escalated to {level.value}"
                if event.status.value not in ("REJECTED", "RESOLVED")
                else f"event {event.status.value.lower()} by review"
            )
            log.info("alert closed for event %s (%s)", event.id, live.closed_reason)
            notify.publish("alert", action="closed", event_id=str(event.id))
        return None

    # --- first time crossing the threshold ----------------------------------
    if live is None:
        alert = Alert(
            event_id=event.id,
            level=level,
            status=AlertStatus.ACTIVE,
            event_type=event.event_type,
            state=event.state,
            district=event.district,
            center_latitude=event.center_latitude,
            center_longitude=event.center_longitude,
            headline=build_headline(event),
            action=ACTION[level],
            evidence_snapshot=build_snapshot(event),
            raised_at=now,
        )
        session.add(alert)
        await session.flush()          # need the id before queueing deliveries
        from app.services.pipeline.routing import route

        await route(session, alert)
        log.info("alert raised: %s %s (%s)", level.value, alert.headline, event.id)
        # The one message in this system that is genuinely urgent. An operator
        # waiting up to five seconds to learn a RED warning was raised is the
        # reason the polling loop was the wrong shape.
        notify.publish(
            "alert",
            action="raised",
            level=level.value,
            event_id=str(event.id),
            headline=alert.headline,
            state=event.state,
        )
        return alert

    # --- situation worsened: escalate in place ------------------------------
    if _rank(level) > _rank(live.level):
        live.previous_level = live.level.value
        live.level = level
        live.action = ACTION[level]
        live.escalated_at = now
        live.evidence_snapshot = build_snapshot(event)
        # An escalation demands fresh attention even if already seen.
        if live.status == AlertStatus.ACKNOWLEDGED:
            live.status = AlertStatus.ACTIVE
            live.acknowledged_at = None
            live.acknowledged_by = None
        # An escalation is new information — re-route so authorities whose
        # minimum level the alert has only now reached are told.
        from app.services.pipeline.routing import route

        await route(session, live)
        log.info(
            "alert escalated %s → %s for event %s",
            live.previous_level,
            level.value,
            event.id,
        )
        return live

    # --- still above threshold but not worse: leave it alone -----------------
    return live
