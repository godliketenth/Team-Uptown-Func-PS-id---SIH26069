"""Geocoding stub.

Prototype-scale: a static lookup table of major Indian cities. Swap the
`resolve_location` implementation for a real geocoder later; callers only
depend on the returned `GeoResolution`.
"""
from __future__ import annotations

import random
import logging
import re
from dataclasses import dataclass

log = logging.getLogger(__name__)

# name -> (lat, lon, district, state)
CITIES: dict[str, tuple[float, float, str, str]] = {
    "Mumbai": (19.0760, 72.8777, "Mumbai Suburban", "Maharashtra"),
    "Thane": (19.2183, 72.9781, "Thane", "Maharashtra"),
    "Navi Mumbai": (19.0330, 73.0297, "Thane", "Maharashtra"),
    "Pune": (18.5204, 73.8567, "Pune", "Maharashtra"),
    "Nagpur": (21.1458, 79.0882, "Nagpur", "Maharashtra"),
    "Nashik": (19.9975, 73.7898, "Nashik", "Maharashtra"),
    "Aurangabad": (19.8762, 75.3433, "Aurangabad", "Maharashtra"),
    "Delhi": (28.6139, 77.2090, "New Delhi", "Delhi"),
    "New Delhi": (28.6139, 77.2090, "New Delhi", "Delhi"),
    "Gurugram": (28.4595, 77.0266, "Gurugram", "Haryana"),
    "Noida": (28.5355, 77.3910, "Gautam Buddha Nagar", "Uttar Pradesh"),
    "Faridabad": (28.4089, 77.3178, "Faridabad", "Haryana"),
    "Ghaziabad": (28.6692, 77.4538, "Ghaziabad", "Uttar Pradesh"),
    "Chandigarh": (30.7333, 76.7794, "Chandigarh", "Chandigarh"),
    "Ludhiana": (30.9010, 75.8573, "Ludhiana", "Punjab"),
    "Amritsar": (31.6340, 74.8723, "Amritsar", "Punjab"),
    "Jaipur": (26.9124, 75.7873, "Jaipur", "Rajasthan"),
    "Jodhpur": (26.2389, 73.0243, "Jodhpur", "Rajasthan"),
    "Udaipur": (24.5854, 73.7125, "Udaipur", "Rajasthan"),
    "Bikaner": (28.0229, 73.3119, "Bikaner", "Rajasthan"),
    "Ahmedabad": (23.0225, 72.5714, "Ahmedabad", "Gujarat"),
    "Surat": (21.1702, 72.8311, "Surat", "Gujarat"),
    "Vadodara": (22.3072, 73.1812, "Vadodara", "Gujarat"),
    "Rajkot": (22.3039, 70.8022, "Rajkot", "Gujarat"),
    "Bhuj": (23.2419, 69.6669, "Kachchh", "Gujarat"),
    "Bhopal": (23.2599, 77.4126, "Bhopal", "Madhya Pradesh"),
    "Indore": (22.7196, 75.8577, "Indore", "Madhya Pradesh"),
    "Jabalpur": (23.1815, 79.9864, "Jabalpur", "Madhya Pradesh"),
    "Lucknow": (26.8467, 80.9462, "Lucknow", "Uttar Pradesh"),
    "Kanpur": (26.4499, 80.3319, "Kanpur Nagar", "Uttar Pradesh"),
    "Varanasi": (25.3176, 82.9739, "Varanasi", "Uttar Pradesh"),
    "Prayagraj": (25.4358, 81.8463, "Prayagraj", "Uttar Pradesh"),
    "Agra": (27.1767, 78.0081, "Agra", "Uttar Pradesh"),
    "Patna": (25.5941, 85.1376, "Patna", "Bihar"),
    "Gaya": (24.7955, 85.0002, "Gaya", "Bihar"),
    "Ranchi": (23.3441, 85.3096, "Ranchi", "Jharkhand"),
    "Kolkata": (22.5726, 88.3639, "Kolkata", "West Bengal"),
    "Howrah": (22.5958, 88.2636, "Howrah", "West Bengal"),
    "Siliguri": (26.7271, 88.3953, "Darjeeling", "West Bengal"),
    "Guwahati": (26.1445, 91.7362, "Kamrup Metropolitan", "Assam"),
    "Dibrugarh": (27.4728, 94.9120, "Dibrugarh", "Assam"),
    "Bhubaneswar": (20.2961, 85.8245, "Khordha", "Odisha"),
    "Cuttack": (20.4625, 85.8830, "Cuttack", "Odisha"),
    "Puri": (19.8135, 85.8312, "Puri", "Odisha"),
    "Visakhapatnam": (17.6868, 83.2185, "Visakhapatnam", "Andhra Pradesh"),
    "Vijayawada": (16.5062, 80.6480, "NTR", "Andhra Pradesh"),
    "Hyderabad": (17.3850, 78.4867, "Hyderabad", "Telangana"),
    "Warangal": (17.9689, 79.5941, "Warangal", "Telangana"),
    "Bengaluru": (12.9716, 77.5946, "Bengaluru Urban", "Karnataka"),
    "Mysuru": (12.2958, 76.6394, "Mysuru", "Karnataka"),
    "Mangaluru": (12.9141, 74.8560, "Dakshina Kannada", "Karnataka"),
    "Hubballi": (15.3647, 75.1240, "Dharwad", "Karnataka"),
    "Chennai": (13.0827, 80.2707, "Chennai", "Tamil Nadu"),
    "Coimbatore": (11.0168, 76.9558, "Coimbatore", "Tamil Nadu"),
    "Madurai": (9.9252, 78.1198, "Madurai", "Tamil Nadu"),
    "Tiruchirappalli": (10.7905, 78.7047, "Tiruchirappalli", "Tamil Nadu"),
    "Kochi": (9.9312, 76.2673, "Ernakulam", "Kerala"),
    "Thiruvananthapuram": (8.5241, 76.9366, "Thiruvananthapuram", "Kerala"),
    "Kozhikode": (11.2588, 75.7804, "Kozhikode", "Kerala"),
    "Srinagar": (34.0837, 74.7973, "Srinagar", "Jammu and Kashmir"),
    "Jammu": (32.7266, 74.8570, "Jammu", "Jammu and Kashmir"),
    "Shimla": (31.1048, 77.1734, "Shimla", "Himachal Pradesh"),
    "Dehradun": (30.3165, 78.0322, "Dehradun", "Uttarakhand"),
    "Raipur": (21.2514, 81.6296, "Raipur", "Chhattisgarh"),
    "Panaji": (15.4909, 73.8278, "North Goa", "Goa"),
}

