"""Photon autocomplete and Nominatim geocoding of submitted free-text locations.

Public Nominatim does not permit autocomplete. Its outbound requests share
a SQLite lock on this host and start at least one second apart. Keep a single
application instance when using the public service; use another provider or a
central geocoding service before scaling across hosts.
"""

from __future__ import annotations

import logging
import math
import sqlite3
import time
from contextlib import contextmanager

import requests
from django.conf import settings
from django.core.cache import cache

from .types import GeoPoint, cache_key

logger = logging.getLogger(__name__)

SEARCH_PATH = "/search"
_CACHE_TTL = 60 * 60  # geocoding is stable; an hour is plenty


class GeocodingError(Exception):
    """Raised when a place cannot be resolved into coordinates."""


def _headers() -> dict[str, str]:
    return {
        "User-Agent": settings.GEOCODER_USER_AGENT,
        "Accept": "application/json",
        "Accept-Language": "en",
    }


@contextmanager
def _geocoder_slot():
    """Serialize provider calls across local workers, including their wait time."""
    connection = sqlite3.connect(
        str(settings.GEOCODER_RATE_LIMIT_DB),
        timeout=settings.UPSTREAM_TIMEOUT + 5,
        isolation_level=None,
    )
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS geocoder_slot "
            "(id INTEGER PRIMARY KEY, next_start REAL NOT NULL)"
        )
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT next_start FROM geocoder_slot WHERE id = 1"
        ).fetchone()
        now = time.time()
        if row is not None and row[0] > now:
            time.sleep(row[0] - now)
        # Store before yielding, and commit even on an HTTP error: failed calls
        # count against the provider's rate limit too.
        connection.execute(
            "INSERT OR REPLACE INTO geocoder_slot (id, next_start) VALUES (1, ?)",
            (time.time() + 1.05,),
        )
        try:
            yield
        finally:
            connection.commit()
    finally:
        connection.close()


def _search(query: str, limit: int, *, allow_country_filter: bool = True) -> list[dict]:
    params = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": limit,
        "dedupe": 1,
        "accept-language": "en",
    }
    if allow_country_filter:
        params["countrycodes"] = "us"

    try:
        with _geocoder_slot():
            response = requests.get(
                f"{settings.NOMINATIM_URL}{SEARCH_PATH}",
                params=params,
                headers=_headers(),
                timeout=settings.UPSTREAM_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
    except (requests.RequestException, ValueError, sqlite3.Error, OSError) as exc:
        logger.warning("Nominatim lookup failed for %r: %s", query, exc)
        raise GeocodingError(
            "Location search is temporarily unavailable. Please try again."
        ) from exc

    if not payload and allow_country_filter:
        # Widen beyond the US default for international queries.
        return _search(query, limit, allow_country_filter=False)
    return payload if isinstance(payload, list) else []


def _short_name(row: dict) -> str:
    address = row.get("address", {}) or {}
    locality = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("hamlet")
        or address.get("municipality")
        or address.get("county")
    )
    state = address.get("state") or address.get("state_code")
    if locality and state:
        return f"{locality}, {state}"
    if locality:
        return locality
    fallback = (row.get("display_name") or "").split(",")
    return ", ".join(part.strip() for part in fallback[:2]) if fallback else "Unknown"


def geocode(query: str) -> GeoPoint:
    """Resolve a free-text place into a single best-match :class:`GeoPoint`."""
    text = (query or "").strip()
    if not text:
        raise GeocodingError("Enter both an origin and a destination.")

    cache_key_value = cache_key("geocode", text.lower())
    cached = cache.get(cache_key_value)
    if cached:
        return GeoPoint(**cached)

    rows = _search(text, limit=1)
    if not rows:
        raise GeocodingError(f"No location found for “{text}”. Try a city and state.")

    row = rows[0]
    place = GeoPoint(
        query=text,
        name=row.get("display_name") or text,
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        country=(row.get("address") or {}).get("country"),
    )
    cache.set(cache_key_value, place.__dict__, _CACHE_TTL)
    return place


def _autocomplete_search(query: str, limit: int) -> list[dict]:
    """Photon supports search-as-you-type; never send these calls to Nominatim."""
    try:
        response = requests.get(
            f"{settings.PHOTON_URL}/api/",
            params={"q": query, "limit": limit, "lang": "en"},
            headers=_headers(),
            timeout=settings.UPSTREAM_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
            raise ValueError("Invalid place-search response")
    except (requests.RequestException, ValueError) as exc:
        raise GeocodingError("Location search is temporarily unavailable. Please try again.") from exc

    rows = []
    for feature in payload["features"]:
        try:
            lon, lat = feature["geometry"]["coordinates"]
            lon, lat = float(lon), float(lat)
            if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                continue
            properties = feature["properties"]
            street = " ".join(str(properties.get(key) or "") for key in ("housenumber", "street")).strip()
            parts = list(dict.fromkeys(
                str(value).strip() for value in (
                    properties.get("name"), street, properties.get("city"),
                    properties.get("district"), properties.get("state"), properties.get("country"),
                ) if value and str(value).strip()
            ))
            if not parts:
                continue
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        rows.append({
            "lat": lat, "lon": lon,
            "label": ", ".join(parts[:2]), "display_name": ", ".join(parts),
            "address": {"country": properties.get("country")},
        })
    return rows


def suggest(query: str, limit: int = 6) -> list[dict]:
    """Return cached Photon suggestions for a debounced autocomplete query."""
    text = (query or "").strip()
    if len(text) < 2:
        return []

    query_key = cache_key("photon-suggest-v2", settings.PHOTON_URL, limit, text.lower())
    cached = cache.get(query_key)
    if cached is not None:
        return cached

    rows = _autocomplete_search(text, limit=limit)

    suggestions: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        try:
            lat, lon = float(row["lat"]), float(row["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        label = row.get("label") or _short_name(row)
        value = row.get("display_name") or label
        label_key = value.lower()
        if label_key in seen:
            continue
        seen.add(label_key)
        suggestions.append(
            {
                "value": value,
                "label": label,
                "lat": lat,
                "lon": lon,
            }
        )
        # A selected search result should not trigger another provider request
        # when the driver submits the plan.
        place = GeoPoint(
            query=value,
            name=value,
            lat=lat,
            lon=lon,
            country=(row.get("address") or {}).get("country"),
        )
        cache.set(cache_key("geocode", value.lower()), place.__dict__, _CACHE_TTL)
        if len(suggestions) >= limit:
            break

    cache.set(query_key, suggestions, _CACHE_TTL)
    return suggestions
