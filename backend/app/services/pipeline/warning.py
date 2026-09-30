"""Phase 2.1 — IMD-style four-colour warning levels.

The India Meteorological Department communicates risk on a four-colour scale
with explicit actions attached:

    GREEN   No warning    — no action needed
    YELLOW  Watch         — be updated
    ORANGE  Alert         — be prepared
    RED     Warning       — take action

IMD derives those colours from *forecast intensity thresholds* (rainfall in
mm/day, temperature departure from normal, wind speed). This platform does not
forecast — it aggregates and verifies citizen and agency reports. So we adopt
IMD's vocabulary and action semantics, which is what makes output legible to a
district officer, but the trigger logic below is **ours, not IMD's official
criteria**, and is stated in those terms wherever it is shown.

The level is driven by the same evidence the rest of the platform exposes:
how many reports, how many independent sources, how reliable they are, and
whether real observed weather agrees.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass


class WarningLevel(str, enum.Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    ORANGE = "ORANGE"
    RED = "RED"


ACTION: dict[WarningLevel, str] = {
    WarningLevel.GREEN: "No action needed",
    WarningLevel.YELLOW: "Watch — be updated",
    WarningLevel.ORANGE: "Alert — be prepared",
    WarningLevel.RED: "Warning — take action",
}

# Hex values follow IMD's published bulletin colours closely enough to be
# recognisable, while staying legible on a dark console.
COLOR: dict[WarningLevel, str] = {
    WarningLevel.GREEN: "#22C55E",
    WarningLevel.YELLOW: "#F5B642",
    WarningLevel.ORANGE: "#FB923C",
    WarningLevel.RED: "#EF4444",
}

ORDER: list[WarningLevel] = [
    WarningLevel.GREEN,
    WarningLevel.YELLOW,
    WarningLevel.ORANGE,
    WarningLevel.RED,
]

# Thresholds. Volume alone never reaches ORANGE: a crowd repeating itself is
# not corroboration, so independent sources and evidence quality gate the
# upper levels.
#
# Contradiction, not weak corroboration, is what holds a level down — see the
# note in assess(). Weather that agrees adds a supporting reason but never
# gates the level on its own.
RED_REPORTS = 25
RED_SOURCES = 4
RED_EVIDENCE = 0.62
ORANGE_REPORTS = 10
ORANGE_SOURCES = 3
ORANGE_EVIDENCE = 0.50
YELLOW_SOURCES = 2
YELLOW_EVIDENCE = 0.38

CONTRADICTED_FLAG_RATIO = 0.5   # most reports flagged → hold the level down


@dataclass
class WarningAssessment:
    level: WarningLevel
    action: str
    reasons: list[str]
    capped_by: str | None = None

    def as_dict(self) -> dict:
        return {
            "level": self.level.value,
            "action": self.action,
            "color": COLOR[self.level],
            "reasons": self.reasons,
            "capped_by": self.capped_by,
        }


def assess(
    *,
    status: str,
    report_count: int,
    source_count: int,
    evidence_score: float,
    corroboration_score: float,
    flagged_report_count: int,
) -> WarningAssessment:
    """Derive a warning level from the event's accumulated evidence."""
    reasons: list[str] = []
    capped_by: str | None = None

    # A human verdict overrides everything the pipeline inferred.
    if status in ("REJECTED", "RESOLVED"):
        return WarningAssessment(
            WarningLevel.GREEN,
            ACTION[WarningLevel.GREEN],
            [f"event {status.lower()} by review"],
        )

    # --- provisional level from evidence ---------------------------------
    if (
        report_count >= RED_REPORTS
        and source_count >= RED_SOURCES
        and evidence_score >= RED_EVIDENCE
    ):
        level = WarningLevel.RED
        reasons.append(
            f"{report_count} reports from {source_count} independent sources, "
            f"evidence {evidence_score:.0%}"
        )
    elif (
        report_count >= ORANGE_REPORTS
        and source_count >= ORANGE_SOURCES
        and evidence_score >= ORANGE_EVIDENCE
    ):
        level = WarningLevel.ORANGE
        reasons.append(
            f"{report_count} reports from {source_count} independent sources, "
            f"evidence {evidence_score:.0%}"
        )
    elif source_count >= YELLOW_SOURCES and evidence_score >= YELLOW_EVIDENCE:
        level = WarningLevel.YELLOW
        reasons.append(f"{source_count} independent sources corroborating")
    else:
        level = WarningLevel.GREEN
        reasons.append("insufficient independent corroboration")

    # --- caps: credibility problems hold the level down -------------------
    if report_count and flagged_report_count / report_count >= CONTRADICTED_FLAG_RATIO:
        if ORDER.index(level) > ORDER.index(WarningLevel.YELLOW):
            level = WarningLevel.YELLOW
            capped_by = "most contributing reports flagged for credibility"

    # NOTE: we deliberately do NOT cap on a low corroboration score. A coarse
    # model grid reading 0mm does not disprove street-level flooding — absence
    # of support is not contradiction. That distinction is already made in the
    # credibility stage, which raises CONTRADICTED_BY_OBSERVATION only when the
    # observation actively opposes the claim; the flagged-ratio cap above is
    # what carries it through to the warning level.

    # A verified event earns at least "be prepared".
    if status == "VERIFIED" and ORDER.index(level) < ORDER.index(WarningLevel.ORANGE):
        level = WarningLevel.ORANGE
        reasons.append("verified by a human reviewer")

    if corroboration_score >= 0.6:
        reasons.append(f"observed weather agrees ({corroboration_score:.0%})")

    return WarningAssessment(level, ACTION[level], reasons, capped_by)
