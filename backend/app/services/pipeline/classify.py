"""Stage 3: event-type classification.

Two implementations behind one boundary:

  * a trained logistic-regression head over sentence embeddings (Phase 1.1),
    used whenever `models/event_classifier.npz` and the embedding model are
    both present; and
  * the original keyword scoring, used as a fallback so the project still runs
    with no ML download.

Measured on a held-out split of the synthetic corpus the two look similar
(keywords 95.7%, model 100.0%) — but that benchmark is near-circular, because
the generator writes the very keywords the rules search for.

On a hand-written set of realistic reports (implicit phrasing, Hinglish,
misspellings, negation traps) the gap is the real story:

    rule-based keywords   40%
    embedding model       65%

The rules fail there because they fall back to a flat prior when no keyword
matches, which resolves to RAIN. The model reads "roads have turned into
rivers" as FLOOD and "AC running non stop and still sweating" as HEATWAVE.

Blending the two was measured and did not beat the model alone, so it is not
done.
"""
from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

import numpy as np

KEYWORDS: dict[str, list[str]] = {
    "RAIN": [
        "rain", "rainfall", "showers", "drizzle", "downpour", "monsoon",
        "बारिश", "बरसात", "વરસાદ",
    ],
    "FLOOD": [
        "flood", "flooding", "waterlogging", "water logging", "inundation",
        "submerged", "overflowing", "बाढ़", "जलभराव", "પૂર",
    ],
    "THUNDERSTORM": [
        "thunderstorm", "lightning", "thunder", "squall", "hailstorm", "hail",
        "गरज", "बिजली", "વીજળી",
    ],
    "HEATWAVE": [
        "heatwave", "heat wave", "scorching", "sweltering", "heat stroke",
        "loo ", "गर्मी", "लू", "ગરમી",
    ],
    "FOG": [
        "fog", "foggy", "mist", "visibility", "smog", "कोहरा", "ધુમ્મસ",
    ],
    "DUST_STORM": [
        "dust storm", "duststorm", "dust", "sandstorm", "आंधी", "धूल", "ધૂળ",
    ],
    "STRONG_WIND": [
        "strong wind", "gusty wind", "gusts", "wind speed", "high winds",
        "तेज हवा", "પવન",
    ],
}

EVENT_TYPES: list[str] = list(KEYWORDS)
SCORE_FLOOR = 0.02

_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    et: [re.compile(re.escape(k.strip()), re.IGNORECASE) for k in kws]
    for et, kws in KEYWORDS.items()
}


def classify(text: str) -> dict[str, float]:
    """Return a normalized score per event type. Never returns an exact 0.

    Uses the trained model when available, otherwise keyword scoring.
    """
    text = text or ""
    if model_available():
        from app.services.pipeline import embeddings

        if embeddings.is_available():
            scored = classify_vector(embeddings.embed(text))
            if scored is not None:
                return scored
    return classify_keywords(text)


def classify_keywords(text: str) -> dict[str, float]:
    """The original rule-based scorer, kept as the offline fallback."""
    text = text or ""
    hits = {
        et: sum(len(p.findall(text)) for p in patterns)
        for et, patterns in _PATTERNS.items()
    }
    total = sum(hits.values())
    if total == 0:
        # No signal: flat prior so downstream reliability decides the outcome.
        flat = round(1.0 / len(EVENT_TYPES), 4)
        return {et: flat for et in EVENT_TYPES}

    raw = {et: (h / total) + SCORE_FLOOR for et, h in hits.items()}
    denom = sum(raw.values())
    return {et: round(v / denom, 4) for et, v in raw.items()}


def has_weather_signal(text: str) -> bool:
    """Is this text about weather at all?

    Deliberately keyword-based even though classification is now a model. A
    softmax over seven weather classes has no "none of the above" option, so it
    answers "which hazard" confidently even for "anyone know when the power
    comes back" — it cannot answer "is this weather". The keyword scorer is a
    poor type classifier but an excellent relevance detector, which is exactly
    what is needed here.

    This replaced a flat-distribution check that silently stopped working when
    the model was introduced.
    """
    text = text or ""
    return any(p.search(text) for patterns in _PATTERNS.values() for p in patterns)


def predict(text: str) -> tuple[str, dict[str, float]]:
    scores = classify(text)
    return max(scores, key=scores.get), scores


# ---------------------------------------------------------------------------
# Trained classifier (Phase 1.1)
# ---------------------------------------------------------------------------
log = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "event_classifier.npz"
_MODEL_LOCK = threading.Lock()
_model: dict | None = None
_model_failed = False


def _load_model() -> dict | None:
    """Load the exported weight matrix once. Inference is pure numpy, so
    scikit-learn is a training-time dependency only."""
    global _model, _model_failed
    if _model is not None:
        return _model
    if _model_failed:
        return None
    with _MODEL_LOCK:
        if _model is not None:
            return _model
        if _model_failed:
            return None
        try:
            if not MODEL_PATH.exists():
                raise FileNotFoundError(
                    f"{MODEL_PATH} not found — run `python training/train_classifier.py`"
                )
            data = np.load(MODEL_PATH, allow_pickle=True)
            _model = {
                "coef": data["coef"].astype(np.float32),
                "intercept": data["intercept"].astype(np.float32),
                "classes": [str(c) for c in data["classes"]],
            }
            log.info("event classifier loaded from %s", MODEL_PATH)
            return _model
        except Exception as exc:
            _model_failed = True
            log.warning("trained classifier unavailable (%s); using keyword rules", exc)
            return None


def model_available() -> bool:
    return _load_model() is not None


def classify_vector(vector) -> dict[str, float] | None:
    """Classify from an already-computed embedding.

    The pipeline embeds each report once for deduplication; reusing that
    vector here avoids a second inference pass per report.
    """
    model = _load_model()
    if model is None or vector is None:
        return None
    try:
        v = np.asarray(vector, dtype=np.float32)
        if v.shape[0] != model["coef"].shape[1]:
            return None
        logits = model["coef"] @ v + model["intercept"]
        exp = np.exp(logits - logits.max())
        probs = exp / exp.sum()
        scored = dict(zip(model["classes"], (round(float(p), 4) for p in probs)))
        # Keep the contract: every event type present, never exactly zero.
        return {et: scored.get(et, SCORE_FLOOR) for et in EVENT_TYPES}
    except Exception as exc:
        log.warning("classifier inference failed: %s", exc)
        return None


def predict_from_vector(vector) -> tuple[str, dict[str, float]] | None:
    scores = classify_vector(vector)
    if scores is None:
        return None
    return max(scores, key=scores.get), scores
