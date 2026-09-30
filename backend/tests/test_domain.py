"""Core domain rules — the decisions this platform exists to make.

Separate from the regression file: these describe intended behaviour rather
than guarding a specific past bug.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone


from app.db.models import SourceType


# --- warning levels -------------------------------------------------------
# The vocabulary and actions follow IMD's published scale; the thresholds are
# ours, derived from accumulated evidence rather than forecast intensity.
def _event(**over):
    base = dict(
        # Not VERIFIED by default: a human verdict deliberately floors the
        # level at ORANGE, which would mask the evidence thresholds these
        # tests are about.
        status="CORROBORATING",
        report_count=1,
        source_count=1,
        evidence_score=0.1,
        corroboration_score=0.5,
        flagged_report_count=0,
    )
    base.update(over)
    return base


def test_warning_escalates_with_evidence():
    from app.services.pipeline.warning import assess

    order = []
    for kwargs in (
        _event(report_count=1, source_count=1, evidence_score=0.10),
        _event(report_count=3, source_count=2, evidence_score=0.40),
        _event(report_count=12, source_count=3, evidence_score=0.52),
        _event(report_count=30, source_count=5, evidence_score=0.70),
    ):
        order.append(assess(**kwargs).level.value)
    assert order == sorted(order, key=["GREEN", "YELLOW", "ORANGE", "RED"].index)
    assert order[0] == "GREEN" and order[-1] == "RED"


def test_a_single_source_cannot_raise_a_red_warning():
    """Volume from one source is not corroboration, however loud."""
    from app.services.pipeline.warning import assess

    a = assess(**_event(report_count=500, source_count=1, evidence_score=0.95))
    assert a.level.value != "RED"
    assert any("corroboration" in r for r in a.reasons)


def test_a_human_verdict_floors_the_level():
    """A verified event earns "be prepared" regardless of how thin the
    automated evidence is — the reviewer has seen something the pipeline
    could not."""
    from app.services.pipeline.warning import assess

    thin = _event(report_count=1, source_count=1, evidence_score=0.05)
    assert assess(**{**thin, "status": "CORROBORATING"}).level.value == "GREEN"
    a = assess(**{**thin, "status": "VERIFIED"})
    assert a.level.value == "ORANGE"
    assert any("reviewer" in r for r in a.reasons)


def test_a_rejected_event_carries_no_warning():
    from app.services.pipeline.warning import assess

    strong = _event(report_count=80, source_count=6, evidence_score=0.9)
    assert assess(**{**strong, "status": "REJECTED"}).level.value == "GREEN"


def test_mass_flagged_reports_cap_the_level_and_say_so():
    """`capped_by` means a credibility problem held the level *down* — as
    distinct from evidence that never reached the threshold."""
    from app.services.pipeline.warning import assess

    a = assess(
        **_event(
            report_count=40,
            source_count=5,
            evidence_score=0.80,
            flagged_report_count=38,
        )
    )
    assert a.level.value == "YELLOW"
    assert a.capped_by is not None


def test_every_warning_states_its_reasons():
    from app.services.pipeline.warning import assess

    a = assess(**_event(report_count=30, source_count=5, evidence_score=0.70))
    assert a.reasons, "an operator must be able to see why this level was chosen"


# --- credibility ----------------------------------------------------------
def test_absent_corroboration_is_weaker_than_contradiction():
    from app.services.pipeline.credibility import assess

    common = dict(
        source_type=SourceType.CITIZEN,
        event_type_scores={"RAIN": 0.9},
        nearby_independent_reports=0,
        location_confidence=0.6,
        text="Heavy rain and waterlogging near the station",
    )
    absent = assess(corroboration={"status": "ok", "contradicted": False}, **common)
    against = assess(corroboration={"status": "ok", "contradicted": True}, **common)
    assert against.risk > absent.risk


def test_duplicate_content_raises_risk_but_is_not_damning():
    from app.services.pipeline.credibility import assess

    common = dict(
        source_type=SourceType.SOCIAL,
        corroboration={"status": "ok", "contradicted": False},
        event_type_scores={"RAIN": 0.9},
        nearby_independent_reports=3,
        location_confidence=0.6,
        text="Heavy rain and waterlogging near the station",
    )
    plain = assess(is_duplicate=False, **common)
    dupe = assess(is_duplicate=True, **common)
    assert dupe.risk > plain.risk
    assert not dupe.needs_review, "a re-post alone should not demand human review"


# --- deduplication --------------------------------------------------------
def test_identical_text_is_maximally_similar():
    from app.services.pipeline.dedupe import compute_similarity

    text = "Heavy waterlogging near Andheri station in Mumbai"
    assert compute_similarity(text, text) >= 0.99


def test_unrelated_text_is_not_similar():
    from app.services.pipeline.dedupe import SIMILARITY_THRESHOLD, compute_similarity

    score = compute_similarity(
        "Heavy waterlogging near Andheri station in Mumbai",
        "Anyone know when the power comes back",
    )
    assert score < SIMILARITY_THRESHOLD


# --- the raw lake ---------------------------------------------------------
def test_lake_falls_back_to_disk_when_the_object_store_is_unreachable(tmp_path, monkeypatch):
    """An object store outage must cost durability of the mirror, never the
    write. The database row is the record; the lake is a replayable copy."""
    import app.services.ingestion.lake as lake
    from app.config import settings

    monkeypatch.setattr(settings, "s3_endpoint_url", "http://127.0.0.1:9", raising=False)
    monkeypatch.setattr(settings, "s3_access_key", "x", raising=False)
    monkeypatch.setattr(settings, "s3_secret_key", "y", raising=False)
    monkeypatch.setattr(settings, "raw_lake_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(lake, "_s3_client", None, raising=False)
    monkeypatch.setattr(lake, "_s3_retry_after", 0.0, raising=False)

    path = lake.write_raw(
        uuid.uuid4(), "CITIZEN", datetime.now(timezone.utc), {"text": "outage test"}
    )
    assert path and not path.startswith("s3://")
    assert list(tmp_path.rglob("*.json")), "the write was lost entirely"


def test_lake_partition_layout_is_stable():
    """The layout is the contract that makes both backends interchangeable."""
    from app.services.ingestion.lake import object_key

    rid = uuid.UUID("00000000-0000-0000-0000-0000000000ab")
    key = object_key(rid, "CITIZEN", datetime(2026, 9, 29, 12, tzinfo=timezone.utc))
    assert key == f"citizen/2026/09/29/{rid}.json"


# --- the event bus --------------------------------------------------------
def test_bus_reports_the_transport_actually_in_use(monkeypatch):
    """`kafka_enabled` says what was asked for; the health field must say what
    is working, or an outage looks like normal operation."""
    from app.services import bus
    from app.config import settings

    monkeypatch.setattr(settings, "kafka_bootstrap_servers", "localhost:9092", raising=False)
    monkeypatch.setattr(bus, "_kafka_active", False, raising=False)
    assert bus.stats.as_dict()["transport"] == "in-process"

    monkeypatch.setattr(bus, "_kafka_active", True, raising=False)
    assert bus.stats.as_dict()["transport"] == "kafka"


# --- live update fan-out --------------------------------------------------
async def test_notify_delivers_to_subscribers():
    from app.services import notify

    with notify.subscription() as queue:
        notify.publish("alert", action="raised", level="RED")
        message = await asyncio.wait_for(queue.get(), timeout=1)
    assert message["kind"] == "alert" and message["level"] == "RED"


async def test_a_slow_subscriber_is_dropped_not_waited_for():
    """Backpressure must never reach the pipeline: every message is only
    'something changed', so losing one costs nothing."""
    from app.services import notify

    with notify.subscription() as queue:
        for _ in range(notify.QUEUE_MAX + 25):
            notify.publish("ingest", published=1)
        assert queue.qsize() == notify.QUEUE_MAX
    assert notify.subscriber_count() == 0, "the subscription must clean itself up"


def test_publishing_with_no_subscribers_is_harmless():
    from app.services import notify

    notify.publish("ingest", published=3)  # must not raise


# --- access control -------------------------------------------------------
def test_no_authenticated_route_is_left_unguarded():
    """Found by audit: `GET /verification/queue` had no dependency at all,
    while all three of its sibling routes required a verifier. It exposed
    which events the platform currently distrusts, before any human had
    looked. This test checks the whole surface rather than that one route, so
    the next omission is caught by construction."""
    import re
    from pathlib import Path

    api = Path(__file__).resolve().parents[1] / "app" / "api" / "v1"
    guards = ("require_admin", "require_verifier", "require_analyst", "get_current_user")

    # Public by design, and listed one route at a time so that adding a new
    # unguarded route is a decision someone has to write down here.
    #
    # The citizen-facing dashboard is the product: a weather warning nobody
    # can read without an account is not a warning. What stays guarded is the
    # operational layer — who was notified, who acted, and which events the
    # platform currently distrusts.
    PUBLIC_ROUTERS = {"analytics", "events", "map", "reports", "auth"}
    PUBLIC_ROUTES = {
        "GET alerts/",                      # active public warnings
        "GET alerts/summary",               # counts behind the public map
        "GET alerts/{alert_id}",            # one warning
        "GET alerts/{alert_id}/advisory",   # the bulletin meant for the public
    }

    unguarded = []
    for path in sorted(api.glob("*.py")):
        if path.stem in PUBLIC_ROUTERS or path.name.startswith("_"):
            continue
        src = path.read_text()
        for m in re.finditer(
            r'@router\.(get|post|patch|put|delete)\("([^"]*)"[^)]*\)\s*\n'
            r'(?:async )?def \w+\(((?:.|\n)*?)\)\s*->',
            src,
        ):
            verb, route, signature = m.groups()
            name = f"{verb.upper()} {path.stem}{route or '/'}"
            if name in PUBLIC_ROUTES:
                continue
            if not any(g in signature for g in guards):
                unguarded.append(name)

    assert not unguarded, f"routes with no auth dependency: {unguarded}"
