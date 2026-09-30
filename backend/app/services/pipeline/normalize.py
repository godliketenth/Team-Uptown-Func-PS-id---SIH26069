"""Stage 1: normalize raw text into a comparable form and pull out metadata.

Hashtags are first-class here: the platform is specified to track #IMD and
other weather hashtags, so they are extracted, canonicalised and persisted
rather than merely stripped.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
HASHTAG_RE = re.compile(r"#(\w+)", re.UNICODE)
MENTION_RE = re.compile(r"@(\w+)", re.UNICODE)
WHITESPACE_RE = re.compile(r"\s+")

DEVANAGARI = range(0x0900, 0x0980)
GUJARATI = range(0x0A80, 0x0B00)
BENGALI = range(0x0980, 0x0A00)
TAMIL = range(0x0B80, 0x0C00)

# Hashtags the platform actively tracks. A post carrying one of these is a
# weather signal by declaration, independent of what the classifier makes of
# the wording.
TRACKED_HASHTAGS: set[str] = {
    "imd",
    "imdweather",
    "weather",
    "weatherupdate",
    "weatheralert",
    "rain",
    "rains",
    "rainfall",
    "monsoon",
    "flood",
    "flooding",
    "waterlogging",
    "thunderstorm",
    "lightning",
    "heatwave",
    "fog",
    "duststorm",
    "cyclone",
    "imdalert",
    "ndma",
    "mausam",
}


@dataclass
class Normalized:
    normalized_text: str
    language: str
    text_hash: str = ""
    urls: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)

    @property
    def tracked_hashtags(self) -> list[str]:
        return [h for h in self.hashtags if h in TRACKED_HASHTAGS]


def detect_language(text: str) -> str:
    """Script-range detection is enough at prototype scale."""
    for ch in text:
        cp = ord(ch)
        if cp in DEVANAGARI:
            return "hi"
        if cp in GUJARATI:
            return "gu"
        if cp in BENGALI:
            return "bn"
        if cp in TAMIL:
            return "ta"
    return "en"


def extract_hashtags(text: str) -> list[str]:
    """Lowercased, de-duplicated, order preserved. `#IMD` and `#imd` are one tag."""
    seen: list[str] = []
    for raw in HASHTAG_RE.findall(text or ""):
        tag = raw.lower()
        if tag not in seen:
            seen.append(tag)
    return seen


def normalize(raw_text: str) -> Normalized:
    text = raw_text or ""
    urls = URL_RE.findall(text)
    hashtags = extract_hashtags(text)
    mentions = [m.lower() for m in MENTION_RE.findall(text)]

    # Markers are removed for comparison, but the words they wrapped stay -
    # "#MumbaiRains" should still read as rain signal to the classifier.
    stripped = URL_RE.sub(" ", text)
    stripped = HASHTAG_RE.sub(r"\1", stripped)
    stripped = MENTION_RE.sub(r"\1", stripped)
    stripped = WHITESPACE_RE.sub(" ", stripped).strip().lower()

    return Normalized(
        normalized_text=stripped,
        language=detect_language(text),
        text_hash=hashlib.sha256(stripped.encode("utf-8")).hexdigest(),
        urls=urls,
        hashtags=hashtags,
        mentions=mentions,
    )
