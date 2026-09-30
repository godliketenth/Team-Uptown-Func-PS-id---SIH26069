"""Pipeline orchestration.

raw_event -> normalize -> geo -> classify -> corroborate -> dedupe ->
reliability -> event_engine

`processing_state` is advanced at each step so /admin/system-health can show a
truthful per-stage breakdown rather than a decorative one.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProcessingState, RawEvent, Report, SourceType
from app.services.pipeline import classify as classify_mod
from app.services.pipeline import credibility as credibility_mod
from app.services.pipeline import embeddings as embeddings_mod
from app.services.pipeline import corroborate as corroborate_mod
from app.services.pipeline import dedupe as dedupe_mod
from app.services.pipeline import normalize as normalize_mod
from app.services.pipeline import reliability as reliability_mod
from app.services.pipeline.event_engine import assign_to_event, point_wkt
from app.services.ingestion.lake import write_raw
from app.services.pipeline.geo import resolve_location

log = logging.getLogger(__name__)


def _parse_observed_at(payload: dict, fallback: datetime) -> datetime:
    value = payload.get("observed_at")
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return fallback
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def process_raw_event(session: AsyncSession, raw_event_id: uuid.UUID) -> Report | None:
    raw = await session.get(RawEvent, raw_event_id)
    if raw is None:
        log.warning("raw_event %s vanished before processing", raw_event_id)
        return None

    # Idempotency: a replay of the same raw event must not double-count.
    existing = (
        await session.execute(select(Report.id).where(Report.raw_event_id == raw.id).limit(1))
    ).scalar_one_or_none()
    if existing is not None:
        return None

    payload = raw.payload or {}
    raw_text = str(payload.get("text") or "")

    report = Report(
        raw_event_id=raw.id,
        source_id=raw.source_id,
        source_type=raw.source_type,
        external_id=raw.external_id,
        raw_text=raw_text,
        observed_at=_parse_observed_at(payload, raw.collected_at),
        media=payload.get("media"),
        processing_state=ProcessingState.RECEIVED,
    )
    session.add(report)
    await session.flush()

    # --- 1. normalize ------------------------------------------------------
    norm = normalize_mod.normalize(raw_text)
    report.normalized_text = norm.normalized_text
    report.language = norm.language
    report.text_hash = norm.text_hash
    report.hashtags = norm.hashtags
    report.tracked_hashtags = norm.tracked_hashtags
    report.mentions = norm.mentions
    report.urls = norm.urls
    report.author = payload.get("author") or payload.get("reporter_handle")
    # Embed the normalized text so the dedup stage can search by meaning.
    # Inference is blocking CPU work, so it runs off the event loop.
    report.embedding = await embeddings_mod.embed_async(norm.normalized_text)
    report.processing_state = ProcessingState.NORMALIZED

    # --- 2. geo ------------------------------------------------------------
    geo = resolve_location(
        raw_text,
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
        city_hint=payload.get("city_hint"),
    )
    report.latitude = geo.latitude
    report.longitude = geo.longitude
    report.city = geo.city
    report.district = geo.district
    report.state = geo.state
    report.location_confidence = geo.confidence
    if geo.latitude is not None and geo.longitude is not None:
        report.geom = point_wkt(geo.latitude, geo.longitude)
    report.processing_state = ProcessingState.ENRICHED
    await session.flush()

    # --- 3. classify -------------------------------------------------------
    # The embedding was computed above for dedup; classifying from it avoids
    # a second inference pass. Falls back to text when there is no vector.
    from_vector = classify_mod.predict_from_vector(report.embedding)
    predicted, scores = from_vector or classify_mod.predict(norm.normalized_text)
    report.predicted_event_type = predicted
    report.event_type_scores = scores
    report.processing_state = ProcessingState.CLASSIFIED

    # --- 4. corroborate against real weather -------------------------------
    report.weather_corroboration = await corroborate_mod.corroborate(
        predicted, report.latitude, report.longitude, report.observed_at, report.city
    )

    # --- 5. dedupe ---------------------------------------------------------
    match = await dedupe_mod.find_duplicate(session, report)
    if match is not None:
        # The duplicate target is found by one statement and written by
        # another, so it can be deleted in between — the load-test benchmark's
        # cleanup did exactly that, three times, and each report whose link
        # pointed at a deleted row failed its whole pipeline with a foreign-key
        # violation and was dropped.
        #
        # Re-checking here closes the realistic window: a concurrent delete has
        # committed by the time we look. It cannot close the window entirely,
        # and that is deliberately not papered over with a savepoint — rolling
        # one back expires the ORM object and the failure simply moves
        # (measured: PendingRollbackError, then MissingGreenlet). If the true
        # race ever fires, the raw event is still in `raw_events` and the whole
        # point of an immutable log is that it can be replayed.
        still_there = await session.scalar(
            select(Report.id).where(Report.id == match.report_id)
        )
        if still_there is None:
            log.warning(
                "dedupe target %s vanished; keeping this report as an original",
                match.report_id,
            )
            match = None
        else:
            report.duplicate_of_report_id = match.report_id
            report.dedup_method = match.method

    report.processing_state = ProcessingState.DEDUPLICATED
    await session.flush()

    # --- 6. reliability ----------------------------------------------------
    nearby = 0 if match else await dedupe_mod.count_nearby_independent_reports(session, report)
    breakdown = reliability_mod.compute_reliability(
        source_type=report.source_type.value,
        corroboration=report.weather_corroboration,
        nearby_independent_reports=nearby,
        location_confidence=report.location_confidence,
    )
    report.reliability_score = breakdown.score
    report.insufficient_evidence = breakdown.band == "INSUFFICIENT_EVIDENCE"
    report.weather_corroboration = dict(report.weather_corroboration or {}) | {
        "nearby_independent_reports": nearby,
        "reliability": breakdown.as_dict(),
    }

    # --- 6b. credibility: fake / misleading detection ----------------------
    assessment = credibility_mod.assess(
        source_type=report.source_type.value,
        corroboration=report.weather_corroboration,
        event_type_scores=report.event_type_scores,
        nearby_independent_reports=nearby,
        location_confidence=report.location_confidence,
        is_duplicate=match is not None,
        text=report.normalized_text,
        embedding=report.embedding,
    )
    report.misinformation_risk = assessment.risk
    report.credibility_flags = assessment.as_dict()

    # --- 7. event assignment ----------------------------------------------
    if match is None:
        event = await assign_to_event(session, report)
        if event is not None:
            report.processing_state = ProcessingState.EVENT_ASSIGNED

    await session.commit()
    return report


async def store_raw_event(
    session: AsyncSession,
    source_id: uuid.UUID | None,
    source_type: SourceType,
    external_id: str | None,
    payload: dict,
    collected_at: datetime | None = None,
) -> RawEvent:
    """Write to the immutable log first; the pipeline always reads from here."""
    raw = RawEvent(
        source_id=source_id,
        source_type=source_type,
        external_id=external_id,
        collected_at=collected_at or datetime.now(timezone.utc),
        payload=payload,
        schema_version=1,
    )
    session.add(raw)
    await session.flush()
    write_raw(raw.id, source_type.value, raw.collected_at, payload)
    return raw
