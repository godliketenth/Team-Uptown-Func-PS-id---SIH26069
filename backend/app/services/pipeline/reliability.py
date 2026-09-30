"""Stage 6: per-report reliability score.

Weights are fixed for the prototype. Everything feeding the score is stored
on the report so the UI can show *why* a report scored what it scored.
"""
from __future__ import annotations

from dataclasses import dataclass

SOURCE_TRUST: dict[str, float] = {
    "GOVERNMENT": 1.0,
    "WEATHER_API": 1.0,
    "SATELLITE": 0.9,
    "WEB_RSS": 0.7,
    "CITIZEN": 0.6,
    "SOCIAL": 0.5,
}

W_SOURCE = 0.30
W_WEATHER = 0.30
W_NEARBY = 0.20
W_LOCATION = 0.20

NEARBY_SATURATION = 5
VERIFIED_THRESHOLD = 0.75
REVIEW_THRESHOLD = 0.40


@dataclass
class ReliabilityBreakdown:
    score: float
    source_trust: float
    weather_corroboration: float
    nearby_support: float
    location_confidence: float
    band: str  # VERIFIABLE | NEEDS_REVIEW | INSUFFICIENT_EVIDENCE

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "components": {
                "source_trust": self.source_trust,
                "weather_corroboration": self.weather_corroboration,
                "nearby_support": self.nearby_support,
                "location_confidence": self.location_confidence,
            },
            "weights": {
                "source_trust": W_SOURCE,
                "weather_corroboration": W_WEATHER,
                "nearby_support": W_NEARBY,
                "location_confidence": W_LOCATION,
            },
            "band": self.band,
        }


def weather_average(corroboration: dict | None) -> float:
    if not corroboration:
        return 0.5
    if "overall_support" in corroboration:
        return float(corroboration["overall_support"])
    supports = [v for k, v in corroboration.items() if k.endswith("_support")]
    return round(sum(supports) / len(supports), 4) if supports else 0.5


def band_for(score: float) -> str:
    if score >= VERIFIED_THRESHOLD:
        return "VERIFIABLE"
    if score >= REVIEW_THRESHOLD:
        return "NEEDS_REVIEW"
    return "INSUFFICIENT_EVIDENCE"


def compute_reliability(
    source_type: str,
    corroboration: dict | None,
    nearby_independent_reports: int,
    location_confidence: float,
) -> ReliabilityBreakdown:
    source_trust = SOURCE_TRUST.get(source_type, 0.5)
    weather = weather_average(corroboration)
    nearby = min(nearby_independent_reports / NEARBY_SATURATION, 1.0)
    location = max(0.0, min(1.0, location_confidence))

    score = round(
        W_SOURCE * source_trust
        + W_WEATHER * weather
        + W_NEARBY * nearby
        + W_LOCATION * location,
        4,
    )
    return ReliabilityBreakdown(
        score=score,
        source_trust=source_trust,
        weather_corroboration=round(weather, 4),
        nearby_support=round(nearby, 4),
        location_confidence=round(location, 4),
        band=band_for(score),
    )
