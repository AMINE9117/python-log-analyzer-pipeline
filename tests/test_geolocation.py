import logging
import unittest
from unittest import mock

import requests

from processing import geolocation as geo

# Pas d'écriture dans logs/ pendant les tests
logging.disable(logging.CRITICAL)


def fake_response(status, data=None, bad_json=False):
    response = mock.Mock()
    response.status_code = status
    if bad_json:
        response.json.side_effect = ValueError('bad json')
    else:
        response.json.return_value = data
    return response


class TestGeolocation(unittest.TestCase):

    def test_private_ips(self):
        for ip in ['10.0.0.1', '127.0.0.1', '192.168.1.1', '172.16.0.1', '172.31.255.1', '169.254.1.1', 'abc']:
            self.assertTrue(geo.is_private_ip(ip), ip)
        for ip in ['8.8.8.8', '172.32.0.1', '45.148.10.147']:
            self.assertFalse(geo.is_private_ip(ip), ip)

    @mock.patch('processing.geolocation.http.get')
    def test_private_ip_not_requested(self, get):
        self.assertEqual(geo.geo_location('192.168.0.1'), 'Unknown')
        get.assert_not_called()

    @mock.patch('processing.geolocation.http.get')
    def test_success(self, get):
        get.return_value = fake_response(200, {'country': 'NL'})
        self.assertEqual(geo.geo_location('8.8.8.8'), 'NL')

    @mock.patch('processing.geolocation.http.get')
    def test_no_country(self, get):
        get.return_value = fake_response(200, {'bogon': True})
        self.assertEqual(geo.geo_location('8.8.8.8'), 'Unknown')

    @mock.patch('processing.geolocation.http.get')
    def test_invalid_json(self, get):
        get.return_value = fake_response(200, bad_json=True)
        self.assertEqual(geo.geo_location('8.8.8.8'), 'Unknown')

    @mock.patch('processing.geolocation.http.get')
    def test_http_error(self, get):
        get.return_value = fake_response(429)
        self.assertIsNone(geo.geo_location('8.8.8.8'))

    @mock.patch('processing.geolocation.http.get')
    def test_timeout(self, get):
        get.side_effect = requests.exceptions.Timeout()
        self.assertIsNone(geo.geo_location('8.8.8.8'))

    @mock.patch('processing.geolocation.http.get')
    def test_cache_avoids_duplicate_requests(self, get):
        get.return_value = fake_response(200, {'country': 'FR'})
        cache = {}
        result = geo.geolocate_ips(['8.8.8.8', '8.8.8.8', '1.1.1.1'], cache)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(result, {'8.8.8.8': 'FR', '1.1.1.1': 'FR'})
        geo.geolocate_ips(['8.8.8.8'], cache)
        self.assertEqual(get.call_count, 2)  # déjà en cache

    @mock.patch('processing.geolocation.http.get')
    def test_service_down_does_not_block(self, get):
        get.side_effect = requests.exceptions.ConnectionError()
        ips = [f'8.8.8.{i}' for i in range(20)]
        cache = {}
        result = geo.geolocate_ips(ips, cache)
        self.assertEqual(get.call_count, geo.MAX_NETWORK_ERRORS)  # on arrête d'appeler le service
        self.assertTrue(all(country == 'Unknown' for country in result.values()))
        self.assertEqual(cache, {})  # les erreurs ne sont pas mises en cache


if __name__ == '__main__':
    unittest.main()
