"""Drop credibility flags that the current rules would no longer raise.

Credibility is scored once, at ingest. When a rule changes, every row scored
under the old rule keeps the old verdict — and a misinformation score is not a
harmless stale number: it decides whether a report sits in a human review
queue. This is the fourth derived column in this project to need a backfill
after its logic changed (warning levels, alerts, deliveries, and now this),
which is why it gets a script rather than a one-off UPDATE.

Scope: the CONTRADICTED_BY_OBSERVATION flag on coarsely-located reports. A
state match places a report at a centroid — for Rajasthan, one point in an
area the size of Germany — so the weather at that point cannot contradict a
state-wide claim.

Risk is recomputed from the remaining flags using the canonical weights rather
than by subtracting, so the result is whatever the current rules say and not
an arithmetic patch on an old answer.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.models import Report
from app.db.session import SessionLocal
from app.services.pipeline.credibility import (
    CONTRADICTED_BY_OBSERVATION,
    FLAG_LABELS,
    FLAG_WEIGHTS,
    REVIEW_RISK,
)

# Matches the threshold that defines UNRESOLVED_LOCATION: too coarse to be
# called located is too coarse to be called wrong.
COARSE_LOCATION = 0.35


async def main() -> int:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Report).where(Report.location_confidence <= COARSE_LOCATION)
            )
        ).scalars().all()

        changed = 0
        left_review = 0
        for report in rows:
            payload = report.credibility_flags or {}
            codes = [f["code"] for f in payload.get("flags", [])]
            if CONTRADICTED_BY_OBSERVATION not in codes:
                continue

            codes = [c for c in codes if c != CONTRADICTED_BY_OBSERVATION]
            risk = min(1.0, sum(FLAG_WEIGHTS[c] for c in codes))
            needs_review = risk >= REVIEW_RISK

            if payload.get("needs_review") and not needs_review:
                left_review += 1

            report.misinformation_risk = risk
            report.credibility_flags = {
                "risk": round(risk, 4),
                "needs_review": needs_review,
                "flags": [
                    {"code": c, "label": FLAG_LABELS[c], "weight": FLAG_WEIGHTS[c]}
                    for c in codes
                ],
            }
            changed += 1

        await session.commit()

    print(f"  examined {len(rows):,} coarsely-located reports")
    print(f"  rescored : {changed:,}")
    print(f"  released from the review queue: {left_review:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
