from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from routing.services.directions import DirectionsError, build_candidates
from routing.services.types import GeoPoint
from routing.test_directions import provider_route


def response(routes):
    result = Mock()
    result.json.return_value = {"code": "Ok", "routes": routes}
    return result


@override_settings(
    ROUTING_PROVIDER="valhalla",
    VALHALLA_BASE_URL="https://routing.example.test",
    ROUTING_CLIENT_ID="wayline-test",
    UPSTREAM_TIMEOUT=10,
    ROUTING_TIMEOUT=15,
)
class ValhallaRoutingTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        # Keep the real rate limiter out of deterministic HTTP adapter tests.
        self.clock = patch("routing.services.directions.time.monotonic", side_effect=range(100, 1000, 2))
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.last_start = patch("routing.services.directions._valhalla_last_start", 0)
        self.last_start.start()
        self.addCleanup(self.last_start.stop)
        self.origin = GeoPoint("Start", "Start", 0, 0)
        self.destination = GeoPoint("End", "End", 0, 0.14)
        self.primary = provider_route([[0, 0], [0, 0.07], [0, 0.14]], 10, 0.3)
        self.north = provider_route([[0, 0], [0.02, 0.07], [0, 0.14]], 11, 0.35)
        self.south = provider_route([[0, 0], [-0.02, 0.07], [0, 0.14]], 12, 0.4)

    @patch("routing.services.directions.requests.post")
    def test_three_native_routes_need_one_request(self, post):
        post.return_value = response([self.primary, self.north, self.south])
        routes = build_candidates(self.origin, self.destination)
        self.assertEqual(len(routes), 3)
        post.assert_called_once_with(
            "https://routing.example.test/route",
            json={
                "locations": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 0.14}],
                "costing": "auto",
                "alternates": 2,
                "format": "osrm",
                "shape_format": "geojson",
                "costing_options": {"auto": {"shortest": False}},
            },
            headers={"X-Client-Id": "wayline-test"},
            timeout=15,
        )
        self.assertEqual(routes[0].geometry, [[0, 0], [0, 0.07], [0, 0.14]])
        self.assertAlmostEqual(routes[0].distance_miles, 10)
        self.assertAlmostEqual(routes[0].duration_hours, 0.3)

    @patch("routing.services.directions.requests.post")
    def test_distance_search_supplies_third_genuine_route_without_waypoints(self, post):
        post.side_effect = [
            response([self.primary, self.north]),
            response([self.primary, self.north, self.south]),
        ]
        routes = build_candidates(self.origin, self.destination)
        self.assertEqual(len(routes), 3)
        self.assertEqual(post.call_count, 2)
        for call in post.call_args_list:
            self.assertEqual(call.kwargs["json"]["locations"], [
                {"lat": 0, "lon": 0}, {"lat": 0, "lon": 0.14},
            ])
        self.assertTrue(post.call_args.kwargs["json"]["costing_options"]["auto"]["shortest"])
        self.assertEqual(routes[2].geometry, [[0, 0], [-0.02, 0.07], [0, 0.14]])

    @patch("routing.services.directions.requests.post")
    def test_both_searches_are_cached_separately(self, post):
        post.side_effect = [response([self.primary]), response([self.north, self.south])]
        first = build_candidates(self.origin, self.destination)
        second = build_candidates(self.origin, self.destination)
        self.assertEqual(first, second)
        self.assertEqual(len(second), 3)
        self.assertEqual(post.call_count, 2)

    @patch("routing.services.directions.requests.post")
    def test_same_path_from_second_search_is_not_a_third_option(self, post):
        post.side_effect = [response([self.primary, self.north]), response([self.primary])]
        self.assertEqual(len(build_candidates(self.origin, self.destination)), 2)
        self.assertEqual(post.call_count, 2)

    @patch("routing.services.directions.requests.post")
    def test_quality_limits_also_apply_to_distance_search(self, post):
        slow = provider_route([[0, 0], [-0.02, 0.07], [0, 0.14]], 12, 0.9)
        post.side_effect = [response([self.primary, self.north]), response([slow])]
        self.assertEqual(len(build_candidates(self.origin, self.destination)), 2)

    @patch("routing.services.directions.requests.post")
    def test_optional_search_outage_preserves_valid_routes(self, post):
        post.side_effect = [response([self.primary, self.north]), requests.Timeout(), requests.Timeout()]
        self.assertEqual(len(build_candidates(self.origin, self.destination)), 2)

    @patch("routing.services.directions.requests.post")
    def test_primary_search_outage_raises_controlled_error(self, post):
        post.side_effect = requests.Timeout()
        with self.assertRaisesMessage(DirectionsError, "timed out"):
            build_candidates(self.origin, self.destination)
        self.assertEqual(post.call_count, 2)

    @patch("routing.services.directions.requests.post")
    def test_temporary_connection_failure_is_retried_once(self, post):
        post.side_effect = [requests.ConnectionError(), response([self.primary, self.north, self.south])]
        self.assertEqual(len(build_candidates(self.origin, self.destination)), 3)
        self.assertEqual(post.call_count, 2)

    @patch("routing.services.directions.requests.post")
    def test_rate_limit_is_not_retried_automatically(self, post):
        http_response = requests.Response()
        http_response.status_code = 429
        post.side_effect = requests.HTTPError(response=http_response)
        with self.assertRaisesMessage(DirectionsError, "busy"):
            build_candidates(self.origin, self.destination)
        post.assert_called_once()

    @patch("routing.services.directions.requests.post")
    def test_malformed_provider_response_is_controlled(self, post):
        for payload in (None, [], {}, {"code": "Ok", "routes": []}, {"code": "Ok", "routes": {}}):
            with self.subTest(payload=payload):
                post.return_value.json.return_value = payload
                with self.assertRaises(DirectionsError):
                    build_candidates(self.origin, self.destination)

    @patch("routing.services.directions.requests.post")
    def test_invalid_json_is_controlled(self, post):
        post.return_value.json.side_effect = ValueError("Invalid JSON")
        with self.assertRaises(DirectionsError):
            build_candidates(self.origin, self.destination)

    @override_settings(ROUTING_PROVIDER="osrm", OSRM_BASE_URL="https://osrm.example.test")
    @patch("routing.services.directions.requests.get")
    def test_legacy_osrm_explicitly_requests_two_alternatives(self, get):
        get.return_value = response([self.primary, self.north, self.south])
        self.assertEqual(len(build_candidates(self.origin, self.destination)), 3)
        self.assertEqual(get.call_args.kwargs["params"]["alternatives"], "2")
