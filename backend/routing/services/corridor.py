"""Corridor sample grid for the forecast heatmap."""

from __future__ import annotations

import math

from .geo import (
    MILES_PER_DEGREE_LAT,
    Bounds,
    LatLon,
    bounds,
    point_to_polyline_miles,
    thin_polyline,
)

_STEP_CANDIDATES = (
    0.1,
    0.15,
    0.2,
    0.25,
    0.3,
    0.4,
    0.5,
    0.65,
    0.8,
    1.0,
    1.25,
    1.5,
    2.0,
)


def _choose_step(area: Bounds, max_cells: int) -> float:
    lat_span = max(area[2] - area[0], 0.000001)
    lon_span = max(area[3] - area[1], 0.000001)
    budget = max(1, max_cells)
    for step in _STEP_CANDIDATES:
        rows = math.ceil(lat_span / step)
        cols = math.ceil(lon_span / step)
        if rows * cols <= budget:
            return step
    step = _STEP_CANDIDATES[-1]
    while math.ceil(lat_span / step) * math.ceil(lon_span / step) > budget:
        step *= 2
    return step


def corridor_cell_size(area: Bounds, max_cells: int) -> float:
    return _choose_step(area, max_cells)


def corridor_points(
    geometries: list[list[list[float]]],
    *,
    radius_miles: float,
    max_cells: int,
) -> tuple[list[LatLon], Bounds]:
    polylines = [
        thin_polyline([(float(lat), float(lon)) for lat, lon in geometry], 900)
        for geometry in geometries
        if geometry
    ]
    if not polylines:
        return [], (0.0, 0.0, 0.0, 0.0)

    all_coords = [point for line in polylines for point in line]
    south, west, north, east = bounds(all_coords)
    lat_padding = radius_miles / MILES_PER_DEGREE_LAT
    # Longitude degrees cover fewer miles at higher latitudes.
    latitude = min(89.0, max(abs(south), abs(north)) + lat_padding)
    lon_padding = lat_padding / math.cos(math.radians(latitude))
    padded = (
        max(-90.0, south - lat_padding), max(-180.0, west - lon_padding),
        min(90.0, north + lat_padding), min(180.0, east + lon_padding),
    )
    south, west, north, east = padded

    step = _choose_step(padded, max_cells)

    kept: list[LatLon] = []
    rows = max(1, math.ceil((north - south) / step))
    cols = max(1, math.ceil((east - west) / step))
    for row in range(rows):
        lat = min(90.0, south + (row + 0.5) * step)
        half_diagonal_miles = (
            step * MILES_PER_DEGREE_LAT / 2
            * math.sqrt(1 + math.cos(math.radians(lat)) ** 2)
        )
        for col in range(cols):
            lon = min(180.0, west + (col + 0.5) * step)
            candidate = (lat, lon)
            # Keep boundary tiles too: sampling only centres inside the buffer
            # leaves uncovered strips when a coarse tile crosses its boundary.
            if any(
                point_to_polyline_miles(candidate, line) <= radius_miles + half_diagonal_miles
                for line in polylines
            ):
                kept.append(candidate)

    return kept, padded
