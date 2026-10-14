from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.test import SimpleTestCase

from routing.services.geocoding import GeocodingError, _search, geocode, suggest


RESULT = {
    "lat": "39.7392",
    "lon": "-104.9903",
    "display_name": "Denver, Colorado, United States",
    "address": {"city": "Denver", "state": "Colorado", "country": "United States"},
}


class PlaceSearchCacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("routing.services.geocoding._autocomplete_search", return_value=[RESULT])
    def test_repeated_successful_query_is_cached_under_query_key(self, search):
        first = suggest("Denver")
        self.assertEqual(suggest(" Denver "), first)
        search.assert_called_once_with("Denver", limit=6)

    @patch("routing.services.geocoding._autocomplete_search", return_value=[RESULT])
    def test_selected_result_is_reused_when_planning(self, search):
        result = suggest("Denver")[0]
        point = geocode(result["value"])
        self.assertEqual(point.coords, (39.7392, -104.9903))
        search.assert_called_once()

    @patch("routing.services.geocoding._autocomplete_search", return_value=[])
    def test_empty_result_is_also_cached(self, search):
        self.assertEqual(suggest("Unfindable"), [])
        self.assertEqual(suggest("Unfindable"), [])
        search.assert_called_once()

    @patch("routing.services.geocoding._autocomplete_search", side_effect=GeocodingError("Unavailable"))
    def test_provider_failure_is_distinct_from_no_results(self, search):
        with self.assertRaisesMessage(GeocodingError, "Unavailable"):
            suggest("Denver")


class GeocoderThrottleTests(SimpleTestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.settings_override = self.settings(
            GEOCODER_RATE_LIMIT_DB=str(Path(directory.name) / "rate-limit.sqlite3")
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.now = 100.0
        self.starts = []
        self.response = Mock()
        self.response.json.return_value = [RESULT]

    def wait(self, delay):
        self.now += delay

    def respond(self, *args, **kwargs):
        self.starts.append(self.now)
        return self.response

    def test_separate_database_connections_share_request_spacing(self):
        with (
            patch("routing.services.geocoding.time.time", side_effect=lambda: self.now),
            patch("routing.services.geocoding.time.sleep", side_effect=self.wait),
            patch("routing.services.geocoding.requests.get", side_effect=self.respond),
        ):
            _search("Denver", 1)
            _search("Chicago", 1)
        self.assertGreaterEqual(self.starts[1] - self.starts[0], 1.0)

    def test_failed_requests_still_count_toward_provider_limit(self):
        with (
            patch("routing.services.geocoding.time.time", side_effect=lambda: self.now),
            patch("routing.services.geocoding.time.sleep", side_effect=self.wait),
            patch("routing.services.geocoding.requests.get", side_effect=self.respond),
        ):
            self.response.raise_for_status.side_effect = requests.HTTPError("unavailable")
            with self.assertRaises(GeocodingError):
                _search("Denver", 1)
            self.response.raise_for_status.side_effect = None
            _search("Chicago", 1)
        self.assertGreaterEqual(self.starts[1] - self.starts[0], 1.0)

    def test_country_fallback_is_rate_limited_too(self):
        self.response.json.side_effect = [[], [RESULT]]
        with (
            patch("routing.services.geocoding.time.time", side_effect=lambda: self.now),
            patch("routing.services.geocoding.time.sleep", side_effect=self.wait),
            patch("routing.services.geocoding.requests.get", side_effect=self.respond),
        ):
            self.assertEqual(_search("Paris", 1), [RESULT])
        self.assertGreaterEqual(self.starts[1] - self.starts[0], 1.0)

class AutocompleteProviderTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def feature(self, name='Denver', street=None, number=None, lon=-104.99):
        return {
            'geometry': {'type': 'Point', 'coordinates': [lon, 39.7392]},
            'properties': {'name': name, 'city': 'Denver', 'state': 'Colorado',
                           'country': 'United States', 'street': street, 'housenumber': number},
        }

    @patch('routing.services.geocoding._search')
    @patch('routing.services.geocoding.requests.get')
    def test_autocomplete_uses_photon_and_selected_coordinates_are_cached(self, get, nominatim):
        get.return_value.json.return_value = {'features': [self.feature()]}
        options = suggest('Den')
        self.assertEqual(options[0]['value'], 'Denver, Colorado, United States')
        self.assertIn('/api/', get.call_args.args[0])
        self.assertEqual(get.call_args.kwargs['params']['q'], 'Den')
        self.assertEqual(geocode(options[0]['value']).coords, (39.7392, -104.99))
        nominatim.assert_not_called()

    @patch('routing.services.geocoding.requests.get')
    def test_distinct_addresses_in_same_city_are_preserved(self, get):
        get.return_value.json.return_value = {'features': [
            self.feature('Depot', 'Main Street', '100'),
            self.feature('Depot', 'Main Street', '200', -104.98),
        ]}
        options = suggest('Depot')
        self.assertEqual(len(options), 2)
        self.assertNotEqual(options[0]['label'], options[1]['label'])

    @patch('routing.services.geocoding.requests.get')
    def test_duplicate_full_labels_do_not_overwrite_selected_coordinates(self, get):
        get.return_value.json.return_value = {'features': [self.feature(), self.feature(lon=-104.98)]}
        options = suggest('Denver')
        self.assertEqual(len(options), 1)
        self.assertEqual(geocode(options[0]['value']).lon, -104.99)

    @patch('routing.services.geocoding.requests.get')
    def test_bad_features_are_skipped(self, get):
        get.return_value.json.return_value = {'features': [None, {}, self.feature(lon=float('nan')), self.feature()]}
        self.assertEqual(len(suggest('Denver')), 1)

    @patch('routing.services.geocoding.requests.get')
    def test_short_query_does_not_contact_provider(self, get):
        self.assertEqual(suggest('D'), [])
        get.assert_not_called()

    @patch('routing.services.geocoding.requests.get')
    def test_malformed_response_is_reported_as_provider_failure(self, get):
        get.return_value.json.return_value = {'unexpected': []}
        with self.assertRaises(GeocodingError):
            suggest('Denver')

    @patch('routing.services.geocoding.requests.get', side_effect=requests.Timeout())
    def test_photon_failure_never_falls_back_to_nominatim_autocomplete(self, get):
        with patch('routing.services.geocoding._search') as nominatim:
            with self.assertRaises(GeocodingError):
                suggest('Denver')
            nominatim.assert_not_called()
