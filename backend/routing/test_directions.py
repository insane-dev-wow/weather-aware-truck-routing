from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from routing.services.directions import (
    DirectionsError,
    RouteCandidate,
    _is_duplicate,
    build_candidates,
)
from routing.services.types import GeoPoint


def candidate(geometry, miles=10.0):
    return RouteCandidate("", "", "Local roads", miles, 0.3, geometry)


def provider_route(geometry, miles=10.0, hours=0.3):
    return {
        "geometry": {"coordinates": [[lon, lat] for lat, lon in geometry]},
        "distance": miles * 1609.344,
        "duration": hours * 3600,
        "legs": [],
    }


class RouteDistinctnessTests(SimpleTestCase):
    def test_nearby_local_alternatives_are_preserved(self):
        primary = candidate([[0, 0], [0, 0.07], [0, 0.14]])
        alternative = candidate([[0, 0], [0.006, 0.07], [0, 0.14]], 10.05)
        self.assertFalse(_is_duplicate(alternative, [primary]))

    def test_identical_route_with_coordinate_noise_is_rejected(self):
        primary = candidate([[0, 0], [0, 0.07], [0, 0.14]])
        noisy = candidate([[0, 0], [0.000001, 0.07], [0, 0.14]], 10.001)
        self.assertTrue(_is_duplicate(noisy, [primary]))

    def test_nearly_same_corridor_is_not_counted_twice_despite_different_metrics(self):
        primary = candidate([[0, 0], [0, 0.07], [0, 0.14], [0, 0.141]], 10)
        variant = candidate([[0, 0], [0, 0.07], [0, 0.14], [0.001, 0.141], [0, 0.141]], 11)
        self.assertTrue(_is_duplicate(variant, [primary]))


