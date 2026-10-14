"""Corridor forecast heatmap payload."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings

from ..constants import LEVEL_COLORS, LEVELS
from .corridor import corridor_cell_size
from .risk import classify
from .types import iso, to_utc
from .weather import point_key


def build_heatmap(cells, series, depart: datetime, hours: int, load_lbs: float, bbox) -> dict:
    depart = to_utc(depart)
    hour_starts = [depart + timedelta(hours=offset) for offset in range(hours + 1)]

    payload_cells = []
    for lat, lon in cells:
        item = series.get(point_key(lat, lon))
        scores: list[float | None] = []
        for moment in hour_starts:
            reading = item.at(moment) if item else None
            if reading is None:
                scores.append(None)
                continue
            scores.append(
                classify(
                    wind_mph=reading["wind_mph"],
                    rain_in_hr=reading["rain_in_hr"],
                    snow_in_hr=reading["snow_in_hr"],
                    load_lbs=load_lbs,
                ).score
            )

        payload_cells.append({"lat": round(lat, 6), "lon": round(lon, 6), "scores": scores})

    return {
        "hours": [iso(moment) for moment in hour_starts],
        "reference_time": iso(depart),
        "horizon_hours": hours,
        "cell_size_degrees": corridor_cell_size(bbox, settings.HEATMAP_MAX_CELLS),
        "levels": list(LEVELS),
        "colors": LEVEL_COLORS,
        "radius_miles": settings.HEATMAP_CORRIDOR_RADIUS_MILES,
        "bbox": [round(value, 4) for value in bbox],
        "cells": payload_cells,
    }
