"""Source connectors.

`StubConnector` wraps the synthetic generator and stands in for every feed the
prototype cannot legally or practically poll yet. Two connectors are genuinely
live: `OpenMeteoConnector` pulls actual observed weather for a handful of
metros, and `NewsRssConnector` pulls real Indian weather reporting from Google
News RSS. Between them, the corroboration layer and part of the intake are
backed by data nobody in this project manufactured.

Both satisfy the same `poll()` contract, which is the seam where a real
IMD/NDMA/social connector drops in later.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import OrderedDict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from app.config import settings
from app.db.models import SourceType
from app.services.ingestion.generator import GeneratedItem, generate_tick
from app.services.pipeline.geo import CITIES, HOT_CITIES

log = logging.getLogger(__name__)


class Connector(ABC):
    source_type: SourceType
    name: str

    @abstractmethod
    async def poll(self, *args, **kwargs) -> list[GeneratedItem]:
        ...


class StubConnector(Connector):
    """Emits synthetic items across all simulated source types."""

    name = "Synthetic Multi-Source Simulator"
    source_type = SourceType.CITIZEN

    def __init__(self, min_items: int = 3, max_items: int = 12):
        self.min_items = min_items
        self.max_items = max_items

    async def poll(
        self,
        condition_hints: dict[str, str] | None = None,
        allowed_sources: set[SourceType] | None = None,
    ) -> list[GeneratedItem]:
        return generate_tick(
            self.min_items, self.max_items, condition_hints, allowed_sources
        )


class OpenMeteoConnector(Connector):
    """Real observed weather for a rotating pair of metros."""

    name = "Open-Meteo Observations"
    source_type = SourceType.WEATHER_API

    def __init__(self, cities: list[str] | None = None, per_poll: int = 2):
        self.cities = cities or HOT_CITIES
        self.per_poll = per_poll
        self._cursor = 0

    def _next_cities(self) -> list[str]:
        picked = []
        for _ in range(min(self.per_poll, len(self.cities))):
            picked.append(self.cities[self._cursor % len(self.cities)])
            self._cursor += 1
        return picked

    async def poll(self, *_args, **_kwargs) -> list[GeneratedItem]:
        if not settings.open_meteo_enabled:
            return []

        items: list[GeneratedItem] = []
        now = datetime.now(timezone.utc)
        try:
            async with httpx.AsyncClient(timeout=settings.open_meteo_timeout_seconds) as client:
                for city in self._next_cities():
                    lat, lon, district, state = CITIES[city]
                    resp = await client.get(
                        settings.open_meteo_url,
                        params={
                            "latitude": round(lat, 2),
                            "longitude": round(lon, 2),
                            "current": "precipitation,temperature_2m,wind_speed_10m,relative_humidity_2m",
                            "timezone": "UTC",
                        },
                    )
                    resp.raise_for_status()
                    current = resp.json().get("current", {})
                    text = self._describe(city, current)
                    if text is None:
                        continue
                    items.append(
                        GeneratedItem(
                            source_type=SourceType.WEATHER_API,
                            external_id=f"openmeteo-{city.lower()}-{current.get('time', now.isoformat())}",
                            collected_at=now,
                            payload={
                                "text": text,
                                "city_hint": city,
                                "latitude": lat,
                                "longitude": lon,
                                "observed_at": now.isoformat(),
                                "observation": current,
                                "provider": "open-meteo",
                            },
                        )
                    )
        except Exception as exc:
            log.warning("open-meteo connector poll failed: %s", exc)
            return []
        return items

    @staticmethod
    def _describe(city: str, current: dict) -> str | None:
        """Only emit an item when the observation actually says something."""
        precip = current.get("precipitation")
        temp = current.get("temperature_2m")
        wind = current.get("wind_speed_10m")
        humidity = current.get("relative_humidity_2m")

        if precip is not None and precip >= 2.0:
            return f"Observed rainfall {precip}mm/h at {city} station"
        if temp is not None and temp >= 38.0:
            return f"Observed temperature {temp}C at {city} station, heatwave threshold crossed"
        if wind is not None and wind >= 30.0:
            return f"Observed strong wind {wind} kmph at {city} station"
        if humidity is not None and humidity >= 95.0:
            return f"Observed humidity {humidity}% at {city} station, fog and low visibility likely"
        return None


class SatelliteConnector(Connector):
    """INSAT-style sector observations, derived from real cloud-cover readings.

    Unlike the citizen and social feeds this is an instrument, not a person:
    it is wide-area, high-trust, and it only speaks when the imagery actually
    shows something. A satellite that reported "nothing over this sector" every
    cycle would be noise, so quiet sectors emit nothing at all.

    Real ingestion would be raster imagery through a CV pipeline; this derives
    the same conclusions from Open-Meteo's cloud-cover field so the text the
    platform stores is backed by a genuine observation.
    """

    name = "INSAT Cloud Imagery"
    source_type = SourceType.SATELLITE

    # A sector scan covers far more ground than a point report.
    SECTOR_RADIUS_KM = 40

    def __init__(self, cities: list[str] | None = None, per_poll: int = 4):
        self.cities = cities or HOT_CITIES
        self.per_poll = per_poll
        self._cursor = 0

    def _next_cities(self) -> list[str]:
        picked = []
        for _ in range(min(self.per_poll, len(self.cities))):
            picked.append(self.cities[self._cursor % len(self.cities)])
            self._cursor += 1
        return picked

    async def poll(self, *_args, **_kwargs) -> list[GeneratedItem]:
        if not settings.open_meteo_enabled:
            return []

        items: list[GeneratedItem] = []
        now = datetime.now(timezone.utc)
        try:
            async with httpx.AsyncClient(timeout=settings.open_meteo_timeout_seconds) as client:
                for city in self._next_cities():
                    lat, lon, _district, _state = CITIES[city]
                    resp = await client.get(
                        settings.open_meteo_url,
                        params={
                            "latitude": round(lat, 2),
                            "longitude": round(lon, 2),
                            "current": (
                                "cloud_cover,cloud_cover_high,precipitation,"
                                "wind_speed_10m,relative_humidity_2m"
                            ),
                            "timezone": "UTC",
                        },
                    )
                    resp.raise_for_status()
                    current = resp.json().get("current", {})
                    text = self._interpret(city, current)
                    if text is None:
                        continue
                    items.append(
                        GeneratedItem(
                            source_type=SourceType.SATELLITE,
                            external_id=(
                                f"insat-{city.lower()}-{current.get('time', now.isoformat())}"
                            ),
                            collected_at=now,
                            payload={
                                "text": text,
                                "city_hint": city,
                                "latitude": lat,
                                "longitude": lon,
                                "observed_at": now.isoformat(),
                                "observation": current,
                                "author": "insat_3d_sector_scan",
                                "provider": "open-meteo/cloud-cover",
                                "sector_radius_km": self.SECTOR_RADIUS_KM,
                            },
                        )
                    )
        except Exception as exc:
            log.warning("satellite connector poll failed: %s", exc)
            return []
        return items

    @staticmethod
    def _interpret(city: str, current: dict) -> str | None:
        """Turn a cloud reading into a sector finding. Quiet sky -> no emission."""
        cloud = current.get("cloud_cover")
        high_cloud = current.get("cloud_cover_high")
        precip = current.get("precipitation")
        wind = current.get("wind_speed_10m")
        humidity = current.get("relative_humidity_2m")

        if cloud is None:
            return None

        sector = f"{city} sector"
        # Phrasing carries the keywords the classifier keys on, so a satellite
        # finding lands in the same event types as a human report.
        if cloud >= 85 and precip is not None and precip >= 1.0:
            if wind is not None and wind >= 25:
                return (
                    f"INSAT-3D SECTOR SCAN: deep convective cloud mass over {sector}, "
                    f"thunderstorm signature with active rainfall #IMD"
                )
            return (
                f"INSAT-3D SECTOR SCAN: dense cloud band over {sector}, "
                f"heavy rainfall signature, cloud cover {cloud}% #IMD"
            )
        if cloud >= 85 and high_cloud is not None and high_cloud >= 60:
            return (
                f"INSAT-3D SECTOR SCAN: towering high cloud over {sector}, "
                f"thunderstorm development likely #IMD"
            )
        if cloud >= 70:
            return (
                f"INSAT-3D SECTOR SCAN: extensive cloud cover {cloud}% over {sector}, "
                f"rain likely #IMD"
            )
        if humidity is not None and humidity >= 92 and cloud <= 30:
            return (
                f"INSAT-3D SECTOR SCAN: low-level moisture over {sector}, "
                f"fog and reduced visibility likely at surface #IMD"
            )
        # Clear sky is not a finding.
        return None


class NewsRssConnector(Connector):
    """A genuinely live feed: real Indian weather reporting, polled from
    Google News RSS search.

    This is the one connector whose *content* is not manufactured anywhere in
    this project. Everything it emits was written by a journalist about
    weather that actually happened, which makes it the honest test of the rest
    of the pipeline: the classifier, the geocoder and the credibility scorer
    all meet language nobody wrote for them.

    Search feeds rather than publisher front-pages, deliberately. General
    Indian news RSS was measured at almost entirely non-weather content, so a
    publisher feed would mostly produce noise that the keyword gate would then
    throw away — a lot of polling for very little signal. A query-scoped feed
    is already on-topic at the source.

    No API key, no scraping, no terms to accept: RSS is a published interface
    meant to be read by machines.
    """

    name = "Google News — India weather"
    source_type = SourceType.WEB_RSS

    # Two queries so a quiet news cycle on one still yields the other. The
    # `when:` operator keeps the window recent, which matters because this
    # platform is about what is happening now, not an archive.
    FEEDS = [
        (
            "india-weather",
            "https://news.google.com/rss/search?"
            "q=weather+OR+rain+OR+flood+India+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        ),
        (
            "imd-alerts",
            "https://news.google.com/rss/search?"
            "q=IMD+warning+rain+alert+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
        ),
    ]

    # A headline must actually be about weather. Google's query is a search,
    # not a guarantee — "Extreme weather raises temperature on Chennai home
    # search" came back in testing and is a property story.
    WEATHER_TERMS = (
        "rain", "rainfall", "flood", "cyclone", "storm", "thunder", "lightning",
        "monsoon", "imd", "heatwave", "heat wave", "temperature", "fog",
        "visibility", "wind", "gale", "downpour", "waterlog", "cloudburst",
        "landslide", "alert", "warning", "weather",
    )

    # Weather mentioned in a context that is not a hazard report. This gate is
    # at the source on purpose, because the credibility layer provably cannot
    # catch it: "Chances of rain in Guwahati for IND vs WI 2nd ODI" classified
    # as RAIN at 0.98 confidence and geocoded to a real city, because it
    # genuinely *is* a statement about rain. Nothing downstream can tell that
    # apart from a hazard report — only the context the headline carries can,
    # and that context is here.
    EXCLUDE_TERMS = (
        # sport fixtures: a rain forecast for a match is not a hazard
        "odi", "t20", "test match", "ipl", "world cup", "asian games",
        "olympic", "innings", "wicket", "stadium", "vs ", " vs", "fixture",
        "match", "tournament", "playoff", "league",
        # markets and property
        "home search", "real estate", "property price", "stocks", "shares",
        "sensex", "nifty",
    )

    MAX_PER_POLL = 6

    def __init__(self) -> None:
        self._cursor = 0
        # Bounded so a long-running process cannot grow this without limit.
        # The pipeline's own exact-text dedup is the real backstop; this only
        # avoids the pointless work of re-submitting what we just submitted.
        self._seen: OrderedDict[str, None] = OrderedDict()

    def _remember(self, guid: str) -> bool:
        """True if this is new."""
        if guid in self._seen:
            return False
        self._seen[guid] = None
        while len(self._seen) > 500:
            self._seen.popitem(last=False)
        return True

    async def poll(self, *_args, **_kwargs) -> list[GeneratedItem]:
        if not settings.news_rss_enabled:
            return []

        feed_id, url = self.FEEDS[self._cursor % len(self.FEEDS)]
        self._cursor += 1
        now = datetime.now(timezone.utc)

        try:
            async with httpx.AsyncClient(
                timeout=settings.news_rss_timeout_seconds, follow_redirects=True
            ) as client:
                resp = await client.get(
                    url,
                    headers={
                        # Identify the client honestly. A feed publisher is
                        # entitled to know who is polling them.
                        "User-Agent": (
                            "NWAP/1.0 (National Weather Analytics Platform; "
                            "SIH26069 prototype; contact: via project repo)"
                        )
                    },
                )
                resp.raise_for_status()
                entries = self._parse(resp.text)
        except Exception as exc:
            log.warning("news rss poll failed for %s: %s", feed_id, exc)
            return []

        items: list[GeneratedItem] = []
        for entry in entries:
            if len(items) >= self.MAX_PER_POLL:
                break
            headline = entry["title"]
            if not self._is_weather(headline):
                continue
            if not self._remember(entry["guid"]):
                continue
            items.append(
                GeneratedItem(
                    source_type=SourceType.WEB_RSS,
                    external_id=f"gnews-{entry['guid'][:64]}",
                    collected_at=now,
                    source_name=self.name,
                    payload={
                        "text": headline,
                        "city_hint": None,
                        "observed_at": (entry["published"] or now).isoformat(),
                        # Flags the pipeline and the UI can trust: this row is
                        # real reporting, not generated. Deliberately carries
                        # no `intended_event_type` — there is no ground truth
                        # to cheat with, which is the point.
                        "is_real": True,
                        "provider": "google-news-rss",
                        "feed": feed_id,
                        "publisher": entry["publisher"],
                        "article_url": entry["link"],
                        "author": entry["publisher"] or "news",
                        "channel": "rss",
                    },
                )
            )
        if items:
            log.info("news rss %s: %s live articles", feed_id, len(items))
        return items

    def _is_weather(self, headline: str) -> bool:
        low = headline.lower()
        if any(term in low for term in self.EXCLUDE_TERMS):
            return False
        return any(term in low for term in self.WEATHER_TERMS)

    @staticmethod
    def _parse(xml_text: str) -> list[dict]:
        """RSS 2.0, parsed with the stdlib rather than a new dependency."""
        import xml.etree.ElementTree as ET

        out: list[dict] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            log.warning("news rss: unparseable feed (%s)", exc)
            return out

        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or link or title).strip()
            source_el = item.find("source")
            publisher = (source_el.text or "").strip() if source_el is not None else None

            # Google appends " - Publisher" to every headline; it is
            # redundant once the publisher is its own field, and leaving it in
            # would skew both the classifier and the dedup similarity score.
            if publisher and title.endswith(f" - {publisher}"):
                title = title[: -len(f" - {publisher}")].strip()

            published = None
            raw_date = item.findtext("pubDate")
            if raw_date:
                try:
                    published = parsedate_to_datetime(raw_date)
                    if published.tzinfo is None:
                        published = published.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    published = None

            out.append(
                {
                    "title": title,
                    "link": link,
                    "guid": guid,
                    "publisher": publisher,
                    "published": published,
                }
            )
        return out
