"""Phase 2.4 — public advisory text.

Turns a verified event into wording that can actually be published: what is
happening, where, how confident we are, and what people should do.

**Deliberately template-based, not model-generated.** A language model that
invents safety instructions in a disaster bulletin is a safety hazard, not a
feature. Every sentence here is fixed text with evidence-driven slots, so the
output is deterministic, auditable, and can be reviewed and signed off in
advance by the people whose name goes on it.

Safety guidance follows standard NDMA/IMD public advice for each hazard. It is
generic by design — a district officer edits before issuing.

Advisories are **computed on demand, never stored**. Derived data that is
written once goes stale the moment the event moves, which this codebase has
already been bitten by three times (warning levels, alerts, deliveries).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.db.models import Event, EventType, WarningLevel
from app.services.pipeline.warning import ACTION

# --- what is happening ------------------------------------------------------
SITUATION: dict[str, str] = {
    "RAIN": "Heavy rainfall is being reported",
    "FLOOD": "Waterlogging and flooding are being reported",
    "THUNDERSTORM": "Thunderstorm activity with lightning is being reported",
    "HEATWAVE": "Heatwave conditions are being reported",
    "FOG": "Dense fog with reduced visibility is being reported",
    "DUST_STORM": "A dust storm with reduced visibility is being reported",
    "STRONG_WIND": "Strong winds are being reported",
}

# --- what to expect ---------------------------------------------------------
EXPECT: dict[str, str] = {
    "RAIN": "Localised waterlogging, slow traffic and possible disruption to commuting.",
    "FLOOD": "Water entering low-lying areas, roads becoming impassable and vehicles stranded.",
    "THUNDERSTORM": "Lightning strikes, sudden gusts, and brief power interruptions.",
    "HEATWAVE": "High daytime temperatures with raised risk of heat exhaustion and heat stroke.",
    "FOG": "Sharply reduced visibility affecting road, rail and air travel, especially at dawn.",
    "DUST_STORM": "Poor visibility, airborne dust and deteriorating air quality.",
    "STRONG_WIND": "Falling hoardings and branches, and hazardous conditions at sea.",
}

# --- what to do (standard NDMA / IMD public guidance) -----------------------
SAFETY: dict[str, list[str]] = {
    "RAIN": [
        "Avoid low-lying and waterlogged areas.",
        "Do not shelter under trees or near electric poles.",
        "Allow extra travel time and drive slowly.",
    ],
    "FLOOD": [
        "Do not attempt to cross flooded roads, on foot or by vehicle.",
        "Move to higher ground if water is entering your premises.",
        "Switch off the mains supply before water reaches electrical fittings.",
        "Keep drinking water covered and use only safe or boiled water.",
    ],
    "THUNDERSTORM": [
        "Stay indoors and away from windows until the storm passes.",
        "Avoid open fields, isolated trees and water bodies.",
        "Unplug electrical appliances where possible.",
    ],
    "HEATWAVE": [
        "Avoid direct sun between 12 noon and 3 pm.",
        "Drink water frequently even if not thirsty; use ORS or lemon water.",
        "Check on elderly neighbours, outdoor workers and young children.",
        "Never leave children or pets in parked vehicles.",
    ],
    "FOG": [
        "Postpone non-essential travel during early morning hours.",
        "Use fog lights and maintain a wide gap from the vehicle ahead.",
        "Check flight and train status before leaving for the terminal.",
    ],
    "DUST_STORM": [
        "Stay indoors and keep windows closed.",
        "Cover your nose and mouth if you must go outside.",
        "Pull over safely and wait if visibility drops while driving.",
    ],
    "STRONG_WIND": [
        "Secure loose objects, hoardings and rooftop items.",
        "Keep clear of old trees, billboards and temporary structures.",
        "Fishermen should not venture out to sea.",
    ],
}

# --- Hindi, kept as fixed strings for the same reason -----------------------
SITUATION_HI: dict[str, str] = {
    "RAIN": "भारी वर्षा की सूचना मिल रही है",
    "FLOOD": "जलभराव और बाढ़ जैसी स्थिति की सूचना मिल रही है",
    "THUNDERSTORM": "गरज के साथ बिजली गिरने की सूचना मिल रही है",
    "HEATWAVE": "लू की स्थिति की सूचना मिल रही है",
    "FOG": "घने कोहरे और कम दृश्यता की सूचना मिल रही है",
    "DUST_STORM": "धूल भरी आँधी और कम दृश्यता की सूचना मिल रही है",
    "STRONG_WIND": "तेज़ हवाओं की सूचना मिल रही है",
}

ACTION_HI: dict[str, str] = {
    "GREEN": "कोई कार्रवाई आवश्यक नहीं",
    "YELLOW": "सतर्क रहें",
    "ORANGE": "तैयार रहें",
    "RED": "कार्रवाई करें",
}

CONFIDENCE_NOTE = {
    "high": "This advisory is supported by multiple independent sources.",
    "medium": "This advisory is based on partially corroborated reports.",
    "low": "This advisory is based on limited reports and is still being verified.",
}


@dataclass
class Advisory:
    level: WarningLevel
    action: str
    headline: str
    situation: str
    expect: str
    safety: list[str] = field(default_factory=list)
    confidence: str = "low"
    confidence_note: str = ""
    evidence_line: str = ""
    issued_at: str = ""
    validity_note: str = ""
    headline_hi: str = ""
    action_hi: str = ""
    disclaimer: str = ""

    def as_dict(self) -> dict:
        return {
            "level": self.level.value,
            "action": self.action,
            "headline": self.headline,
            "situation": self.situation,
            "expect": self.expect,
            "safety": self.safety,
            "confidence": self.confidence,
            "confidence_note": self.confidence_note,
            "evidence_line": self.evidence_line,
            "issued_at": self.issued_at,
            "validity_note": self.validity_note,
            "hindi": {"headline": self.headline_hi, "action": self.action_hi},
            "disclaimer": self.disclaimer,
        }

    def as_text(self) -> str:
        """Plain-text bulletin, ready to paste into a bulletin or message."""
        lines = [
            f"[{self.level.value}] {self.headline}",
            "",
            self.situation,
            "",
            f"WHAT TO EXPECT: {self.expect}",
            "",
            "WHAT TO DO:",
            *[f"  • {s}" for s in self.safety],
            "",
            f"CONFIDENCE: {self.confidence.upper()} — {self.confidence_note}",
            f"EVIDENCE: {self.evidence_line}",
            f"ISSUED: {self.issued_at}",
            self.validity_note,
            "",
            self.disclaimer,
        ]
        return "\n".join(lines)


def _place(event: Event) -> str:
    if event.district and event.state and event.district != event.state:
        return f"{event.district}, {event.state}"
    return event.district or event.state or "the affected area"


def _confidence(event: Event) -> str:
    """Confidence is about corroboration, not volume — a hundred copies of one
    claim is not stronger evidence than three independent ones."""
    if event.source_count >= 4 and event.evidence_score >= 0.6:
        return "high"
    if event.source_count >= 3 and event.evidence_score >= 0.45:
        return "medium"
    return "low"


def build(event: Event) -> Advisory:
    etype = event.event_type.value if isinstance(event.event_type, EventType) else str(event.event_type)
    level = event.warning_level
    place = _place(event)
    confidence = _confidence(event)

    flagged_note = ""
    if event.flagged_report_count and event.report_count:
        share = event.flagged_report_count / event.report_count
        if share >= 0.25:
            flagged_note = (
                f" {event.flagged_report_count} of {event.report_count} contributing "
                "reports are flagged for credibility review."
            )

    return Advisory(
        level=level,
        action=ACTION[level],
        headline=f"{SITUATION[etype].replace(' is being reported', '').replace(' are being reported', '')} — {place}",
        situation=f"{SITUATION[etype]} across {place}.",
        expect=EXPECT[etype],
        safety=SAFETY[etype],
        confidence=confidence,
        confidence_note=CONFIDENCE_NOTE[confidence] + flagged_note,
        evidence_line=(
            f"{event.report_count} reports from {event.source_count} independent sources; "
            f"reliability {event.evidence_score:.0%}, "
            f"observed-weather agreement {event.corroboration_score:.0%}."
        ),
        issued_at=datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC"),
        validity_note=(
            "Situation is being monitored continuously; this advisory reflects "
            "reports received up to the time of issue."
        ),
        headline_hi=f"{SITUATION_HI[etype]} — {place}",
        action_hi=ACTION_HI[level.value],
        disclaimer=(
            "Generated by NWAP from aggregated public and agency reports. "
            "Not an official IMD forecast. Review before public issue."
        ),
    )
