
import logging
import sys
from pathlib import Path
from unittest import mock
import requests

# Ajouter la racine du projet au chemin de recherche Python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from processing import geolocation as geo

# Pas d'ecriture dans logs/ pendant les tests
logging.disable(logging.CRITICAL)


def fake_response(status, data=None, bad_json=False):
    response = mock.Mock()
    response.status_code = status
    response.headers = {}

    if bad_json:
        response.json.side_effect = ValueError('bad json')
    else:
        response.json.return_value = data

    return response


def test_private_ips():
    for ip in [
        '10.0.0.1',
        '127.0.0.1',
        '192.168.1.1',
        '172.16.0.1',
        '172.31.255.1',
        '169.254.1.1',
        'abc'
    ]:
        assert geo.is_private_ip(ip), ip

    for ip in ['8.8.8.8', '172.32.0.1', '45.148.10.147']:
        assert not geo.is_private_ip(ip), ip


def test_private_ip_not_requested():
    with mock.patch('processing.geolocation.http.get') as get:
        assert geo.geo_location('192.168.0.1') == 'Unknown'
        get.assert_not_called()


def test_success():
    with mock.patch('processing.geolocation.http.get') as get:
        get.return_value = fake_response(200, {'country': 'NL'})
        assert geo.geo_location('8.8.8.8') == 'NL'


def test_no_country():
    with mock.patch('processing.geolocation.http.get') as get:
        get.return_value = fake_response(200, {'bogon': True})
        assert geo.geo_location('8.8.8.8') == 'Unknown'


def test_invalid_json():
    with mock.patch('processing.geolocation.http.get') as get:
        get.return_value = fake_response(200, bad_json=True)
        assert geo.geo_location('8.8.8.8') == 'Unknown'


def test_http_error():
    with mock.patch('processing.geolocation.time.sleep'):
        with mock.patch('processing.geolocation.http.get') as get:
            get.return_value = fake_response(429)
            assert geo.geo_location('8.8.8.8') is None
            assert get.call_count == geo.MAX_RETRIES


def test_timeout():
    with mock.patch('processing.geolocation.time.sleep'):
        with mock.patch('processing.geolocation.http.get') as get:
            get.side_effect = requests.exceptions.Timeout()
            assert geo.geo_location('8.8.8.8') is None
            assert get.call_count == geo.MAX_RETRIES


def test_cache_avoids_duplicate_requests():
    with mock.patch('processing.geolocation.http.get') as get:
        get.return_value = fake_response(200, {'country': 'FR'})

        cache = {}

        result = geo.geolocate_ips(
            ['8.8.8.8', '8.8.8.8', '1.1.1.1'],
            cache
        )

        assert get.call_count == 2
        assert result == {
            '8.8.8.8': 'FR',
            '1.1.1.1': 'FR'
        }

        geo.geolocate_ips(['8.8.8.8'], cache)

        assert get.call_count == 2


def test_service_down_does_not_block():
    with mock.patch('processing.geolocation.time.sleep'):
        with mock.patch('processing.geolocation.http.get') as get:
            get.side_effect = requests.exceptions.ConnectionError()

            ips = [f'8.8.8.{i}' for i in range(20)]
            cache = {}

            result = geo.geolocate_ips(ips, cache)

            assert get.call_count == (
                geo.MAX_NETWORK_ERRORS * geo.MAX_RETRIES
            )

            assert all(
                country == 'Unknown'
                for country in result.values()
            )

            assert cache == {}


def run_tests():
    tests = [
        test_private_ips,
        test_private_ip_not_requested,
        test_success,
        test_no_country,
        test_invalid_json,
        test_http_error,
        test_timeout,
        test_cache_avoids_duplicate_requests,
        test_service_down_does_not_block
    ]

    failures = 0

    for test in tests:
        try:
            test()
            print(test.__name__ + ' ... OK')
        except Exception as error:
            failures += 1
            print(test.__name__ + ' ... ECHEC')
            print('Erreur :', error)

    print()
    print('Tests executes :', len(tests))
    print('Reussis :', len(tests) - failures)
    print('Echoues :', failures)

    if failures > 0:
        raise SystemExit(1)


if __name__ == '__main__':
    run_tests()
