"""Pure geometry helpers. Coordinates are ``(lat, lon)`` tuples."""

from __future__ import annotations

import math

EARTH_RADIUS_MILES = 3958.7613
MILES_PER_DEGREE_LAT = 69.0547

LatLon = tuple[float, float]
Bounds = tuple[float, float, float, float]  # south, west, north, east


def haversine_miles(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    h = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2.0 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(h)))


def cumulative_miles(coords: list[LatLon]) -> list[float]:
    if not coords:
        return []
    running = [0.0]
    for index in range(1, len(coords)):
        running.append(running[-1] + haversine_miles(coords[index - 1], coords[index]))
    return running


def point_at_miles(coords: list[LatLon], running: list[float], target: float) -> LatLon:
    if not coords:
        raise ValueError("empty geometry")
    if target <= 0:
        return coords[0]
    if target >= running[-1]:
        return coords[-1]

    lo, hi = 0, len(running) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if running[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    i = max(1, lo)
    span = running[i] - running[i - 1]
    ratio = 0.0 if span <= 0 else (target - running[i - 1]) / span
    (lat1, lon1), (lat2, lon2) = coords[i - 1], coords[i]
    return (lat1 + (lat2 - lat1) * ratio, lon1 + (lon2 - lon1) * ratio)


def resample(coords: list[LatLon], interval_miles: float) -> list[tuple[float, LatLon]]:
    """Return ``(mile_marker, point)`` every ``interval_miles`` plus the endpoint."""
    running = cumulative_miles(coords)
    if not running:
        return []
    total = running[-1]
    if total <= 0 or interval_miles <= 0:
        return [(0.0, coords[0])]

    marks: list[tuple[float, LatLon]] = []
    mile = 0.0
    while mile < total - 1e-9:
        marks.append((mile, point_at_miles(coords, running, mile)))
        mile += interval_miles
    if abs(marks[-1][0] - total) > 1e-6:
        marks.append((total, coords[-1]))
    return marks


def thin_polyline(coords: list, max_points: int) -> list:
    """Uniformly subsample a long polyline, always keeping the endpoints."""
    if len(coords) <= max_points:
        return coords
    stride = len(coords) / float(max_points)
    thinned = [coords[int(index * stride)] for index in range(max_points)]
    if thinned[-1] != coords[-1]:
        thinned.append(coords[-1])
    return thinned


def _offset_xy(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    x = math.radians(lon - lon0) * math.cos(math.radians((lat + lat0) / 2.0)) * EARTH_RADIUS_MILES
    y = math.radians(lat - lat0) * EARTH_RADIUS_MILES
    return x, y


def point_to_polyline_miles(point: LatLon, coords: list[LatLon]) -> float:
    if not coords:
        return float("inf")
    if len(coords) == 1:
        return haversine_miles(point, coords[0])

    lat0, lon0 = point
    px, py = 0.0, 0.0
    best = float("inf")
    for index in range(1, len(coords)):
        ax, ay = _offset_xy(coords[index - 1][0], coords[index - 1][1], lat0, lon0)
        bx, by = _offset_xy(coords[index][0], coords[index][1], lat0, lon0)
        dx, dy = bx - ax, by - ay
        seg_sq = dx * dx + dy * dy
        if seg_sq <= 1e-12:
            t = 0.0
        else:
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_sq))
        cx, cy = ax + t * dx, ay + t * dy
        distance = math.hypot(px - cx, py - cy)
        if distance < best:
            best = distance
    return best


def bounds(coords: list[LatLon]) -> Bounds:
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    return (min(lats), min(lons), max(lats), max(lons))
