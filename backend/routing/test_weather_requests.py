from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from routing.services.weather import (
    WeatherError, HourlySeries, _fetch_chunk, fetch_series,
    _record_cooldown, _check_cooldown, _series_cache_key,
)


class WeatherRequestTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_rate_limit_is_reported_without_retry(self):
        response = Mock(status_code=429, headers={"Retry-After": "120"})
        response.json.return_value = {"reason": "Minutely API request limit exceeded"}
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
        with patch("routing.services.weather.requests.get", return_value=response) as get:
            with self.assertRaisesRegex(WeatherError, "request limit"):
                _fetch_chunk([(39, -100)], 3)
            with self.assertRaisesRegex(WeatherError, "paused for about 2 minute"):
                _fetch_chunk([(40, -100)], 3)
        self.assertEqual(get.call_count, 1)

    def test_provider_cooldown_expiry_and_hourly_limit(self):
        response = Mock(headers={})
        response.json.return_value = {"reason": "Hourly API request limit exceeded"}
        with patch("routing.services.weather.time.time", return_value=1000):
            _record_cooldown(response)
            with self.assertRaisesRegex(WeatherError, "60 minute"):
                _check_cooldown()
        with patch("routing.services.weather.time.time", return_value=4601):
            _check_cooldown()

    def test_complete_cached_forecast_remains_available_during_cooldown(self):
        point = (39, -100)
        cache.set(_series_cache_key(point, 3), HourlySeries(*point).__dict__)
        response = Mock(headers={"Retry-After": "120"})
        response.json.return_value = {}
        _record_cooldown(response)
        with patch("routing.services.weather.requests.get") as get:
            self.assertIn(point, fetch_series([point], 3))
            with self.assertRaises(WeatherError):
                fetch_series([point, (40, -100)], 3)
            get.assert_not_called()

    def test_timeout_is_distinguished_from_provider_failure(self):
        with patch("routing.services.weather.requests.get", side_effect=requests.Timeout):
            with self.assertRaisesRegex(WeatherError, "timed out"):
                _fetch_chunk([(39, -100)], 3)

    def test_incomplete_response_cannot_be_assigned_to_wrong_locations(self):
        response = Mock()
        response.json.return_value = [{"hourly": {}}]
        with patch("routing.services.weather.requests.get", return_value=response):
            with self.assertRaisesRegex(WeatherError, "incomplete batch"):
                _fetch_chunk([(39, -100), (40, -100)], 3)

    @override_settings(WEATHER_CHUNK_SIZE=1, WEATHER_MAX_WORKERS=1)
    def test_failure_stops_queue_and_retry_reuses_successful_batches(self):
        points = [(39, -100), (40, -100), (41, -100)]
        with patch("routing.services.weather._fetch_chunk", side_effect=[
            [HourlySeries(39, -100)], WeatherError("rate limit"),
        ]) as fetch:
            with self.assertRaises(WeatherError):
                fetch_series(points, 3)
            self.assertEqual(fetch.call_count, 2)
        with patch("routing.services.weather._fetch_chunk", side_effect=[
            [HourlySeries(40, -100)], [HourlySeries(41, -100)],
        ]) as fetch:
            self.assertEqual(len(fetch_series(points, 3)), 3)
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(fetch.call_args_list[0].args[0], [(40, -100)])
