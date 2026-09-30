"""Regression tests: one per bug this project actually shipped and fixed.

Every test here failed at some point against real code. They are written from
the measurement that exposed the bug, not from the fix, so they would catch a
reintroduction rather than merely re-describing the current implementation.
"""
from __future__ import annotations

import random
from pathlib import Path
from unittest import mock

import pytest

from app.db.models import SourceType

# The gazetteer is committed, but a developer working from a partial checkout
# should get a clear skip rather than a confusing failure.
_GAZETTEER = Path(__file__).resolve().parents[1] / "data" / "gazetteer.json"
needs_gazetteer = pytest.mark.skipif(
    not _GAZETTEER.exists(),
    reason="data/gazetteer.json missing — run build_gazetteer.py",
)


# --------------------------------------------------------------------------
# The generator's diurnal weighting silently did nothing.
#
# `random.choices` renormalises weights within each region's candidate list, so
# a region whose hazards are all daytime hazards still emitted them uniformly
# at night. Measured before the fix: heatwaves at 01:00 as often as at noon,
# a flat hazard mix across all 24 hours, which made the preparedness
# hour-of-day chart pure noise.
# --------------------------------------------------------------------------
def _mix(city: str, hour: int, n: int = 3000) -> dict[str, float]:
    from app.services.ingestion import generator as g

    random.seed(20260929)
    with mock.patch.object(g, "_ist_hour", lambda: hour):
        counts: dict[str, int] = {}
        for _ in range(n):
            t = g._pick_event_type(city)
            counts[t] = counts.get(t, 0) + 1
    return {k: v / n for k, v in counts.items()}


def test_heatwave_is_rare_at_night_and_common_at_midday():
    night = _mix("Jaipur", 1).get("HEATWAVE", 0.0)
    midday = _mix("Jaipur", 13).get("HEATWAVE", 0.0)
    assert midday > night * 3, (
        f"diurnal weighting is not reaching the output: heatwave {night:.0%} at 01:00 "
        f"vs {midday:.0%} at 13:00"
    )


def test_fog_peaks_in_the_early_morning():
    dawn = _mix("Delhi", 5).get("FOG", 0.0)
    afternoon = _mix("Delhi", 14).get("FOG", 0.0)
    assert dawn > afternoon * 3, f"fog {dawn:.0%} at 05:00 vs {afternoon:.0%} at 14:00"


# --------------------------------------------------------------------------
# "Floods kill more than 100 in Thailand and India" geocoded to Than, Gujarat.
#
# 121 of 8,138 place names are also English words. Excluding them all would
# have deleted Agra, Assam, Amritsar and Darjeeling, so they are marked at
# build time and require capitalisation instead.
# --------------------------------------------------------------------------
@needs_gazetteer
def test_english_word_lowercase_is_not_a_place():
    from app.services.pipeline.geo import gazetteer_match

    assert gazetteer_match("Floods kill more than 100 in Thailand and India") is None
    assert gazetteer_match("the delay was longer than expected") is None


@needs_gazetteer
def test_ambiguous_name_still_resolves_when_capitalised():
    from app.services.pipeline.geo import resolve_location

    for text, expected in (
        ("Heavy rain warning issued for Agra", "Agra"),
        ("Landslide risk across Darjeeling district", "Darjeeling"),
        ("Assam floods displace thousands", "Assam"),
    ):
        g = resolve_location(text)
        found = (g.city, g.district, g.state)
        assert expected in found, f"{expected!r} not resolved from {text!r}: {found}"


@needs_gazetteer
def test_unambiguous_name_resolves_even_lowercase():
    """Social posts are not capitalised; the rule must not cost us those."""
    from app.services.pipeline.geo import resolve_location

    g = resolve_location("flooding near uttarkashi overnight")
    assert g.district == "Uttarkashi"


@needs_gazetteer
def test_gazetteer_prefers_the_more_specific_place():
    from app.services.pipeline.geo import resolve_location

    g = resolve_location("Heavy rain lashes Uttarkashi in Uttarakhand overnight")
    assert g.district == "Uttarkashi" and g.state == "Uttarakhand"


