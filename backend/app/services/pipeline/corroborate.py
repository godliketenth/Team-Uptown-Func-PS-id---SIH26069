"""Stage 4: corroborate a report's claim against real observed weather.

The one real external call in the prototype: Open-Meteo (free, no API key).
Results are cached per (lat@0.1deg, lon@0.1deg, hour) for the process
lifetime. Any failure degrades to a neutral 0.5 support score — corroboration
must never block the pipeline.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.config import settings

log = logging.getLogger(__name__)

NEUTRAL = 0.5
_CACHE: dict[tuple[float, float, str], dict] = {}
_CACHE_MAX = 2000

# Support thresholds per variable.
RAIN_MM_STRONG = 2.0
WIND_KMH_STRONG = 30.0
HEAT_C_STRONG = 38.0
FOG_HUMIDITY = 90.0


# Cache hit/miss counters, surfaced in admin system health.
CACHE_STATS = {"hits": 0, "misses": 0}


def _cache_key(
    lat: float, lon: float, when: datetime, city: str | None = None
) -> tuple[str, str]:
    """Key on the city when we have one.

    A city-matched report's coordinates carry ±0.05 degrees of jitter, applied
    only so pins do not stack on one pixel. Keying on those jittered
    coordinates scattered a single city across ~3.5 cache cells and made 3.5x
    more API calls than the data warranted — and querying a jittered point is
    no more accurate than querying the city centre, it is just noisier.

    True GPS reports keep coordinate-based keys, rounded to the model's own
    ~0.1 degree resolution.
    """
    hour = when.strftime("%Y-%m-%dT%H")
    if city:
        return (f"city:{city}", hour)
    return (f"pt:{round(lat, 1)},{round(lon, 1)}", hour)


def _clamp(v: float) -> float:
    return round(max(0.0, min(1.0, v)), 4)


async def fetch_weather(
    lat: float, lon: float, when: datetime, city: str | None = None
) -> dict | None:
    """Hourly precipitation / temperature / wind / humidity at the nearest hour."""
    if not settings.open_meteo_enabled:
        return None

    key = _cache_key(lat, lon, when, city)
    if key in _CACHE:
        CACHE_STATS["hits"] += 1
        return _CACHE[key]
    CACHE_STATS["misses"] += 1

    params = {
        "latitude": round(lat, 2),
        "longitude": round(lon, 2),
        "hourly": "precipitation,temperature_2m,wind_speed_10m,relative_humidity_2m,visibility",
        "past_days": 1,
        "forecast_days": 1,
        "timezone": "UTC",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.open_meteo_timeout_seconds) as client:
            resp = await client.get(settings.open_meteo_url, params=params)
            resp.raise_for_status()
            hourly = resp.json().get("hourly", {})
    except Exception as exc:  # network down, rate limited, malformed - all non-fatal
        log.warning("open-meteo lookup failed (%s); using neutral corroboration", exc)
        return None

    times: list[str] = hourly.get("time", [])
    if not times:
        return None

    target = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00")
    try:
        idx = times.index(target)
    except ValueError:
        idx = min(range(len(times)), key=lambda i: abs(_hour_delta(times[i], target)))

    def at(name: str) -> float | None:
        series = hourly.get(name) or []
        if idx < len(series) and series[idx] is not None:
            return float(series[idx])
        return None

    observation = {
        "time": times[idx],
        "precipitation_mm": at("precipitation"),
        "temperature_c": at("temperature_2m"),
        "wind_speed_kmh": at("wind_speed_10m"),
        "humidity_pct": at("relative_humidity_2m"),
        "visibility_m": at("visibility"),
    }
    if len(_CACHE) < _CACHE_MAX:
        _CACHE[key] = observation
    return observation


def _hour_delta(a: str, b: str) -> float:
    try:
        return (datetime.fromisoformat(a) - datetime.fromisoformat(b)).total_seconds()
    except ValueError:
        return 1e9


# A coarse model grid cell that simply lacks the signal does NOT disprove a
# street-level observation - rain and flooding are intensely local. Only an
# actively opposing reading counts as a contradiction.
CONTRADICTION_RULES: dict[str, str] = {
    "RAIN": "no measurable rain and dry air",
    "FLOOD": "no measurable rain and dry air",
    "THUNDERSTORM": "calm, dry conditions",
    "HEATWAVE": "temperature well below heatwave range",
    "FOG": "clear long-range visibility",
    "DUST_STORM": "near-calm wind",
    "STRONG_WIND": "near-calm wind",
}


def detect_contradiction(event_type: str, obs: dict) -> bool:
    """True only when the observation actively opposes the claim."""
    precip = obs.get("precipitation_mm")
    temp = obs.get("temperature_c")
    wind = obs.get("wind_speed_kmh")
    humidity = obs.get("humidity_pct")
    visibility = obs.get("visibility_m")

    if event_type in ("RAIN", "FLOOD"):
        return precip is not None and precip == 0 and humidity is not None and humidity < 55
    if event_type == "THUNDERSTORM":
        return (
            precip is not None
            and precip == 0
            and wind is not None
            and wind < 10
            and humidity is not None
            and humidity < 55
        )
    if event_type == "HEATWAVE":
        return temp is not None and temp < 30.0
    if event_type == "FOG":
        if visibility is not None:
            return visibility > 8000
        return humidity is not None and humidity < 50
    if event_type in ("DUST_STORM", "STRONG_WIND"):
        return wind is not None and wind < 10.0
    return False


def score_support(event_type: str, obs: dict | None) -> dict:
    """Turn an observation into per-variable support scores for the claim."""
    if not obs:
        return {
            "status": "unavailable",
            "rainfall_support": NEUTRAL,
            "temperature_support": NEUTRAL,
            "wind_support": NEUTRAL,
            "visibility_support": NEUTRAL,
            "overall_support": NEUTRAL,
        }

    precip = obs.get("precipitation_mm")
    temp = obs.get("temperature_c")
    wind = obs.get("wind_speed_kmh")
    humidity = obs.get("humidity_pct")
    visibility = obs.get("visibility_m")

    rainfall_support = NEUTRAL if precip is None else _clamp(precip / RAIN_MM_STRONG)
    temperature_support = NEUTRAL if temp is None else _clamp((temp - 30.0) / (HEAT_C_STRONG - 30.0))
    wind_support = NEUTRAL if wind is None else _clamp(wind / WIND_KMH_STRONG)
    if visibility is not None:
        visibility_support = _clamp(1.0 - (visibility / 10000.0))
    elif humidity is not None:
        visibility_support = _clamp((humidity - 60.0) / (FOG_HUMIDITY - 60.0))
    else:
        visibility_support = NEUTRAL

    driver = {
        "RAIN": rainfall_support,
        "FLOOD": rainfall_support,
        "THUNDERSTORM": max(rainfall_support, wind_support),
        "HEATWAVE": temperature_support,
        "FOG": visibility_support,
        "DUST_STORM": wind_support,
        "STRONG_WIND": wind_support,
    }.get(event_type, NEUTRAL)

    contradicted = detect_contradiction(event_type, obs)

    return {
        "status": "ok",
        "contradicted": contradicted,
        "contradiction_reason": CONTRADICTION_RULES.get(event_type) if contradicted else None,
        "observed_at": obs.get("time"),
        "precipitation_mm": precip,
        "temperature_c": temp,
        "wind_speed_kmh": wind,
        "humidity_pct": humidity,
        "rainfall_support": rainfall_support,
        "temperature_support": temperature_support,
        "wind_support": wind_support,
        "visibility_support": visibility_support,
        "overall_support": _clamp(driver),
    }


async def corroborate(
    event_type: str,
    lat: float | None,
    lon: float | None,
    when: datetime,
    city: str | None = None,
) -> dict:
    if lat is None or lon is None:
        return score_support(event_type, None) | {"status": "no_location"}
    return score_support(event_type, await fetch_weather(lat, lon, when, city))


# Observation -> the event type that reading would support. Used to keep
# generated traffic anchored to weather that is actually happening, so that
# corroboration is a meaningful signal rather than uniformly negative.
async def dominant_condition(
    lat: float, lon: float, when: datetime, city: str | None = None
) -> str | None:
    obs = await fetch_weather(lat, lon, when, city)
    if not obs:
        return None

    precip = obs.get("precipitation_mm")
    temp = obs.get("temperature_c")
    wind = obs.get("wind_speed_kmh")
    humidity = obs.get("humidity_pct")
    visibility = obs.get("visibility_m")

    if precip is not None and precip >= 6.0:
        return "FLOOD"
    if precip is not None and precip >= 1.0:
        return "RAIN"
    if temp is not None and temp >= HEAT_C_STRONG:
        return "HEATWAVE"
    if wind is not None and wind >= WIND_KMH_STRONG:
        return "STRONG_WIND"
    if visibility is not None and visibility < 2000:
        return "FOG"
    if humidity is not None and humidity >= FOG_HUMIDITY:
        return "FOG"
    if humidity is not None and humidity >= 70 and precip is not None and precip > 0:
        return "RAIN"
    return None
