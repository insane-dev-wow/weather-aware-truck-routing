"""Unit tests for the risk engine, geometry helpers and ranking logic."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from routing.constants import LEVELS
from routing.services import risk
from routing.services.corridor import corridor_cell_size, corridor_points
from routing.services.geo import (
    cumulative_miles,
    haversine_miles,
    point_to_polyline_miles,
    resample,
)
from routing.services.directions import RouteCandidate
from routing.services.geocoding import GeocodingError
from routing.services.heatmap import build_heatmap
from routing.services.planner import (
    PlanRequest,
    _segment_weights,
    _summarise_route,
    build_plan,
)
from routing.services.recommend import rank_key, recommend
from routing.services.types import GeoPoint, iso
from routing.services.weather import _parse_one, point_key, required_forecast_days
from routing.views import create_route_plan, place_suggest


class WindBandTests(SimpleTestCase):
    def test_band_edges(self):
        cases = [
            (0.0, "low"),
            (24.9, "low"),
            (25.0, "moderate"),
            (34.9, "moderate"),
            (35.0, "high"),
            (44.9, "high"),
            (45.0, "severe"),
            (54.9, "severe"),
            (55.0, "no_travel"),
            (90.0, "no_travel"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(risk.wind_level(value), expected)


class RainBandTests(SimpleTestCase):
    def test_band_edges(self):
        cases = [
            (0.0, "low"),
            (0.09, "low"),
            (0.10, "moderate"),
            (0.24, "moderate"),
            (0.25, "high"),
            (0.49, "high"),
            (0.50, "severe"),
            (1.00, "severe"),
            (1.01, "no_travel"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(risk.rain_level(value), expected)


class SnowBandTests(SimpleTestCase):
    def test_band_edges(self):
        cases = [
            (0.0, "low"),
            (0.49, "low"),
            (0.50, "moderate"),
            (0.99, "moderate"),
            (1.00, "high"),
            (1.99, "high"),
            (2.00, "severe"),
            (3.00, "severe"),
            (3.01, "no_travel"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(risk.snow_level(value), expected)


class LoadEscalationTests(SimpleTestCase):
    def test_fifty_five_mph_blocks_any_load(self):
        forced, _ = risk.load_escalation(55, 1_000)
        self.assertEqual(forced, "no_travel")

    def test_heavy_load_in_severe_wind_is_no_travel(self):
        forced, _ = risk.load_escalation(48, 30_001)
        self.assertEqual(forced, "no_travel")

    def test_exactly_thirty_thousand_is_not_escalated(self):
        forced, _ = risk.load_escalation(48, 30_000)
        self.assertIsNone(forced)

    def test_very_heavy_load_promotes_high_wind_to_severe(self):
        forced, _ = risk.load_escalation(40, 40_001)
        self.assertEqual(forced, "severe")

    def test_exactly_forty_thousand_is_not_escalated(self):
        forced, _ = risk.load_escalation(40, 40_000)
        self.assertIsNone(forced)

    def test_moderate_wind_is_never_escalated(self):
        forced, _ = risk.load_escalation(30, 80_000)
        self.assertIsNone(forced)


class ClassificationTests(SimpleTestCase):
    def test_level_is_the_worst_of_all_threats(self):
        verdict = risk.classify(wind_mph=12, rain_in_hr=0.6, snow_in_hr=0.0, load_lbs=10_000)
        self.assertEqual(verdict.level, "severe")

    def test_load_escalation_applies_on_top_of_rain(self):
        # Rain alone is only moderate; the light 38 mph wind + heavy load wins.
        verdict = risk.classify(wind_mph=38, rain_in_hr=0.15, snow_in_hr=0.0, load_lbs=45_000)
        self.assertEqual(verdict.level, "severe")
        self.assertTrue(verdict.escalations)

    def test_clear_conditions_are_low(self):
        verdict = risk.classify(wind_mph=5, rain_in_hr=0.0, snow_in_hr=0.0, load_lbs=20_000)
        self.assertEqual(verdict.level, "low")
        self.assertEqual(verdict.score, 0.0)

    def test_score_matches_level_index(self):
        for index, level in enumerate(LEVELS):
            self.assertEqual(risk.LEVEL_SCORE[level], float(index))


class GeometryTests(SimpleTestCase):
    def test_haversine_one_degree_of_latitude(self):
        distance = haversine_miles((0.0, 0.0), (1.0, 0.0))
        self.assertAlmostEqual(distance, 69.05, delta=0.5)

    def test_cumulative_and_resample(self):
        coords = [(0.0, 0.0), (1.0, 0.0)]
        running = cumulative_miles(coords)
        self.assertAlmostEqual(running[-1], 69.05, delta=0.5)

        marks = resample(coords, 25)
        self.assertEqual(marks[0][0], 0.0)
        self.assertAlmostEqual(marks[1][0], 25.0)
        self.assertAlmostEqual(marks[-1][0], running[-1], places=3)

    def test_point_to_polyline_distance(self):
        line = [(0.0, 0.0), (1.0, 0.0)]  # meridian at lon 0
        # Query sits on the equator, 0.1 degrees of longitude east of the line.
        self.assertAlmostEqual(point_to_polyline_miles((0.0, 0.1), line), 6.9, delta=0.4)

    def test_segment_weights_partition_the_route(self):
        weights = _segment_weights([0.0, 25.0, 50.0, 75.0])
        self.assertEqual(weights, [12.5, 25.0, 25.0, 12.5])
        self.assertEqual(sum(weights), 75.0)

    def test_segment_weights_cover_irregular_endpoint_once(self):
        for marks in ([0.0, 25.0, 50.0, 53.0], [0.0, 2.0], [0.0]):
            with self.subTest(marks=marks):
                self.assertAlmostEqual(sum(_segment_weights(marks)), marks[-1])


class CorridorTests(SimpleTestCase):
    def test_grid_stays_within_budget_and_covers_route(self):
        geometry = [[0.0, 0.0], [0.0, 1.0], [0.0, 2.0]]
        cells, bounds = corridor_points([geometry], radius_miles=20, max_cells=120)
        self.assertTrue(cells)
        self.assertLessEqual(len(cells), 120)
        self.assertLess(bounds[1], 0.0)
        self.assertGreater(bounds[3], 2.0)
        half = corridor_cell_size(bounds, 120) / 2
        for _, (lat, lon) in resample(geometry, 1):
            self.assertTrue(any(abs(lat - a) <= half and abs(lon - b) <= half for a, b in cells))

    def test_denver_corridor_has_no_missing_interior_tiles_at_any_budget(self):
        routes = [
            [[39.74, -104.98], [39.0, -99.0], [39.10, -94.58]],
            [[39.74, -104.98], [40.0, -99.0], [39.10, -94.58]],
        ]
        # Probe the entire corridor independently of the sampling lattice.
        probes = [
            (38.4 + row * 0.08, -105.7 + col * 0.08)
            for row in range(29) for col in range(149)
        ]
        probes = [p for p in probes if any(point_to_polyline_miles(p, line) <= 35 for line in routes)]
        for budget in (24, 120, 240, 960, 3840):
            with self.subTest(budget=budget):
                cells, area = corridor_points(routes, radius_miles=35, max_cells=budget)
                self.assertLessEqual(len(cells), budget)
                half = corridor_cell_size(area, budget) / 2
                for lat, lon in probes:
                    self.assertTrue(
                        any(abs(lat - a) <= half + 1e-6 and abs(lon - b) <= half + 1e-6 for a, b in cells),
                        f"Uncovered forecast area at {lat}, {lon}",
                    )

    def test_large_area_can_coarsen_beyond_old_two_degree_limit(self):
        geometry = [[30, -120], [55, -60]]
        cells, area = corridor_points([geometry], radius_miles=35, max_cells=16)
        self.assertLessEqual(len(cells), 16)
        self.assertGreater(corridor_cell_size(area, 16), 2)

    def test_denser_denver_grid_halves_tile_width(self):
        routes = [[[39.74, -104.98], [39.0, -99.0], [39.10, -94.58]]]
        cells, area = corridor_points(routes, radius_miles=35, max_cells=960)
        self.assertLessEqual(len(cells), 960)
        self.assertLessEqual(corridor_cell_size(area, 960), corridor_cell_size(area, 240) / 2)
        self.assertEqual(corridor_cell_size(area, 3840), 0.1)

    def test_empty_geometry_returns_no_forecast_cells(self):
        self.assertEqual(corridor_points([], radius_miles=35, max_cells=240), ([], (0, 0, 0, 0)))


def _route(route_id, **overrides):
    base = {
        "id": route_id,
        "label": f"Route {route_id}",
        "no_travel_miles": 0.0,
        "severe_miles": 0.0,
        "high_miles": 0.0,
        "avg_score": 0.0,
        "duration_hours": 10.0,
    }
    base.update(overrides)
    return base


class RecommendationTests(SimpleTestCase):
    def test_severe_miles_outrank_everything_else(self):
        fast_but_risky = _route("a", severe_miles=40.0, duration_hours=8.0)
        slow_but_safe = _route("b", severe_miles=2.0, duration_hours=12.0)
        result = recommend([fast_but_risky, slow_but_safe])
        self.assertEqual(result["route_id"], "b")
        self.assertEqual(result["rank"]["b"], 1)

    def test_no_travel_miles_are_disqualifying(self):
        short_dangerous = _route("a", no_travel_miles=5.0, duration_hours=6.0)
        long_clear = _route("b", duration_hours=14.0)
        result = recommend([short_dangerous, long_clear])
        self.assertEqual(result["route_id"], "b")

    def test_average_risk_breaks_a_high_mile_tie(self):
        alpha = _route("a", high_miles=10.0, avg_score=1.5)
        beta = _route("b", high_miles=10.0, avg_score=1.1)
        result = recommend([alpha, beta])
        self.assertEqual(result["route_id"], "b")

    def test_travel_time_is_the_final_tie_breaker(self):
        alpha = _route("a", duration_hours=9.0)
        beta = _route("b", duration_hours=8.0)
        result = recommend([alpha, beta])
        self.assertEqual(result["route_id"], "b")

    def test_rank_key_is_stable_and_ordered(self):
        keys = sorted(
            [rank_key(_route("a", severe_miles=1.0)), rank_key(_route("b"))]
        )
        self.assertEqual(keys[0], rank_key(_route("b")))


def _summary(levels, miles=None):
    miles = miles or [25.0 * index for index in range(len(levels))]
    checkpoints = [
        {"index": index, "assessment": (
            risk.RiskAssessment(level, risk.LEVEL_SCORE[level]) if level else None
        )}
        for index, level in enumerate(levels)
    ]
    return _summarise_route(None, _segment_weights(miles), checkpoints)


class ForecastCoverageTests(SimpleTestCase):
    def test_unknown_weather_is_not_summarized_as_low_risk(self):
        summary = _summary([None, None, None, None])
        self.assertIsNone(summary["avg_score"])
        self.assertEqual(summary["max_level"], "unknown")
        self.assertFalse(summary["viable"])
        self.assertFalse(summary["eligible_for_recommendation"])
        self.assertEqual(summary["forecast_coverage_pct"], 0)
        self.assertEqual(summary["unknown_miles"], 75)

    def test_partial_forecast_tracks_unknown_miles_and_is_excluded(self):
        incomplete = _summary(["low", None, "low"])
        complete = _summary(["high", "high", "high"])
        self.assertEqual(incomplete["known_miles"], 25)
        self.assertEqual(incomplete["unknown_miles"], 25)
        self.assertEqual(incomplete["forecast_coverage_pct"], 50)
        self.assertEqual(incomplete["scored_checkpoint_count"], 2)
        result = recommend([_route("unknown", **incomplete), _route("covered", **complete)])
        self.assertEqual(result["route_id"], "covered")
        self.assertEqual(result["status"], "recommended")
        self.assertEqual(result["order"], ["covered", "unknown"])
        self.assertIsNone(result["criteria"][0]["values"]["unknown"])

    def test_no_recommendation_when_all_routes_lack_forecast_coverage(self):
        result = recommend([
            _route("a", **_summary([None, None])),
            _route("b", **_summary(["low", None])),
        ])
        self.assertEqual(result["status"], "insufficient_forecast")
        self.assertIsNone(result["route_id"])
        self.assertIsNone(result["label"])
        self.assertTrue(all(item["winner"] is None for item in result["criteria"]))

    def test_even_a_rounded_zero_no_travel_segment_blocks_recommendation(self):
        summary = _summary(["low", "no_travel"], [0.0, 0.01])
        self.assertEqual(summary["no_travel_miles"], 0)
        self.assertFalse(summary["viable"])
        result = recommend([_route("blocked", **summary)])
        self.assertEqual(result["status"], "blocked")
        safe_result = recommend([
            _route("blocked", **summary),
            _route("safe", **_summary(["severe", "severe"])),
        ])
        self.assertEqual(safe_result["route_id"], "safe")

    def test_endpoint_exposure_does_not_outrank_larger_interior_exposure(self):
        endpoint = _summary(["severe", "low", "low", "low"])
        interior = _summary(["low", "severe", "low", "low"], [0, 20, 40, 60])
        self.assertEqual(endpoint["severe_miles"], 12.5)
        self.assertEqual(interior["severe_miles"], 20)
        result = recommend([_route("endpoint", **endpoint), _route("interior", **interior)])
        self.assertEqual(result["route_id"], "endpoint")


def _hourly_raw(**overrides):
    hourly = {
        "time": ["2026-10-13T10:00", "2026-10-13T11:00", "2026-10-13T12:00"],
        "wind_speed_10m": [5, 5, 5],
        "rain": [0, 0, 0],
        "showers": [0, 0, 0],
        "snowfall": [0, 0, 0],
        "precipitation": [0, 0, 0],
        "temperature_2m": [65, 65, 65],
        "weather_code": [0, 0, 0],
    }
    hourly.update(overrides)
    return {"hourly": hourly}


class WeatherInterpretationTests(SimpleTestCase):
    moment = datetime(2026, 10, 13, 10, 45, tzinfo=timezone.utc)

    def test_convective_showers_contribute_to_rain_risk(self):
        series = _parse_one(_hourly_raw(rain=[0.01] * 3, showers=[0.60] * 3), (0, 0))
        reading = series.at(self.moment)
        self.assertAlmostEqual(reading["rain_in_hr"], 0.61)
        assessment = risk.classify(
            wind_mph=reading["wind_mph"], rain_in_hr=reading["rain_in_hr"],
            snow_in_hr=reading["snow_in_hr"], load_lbs=10000,
        )
        self.assertEqual(assessment.level, "severe")

    def test_arrival_uses_covering_precipitation_interval_and_prior_wind_instant(self):
        series = _parse_one(_hourly_raw(
            wind_speed_10m=[10, 60, 5], rain=[0, 0.6, 0], snowfall=[0, 1.5, 0],
        ), (0, 0))
        reading = series.at(self.moment)
        self.assertEqual(reading["wind_mph"], 10)
        self.assertEqual(reading["rain_in_hr"], 0.6)
        self.assertEqual(reading["snow_in_hr"], 1.5)
        exact_hour = series.at(self.moment.replace(minute=0))
        self.assertEqual(exact_hour["rain_in_hr"], 0)
        local = self.moment.astimezone(timezone(timedelta(hours=-4)))
        self.assertEqual(series.at(local), reading)

    def test_null_risk_inputs_cannot_be_classified_as_clear(self):
        for variable in ("wind_speed_10m", "rain", "showers", "snowfall"):
            with self.subTest(variable=variable):
                series = _parse_one(_hourly_raw(**{variable: [None] * 3}), (0, 0))
                self.assertIsNone(series.at(self.moment))

    def test_short_missing_or_nonfinite_risk_arrays_are_unknown(self):
        for values in ([], [0], [float("nan")] * 3, [float("inf")] * 3):
            with self.subTest(values=values):
                self.assertIsNone(_parse_one(_hourly_raw(rain=values), (0, 0)).at(self.moment))

    def test_missing_optional_conditions_are_not_fabricated_as_clear_sky(self):
        series = _parse_one(_hourly_raw(temperature_2m=[None] * 3, weather_code=[None] * 3), (0, 0))
        reading = series.at(self.moment)
        self.assertIsNone(reading["temp_f"])
        self.assertIsNone(reading["weather_code"])
        self.assertEqual(reading["weather"], "Unknown")

    def test_missing_covering_interval_is_unknown(self):
        series = _parse_one(_hourly_raw(), (0, 0))
        self.assertIsNone(series.at(self.moment.replace(hour=12)))

    def test_forecast_days_include_next_day_precipitation_bucket(self):
        now = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
        with patch("routing.services.weather.datetime", wraps=datetime) as clock:
            clock.now.return_value = now
            depart = now.replace(hour=23, minute=30)
            self.assertEqual(required_forecast_days(depart, 48), 4)
            self.assertEqual(required_forecast_days(depart, 24 * 30), 16)


class HeatmapForecastTests(SimpleTestCase):
    def test_full_48_hour_horizon_is_inclusive_and_anchored_to_departure(self):
        depart = datetime(2026, 10, 13, 10, 45, tzinfo=timezone.utc)
        heatmap = build_heatmap([(0, 0)], {}, depart, 48, 10000, (0, 0, 1, 1))
        self.assertEqual(len(heatmap["hours"]), 49)
        self.assertEqual(heatmap["hours"][0], iso(depart))
        self.assertEqual(heatmap["hours"][-1], iso(depart + timedelta(hours=48)))
        self.assertEqual(heatmap["reference_time"], iso(depart))
        self.assertEqual(heatmap["horizon_hours"], 48)
        self.assertEqual(heatmap["cells"][0]["scores"], [None] * 49)
        self.assertGreater(heatmap["cell_size_degrees"], 0)

    def test_heatmap_uses_the_same_load_rules_and_preserves_unknown_hours(self):
        depart = datetime(2026, 10, 13, 10, tzinfo=timezone.utc)
        series = _parse_one(_hourly_raw(wind_speed_10m=[40, 40, None]), (0, 0))
        heatmap = build_heatmap([(0, 0)], {point_key(0, 0): series}, depart, 2, 45000, (0, 0, 1, 1))
        self.assertEqual(heatmap["cells"][0]["scores"], [3, 3, None])


class PlanCoverageIntegrationTests(SimpleTestCase):
    def test_later_storm_only_affects_route_when_arrival_overlaps_it(self):
        departure = datetime(2026, 10, 13, 10, tzinfo=timezone.utc)
        storm = departure + timedelta(hours=45)
        route = RouteCandidate("route-1", "Route A", "Test road", 35, 1, [[40, -75], [40.5, -75]])

        def reading(moment):
            return {"wind_mph": 50 if moment >= storm else 9.6,
                    "rain_in_hr": 0, "snow_in_hr": 0, "temp_f": 60,
                    "weather": "Test forecast", "weather_code": 0}

        def forecasts(points, days):
            return {point_key(lat, lon): SimpleNamespace(at=reading) for lat, lon in points}

        def plan_at(moment):
            with patch("routing.services.planner.geocode", side_effect=[
                GeoPoint("origin", "Origin", 40, -75),
                GeoPoint("destination", "Destination", 40.5, -75),
            ]), patch("routing.services.planner.build_candidates", return_value=[route]), \
                 patch("routing.services.planner.fetch_series", side_effect=forecasts):
                return build_plan(PlanRequest("origin", "destination", moment, 44000, 25))

        early = plan_at(departure)
        self.assertEqual(early["routes"][0]["avg_score"], 0)
        self.assertTrue(all(cp["level"] == "low" for cp in early["routes"][0]["checkpoints"]))
        self.assertTrue(all(cell["scores"][45] == 4 for cell in early["heatmap"]["cells"]))
        late = plan_at(storm)
        self.assertEqual(late["routes"][0]["avg_score"], 4)
        self.assertEqual(late["recommendation"]["status"], "blocked")

    def test_place_search_provider_failure_is_not_reported_as_no_matches(self):
        request = APIRequestFactory().get("/api/places/", {"q": "Denver"})
        with patch("routing.views.suggest", side_effect=GeocodingError("Location search is temporarily unavailable.")):
            response = place_suggest(request)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data, {"detail": "Location search is temporarily unavailable."})

    def test_plan_with_missing_forecasts_does_not_recommend_and_reports_shortfall(self):
        origin = GeoPoint("origin", "Origin", 40, -75)
        destination = GeoPoint("destination", "Destination", 40.5, -75)
        route = RouteCandidate("route-1", "Route A", "Test road", 35, 1, [[40, -75], [40.5, -75]])
        request = PlanRequest("origin", "destination", datetime(2026, 10, 13, 10, tzinfo=timezone.utc), 10000, 25)
        with patch("routing.services.planner.geocode", side_effect=[origin, destination]), \
             patch("routing.services.planner.build_candidates", return_value=[route]), \
             patch("routing.services.planner.corridor_points", return_value=([(40, -75)], (40, -75, 40.5, -75))), \
             patch("routing.services.planner.fetch_series", return_value={}):
            result = build_plan(request)
        self.assertEqual(result["recommendation"]["status"], "insufficient_forecast")
        self.assertIsNone(result["recommendation"]["route_id"])
        self.assertTrue(all(item["level"] == "unknown" for item in result["routes"][0]["checkpoints"]))
        self.assertEqual(len(result["heatmap"]["hours"]), 49)
        self.assertTrue(any("1 of 3 route options available" in warning for warning in result["warnings"]))

    def test_unavailable_recommendation_can_be_saved_without_null_database_label(self):
        now = datetime(2026, 10, 13, 10, tzinfo=timezone.utc)
        request = APIRequestFactory().post("/api/route-plans/", {
            "origin": "Denver", "destination": "Kansas City", "depart_at": iso(now), "load_lbs": 10000,
        }, format="json")
        with patch("routing.views.build_plan", return_value={"recommendation": {"label": None, "route_id": None, "status": "insufficient_forecast"}}), \
             patch("routing.views.RoutePlan.objects.create", return_value=SimpleNamespace(id=1, created_at=now)) as save:
            response = create_route_plan(request)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(save.call_args.kwargs["recommended_route"], "")
