"""Synthetic source simulator.

Stands in for live social / citizen / government feeds, which the prototype
has no production access to. Every downstream stage (dedup, classification,
clustering, severity escalation) is exercised by what this produces.
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.db.models import SourceType
from app.services.pipeline.geo import CITIES, CITY_NAMES, HOT_CITIES, jitter

# Relative volume *within a single poll*. Overall cadence is no longer encoded
# here - the scheduler's poll intervals own that - so these describe how chatty
# each feed is when it does run, not how often it runs.
SOURCE_WEIGHTS: list[tuple[SourceType, float]] = [
    (SourceType.CITIZEN, 0.40),
    (SourceType.SOCIAL, 0.30),
    (SourceType.WEATHER_API, 0.15),
    (SourceType.GOVERNMENT, 0.10),
    (SourceType.WEB_RSS, 0.05),
]

TEMPLATES: dict[str, list[str]] = {
    "RAIN": [
        "Heavy rain reported near {city}",
        "Continuous rainfall since morning in {city}, roads are slippery",
        "{city} receiving intense showers, IMD nowcast active",
        "Moderate to heavy rain lashing parts of {city}",
        "Rainfall intensity picking up across {city} outskirts",
        "Sudden downpour in central {city}, traffic slowing down",
    ],
    "FLOOD": [
        "{city} experiencing waterlogging on main road",
        "Severe waterlogging near {city} bus depot, knee deep water",
        "Low lying areas of {city} inundated after overnight rain",
        "Drains overflowing in {city}, water entering shops",
        "Flood-like situation reported from {city} riverfront",
        "Underpass submerged in {city}, vehicles stranded",
    ],
    "THUNDERSTORM": [
        "Loud thunder and lightning over {city} right now",
        "Thunderstorm with gusty winds approaching {city}",
        "Frequent lightning strikes reported around {city}",
        "Hailstorm briefly hit the {city} region",
        "Squally thunderstorm warning issued for {city}",
        "Sky darkened over {city}, thunder audible from the east",
        "Lightning activity intensifying north of {city}",
    ],
    "HEATWAVE": [
        "Scorching heat in {city}, temperature well above normal",
        "Heatwave conditions persist over {city} for third day",
        "{city} sweltering, heat stroke advisory issued",
        "Severe heat wave alert for {city} district",
        "Day temperature soaring in {city}, avoid afternoon travel",
    ],
    "FOG": [
        "Visibility dropping due to fog in {city}",
        "Dense fog blanket over {city}, flights delayed",
        "Morning mist reducing visibility near {city} highway",
        "Shallow fog reported across {city} early hours",
        "Smog and fog mix cutting visibility in {city}",
        "Fog layer persisting past sunrise in {city}",
    ],
    "DUST_STORM": [
        "Dust storm sweeping through {city} outskirts",
        "Strong dust haze reducing visibility in {city}",
        "Sudden dust storm hit {city} before rainfall",
        "Blowing dust reported across {city} region",
        "Thick dust cloud rolling in towards {city}",
        "Air quality dropping sharply in {city} amid blowing dust",
    ],
    "STRONG_WIND": [
        "Strong wind gusts recorded at {city} observatory",
        "Gusty winds uprooting hoardings in {city}",
        "High winds along the {city} coast, advisory for fishermen",
        "Wind speed crossing 45 kmph near {city}",
        "Trees swaying heavily in {city}, loose debris on roads",
        "Sustained strong winds reported west of {city}",
    ],
}

# Non-English templates so language detection has genuine input.
TEMPLATES_HI: dict[str, list[str]] = {
    "RAIN": ["{city} में भारी बारिश हो रही है", "{city} में तेज बारिश, सड़कों पर पानी"],
    "FLOOD": ["{city} में जलभराव की स्थिति", "{city} के निचले इलाकों में बाढ़ जैसे हालात"],
    "THUNDERSTORM": ["{city} में गरज के साथ बिजली चमक रही है"],
    "HEATWAVE": ["{city} में भीषण गर्मी और लू चल रही है"],
    "FOG": ["{city} में घना कोहरा, दृश्यता कम"],
    "DUST_STORM": ["{city} में आंधी और धूल का गुबार"],
    "STRONG_WIND": ["{city} में तेज हवा चल रही है"],
}

TEMPLATES_GU: dict[str, list[str]] = {
    "RAIN": ["{city} માં ભારે વરસાદ પડી રહ્યો છે"],
    "FLOOD": ["{city} માં પૂર જેવી સ્થિતિ, પાણી ભરાયું"],
    "HEATWAVE": ["{city} માં આકરી ગરમી"],
    "FOG": ["{city} માં ધુમ્મસ છવાયું"],
}

GUJARAT_CITIES = ["Ahmedabad", "Surat", "Vadodara", "Rajkot", "Bhuj"]

# Event types that are plausible for a given region, so the map does not show
# a heatwave in Srinagar next to fog in Chennai.
# Hour-of-day weighting (IST). Real weather reporting has strong diurnal
# structure — fog at dawn, heat at midday, convective storms late afternoon —
# and without it any time-of-day analysis is noise dressed up as insight.
#
# We bias *which event type is generated now* rather than backdating
# timestamps, because reports must stay recent for clustering to work.
DIURNAL_WEIGHT: dict[str, list[float]] = {
    #          0    1    2    3    4    5    6    7    8    9   10   11
    #         12   13   14   15   16   17   18   19   20   21   22   23
    "FOG": [1.2, 1.4, 1.6, 1.8, 2.4, 3.0, 3.0, 2.4, 1.4, 0.6, 0.3, 0.2,
            0.2, 0.2, 0.2, 0.2, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0, 1.1, 1.2],
    "HEATWAVE": [0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.3, 0.5, 0.9, 1.5, 2.2, 2.8,
                 3.0, 3.0, 2.8, 2.4, 1.8, 1.2, 0.7, 0.4, 0.3, 0.2, 0.2, 0.2],
    "THUNDERSTORM": [0.4, 0.3, 0.3, 0.3, 0.3, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0,
                     1.3, 1.7, 2.2, 2.8, 3.0, 2.9, 2.5, 1.9, 1.4, 1.0, 0.7, 0.5],
    "RAIN": [0.7, 0.6, 0.6, 0.6, 0.7, 0.8, 0.9, 1.0, 1.0, 1.0, 1.0, 1.1,
             1.2, 1.4, 1.6, 1.8, 1.9, 1.8, 1.6, 1.4, 1.2, 1.0, 0.9, 0.8],
    # Flooding lags the rain that causes it.
    "FLOOD": [0.6, 0.5, 0.5, 0.5, 0.5, 0.6, 0.7, 0.9, 1.0, 1.0, 1.0, 1.0,
              1.1, 1.2, 1.4, 1.7, 2.0, 2.2, 2.2, 2.0, 1.6, 1.2, 0.9, 0.7],
    "DUST_STORM": [0.2, 0.2, 0.2, 0.2, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.3,
                   1.7, 2.2, 2.7, 3.0, 2.8, 2.3, 1.6, 1.0, 0.6, 0.4, 0.3, 0.2],
    "STRONG_WIND": [0.5, 0.4, 0.4, 0.4, 0.4, 0.5, 0.6, 0.7, 0.9, 1.1, 1.3, 1.6,
                    1.9, 2.2, 2.4, 2.4, 2.2, 1.9, 1.5, 1.1, 0.9, 0.7, 0.6, 0.5],
}

# The largest value appearing in DIURNAL_WEIGHT; an absolute acceptance
# probability is measured against this so a weight of 3.0 always passes.
DIURNAL_MAX = 3.0

REGIONAL_BIAS: dict[str, list[str]] = {
    "Rajasthan": ["HEATWAVE", "DUST_STORM", "STRONG_WIND", "RAIN"],
    "Delhi": ["FOG", "HEATWAVE", "DUST_STORM", "RAIN", "THUNDERSTORM"],
    "Maharashtra": ["RAIN", "FLOOD", "THUNDERSTORM", "STRONG_WIND"],
    "Kerala": ["RAIN", "FLOOD", "THUNDERSTORM"],
    "Assam": ["RAIN", "FLOOD", "THUNDERSTORM"],
    "West Bengal": ["RAIN", "FLOOD", "THUNDERSTORM", "FOG"],
    "Tamil Nadu": ["RAIN", "FLOOD", "THUNDERSTORM", "HEATWAVE"],
    "Punjab": ["FOG", "RAIN", "STRONG_WIND"],
    "Uttar Pradesh": ["FOG", "HEATWAVE", "RAIN", "THUNDERSTORM"],
    "Bihar": ["FLOOD", "RAIN", "HEATWAVE", "FOG"],
    "Gujarat": ["HEATWAVE", "RAIN", "FLOOD", "DUST_STORM"],
}
DEFAULT_TYPES = ["RAIN", "FLOOD", "THUNDERSTORM", "FOG", "STRONG_WIND", "HEATWAVE"]

# Weather hashtags the platform is specified to track. #IMD rides along with
# most weather chatter; the rest vary by event type and city.
BASE_HASHTAGS = ["IMD", "Weather", "WeatherUpdate", "Mausam"]

EVENT_HASHTAGS: dict[str, list[str]] = {
    "RAIN": ["Rain", "Rainfall", "Monsoon", "RainAlert"],
    "FLOOD": ["Flood", "Waterlogging", "Flooding", "FloodAlert"],
    "THUNDERSTORM": ["Thunderstorm", "Lightning", "StormAlert"],
    "HEATWAVE": ["HeatWave", "Heat", "HeatAlert"],
    "FOG": ["Fog", "LowVisibility", "FogAlert"],
    "DUST_STORM": ["DustStorm", "Andhi", "DustAlert"],
    "STRONG_WIND": ["StrongWinds", "GustyWinds", "WindAlert"],
}

SOCIAL_HANDLES = [
    "@citywatch", "@monsoonupdates", "@roadalertsindia", "@weatherwatcher",
    "@localnews24", "@commuterdiary",
]
GOV_PREFIXES = ["IMD BULLETIN:", "NDMA ADVISORY:", "STATE EOC:", "CWC NOTICE:"]
RSS_PREFIXES = ["[Newswire]", "[RegionalDaily]", "[PressTrust]"]

MEDIA_POOL = [
    {"url": "https://cdn.example.org/media/street_flood_01.jpg", "type": "image"},
    {"url": "https://cdn.example.org/media/sky_storm_02.jpg", "type": "image"},
    {"url": "https://cdn.example.org/media/fog_highway_03.jpg", "type": "image"},
    {"url": "https://cdn.example.org/media/clip_rain_04.mp4", "type": "video"},
]

DUPLICATE_CHANCE = 0.10
BURST_CHANCE = 0.15
BURST_SIZE = (6, 12)
GPS_CHANCE = 0.35
MEDIA_CHANCE = 0.25
NOISE_CHANCE = 0.08  # off-topic chatter; exercises relevance detection


@dataclass
class GeneratedItem:
    source_type: SourceType
    external_id: str
    collected_at: datetime
    payload: dict
    # When set, the item is attributed to this exact source row rather than
    # spread across the due sources of its type. A real feed must not be
    # credited to a simulated one — the whole value of a live source is that
    # you can point at it and say which rows came from outside this project.
    source_name: str | None = None


@dataclass
class GeneratorState:
    """Keeps a short memory of what was emitted so duplicates and bursts can
    reference real recent content."""

    recent: list[dict] = field(default_factory=list)
    burst: dict | None = None
    burst_remaining: int = 0
    ticks: int = 0

    def remember(self, payload: dict) -> None:
        self.recent.append(payload)
        if len(self.recent) > 40:
            self.recent.pop(0)


STATE = GeneratorState()


# The stub stands in for the person-driven feeds only; WEATHER_API and
# SATELLITE have their own real connectors.
SIMULATED_SOURCES = {
    SourceType.CITIZEN,
    SourceType.SOCIAL,
    SourceType.GOVERNMENT,
    SourceType.WEB_RSS,
}


def _weighted_source(allowed: set[SourceType] | None = None) -> SourceType:
    pool = [
        (st, w)
        for st, w in SOURCE_WEIGHTS
        if st in SIMULATED_SOURCES and (allowed is None or st in allowed)
    ]
    if not pool:
        return SourceType.CITIZEN
    total = sum(w for _, w in pool)
    roll = random.random() * total
    cumulative = 0.0
    for source_type, weight in pool:
        cumulative += weight
        if roll <= cumulative:
            return source_type
    return pool[-1][0]


def _pick_city() -> str:
    return random.choice(HOT_CITIES) if random.random() < 0.55 else random.choice(CITY_NAMES)


# Probability that a report describes the weather actually observed at that
# city right now. The remainder are genuinely unsupported claims - which is
# exactly what the credibility stage exists to surface.
OBSERVED_BIAS = 0.75


def _ist_hour() -> int:
    """Current hour in IST — the timezone the reporting population lives in."""
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).hour


def _pick_event_type(city: str, hints: dict[str, str] | None = None) -> str:
    # Real observed weather still wins when we have a reading for this city.
    if hints and city in hints and random.random() < OBSERVED_BIAS:
        return hints[city]

    state = CITIES[city][3]
    candidates = REGIONAL_BIAS.get(state, DEFAULT_TYPES)
    hour = _ist_hour()
    weights = [DIURNAL_WEIGHT.get(t, [1.0] * 24)[hour] for t in candidates]
    if sum(weights) <= 0:
        return random.choice(candidates)

    # `random.choices` renormalises within `candidates`, which destroys the
    # diurnal signal for any region whose hazards are *all* daytime hazards:
    # a Rajasthan city choosing between HEATWAVE (0.2 at 01:00) and DUST_STORM
    # (0.2 at 01:00) still picks one of them every time, so heatwaves appeared
    # at 1am as often as at noon. Measured: hazard mix was flat across all 24
    # hours, which made the preparedness hour-of-day chart pure noise.
    #
    # Accepting against the *absolute* weight fixes that — a hazard implausible
    # at this hour is usually rejected, and the fallback is the candidate the
    # clock actually favours rather than a uniform draw.
    # A few rejection rounds, then accept the weighted draw. A deterministic
    # fallback would funnel every rejection into a single hazard (measured:
    # 94% RAIN at 01:00), which trades one unrealistic distribution for
    # another. Bounded retries skew the mix toward what the clock supports
    # while leaving the tail intact — unusual hours stay possible, just rare.
    for _ in range(3):
        picked = random.choices(candidates, weights=weights, k=1)[0]
        if random.random() < DIURNAL_WEIGHT.get(picked, [1.0] * 24)[hour] / DIURNAL_MAX:
            return picked
    return random.choices(candidates, weights=weights, k=1)[0]


def _compose_text(city: str, event_type: str, template: str | None = None) -> str:
    if template is not None:
        return template.format(city=city)
    if city in GUJARAT_CITIES and event_type in TEMPLATES_GU and random.random() < 0.30:
        return random.choice(TEMPLATES_GU[event_type]).format(city=city)
    if event_type in TEMPLATES_HI and random.random() < 0.18:
        return random.choice(TEMPLATES_HI[event_type]).format(city=city)
    return random.choice(TEMPLATES[event_type]).format(city=city)


def _hashtags_for(city: str, event_type: str, source_type: SourceType) -> list[str]:
    """Social posts are hashtag-heavy; official bulletins carry one or two."""
    tags: list[str] = []
    if source_type in (SourceType.SOCIAL, SourceType.CITIZEN):
        tags.append("IMD")
        tags.extend(random.sample(EVENT_HASHTAGS[event_type], k=random.randint(1, 2)))
        if random.random() < 0.55:
            # City tags like #MumbaiRains are how these actually trend.
            city_tag = city.replace(" ", "")
            suffix = {"RAIN": "Rains", "FLOOD": "Floods", "HEATWAVE": "Heat"}.get(event_type, "")
            tags.append(f"{city_tag}{suffix}")
        if random.random() < 0.3:
            tags.append(random.choice(BASE_HASHTAGS))
    elif source_type in (SourceType.GOVERNMENT, SourceType.WEB_RSS):
        tags.append("IMD")
        if random.random() < 0.5:
            tags.append(random.choice(EVENT_HASHTAGS[event_type]))

    seen: list[str] = []
    for t in tags:
        if t.lower() not in {x.lower() for x in seen}:
            seen.append(t)
    return seen


def _decorate(text: str, source_type: SourceType, hashtags: list[str]) -> str:
    tag_str = " ".join(f"#{t}" for t in hashtags)
    if source_type == SourceType.SOCIAL:
        body = f"{text} {random.choice(SOCIAL_HANDLES)}"
        if tag_str:
            body = f"{body} {tag_str}"
        if random.random() < 0.4:
            body = f"{body} https://t.co/{uuid.uuid4().hex[:8]}"
        return body
    if source_type == SourceType.GOVERNMENT:
        return f"{random.choice(GOV_PREFIXES)} {text}" + (f" {tag_str}" if tag_str else "")
    if source_type == SourceType.WEB_RSS:
        return f"{random.choice(RSS_PREFIXES)} {text}" + (f" {tag_str}" if tag_str else "")
    return f"{text} {tag_str}".strip() if tag_str else text


def _build_payload(
    city: str, event_type: str, source_type: SourceType, template: str | None = None
) -> dict:
    hashtags = _hashtags_for(city, event_type, source_type)
    text = _decorate(_compose_text(city, event_type, template), source_type, hashtags)
    lat, lon, district, state = CITIES[city]
    payload: dict = {
        "text": text,
        "city_hint": city,
        "intended_event_type": event_type,  # ground truth, for demo comparison only
        "author": _author_for(source_type),
        "observed_at": _recent_timestamp().isoformat(),
    }
    if source_type in (SourceType.WEATHER_API, SourceType.GOVERNMENT) or random.random() < GPS_CHANCE:
        jlat, jlon = jitter(lat, lon)
        payload["latitude"] = jlat
        payload["longitude"] = jlon
    if random.random() < MEDIA_CHANCE:
        payload["media"] = [random.choice(MEDIA_POOL)]
    return payload


CITIZEN_HANDLES = ["rk_sharma", "meena.p", "arjun_t", "s_iyer", "d_banerjee", "nfaruqui"]
GOV_DESKS = ["imd_rmc_desk", "ndma_ops", "state_eoc", "cwc_monitoring"]
RSS_DESKS = ["newswire_desk", "regionaldaily_desk", "presstrust_desk"]


def _author_for(source_type: SourceType) -> str | None:
    """An attributable author is what makes 'verify untrusted sources' possible."""
    if source_type == SourceType.SOCIAL:
        return random.choice(SOCIAL_HANDLES)
    if source_type == SourceType.CITIZEN:
        return random.choice(CITIZEN_HANDLES)
    if source_type == SourceType.GOVERNMENT:
        return random.choice(GOV_DESKS)
    if source_type == SourceType.WEB_RSS:
        return random.choice(RSS_DESKS)
    return None


def _recent_timestamp() -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=random.randint(0, 240))


# Off-topic chatter that shares a timeline with weather reports. A real social
# stream is enormously varied here; four fixed sentences made the credibility
# task trivially memorisable rather than learnable.
#
# The last block is deliberately held out of training (see training/
# train_credibility.py) so generalisation can be measured on phrasing the model
# has never seen.
NOISE_POOL: list[str] = [
    # transport / civic
    "Traffic moving slowly on the ring road today",
    "Metro line 2 running late again this morning",
    "Anyone know when the power comes back?",
    "Water supply has been off since yesterday in our block",
    "Garbage collection skipped our lane for the third day",
    "Road digging work started outside the school gate",
    "Bus frequency has dropped a lot on this route",
    "Streetlight near the junction still not repaired",
    # everyday life
    "Market closed early, no idea why",
    "Great weather for a walk honestly",
    "Finally got my driving licence renewed today",
    "The new cafe near the station is quite good",
    "Cricket match tickets sold out in ten minutes",
    "Exam results are out, all the best everyone",
    "Anyone recommend a good dentist nearby?",
    "Lost my earphones somewhere near the mall",
    # civic complaints unrelated to weather
    "Network has been terrible all week on this operator",
    "Bank branch was shut without any notice",
    "Parking charges near the market have doubled",
    "Stray dogs issue in the colony is getting worse",
    # Hinglish / romanised
    "Aaj office jaldi nikalna padega, meeting hai",
    "Bhai koi accha mechanic jaanta hai idhar",
    "Kal ka match dekha kya, zabardast tha",
    "Bijli ka bill is baar bahut zyada aaya hai",
    # native script, still off-topic
    "आज बाज़ार में बहुत भीड़ थी",
    "नई सड़क का काम कब पूरा होगा",
    "કાલે રજા છે કે નહીં કોઈને ખબર છે",
    # vague or content-free posts
    "Not sure what is happening here",
    "Can someone please confirm this",
    "Sharing for wider reach",
    "This is getting out of hand now",
    "Why is nobody talking about this",
]

# Held out of the credibility training set to test generalisation honestly.
NOISE_HOLDOUT: list[str] = [
    "Ticket counter queue is moving very slowly today",
    "Does anyone have the new timetable for this route",
    "Shop shutters are down, seems like a strike",
    "My package has been stuck at the sorting facility",
    "Koi batao yeh form kahan jama karna hai",
    "पानी का कनेक्शन अब तक नहीं लगा है",
]


def _noise_payload() -> dict:
    # 15% drawn from the held-out pool so live data exercises it too.
    pool = NOISE_HOLDOUT if random.random() < 0.15 else NOISE_POOL
    return {
        "text": random.choice(pool),
        "city_hint": None,
        "intended_event_type": None,
        # Explicit marker. Relying on a missing intended_event_type silently
        # swept in satellite and weather-API observations, which are the most
        # trustworthy sources we have — the exact opposite of noise.
        "is_noise": True,
        "observed_at": _recent_timestamp().isoformat(),
    }


def _near_duplicate(payload: dict) -> dict:
    clone = dict(payload)
    text = clone["text"]
    if random.random() < 0.5:
        clone["text"] = text  # literal duplicate
        clone["_dup_kind"] = "exact"
    else:
        suffix = random.choice(["!", " ...", " please help", " #alert", " (unconfirmed)"])
        clone["text"] = text + suffix
        clone["_dup_kind"] = "near"
    clone["observed_at"] = _recent_timestamp().isoformat()
    return clone


def generate_tick(
    min_items: int = 3,
    max_items: int = 12,
    condition_hints: dict[str, str] | None = None,
    allowed_sources: set[SourceType] | None = None,
) -> list[GeneratedItem]:
    """Produce one scheduler tick worth of raw source items."""
    STATE.ticks += 1
    items: list[GeneratedItem] = []

    # Guarantee a visible clustering moment early on: force a burst on the
    # second tick, then let it happen at random afterwards.
    if STATE.burst_remaining <= 0 and (STATE.ticks == 2 or random.random() < BURST_CHANCE):
        city = random.choice(HOT_CITIES)
        event_type = _pick_event_type(city, condition_hints)
        # Distinct templates per burst report: two identical texts in the same
        # city inside 30 minutes would be collapsed by the dedup stage, which
        # would quietly starve the cluster this burst exists to demonstrate.
        rotation = TEMPLATES[event_type][:] + TEMPLATES_HI.get(event_type, [])
        random.shuffle(rotation)
        # A real event gets picked up by several kinds of source, not one.
        # Cycling them is also what pushes the event past the >=3 independent
        # sources that escalate it to NEEDS_REVIEW.
        sources = [s for s in SIMULATED_SOURCES if allowed_sources is None or s in allowed_sources]
        random.shuffle(sources)
        STATE.burst = {
            "city": city,
            "event_type": event_type,
            "rotation": rotation,
            "sources": sources,
            "source_cursor": 0,
        }
        STATE.burst_remaining = random.randint(*BURST_SIZE)

    count = random.randint(min_items, max_items)
    for _ in range(count):
        template: str | None = None
        forced_source: SourceType | None = None
        if STATE.burst_remaining > 0 and STATE.burst and random.random() < 0.7:
            city = STATE.burst["city"]
            event_type = STATE.burst["event_type"]
            rotation = STATE.burst["rotation"]
            template = rotation.pop() if rotation else None
            # Which sources are due changes between ticks, so intersect the
            # burst's rotation with what is currently pollable - otherwise the
            # burst emits for a source that is not due and the item is dropped.
            rotation_sources = [
                s
                for s in STATE.burst["sources"]
                if allowed_sources is None or s in allowed_sources
            ]
            forced_source = (
                rotation_sources[STATE.burst["source_cursor"] % len(rotation_sources)]
                if rotation_sources
                else None
            )
            STATE.burst["source_cursor"] += 1
            STATE.burst_remaining -= 1
        elif random.random() < NOISE_CHANCE:
            source_type = _weighted_source(allowed_sources)
            payload = _noise_payload()
            items.append(
                GeneratedItem(
                    source_type=source_type,
                    external_id=f"{source_type.value.lower()}-{uuid.uuid4().hex[:12]}",
                    collected_at=datetime.now(timezone.utc),
                    payload=payload,
                )
            )
            continue
        else:
            city = _pick_city()
            event_type = _pick_event_type(city, condition_hints)

        source_type = forced_source or _weighted_source(allowed_sources)

        if template is None and STATE.recent and random.random() < DUPLICATE_CHANCE:
            payload = _near_duplicate(random.choice(STATE.recent))
        else:
            payload = _build_payload(city, event_type, source_type, template)
            STATE.remember(payload)

        items.append(
            GeneratedItem(
                source_type=source_type,
                external_id=f"{source_type.value.lower()}-{uuid.uuid4().hex[:12]}",
                collected_at=datetime.now(timezone.utc),
                payload=payload,
            )
        )

    # A source that polled should contribute something. Without this a slow
    # feed like RSS loses the per-item weighted draw on the rare ticks it is
    # due, and its row in the admin table stays at zero for no good reason.
    produced = {i.source_type for i in items}
    for source_type in sorted(
        (allowed_sources or SIMULATED_SOURCES) & SIMULATED_SOURCES, key=lambda s: s.value
    ):
        if source_type in produced:
            continue
        city = _pick_city()
        event_type = _pick_event_type(city, condition_hints)
        payload = _build_payload(city, event_type, source_type)
        STATE.remember(payload)
        items.append(
            GeneratedItem(
                source_type=source_type,
                external_id=f"{source_type.value.lower()}-{uuid.uuid4().hex[:12]}",
                collected_at=datetime.now(timezone.utc),
                payload=payload,
            )
        )

    return items
