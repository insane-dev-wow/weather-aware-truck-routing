"""Hourly forecast lookups via Open-Meteo (no API key required).

Open-Meteo accepts many coordinates per request and returns one hourly series
per coordinate, in the same order. That lets us fetch every route checkpoint and
every heat-map cell for a whole corridor with a handful of HTTP calls, which we
run concurrently and cache per grid point.
"""

from __future__ import annotations

import logging
import math
import time
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests
from django.conf import settings
from django.core.cache import cache

from .types import cache_key, floor_to_hour, to_utc

logger = logging.getLogger(__name__)

HOURLY_VARIABLES = (
    "wind_speed_10m",
    "rain",
    "showers",
    "snowfall",
    "precipitation",
    "temperature_2m",
    "weather_code",
)
MAX_FORECAST_DAYS = 16
_CACHE_TTL = 60 * 30

WMO_LABELS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Rain showers",
    82: "Violent rain showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Severe thunderstorm with hail",
}


class WeatherError(Exception):
    """Raised when forecast data cannot be retrieved."""


def _cooldown_key():
    return cache_key("weather-cooldown", settings.OPEN_METEO_URL)


def _check_cooldown():
    until = cache.get(_cooldown_key())
    if until and until > time.time():
        minutes = max(1, math.ceil((until - time.time()) / 60))
        raise WeatherError(
            f"The weather provider's request limit was reached. "
            f"New weather requests are paused for about {minutes} minute(s). "
            "Cached forecasts can still be used."
        )


def _record_cooldown(response):
    seconds = 60
    try:
        reason = str(response.json().get("reason", "")).lower()
        if "day" in reason or "daily" in reason:
            seconds = 86400
        elif "hour" in reason:
            seconds = 3600
    except (ValueError, AttributeError, TypeError):
        pass
    retry_after = response.headers.get("Retry-After")
    if isinstance(retry_after, str):
        try:
            seconds = max(1, int(retry_after))
        except ValueError:
            try:
                seconds = max(1, math.ceil(parsedate_to_datetime(retry_after).timestamp() - time.time()))
            except (ValueError, TypeError, OverflowError):
                pass
    until = max(cache.get(_cooldown_key()) or 0, time.time() + seconds)
    cache.set(_cooldown_key(), until, max(1, math.ceil(until - time.time())))
    logger.warning("Weather provider cooldown: %d seconds", seconds)


@dataclass
class HourlySeries:
    lat: float
    lon: float
    times: list[str] = field(default_factory=list)
    wind_mph: list[float | None] = field(default_factory=list)
    rain_in: list[float | None] = field(default_factory=list)
    showers_in: list[float | None] = field(default_factory=list)
    snow_in: list[float | None] = field(default_factory=list)
    precip_in: list[float | None] = field(default_factory=list)
    temp_f: list[float | None] = field(default_factory=list)
    code: list[int | None] = field(default_factory=list)

    def at(self, moment: datetime) -> dict | None:
        """Sample wind at the previous hourly instant and precipitation at its
        interval end. Open-Meteo's rain/snow totals describe the preceding hour:
        e.g. 10:45 uses 10:00 wind and 11:00 precipitation (10:00–11:00).
        At an exact hourly boundary, the precipitation interval ends there.
        Missing risk inputs remain unknown; they never become clear weather.
        """
        moment = to_utc(moment)
        instant = floor_to_hour(moment)
        interval_end = instant if moment == instant else instant + timedelta(hours=1)
        try:
            index = self.times.index(instant.strftime("%Y-%m-%dT%H:00"))
            precip_index = self.times.index(interval_end.strftime("%Y-%m-%dT%H:00"))
        except ValueError:
            return None

        def value(values, at):
            return values[at] if at < len(values) else None

        wind = value(self.wind_mph, index)
        rain = value(self.rain_in, precip_index)
        showers = value(self.showers_in, precip_index)
        snow = value(self.snow_in, precip_index)
        if any(item is None or not math.isfinite(item) for item in (wind, rain, showers, snow)):
            return None
        code = value(self.code, index)
        return {
            "wind_mph": wind,
            "rain_in_hr": rain + showers,
            "snow_in_hr": snow,
            "precip_in_hr": value(self.precip_in, precip_index),
            "temp_f": value(self.temp_f, index),
            "weather_code": code,
            "weather": WMO_LABELS.get(code, "Unknown"),
        }


def point_key(lat: float, lon: float) -> tuple[float, float]:
    """Canonical key used to dedupe and look up a coordinate's series."""
    return (round(lat, 3), round(lon, 3))


def _series_cache_key(key: tuple[float, float], days: int) -> str:
    return cache_key("wx-v3", settings.OPEN_METEO_URL, datetime.now(timezone.utc).date(),
                     f"{key[0]:.3f}", f"{key[1]:.3f}", days)


def _as_float_list(value) -> list[float | None]:
    if not isinstance(value, list):
        return []
    return [float(v) if v is not None and math.isfinite(float(v)) else None for v in value]


def _parse_one(raw: dict, fallback: tuple[float, float]) -> HourlySeries:
    hourly = raw.get("hourly") or {}
    times = list(hourly.get("time") or [])
    return HourlySeries(
        lat=float(raw.get("latitude", fallback[0])),
        lon=float(raw.get("longitude", fallback[1])),
        times=times,
        wind_mph=_as_float_list(hourly.get("wind_speed_10m")),
        rain_in=_as_float_list(hourly.get("rain")),
        showers_in=_as_float_list(hourly.get("showers")),
        snow_in=_as_float_list(hourly.get("snowfall")),
        precip_in=_as_float_list(hourly.get("precipitation")),
        temp_f=_as_float_list(hourly.get("temperature_2m")),
        code=[int(v) if v is not None else None for v in (hourly.get("weather_code") or [])],
    )