# Devanagari / Gujarati aliases so non-English reports still geocode.
ALIASES: dict[str, str] = {
    "मुंबई": "Mumbai",
    "दिल्ली": "Delhi",
    "जयपुर": "Jaipur",
    "लखनऊ": "Lucknow",
    "पटना": "Patna",
    "भोपाल": "Bhopal",
    "कोलकाता": "Kolkata",
    "चेन्नई": "Chennai",
    "पुणे": "Pune",
    "અમદાવાદ": "Ahmedabad",
    "સુરત": "Surat",
    "રાજકોટ": "Rajkot",
    "વડોદરા": "Vadodara",
}

CITY_NAMES: list[str] = list(CITIES.keys())

# Cities that attract disproportionate reporting volume (keeps clusters dense).
HOT_CITIES: list[str] = [
    "Mumbai",
    "Delhi",
    "Chennai",
    "Kolkata",
    "Bengaluru",
    "Ahmedabad",
    "Guwahati",
    "Patna",
]

JITTER_DEGREES = 0.05

_MATCHERS: list[tuple[str, re.Pattern[str]]] = [
    (canonical, re.compile(rf"(?<![\w]){re.escape(name.lower())}(?![\w])"))
    for name, canonical in (
        [(c, c) for c in CITY_NAMES] + [(a, c) for a, c in ALIASES.items()]
    )
]
# Longer names first so "Navi Mumbai" wins over "Mumbai".
_MATCHERS.sort(key=lambda m: -len(m[1].pattern))


@dataclass
class GeoResolution:
    latitude: float | None
    longitude: float | None
    city: str | None
    district: str | None
    state: str | None
    confidence: float  # 1.0 GPS, 0.6 city-matched, 0.3 unresolved
    method: str


def city_record(city: str) -> tuple[float, float, str, str] | None:
    return CITIES.get(city)


def jitter(lat: float, lon: float, amount: float = JITTER_DEGREES) -> tuple[float, float]:
    """Spread co-located reports so they do not stack on a single pixel."""
    return (
        round(lat + random.uniform(-amount, amount), 6),
        round(lon + random.uniform(-amount, amount), 6),
    )


def match_city(text: str) -> str | None:
    lowered = text.lower()
    for canonical, pattern in _MATCHERS:
        if pattern.search(lowered):
            return canonical
    return None


# A town centroid is a place; a state centroid is the middle of an area the
# size of a country. The confidence says so, and the credibility layer and the
# map both read it.
_GAZETTEER_CONFIDENCE = {"town": 0.55, "district": 0.45, "state": 0.30}

