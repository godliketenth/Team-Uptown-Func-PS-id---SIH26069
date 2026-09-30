"""Stage 6b: flag fake, misleading or untrustworthy reports.

This is the "identify fake or misleading reports / verify untrusted sources"
half of the platform. It is rule-based and explainable on purpose: every flag
names the evidence that raised it, so a human verifier can agree or disagree
with a specific claim rather than with an opaque score.

It is also the natural drop-in point for a trained classifier - keep the
`assess(...) -> CredibilityAssessment` signature and callers need no change.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import logging
import threading
from pathlib import Path

import numpy as np

from app.services.pipeline.reliability import SOURCE_TRUST

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Learned relevance signal (Phase 1.3)
# ---------------------------------------------------------------------------
RELEVANCE_MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "credibility_model.npz"
RELEVANCE_THRESHOLD = 0.5
_REL_LOCK = threading.Lock()
_relevance: dict | None = None
_relevance_failed = False


def _load_relevance() -> dict | None:
    global _relevance, _relevance_failed
    if _relevance is not None:
        return _relevance
    if _relevance_failed:
        return None
    with _REL_LOCK:
        if _relevance is not None:
            return _relevance
        if _relevance_failed:
            return None
        try:
            if not RELEVANCE_MODEL_PATH.exists():
                raise FileNotFoundError(RELEVANCE_MODEL_PATH)
            data = np.load(RELEVANCE_MODEL_PATH)
            _relevance = {
                "coef": data["coef"].astype(np.float32).ravel(),
                "intercept": float(data["intercept"][0]),
            }
            log.info("relevance model loaded from %s", RELEVANCE_MODEL_PATH)
            return _relevance
        except Exception as exc:
            _relevance_failed = True
            log.warning("relevance model unavailable (%s); using keyword fallback", exc)
            return None


def off_topic_probability_from_vector(vector) -> float | None:
    """P(this is not a weather report), from an already-computed embedding.

    The pipeline embeds each report once during normalization; reusing that
    vector here avoids a second inference pass, which measured 6.5ms per
    report — the single largest avoidable cost in the pipeline.
    """
    model = _load_relevance()
    if model is None or vector is None:
        return None
    try:
        z = float(np.dot(model["coef"], np.asarray(vector, dtype=np.float32)) + model["intercept"])
        return float(1.0 / (1.0 + np.exp(-z)))
    except Exception as exc:
        log.warning("relevance inference failed: %s", exc)
        return None


def off_topic_probability(text: str) -> float | None:
    """P(this is not a weather report) from raw text. Prefer the vector form
    when a vector is already to hand."""
    model = _load_relevance()
    if model is None or not text:
        return None
    from app.services.pipeline import embeddings

    vec = embeddings.embed(text)
    if vec is None:
        return None
    try:
        z = float(np.dot(model["coef"], np.asarray(vec, dtype=np.float32)) + model["intercept"])
        return float(1.0 / (1.0 + np.exp(-z)))
    except Exception as exc:
        log.warning("relevance inference failed: %s", exc)
        return None

# Flag codes, ordered roughly by how damning they are.
CONTRADICTED_BY_OBSERVATION = "CONTRADICTED_BY_OBSERVATION"
UNCORROBORATED = "UNCORROBORATED"
LOW_TRUST_SOURCE = "LOW_TRUST_SOURCE"
UNRESOLVED_LOCATION = "UNRESOLVED_LOCATION"
NO_WEATHER_SIGNAL = "NO_WEATHER_SIGNAL"
DUPLICATE_CONTENT = "DUPLICATE_CONTENT"

FLAG_LABELS: dict[str, str] = {
    CONTRADICTED_BY_OBSERVATION: "Contradicted by observed weather",
    UNCORROBORATED: "No independent source nearby",
    LOW_TRUST_SOURCE: "Low-trust source",
    UNRESOLVED_LOCATION: "Location could not be resolved",
    NO_WEATHER_SIGNAL: "No weather terms detected",
    DUPLICATE_CONTENT: "Duplicate of an earlier report",
}

# How much each flag contributes to the 0-1 misinformation risk.
FLAG_WEIGHTS: dict[str, float] = {
    CONTRADICTED_BY_OBSERVATION: 0.40,
    UNCORROBORATED: 0.20,
    LOW_TRUST_SOURCE: 0.15,
    UNRESOLVED_LOCATION: 0.10,
    NO_WEATHER_SIGNAL: 0.25,
    DUPLICATE_CONTENT: 0.10,
}

LOW_TRUST_CEILING = 0.55       # SOCIAL (0.5) trips this; CITIZEN (0.6) does not
FLAT_SCORE_EPSILON = 0.02      # classifier returned its no-signal flat prior
REVIEW_RISK = 0.50             # at or above this, a human should look


@dataclass
class CredibilityAssessment:
    risk: float
    flags: list[str] = field(default_factory=list)
    needs_review: bool = False

    def as_dict(self) -> dict:
        return {
            "risk": self.risk,
            "needs_review": self.needs_review,
            "flags": [
                {"code": code, "label": FLAG_LABELS[code], "weight": FLAG_WEIGHTS[code]}
                for code in self.flags
            ],
        }


def _no_weather_signal(
    text: str | None, scores: dict[str, float] | None, vector=None
) -> bool:
    """True when nothing in the text is about weather.

    Never uses the shape of the hazard classifier's output. That classifier is
    a softmax over seven weather classes with no "none of the above" option, so
    it labels off-topic text confidently — checking its distribution for
    flatness (as this once did) silently stopped detecting anything the moment
    the model was introduced.

    Prefers the trained relevance model, which measured precision 1.000 against
    the keyword detector's 0.344 on the same data. Precision is what matters
    here: wrongly calling a genuine report irrelevant suppresses real signal,
    which is worse than missing one off-topic post.
    """
    from app.services.pipeline.classify import has_weather_signal

    # Prefer the vector the pipeline already computed.
    probability = (
        off_topic_probability_from_vector(vector)
        if vector is not None
        else (off_topic_probability(text) if text is not None else None)
    )
    if probability is not None:
        return probability >= RELEVANCE_THRESHOLD
    if text is not None:
        return not has_weather_signal(text)

    # No text available: fall back to the old flatness heuristic.
    if not scores or len(scores) < 2:
        return True
    values = list(scores.values())
    return max(values) - min(values) < FLAT_SCORE_EPSILON


def assess(
    source_type: str,
    corroboration: dict | None,
    event_type_scores: dict[str, float] | None,
    nearby_independent_reports: int,
    location_confidence: float,
    is_duplicate: bool = False,
    text: str | None = None,
    embedding=None,
) -> CredibilityAssessment:
    flags: list[str] = []

    # Only an actively opposing reading counts (see corroborate.detect_contradiction).
    # Merely absent support is not evidence of falsehood - the model grid is far
    # coarser than the phenomena being reported.
    #
    # And the same argument applies to the *location*: a state-level match
    # places the report at a centroid, which for Rajasthan is one point in an
    # area the size of Germany. Checking the weather at that point says
    # nothing about a state-wide claim, so a coarse location cannot
    # contradict. Without this, real IMD-sourced journalism scored 0.80 risk
    # and landed in the review queue — "Rainfall activity to decline in
    # Rajasthan" was called contradicted because it was not raining at the
    # centroid, which is exactly what the headline said.
    #
    # The threshold is the one that already defines an unresolved location:
    # too coarse to be called located is too coarse to be called wrong.
    if corroboration and corroboration.get("status") == "ok":
        if bool(corroboration.get("contradicted")) and location_confidence > 0.35:
            flags.append(CONTRADICTED_BY_OBSERVATION)

    if nearby_independent_reports == 0:
        flags.append(UNCORROBORATED)

    if SOURCE_TRUST.get(source_type, 0.5) <= LOW_TRUST_CEILING:
        flags.append(LOW_TRUST_SOURCE)

    if location_confidence <= 0.35:
        flags.append(UNRESOLVED_LOCATION)

    if _no_weather_signal(text, event_type_scores, embedding):
        flags.append(NO_WEATHER_SIGNAL)

    if is_duplicate:
        flags.append(DUPLICATE_CONTENT)

    risk = round(min(1.0, sum(FLAG_WEIGHTS[f] for f in flags)), 4)
    return CredibilityAssessment(
        risk=risk, flags=flags, needs_review=risk >= REVIEW_RISK
    )