def _fetch_chunk(
    coordinates: list[tuple[float, float]], days: int
) -> list[HourlySeries]:
    _check_cooldown()
    latitudes = ",".join(f"{lat:.3f}" for lat, _ in coordinates)
    longitudes = ",".join(f"{lon:.3f}" for _, lon in coordinates)
    params = {
        "latitude": latitudes,
        "longitude": longitudes,
        "hourly": ",".join(HOURLY_VARIABLES),
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "temperature_unit": "fahrenheit",
        "timezone": "UTC",
        "forecast_days": days,
        "past_days": 1,
        "models": "best_match",
    }
    try:
        response = requests.get(
            settings.OPEN_METEO_URL, params=params, timeout=settings.UPSTREAM_TIMEOUT
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        failed_response = getattr(exc, "response", None)
        status = failed_response.status_code if failed_response is not None else None
        logger.warning("Forecast request failed: %s; status=%s; locations=%d; days=%d",
                       type(exc).__name__, status, len(coordinates), days)
        if status == 429:
            _record_cooldown(failed_response)
            _check_cooldown()
            message = "The weather provider's request limit was reached. Wait before trying again."
        elif isinstance(exc, requests.Timeout):
            message = "The weather provider timed out. Please retry your trip."
        elif isinstance(exc, requests.ConnectionError):
            message = "Could not connect to the weather provider. Please try again."
        elif status is not None and status >= 500:
            message = "The weather provider is temporarily unavailable. Please try again later."
        elif status is not None:
            message = f"The weather provider rejected the forecast request (HTTP {status})."
        else:
            message = "The weather provider returned an invalid response. Please retry your trip."
        raise WeatherError(message) from exc

    if isinstance(payload, dict) and "error" in payload:
        raise WeatherError(f"Forecast provider error: {payload.get('reason', 'unknown')}")

    rows = payload if isinstance(payload, list) else [payload]
    if len(rows) != len(coordinates):
        logger.warning(
            "Open-Meteo returned %d rows for %d coordinates", len(rows), len(coordinates)
        )
        raise WeatherError("The weather provider returned an incomplete batch. Please retry your trip.")
    try:
        return [_parse_one(row, coordinates[index]) for index, row in enumerate(rows)]
    except (ValueError, TypeError, AttributeError) as exc:
        raise WeatherError("The weather provider returned malformed forecast data. Please retry your trip.") from exc


def fetch_series(
    points: list[tuple[float, float]], days: int
) -> dict[tuple[float, float], HourlySeries]:
    """Fetch and cache hourly series for many points.

    Returns a mapping keyed by :func:`point_key`.
    """
    days = max(1, min(int(days), MAX_FORECAST_DAYS))

    unique: dict[tuple[float, float], tuple[float, float]] = {}
    for lat, lon in points:
        unique[point_key(lat, lon)] = (lat, lon)

    resolved: dict[tuple[float, float], HourlySeries] = {}
    pending: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for key, coordinates in unique.items():
        cached = cache.get(_series_cache_key(key, days))
        if cached:
            resolved[key] = HourlySeries(**cached)
        else:
            pending.append((key, coordinates))

    if pending:
        _check_cooldown()
        chunk_size = max(1, settings.WEATHER_CHUNK_SIZE)
        batches = [
            pending[index : index + chunk_size]
            for index in range(0, len(pending), chunk_size)
        ]

        def work(batch):
            series = _fetch_chunk([coordinates for _, coordinates in batch], days)
            return batch, series

        # Submit only one wave at a time. A failure must not leave dozens of
        # already-queued requests hitting a rate-limited provider.
        with ThreadPoolExecutor(max_workers=max(1, settings.WEATHER_MAX_WORKERS)) as pool:
            pending_batches = iter(batches)
            active = set()
            for _ in range(max(1, settings.WEATHER_MAX_WORKERS)):
                batch = next(pending_batches, None)
                if batch is not None:
                    active.add(pool.submit(work, batch))
            failure = None
            while active:
                done, active = wait(active, return_when=FIRST_COMPLETED)
                for future in done:
                    try:
                        batch, series = future.result()
                    except WeatherError as exc:
                        failure = failure or exc
                        continue
                    for (key, _coordinates), item in zip(batch, series):
                        resolved[key] = item
                        cache.set(_series_cache_key(key, days), item.__dict__, _CACHE_TTL)
                if failure is None:
                    for _ in done:
                        batch = next(pending_batches, None)
                        if batch is not None:
                            active.add(pool.submit(work, batch))
            if failure is not None:
                raise failure

    return resolved


def required_forecast_days(depart_at: datetime, horizon_hours: float) -> int:
    """Days of forecast needed to cover a horizon that starts at ``depart_at``."""
    end = to_utc(depart_at) + timedelta(hours=max(horizon_hours, 0))
    interval_end = floor_to_hour(end)
    if end > interval_end:
        interval_end += timedelta(hours=1)
    days = (interval_end.date() - datetime.now(timezone.utc).date()).days + 1
    return max(1, min(days, MAX_FORECAST_DAYS))