# Gazetteer names that are ordinary English words or so generic that a bare
# match says nothing. Each of these was a real false positive on live
# headlines or an obvious hazard before it was one.
_GAZETTEER_STOPWORDS = {
    "india", "central", "union", "national", "high", "mall", "market",
    "north", "south", "east", "west", "city", "town", "district", "state",
    "river", "hills", "point", "fort", "road", "park", "garden", "colony",
    "nagar", "pur", "bazar", "bazaar", "sector", "line", "lines", "camp",
    "gola", "kot", "bank", "post", "well", "mile", "cross", "gate", "power",
}

_GAZETTEER: dict[str, dict] | None = None
_MAX_NAME_WORDS = 3


def _load_gazetteer() -> dict[str, dict]:
    """Lazy-loaded. Absent file is not an error — the platform falls back to
    the 65-city table, which is how it ran before this existed."""
    global _GAZETTEER
    if _GAZETTEER is None:
        import json
        from pathlib import Path

        path = Path(__file__).resolve().parents[3] / "data" / "gazetteer.json"
        try:
            _GAZETTEER = json.loads(path.read_text(encoding="utf-8"))
            log.info("gazetteer loaded: %s place names", len(_GAZETTEER))
        except Exception as exc:
            log.warning("gazetteer unavailable (%s); using the city table only", exc)
            _GAZETTEER = {}
    return _GAZETTEER


def gazetteer_match(text: str) -> tuple[str, dict] | None:
    """Longest place name mentioned in the text, most specific kind winning.

    Scans word n-grams rather than substrings: a substring search finds "Pune"
    inside "Punely" and "Goa" inside "Goat", which is how a geocoder ends up
    confidently placing an event in the wrong state.
    """
    gaz = _load_gazetteer()
    if not gaz:
        return None

    # Keep the original casing: an ambiguous name is only a place when it is
    # written as one.
    words = re.findall(r"[A-Za-z\u0900-\u097F]+", text)
    best: tuple[int, int, str, dict] | None = None
    specificity = {"town": 2, "district": 1, "state": 0}

    for size in range(1, _MAX_NAME_WORDS + 1):
        for i in range(len(words) - size + 1):
            raw_phrase = " ".join(words[i : i + size])
            phrase = raw_phrase.lower()
            if phrase in _GAZETTEER_STOPWORDS:
                continue
            rec = gaz.get(phrase)
            if rec is None:
                continue
            # "than" the conjunction vs "Than" the town in Gujarat. Every word
            # of the name must be capitalised for an ambiguous match to count.
            if rec.get("ambiguous") and not all(w[:1].isupper() for w in raw_phrase.split()):
                continue
            # More words is a stronger claim; then prefer the more specific
            # kind, since "Uttarkashi, Uttarakhand" should resolve to the
            # district rather than the state.
            rank = (size, specificity.get(rec["kind"], 0))
            if best is None or rank > (best[0], best[1]):
                best = (size, specificity.get(rec["kind"], 0), phrase.title(), rec)

    if best is None:
        return None
    return best[2], best[3]


def resolve_location(
    text: str,
    latitude: float | None = None,
    longitude: float | None = None,
    city_hint: str | None = None,
) -> GeoResolution:
    """GPS wins; otherwise substring-match a known city; otherwise unresolved."""
    if latitude is not None and longitude is not None:
        city = city_hint or match_city(text)
        rec = CITIES.get(city) if city else None
        return GeoResolution(
            latitude=float(latitude),
            longitude=float(longitude),
            city=city,
            district=rec[2] if rec else None,
            state=rec[3] if rec else None,
            confidence=1.0,
            method="gps",
        )

    city = city_hint if city_hint in CITIES else match_city(text)
    if city:
        lat, lon, district, state = CITIES[city]
        jlat, jlon = jitter(lat, lon)
        return GeoResolution(jlat, jlon, city, district, state, 0.6, "city_match")

    hit = gazetteer_match(text)
    if hit:
        name, rec = hit
        # No jitter here. The 65-city table jitters to spread synthetic
        # reports around a metro; a gazetteer hit is a real claim about a real
        # place, and a district or state centroid is already coarse enough
        # without adding noise to it.
        return GeoResolution(
            latitude=rec["lat"],
            longitude=rec["lon"],
            city=name if rec["kind"] == "town" else None,
            district=rec["district"],
            state=rec["state"],
            confidence=_GAZETTEER_CONFIDENCE[rec["kind"]],
            method=f"gazetteer_{rec['kind']}",
        )

    return GeoResolution(None, None, None, None, None, 0.3, "unresolved")
