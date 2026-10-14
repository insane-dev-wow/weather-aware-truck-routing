"""Route alternatives from Valhalla (default) or OSRM."""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from functools import cached_property

import requests
from django.conf import settings
from django.core.cache import cache

from .geo import (
    cumulative_miles,
    haversine_miles,
    point_at_miles,
)
from .types import GeoPoint, cache_key

logger = logging.getLogger(__name__)

METERS_PER_MILE = 1609.344
# Product limits for alternatives relative to the fastest usable provider route.
# Weather ranking only runs after these route-quality checks.
MAX_DETOUR_FACTOR = 1.55
MAX_DURATION_FACTOR = 1.5
MAX_RETRACED_FRACTION = 0.05
RETRACING_ALLOWANCE_MILES = 1.0
MAX_SHARED_PATH_FRACTION = 0.95
_valhalla_lock = threading.Lock()
_valhalla_last_start = 0.0


class DirectionsError(Exception):
    """Raised when no drivable route can be produced."""


@dataclass
class RouteCandidate:
    key: str
    label: str
    summary: str
    distance_miles: float
    duration_hours: float
    geometry: list[list[float]]  # [lat, lon]

    @cached_property
    def segment_lengths(self) -> dict:
        """Full-geometry road segments for comparing routes from one engine."""
        lengths = {}
        for start, end in zip(self.geometry, self.geometry[1:]):
            a = tuple(round(value, 6) for value in start)
            b = tuple(round(value, 6) for value in end)
            if a != b:
                lengths[tuple(sorted((a, b)))] = haversine_miles(start, end)
        return lengths

    @property
    def avg_speed_mph(self) -> float:
        if self.duration_hours <= 0:
            return 0.0
        return self.distance_miles / self.duration_hours


def _coords_param(points: list[GeoPoint | tuple[float, float]]) -> str:
    parts = []
    for point in points:
        lat, lon = (point.lat, point.lon) if isinstance(point, GeoPoint) else point
        parts.append(f"{lon:.6f},{lat:.6f}")
    return ";".join(parts)


