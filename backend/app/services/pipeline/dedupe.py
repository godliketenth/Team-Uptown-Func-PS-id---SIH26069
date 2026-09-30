"""Stage 5: three-stage deduplication.

1. Exact      - same source_id + external_id
2. Hash       - identical sha256 of normalized text
3. Semantic   - embedding cosine similarity AND within 10km AND within 30 minutes

Candidates are limited to the last 2 hours in the same district to keep the
scan small.

Stage 3 uses sentence embeddings (pgvector) when the model is available and
falls back to `difflib` character similarity when it is not, so the project
still runs with no ML download.

Thresholds were calibrated on real intake rather than guessed. Measured within
the 10km/30min window that the threshold actually judges:

  * syndicated copies of one report          cos 0.93 - 0.95
  * same event, different wording            cos 0.86 - 0.88
  * cross-language restatements              cos 0.845 - 0.849
  * p90 of genuinely independent pairs       cos 0.785

0.82 sits above that p90 and below the cross-language cluster. For comparison,
difflib scored those same cross-language pairs 0.386 - 0.403 and the
different-wording pairs as low as 0.448 - it could not see them at all.
"""
from __future__ import annotations

import difflib
from datetime import timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Report
from app.services.pipeline import embeddings
from app.services.pipeline.event_engine import report_point

SIMILARITY_THRESHOLD = 0.85        # difflib fallback (character similarity)
SEMANTIC_THRESHOLD = 0.82          # embeddings (cosine), calibrated above
RADIUS_METERS = 10_000
TIME_WINDOW = timedelta(minutes=30)
CANDIDATE_WINDOW = timedelta(hours=2)


def compute_similarity(text_a: str, text_b: str) -> float:
    """Semantic similarity when the embedding model is loaded, character
    similarity otherwise. Kept as the single swap point for this stage."""
    if not text_a or not text_b:
        return 0.0
    if embeddings.is_available():
        vectors = embeddings.embed_many([text_a, text_b])
        if vectors:
            return embeddings.cosine(vectors[0], vectors[1])
    return difflib.SequenceMatcher(None, text_a, text_b).ratio()


class DuplicateMatch:
    def __init__(self, report_id, method: str, similarity: float | None = None):
        self.report_id = report_id
        self.method = method
        self.similarity = similarity


async def find_duplicate(session: AsyncSession, report: Report) -> DuplicateMatch | None:
    # --- Stage 1: exact source + external id -------------------------------
    if report.source_id and report.external_id:
        stmt = select(Report.id).where(
            Report.id != report.id,
            Report.source_id == report.source_id,
            Report.external_id == report.external_id,
            Report.duplicate_of_report_id.is_(None),
        ).limit(1)
        hit = (await session.execute(stmt)).scalar_one_or_none()
        if hit:
            return DuplicateMatch(hit, "exact_external_id", 1.0)

    if not report.text_hash:
        return None

    since = report.observed_at - CANDIDATE_WINDOW

    # --- Stage 2: identical normalized text --------------------------------
    stmt = select(Report.id).where(
        Report.id != report.id,
        Report.text_hash == report.text_hash,
        Report.observed_at >= since,
        Report.duplicate_of_report_id.is_(None),
    ).limit(1)
    hit = (await session.execute(stmt)).scalar_one_or_none()
    if hit:
        return DuplicateMatch(hit, "text_hash", 1.0)

    # --- Stage 3: fuzzy text + spatial + temporal --------------------------
    conditions = [
        Report.id != report.id,
        Report.observed_at >= report.observed_at - TIME_WINDOW,
        Report.observed_at <= report.observed_at + TIME_WINDOW,
        Report.duplicate_of_report_id.is_(None),
        Report.normalized_text.is_not(None),
    ]
    point = report_point(report)
    if point is not None:
        conditions.append(func.ST_DWithin(Report.geom, point, RADIUS_METERS))
    elif report.district:
        conditions.append(Report.district == report.district)
    else:
        return None

    # --- Stage 3a: semantic search over the same window --------------------
    if report.embedding is not None:
        # pgvector's <=> is cosine DISTANCE, so similarity is 1 - distance.
        # Ordering by distance lets Postgres return the nearest candidate
        # directly rather than scoring every row in Python.
        distance = Report.embedding.cosine_distance(report.embedding)
        stmt = (
            select(Report.id, distance.label("distance"))
            .where(and_(*conditions, Report.embedding.is_not(None)))
            .order_by(distance)
            .limit(5)
        )
        rows = (await session.execute(stmt)).all()
        if rows:
            candidate_id, dist = rows[0]
            similarity = 1.0 - float(dist)
            if similarity >= SEMANTIC_THRESHOLD:
                return DuplicateMatch(candidate_id, "semantic", round(similarity, 4))
            # A near miss on meaning is not worth a second character-level pass.
            return None

    # --- Stage 3b: character similarity when no embedding exists -----------
    stmt = (
        select(Report.id, Report.normalized_text)
        .where(and_(*conditions))
        .order_by(Report.observed_at.desc())
        .limit(80)
    )
    for candidate_id, candidate_text in (await session.execute(stmt)).all():
        ratio = difflib.SequenceMatcher(
            None, report.normalized_text or "", candidate_text or ""
        ).ratio()
        if ratio > SIMILARITY_THRESHOLD:
            return DuplicateMatch(candidate_id, "fuzzy_text", round(ratio, 4))

    return None


async def count_nearby_independent_reports(
    session: AsyncSession, report: Report, radius_m: int = 15_000
) -> int:
    """Distinct *other* sources reporting the same type nearby & recently.
    Feeds the corroboration term of the reliability score."""
    point = report_point(report)
    if point is None:
        return 0
    stmt = select(func.count(func.distinct(Report.source_id))).where(
        Report.id != report.id,
        Report.predicted_event_type == report.predicted_event_type,
        Report.observed_at >= report.observed_at - timedelta(minutes=90),
        Report.duplicate_of_report_id.is_(None),
        or_(Report.source_id.is_(None), Report.source_id != report.source_id),
        func.ST_DWithin(Report.geom, point, radius_m),
    )
    return int((await session.execute(stmt)).scalar() or 0)
