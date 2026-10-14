"""Orchestrate geocoding, routing, weather, risk, and recommendation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings

from ..constants import HEATMAP_HOURS, LEVEL_LABELS, LEVELS, ROUTE_OPTION_COUNT
from .corridor import corridor_points
from .directions import build_candidates
from .geo import resample, thin_polyline
from .geocoding import geocode
from .heatmap import build_heatmap
from .recommend import is_blocked, recommend
from .risk import RiskAssessment, classify
from .types import iso, to_utc
from .weather import fetch_series, point_key, required_forecast_days

_GEOMETRY_POINTS = 700


@dataclass
class PlanRequest:
    origin: str
    destination: str
    depart_at: datetime
    load_lbs: float
    sample_interval_miles: int
    heatmap_hours: int = HEATMAP_HOURS


def _segment_weights(miles: list[float]) -> list[float]:
    count = len(miles)
    if count == 0:
        return []
    if count == 1:
        return [0.0]

    weights: list[float] = []
    for index in range(count):
        if index == 0:
            span = (miles[1] - miles[0]) / 2.0
        elif index == count - 1:
            span = (miles[-1] - miles[-2]) / 2.0
        else:
            span = (miles[index + 1] - miles[index - 1]) / 2.0
        weights.append(max(span, 0.0))
    return weights


def _checkpoint_payload(checkpoint: dict, weight_miles: float) -> dict:
    assessment: RiskAssessment | None = checkpoint["assessment"]
    reading: dict | None = checkpoint["reading"]
    eta: datetime = checkpoint["eta"]

    payload = {
        "index": checkpoint["index"],
        "mile": round(checkpoint["mile"], 1),
        "lat": round(checkpoint["lat"], 5),
        "lon": round(checkpoint["lon"], 5),
        "eta": iso(eta),
        "eta_label": eta.strftime("%a %b %d \u00b7 %H:%MZ"),
        "weight_miles": round(weight_miles, 1),
    }

    if assessment is None or reading is None:
        payload.update(
            {
                "level": "unknown",
                "level_label": "No forecast",
                "score": None,
                "headline": "Forecast unavailable or incomplete at this arrival time",
                "factors": [],
                "escalations": [],
                "wind_mph": None,
                "rain_in_hr": None,
                "snow_in_hr": None,
                "temp_f": None,
                "weather": "Unavailable",
                "weather_code": None,
            }
        )
        return payload

    payload.update(
        {
            "level": assessment.level,
            "level_label": LEVEL_LABELS[assessment.level],
            "score": assessment.score,
            "headline": assessment.headline,
            "factors": [factor.as_dict() for factor in assessment.factors],
            "escalations": assessment.escalations,
            "wind_mph": round(reading["wind_mph"], 1),
            "rain_in_hr": round(reading["rain_in_hr"], 3),
            "snow_in_hr": round(reading["snow_in_hr"], 3),
            "temp_f": round(reading["temp_f"], 1) if reading["temp_f"] is not None else None,
            "weather": reading["weather"],
            "weather_code": reading["weather_code"],
        }
    )
    return payload


def _summarise_route(candidate, weight_miles: list[float], checkpoints: list[dict]) -> dict:
    miles_by_level = {level: 0.0 for level in LEVELS}
    counts = {level: 0 for level in LEVELS}
    weighted_score = 0.0
    total_weight = 0.0
    worst_index: int | None = None
    worst_score = -1.0

    for checkpoint, weight in zip(checkpoints, weight_miles):
        assessment = checkpoint["assessment"]
        if assessment is None:
            continue
        level = assessment.level
        counts[level] += 1
        miles_by_level[level] += weight
        weighted_score += assessment.score * weight
        total_weight += weight
        if assessment.score > worst_score:
            worst_score = assessment.score
            worst_index = checkpoint["index"]

    scored_count = sum(counts.values())
    complete = bool(checkpoints) and scored_count == len(checkpoints)
    all_miles = sum(weight_miles)
    coverage = total_weight / all_miles if all_miles else (
        scored_count / len(checkpoints) if checkpoints else 0.0
    )
    avg_score = weighted_score / total_weight if total_weight else None
    max_level = "unknown"
    if worst_index is not None:
        max_level = checkpoints[worst_index]["assessment"].level
        if avg_score is None:
            avg_score = checkpoints[worst_index]["assessment"].score
    viable = complete and counts["no_travel"] == 0

    return {
        "no_travel_miles": round(miles_by_level["no_travel"], 1),
        "severe_miles": round(miles_by_level["severe"], 1),
        "high_miles": round(miles_by_level["high"], 1),
        "moderate_miles": round(miles_by_level["moderate"], 1),
        "low_miles": round(miles_by_level["low"], 1),
        "avg_score": round(avg_score, 3) if avg_score is not None else None,
        "max_level": max_level,
        "worst_checkpoint_index": worst_index,
        "viable": viable,
        "eligible_for_recommendation": viable,
        "forecast_complete": complete,
        "forecast_coverage_pct": round(coverage * 100, 1),
        "known_miles": round(total_weight, 1),
        "unknown_miles": round(max(all_miles - total_weight, 0.0), 1),
        "scored_checkpoint_count": scored_count,
        "counts": counts,
        "checkpoint_count": len(checkpoints),
    }


def build_plan(request: PlanRequest) -> dict:
    origin = geocode(request.origin)
    destination = geocode(request.destination)
    candidates = build_candidates(origin, destination, ROUTE_OPTION_COUNT)

    depart = to_utc(request.depart_at)
    sample = max(1, int(request.sample_interval_miles))
    hours = max(6, min(int(request.heatmap_hours), HEATMAP_HOURS))

    routes: list[dict] = []
    weather_points: list[tuple[float, float]] = []

    for candidate in candidates:
        coordinates = [(float(lat), float(lon)) for lat, lon in candidate.geometry]
        marks = resample(coordinates, sample)
        geometry_miles = marks[-1][0] if marks else 0.0

        checkpoints = []
        for index, (mile, (lat, lon)) in enumerate(marks):
            fraction = (mile / geometry_miles) if geometry_miles > 0 else 0.0
            checkpoints.append(
                {
                    "index": index,
                    "mile": mile,
                    "lat": lat,
                    "lon": lon,
                    "eta": depart + timedelta(hours=candidate.duration_hours * fraction),
                    "reading": None,
                    "assessment": None,
                }
            )
            weather_points.append((lat, lon))

        routes.append({"candidate": candidate, "checkpoints": checkpoints})

    cells, corridor_bounds = corridor_points(
        [route["candidate"].geometry for route in routes],
        radius_miles=settings.HEATMAP_CORRIDOR_RADIUS_MILES,
        max_cells=settings.HEATMAP_MAX_CELLS,
    )
    weather_points.extend(cells)

    longest = max((route["candidate"].duration_hours for route in routes), default=0.0)
    days = required_forecast_days(depart, max(longest, hours))
    series = fetch_series(weather_points, days)

    warnings: list[str] = []
    if len(candidates) < ROUTE_OPTION_COUNT:
        warnings.append(
            f"{len(candidates)} of {ROUTE_OPTION_COUNT} route options available. "
            "The routing service has no more distinct alternatives within the route-quality limits."
        )
    for route in routes:
        missing = 0
        for checkpoint in route["checkpoints"]:
            item = series.get(point_key(checkpoint["lat"], checkpoint["lon"]))
            reading = item.at(checkpoint["eta"]) if item else None
            if reading is None:
                missing += 1
                continue
            checkpoint["reading"] = reading
            checkpoint["assessment"] = classify(
                wind_mph=reading["wind_mph"],
                rain_in_hr=reading["rain_in_hr"],
                snow_in_hr=reading["snow_in_hr"],
                load_lbs=request.load_lbs,
            )
        if missing:
            warnings.append(
                f"{route['candidate'].label}: {missing} checkpoint(s) have missing or incomplete "
                "arrival-time forecasts. This route is excluded from recommendation."
            )

    summaries: list[dict] = []
    for route in routes:
        candidate = route["candidate"]
        checkpoints = route["checkpoints"]
        weights = _segment_weights([checkpoint["mile"] for checkpoint in checkpoints])
        summary = _summarise_route(candidate, weights, checkpoints)

        summaries.append(
            {
                "id": candidate.key,
                "label": candidate.label,
                "summary": candidate.summary,
                "distance_miles": round(candidate.distance_miles, 1),
                "duration_hours": round(candidate.duration_hours, 2),
                "avg_speed_mph": round(candidate.avg_speed_mph, 1),
                "depart_at": iso(depart),
                "arrive_at": iso(depart + timedelta(hours=candidate.duration_hours)),
                "geometry": thin_polyline(candidate.geometry, _GEOMETRY_POINTS),
                "checkpoints": [
                    _checkpoint_payload(checkpoint, weight)
                    for checkpoint, weight in zip(checkpoints, weights)
                ],
                **summary,
            }
        )

    recommendation = recommend(summaries)
    if summaries and all(is_blocked(route) for route in summaries):
        warnings.append(
            "Every route option includes No-Travel conditions. Strongly consider "
            "shifting the departure time or splitting the trip."
        )

    return {
        "request": {
            "origin": request.origin,
            "destination": request.destination,
            "depart_at": iso(depart),
            "load_lbs": request.load_lbs,
            "sample_interval_miles": sample,
            "heatmap_hours": hours,
        },
        "origin": origin.as_dict(),
        "destination": destination.as_dict(),
        "routing": {
            "provider": settings.ROUTING_PROVIDER,
            "provider_label": "Valhalla" if settings.ROUTING_PROVIDER == "valhalla" else "OSRM",
            "requested_routes": ROUTE_OPTION_COUNT,
            "returned_routes": len(summaries),
        },
        "routes": summaries,
        "recommendation": recommendation,
        "heatmap": build_heatmap(cells, series, depart, hours, request.load_lbs, corridor_bounds),
        "warnings": warnings,
    }