def _request_routes(
    points: list[GeoPoint | tuple[float, float]], *, alternatives: bool,
) -> list[dict]:
    if settings.ROUTING_PROVIDER == "valhalla":
        return _request_valhalla(points)
    if settings.ROUTING_PROVIDER != "osrm":
        raise DirectionsError("The configured routing provider is not supported.")
    url = f"{settings.OSRM_BASE_URL}/route/v1/driving/{_coords_param(points)}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "true",
        "annotations": "false",
        "alternatives": "2" if alternatives else "false",
    }
    try:
        response = requests.get(
            url, params=params, timeout=settings.UPSTREAM_TIMEOUT
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise DirectionsError(
            "The routing service is unavailable right now. Please try again."
        ) from exc

    if payload.get("code") != "Ok" or not payload.get("routes"):
        message = payload.get("message") or payload.get("code") or "unknown error"
        raise DirectionsError(f"Could not find a drivable route ({message}).")
    return payload["routes"]


def _request_valhalla(
    points: list[GeoPoint | tuple[float, float]], *, shortest: bool = False,
) -> list[dict]:
    """Ask the engine for a primary route plus two alternatives.

    The second search changes the engine's distance/time preference, never the
    user's endpoints. OSRM-format output keeps metrics in metres and seconds.
    """
    locations = [
        {"lat": point.lat, "lon": point.lon}
        if isinstance(point, GeoPoint) else {"lat": point[0], "lon": point[1]}
        for point in points
    ]
    body = {
        "locations": locations,
        "costing": "auto",
        "alternates": 2,
        "format": "osrm",
        "shape_format": "geojson",
        "costing_options": {"auto": {"shortest": shortest}},
    }
    key = cache_key("valhalla-v1", settings.VALHALLA_BASE_URL, locations, shortest)
    cached = cache.get(key)
    if cached is not None:
        return cached

    payload = _fetch_valhalla(body)
    if (
        not isinstance(payload, dict)
        or payload.get("code") != "Ok"
        or not isinstance(payload.get("routes"), list)
        or not payload["routes"]
    ):
        raise DirectionsError("The routing service could not find a drivable route for this trip.")
    cache.set(key, payload["routes"], timeout=1800)
    return payload["routes"]


def _fetch_valhalla(body: dict) -> dict:
    """Retry one transient failure, while keeping all attempts rate limited."""
    global _valhalla_last_start
    for attempt in range(2):
        with _valhalla_lock:
            delay = 1.1 - (time.monotonic() - _valhalla_last_start)
            if delay > 0:
                time.sleep(delay)
            _valhalla_last_start = time.monotonic()
        try:
            response = requests.post(
                f"{settings.VALHALLA_BASE_URL}/route", json=body,
                headers={"X-Client-Id": settings.ROUTING_CLIENT_ID},
                timeout=settings.ROUTING_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            transient = isinstance(exc, (requests.Timeout, requests.ConnectionError)) or status in (502, 503, 504)
            if attempt == 0 and transient:
                logger.info("Retrying routing request after %s (status %s)", type(exc).__name__, status)
                continue
            logger.warning("Routing request failed: %s (status %s)", type(exc).__name__, status)
            if isinstance(exc, requests.Timeout):
                message = "The routing provider timed out. Please retry your trip."
            elif status == 429:
                message = "The routing provider is busy. Wait a moment before retrying."
            elif status == 400:
                message = "The routing provider could not route between these locations. Check the selected places."
            elif isinstance(exc, ValueError):
                message = "The routing provider returned an invalid response. Please retry your trip."
            else:
                message = "Could not connect to the routing provider. Please retry your trip."
            raise DirectionsError(message) from exc


def _summarise(route: dict) -> str:
    """Build a human-readable corridor name from OSRM step road refs."""
    weights: dict[str, float] = {}
    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            name = step.get("ref") or step.get("name") or ""
            name = name.strip()
            if not name:
                continue
            weights[name] = weights.get(name, 0.0) + float(step.get("distance", 0.0))

    if not weights:
        return "Local roads"

    top = sorted(weights.items(), key=lambda item: item[1], reverse=True)[:3]
    return " · ".join(name for name, _ in top)


def _to_candidate(route: dict) -> RouteCandidate:
    coordinates = route.get("geometry", {}).get("coordinates", [])
    geometry = [[float(lat), float(lon)] for lon, lat in coordinates]
    distance = float(route.get("distance", 0.0)) / METERS_PER_MILE
    duration = float(route.get("duration", 0.0)) / 3600.0
    if (
        not math.isfinite(distance) or distance <= 0
        or not math.isfinite(duration) or duration <= 0
        or len(geometry) < 2
        or any(
            not math.isfinite(lat) or not -90 <= lat <= 90
            or not math.isfinite(lon) or not -180 <= lon <= 180
            for lat, lon in geometry
        )
        or all(point == geometry[0] for point in geometry)
    ):
        raise ValueError("Invalid routing metrics or geometry")
    return RouteCandidate(
        key="",
        label="",
        summary=_summarise(route),
        distance_miles=distance,
        duration_hours=duration,
        geometry=geometry,
    )


def _signature(candidate: RouteCandidate) -> tuple:
    """Sample corresponding positions without rounding away local alternatives."""
    coordinates = [tuple(p) for p in candidate.geometry]
    running = cumulative_miles(coordinates)
    total = running[-1] if running else 0.0
    samples = []
    for fraction in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        point = point_at_miles(
            coordinates, running, total * fraction
        )
        samples.append((round(point[0], 5), round(point[1], 5)))
    return (round(candidate.distance_miles, 2),) + tuple(samples)


def _is_duplicate(candidate: RouteCandidate, taken: list[RouteCandidate]) -> bool:
    signature = _signature(candidate)
    for other in taken:
        shared_miles = sum(
            min(miles, other.segment_lengths[edge])
            for edge, miles in candidate.segment_lengths.items()
            if edge in other.segment_lengths
        )
        shorter_geometry = min(
            sum(candidate.segment_lengths.values()), sum(other.segment_lengths.values())
        )
        if shorter_geometry > 0 and shared_miles / shorter_geometry >= MAX_SHARED_PATH_FRACTION:
            return True
        other_signature = _signature(other)
        if signature == other_signature:
            return True
        # A fixed 20-mile tolerance erases every alternative on a local trip.
        # Scale both tolerances with distance and compare matching positions.
        trip_miles = min(candidate.distance_miles, other.distance_miles)
        length_tolerance = min(1.0, max(0.02, trip_miles * 0.002))
        corridor_tolerance = min(0.25, max(0.005, trip_miles * 0.001))
        if abs(candidate.distance_miles - other.distance_miles) <= length_tolerance and all(
            haversine_miles(point, other_point) <= corridor_tolerance
            for point, other_point in zip(signature[1:], other_signature[1:])
        ):
            return True
    return False


def _has_excessive_retracing(candidate: RouteCandidate) -> bool:
    """Reject substantial repeated road segments, allowing small access loops.

    Use the full provider geometry, before map simplification. Treat an edge
    traversed in either direction as the same road; a winding road by itself
    is not backtracking. Coordinate rounding tolerates sub-metre noise.
    """
    seen = set()
    total_miles = repeated_miles = 0.0
    for start, end in zip(candidate.geometry, candidate.geometry[1:]):
        a = tuple(round(value, 6) for value in start)
        b = tuple(round(value, 6) for value in end)
        if a == b:
            continue
        miles = haversine_miles(start, end)
        total_miles += miles
        edge = tuple(sorted((a, b)))
        if edge in seen:
            repeated_miles += miles
        seen.add(edge)
    return repeated_miles > max(
        RETRACING_ALLOWANCE_MILES, total_miles * MAX_RETRACED_FRACTION
    )


def _select_candidates(routes: list[dict], count: int) -> list[RouteCandidate]:
    usable: list[RouteCandidate] = []
    for route in routes:
        try:
            candidate = _to_candidate(route)
        except (AttributeError, TypeError, ValueError, OverflowError):
            logger.warning("Discarding an invalid route from the routing provider")
            continue
        if not _has_excessive_retracing(candidate):
            usable.append(candidate)

    if not usable:
        return []

    # A shorter but much slower route must not become the quality baseline.
    usable.sort(key=lambda item: (item.duration_hours, item.distance_miles))
    fastest = usable[0]
    accepted: list[RouteCandidate] = []
    for candidate in usable:
        if (
            candidate.distance_miles > fastest.distance_miles * MAX_DETOUR_FACTOR
            or candidate.duration_hours > fastest.duration_hours * MAX_DURATION_FACTOR
            or _is_duplicate(candidate, accepted)
        ):
            continue
        accepted.append(candidate)
        if len(accepted) >= count:
            break
    return accepted


def build_candidates(
    origin: GeoPoint, destination: GeoPoint, count: int = 3
) -> list[RouteCandidate]:
    """Find three distinct provider routes, retaining quality checks for all."""
    if origin.coords == destination.coords:
        raise DirectionsError("Origin and destination are the same place.")
    if count < 1:
        raise ValueError("At least one route must be requested")

    points = [origin, destination]
    routes = _request_routes(points, alternatives=True)
    accepted = _select_candidates(routes, count)
    if len(accepted) < count and settings.ROUTING_PROVIDER == "valhalla":
        try:
            distance_routes = _request_valhalla(points, shortest=True)
        except DirectionsError:
            # Preserve usable first-search results on an optional-search outage.
            if not accepted:
                raise
            logger.warning("Additional route search unavailable")
        else:
            accepted = _select_candidates(routes + distance_routes, count)
    if not accepted:
        raise DirectionsError("The routing provider returned no usable routes for this trip.")

    accepted.sort(key=lambda item: item.distance_miles)
    for index, candidate in enumerate(accepted):
        candidate.label = f"Route {chr(ord('A') + index)}"
        candidate.key = f"route-{index + 1}"
    return accepted
