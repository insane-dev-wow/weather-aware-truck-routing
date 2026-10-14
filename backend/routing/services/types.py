from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def cache_key(*parts: object) -> str:
    """Build a cache-safe key (LocMem/memcached reject spaces, commas, etc.)."""
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def to_utc(value: datetime) -> datetime:
    """Normalise a datetime to an aware UTC value."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def floor_to_hour(value: datetime) -> datetime:
    value = to_utc(value)
    return value.replace(minute=0, second=0, microsecond=0)


def iso(value: datetime) -> str:
    value = to_utc(value).replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class GeoPoint:
    """A resolved place. ``name`` is the human-readable label from Nominatim."""

    query: str
    name: str
    lat: float
    lon: float
    country: str | None = None

    @property
    def coords(self) -> tuple[float, float]:
        return (self.lat, self.lon)

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "name": self.name,
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "country": self.country,
        }