@override_settings(ROUTING_PROVIDER="osrm")
class NativeCandidateTests(SimpleTestCase):
    def setUp(self):
        self.origin = GeoPoint("start", "Start", 0, 0)
        self.destination = GeoPoint("end", "End", 0, 0.14)
        self.primary = provider_route([[0, 0], [0, 0.07], [0, 0.14]])
        self.north = [[0, 0], [0.006, 0.07], [0, 0.14]]
        self.south = [[0, 0], [-0.006, 0.07], [0, 0.14]]

    @patch("routing.services.directions._request_routes")
    def test_three_native_alternatives_keep_ids_and_distance_order(self, request):
        request.return_value = [
            provider_route(self.south, 10.2),
            self.primary,
            provider_route(self.north, 10.1),
        ]
        result = build_candidates(self.origin, self.destination)
        self.assertEqual([route.key for route in result], ["route-1", "route-2", "route-3"])
        self.assertEqual([route.label for route in result], ["Route A", "Route B", "Route C"])
        self.assertEqual([round(route.distance_miles, 1) for route in result], [10, 10.1, 10.2])
        request.assert_called_once_with([self.origin, self.destination], alternatives=True)

    @patch("routing.services.directions._request_routes")
    def test_one_native_route_never_triggers_synthetic_waypoint_requests(self, request):
        request.return_value = [self.primary]
        result = build_candidates(self.origin, self.destination)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].geometry, [[0, 0], [0, 0.07], [0, 0.14]])
        request.assert_called_once_with([self.origin, self.destination], alternatives=True)

    @patch("routing.services.directions._request_routes")
    def test_two_native_routes_are_not_padded_to_three(self, request):
        request.return_value = [self.primary, provider_route(self.north, 10.1)]
        self.assertEqual(len(build_candidates(self.origin, self.destination)), 2)
        request.assert_called_once_with([self.origin, self.destination], alternatives=True)

    @patch("routing.services.directions._request_routes")
    def test_duplicates_and_bad_routes_do_not_hide_later_valid_options(self, request):
        request.return_value = [
            self.primary,
            self.primary,
            provider_route(self.north, 20),
            provider_route(self.north, 10.1, hours=0.8),
            provider_route(self.north, 10.1),
            provider_route(self.south, 10.2),
        ]
        self.assertEqual(len(build_candidates(self.origin, self.destination)), 3)
        request.assert_called_once()

    @patch("routing.services.directions._request_routes")
    def test_requested_candidate_limit_is_respected(self, request):
        request.return_value = [
            self.primary,
            provider_route(self.north, 10.1),
            provider_route(self.south, 10.2),
        ]
        self.assertEqual(len(build_candidates(self.origin, self.destination, count=2)), 2)

    @patch("routing.services.directions._request_routes")
    def test_excessive_native_distance_is_rejected(self, request):
        request.return_value = [self.primary, provider_route(self.north, 16, hours=0.4)]
        self.assertEqual(len(build_candidates(self.origin, self.destination)), 1)

    @patch("routing.services.directions._request_routes")
    def test_small_distance_detour_with_double_driving_time_is_rejected(self, request):
        request.return_value = [self.primary, provider_route(self.north, 11, hours=0.61)]
        self.assertEqual(len(build_candidates(self.origin, self.destination)), 1)

    @patch("routing.services.directions._request_routes")
    def test_fastest_valid_route_is_baseline_even_if_provider_returns_it_later(self, request):
        request.return_value = [provider_route(self.north, 9, hours=0.8), self.primary]
        result = build_candidates(self.origin, self.destination)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0].duration_hours, 0.3)

    @patch("routing.services.directions._request_routes")
    def test_large_out_and_back_spur_is_rejected_within_distance_and_time_limits(self, request):
        spur = [
            [0, 0], [0, 0.04], [0.015, 0.04], [0.03, 0.04],
            [0.015, 0.04], [0, 0.04], [0, 0.14],
        ]
        request.return_value = [self.primary, provider_route(spur, 14.0, hours=0.4)]
        self.assertEqual(len(build_candidates(self.origin, self.destination)), 1)

    @patch("routing.services.directions._request_routes")
    def test_retracing_route_cannot_be_fastest_baseline(self, request):
        spur = [
            [0, 0], [0, 0.04], [0.015, 0.04], [0.03, 0.04],
            [0.015, 0.04], [0, 0.04], [0, 0.14],
        ]
        request.return_value = [provider_route(spur, 14.0, hours=0.05), self.primary]
        result = build_candidates(self.origin, self.destination)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].geometry, [[0, 0], [0, 0.07], [0, 0.14]])

    @patch("routing.services.directions._request_routes")
    def test_small_access_road_retrace_is_preserved(self, request):
        access = [[0, 0], [0, 0.0002], [0, 0], [0.006, 0.07], [0, 0.14]]
        request.return_value = [self.primary, provider_route(access, 10.1)]
        self.assertEqual(len(build_candidates(self.origin, self.destination)), 2)

    @patch("routing.services.directions._request_routes")
    def test_winding_route_without_retracing_is_preserved(self, request):
        winding = [[0, 0], [0.015, 0.04], [-0.01, 0.08], [0.015, 0.10], [0, 0.14]]
        request.return_value = [self.primary, provider_route(winding, 12, hours=0.4)]
        self.assertEqual(len(build_candidates(self.origin, self.destination)), 2)

    @patch("routing.services.directions._request_routes")
    def test_duplicate_adjacent_vertices_do_not_count_as_retracing(self, request):
        geometry = [[0, 0], [0, 0], [0.006, 0.07], [0.006, 0.07], [0, 0.14]]
        request.return_value = [self.primary, provider_route(geometry, 10.1)]
        self.assertEqual(len(build_candidates(self.origin, self.destination)), 2)

    @patch("routing.services.directions._request_routes")
    def test_invalid_provider_candidates_are_skipped(self, request):
        malformed = [
            provider_route([]),
            provider_route([[0, 0]]),
            provider_route([[0, 0], [float("nan"), 0.14]]),
            provider_route([[0, 0], [91, 0.14]]),
            provider_route([[0, 0], [0, 181]]),
            provider_route(self.north, miles=0),
            provider_route(self.north, miles=-1),
            provider_route(self.north, miles=float("inf")),
            provider_route(self.north, hours=0),
            provider_route(self.north, hours=-1),
            provider_route(self.north, hours=float("nan")),
        ]
        for bad_route in malformed:
            with self.subTest(route=bad_route):
                request.return_value = [bad_route, self.primary]
                self.assertEqual(len(build_candidates(self.origin, self.destination)), 1)

    @patch("routing.services.directions._request_routes")
    def test_all_invalid_provider_candidates_raise_directions_error(self, request):
        request.return_value = [provider_route([]), provider_route(self.north, hours=0)]
        with self.assertRaises(DirectionsError):
            build_candidates(self.origin, self.destination)

    @patch("routing.services.directions._request_routes")
    def test_identical_origin_and_destination_are_rejected_before_request(self, request):
        with self.assertRaises(DirectionsError):
            build_candidates(self.origin, self.origin)
        request.assert_not_called()