@needs_gazetteer
def test_generic_text_resolves_to_nothing():
    from app.services.pipeline.geo import gazetteer_match

    for text in (
        "anyone know when the power comes back",
        "my order still has not arrived",
        "great weather for a walk honestly",
    ):
        assert gazetteer_match(text) is None, text


# --------------------------------------------------------------------------
# Real IMD-sourced journalism scored 0.80 misinformation risk.
#
# A state match places a report at a centroid — for Rajasthan, one point in an
# area the size of Germany. "Rainfall activity to decline in Rajasthan" was
# called contradicted because it was not raining at that point, which is
# exactly what the headline said.
# --------------------------------------------------------------------------
CONTRADICTING = {"status": "ok", "contradicted": True, "support": 0.0}


def _assess(confidence: float):
    from app.services.pipeline.credibility import assess

    return assess(
        source_type=SourceType.WEB_RSS,
        corroboration=CONTRADICTING,
        event_type_scores={"RAIN": 0.8},
        nearby_independent_reports=0,
        location_confidence=confidence,
        text="Rainfall activity to decline in Rajasthan, Met predicts",
    )


def _codes(assessment) -> set[str]:
    return {f["code"] if isinstance(f, dict) else f for f in assessment.flags}


def test_state_centroid_cannot_contradict_an_observation():
    a = _assess(0.30)
    assert "CONTRADICTED_BY_OBSERVATION" not in _codes(a)
    assert not a.needs_review, "real journalism must not land in the review queue"


def test_a_precise_location_still_contradicts():
    """The fix must not disable the flag wholesale."""
    assert "CONTRADICTED_BY_OBSERVATION" in _codes(_assess(0.60))
    assert "CONTRADICTED_BY_OBSERVATION" in _codes(_assess(0.45))


# --------------------------------------------------------------------------
# A cricket fixture would have created a phantom rain event.
#
# "Chances of rain in Guwahati for IND vs WI 2nd ODI" classified as RAIN at
# 0.98 confidence and geocoded to a real city. Nothing downstream can catch
# that — it genuinely is a statement about rain — so the gate is at the source.
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "headline,keep",
    [
        ("IMD issues red alert for very heavy rainfall in Uttarakhand", True),
        ("High alert in Uttarkashi after IMD rain warning", True),
        ("India Weather Update: Heavy Rain, Floods And Landslides Hit Several States", True),
        ("Karnataka Weather Turns Monsoon-Like IMD Issues 7-Day Heavy Rain Forecast", True),
        ("Chances of rain in Guwahati on Wednesday: forecast for IND vs WI 2nd ODI", False),
        ("India-Pakistan Asian Games final? Japan's rain could set it up", False),
        ("Extreme weather raises temperature on Chennai home search", False),
    ],
)
def test_news_relevance_gate(headline: str, keep: bool):
    from app.services.ingestion.connectors import NewsRssConnector

    assert NewsRssConnector()._is_weather(headline) is keep, headline


# --------------------------------------------------------------------------
# NO_WEATHER_SIGNAL fired 0 times in 90 minutes after a refactor.
#
# The flag had been detecting off-topic text via a flat classifier
# distribution, but softmax has no "none of the above": "anyone know when the
# power comes back" scored THUNDERSTORM at 98%.
# --------------------------------------------------------------------------
def test_off_topic_text_is_recognised_as_having_no_weather_signal():
    from app.services.pipeline.classify import has_weather_signal

    assert has_weather_signal("Heavy rain and waterlogging near the station") is True
    assert has_weather_signal("anyone know when the power comes back") is False


# --------------------------------------------------------------------------
# Absence of corroboration is not evidence of falsehood, and must not cap the
# warning level. Only an actively opposing reading counts.
# --------------------------------------------------------------------------
def test_low_corroboration_does_not_cap_the_warning_level():
    from app.services.pipeline.warning import assess

    strong = dict(
        status="VERIFIED",
        report_count=40,
        source_count=5,
        evidence_score=0.75,
        flagged_report_count=0,
    )
    with_support = assess(corroboration_score=0.9, **strong)
    without_support = assess(corroboration_score=0.0, **strong)
    assert without_support.level == with_support.level, (
        "missing corroboration silently downgraded the warning; absence of support "
        "is not contradiction"
    )
