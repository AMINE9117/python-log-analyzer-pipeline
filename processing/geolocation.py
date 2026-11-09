
import os
import time
import ipaddress
import requests as http
from dotenv import load_dotenv

from log_config import get_logger

load_dotenv()
IPINFO_TOKEN = os.getenv('IPINFO_TOKEN')

logger = get_logger('geolocation')

UNKNOWN = 'Unknown'
TIMEOUT = 10
MAX_RETRIES = 3
RETRY_DELAY = 2
MAX_NETWORK_ERRORS = 5


def is_private_ip(ip: str):
    """Vrai si l'adresse IP est privee, locale ou non publique."""

    try:
        address = ipaddress.ip_address(ip)
        return not address.is_global
    except ValueError:
        return True


def geo_location(ip):
    """
    Retourne le code pays de l'IP.
    Retourne Unknown si aucune information n'est disponible.
    Retourne None si le service est indisponible.
    """

    if is_private_ip(ip):
        logger.debug(f"Private or non-public IP: {ip}")
        return UNKNOWN

    if not IPINFO_TOKEN:
        logger.error("IPINFO_TOKEN is missing from .env")
        return None

    url = f"https://api.ipinfo.io/lite/{ip}"

    for attempt in range(1, MAX_RETRIES + 1):

        try:
            response = http.get(
                url,
                params={"token": IPINFO_TOKEN},
                timeout=TIMEOUT
            )

            if response.status_code == 429:
                logger.warning(
                    f"IPinfo rate limit (429) for {ip}, "
                    f"attempt {attempt}/{MAX_RETRIES}"
                )

                if attempt < MAX_RETRIES:
                    retry_after = response.headers.get('Retry-After')

                    try:
                        delay = int(retry_after) if retry_after else RETRY_DELAY * attempt
                    except (ValueError, TypeError):
                        delay = RETRY_DELAY * attempt

                    time.sleep(min(delay, 60))
                    continue

                return None

            if response.status_code in (500, 502, 503, 504):
                logger.warning(
                    f"IPinfo server error {response.status_code} "
                    f"for {ip}, attempt {attempt}/{MAX_RETRIES}"
                )

                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
                    continue

                return None

            if response.status_code != 200:
                logger.error(
                    f"IPinfo HTTP error {response.status_code} for {ip}"
                )
                return None

            try:
                data = response.json()
            except ValueError:
                logger.error(f"Invalid JSON response for {ip}")
                return UNKNOWN

            country = (
                data.get('country_code') or data.get('country')
                if isinstance(data, dict)
                else None
            )

            if not country:
                logger.warning(f"No country found for {ip}")
                return UNKNOWN

            return country.upper()

        except http.exceptions.Timeout:
            logger.warning(
                f"Timeout for {ip}, attempt {attempt}/{MAX_RETRIES}"
            )

        except http.exceptions.RequestException as error:
            logger.error(
                f"Network error for {ip}: {error}, "
                f"attempt {attempt}/{MAX_RETRIES}"
            )

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY * attempt)

    return None


def geolocate_ips(ips, cache: dict):
    """
    Geolocalise chaque IP une seule fois.
    Les IP publiques avec Unknown sont reessayees.
    Les erreurs temporaires ne sont pas enregistrees dans le cache.
    """

    unique_ips = set(ips)

    to_locate = sorted(
        ip for ip in unique_ips
        if ip not in cache
        or (
            cache[ip] == UNKNOWN
            and not is_private_ip(ip)
        )
    )

    logger.info(
        f"{len(unique_ips)} IPs, {len(to_locate)} IPs to locate"
    )

    if to_locate:
        print(
            f"   {len(to_locate)} IPs to locate "
            "(this may take a few minutes)..."
        )

    countries = {}
    network_errors = 0
    service_down = False

    for number, ip in enumerate(to_locate, start=1):

        if service_down:
            country = None
        else:
            country = geo_location(ip)

        if country is None:
            network_errors += 1
            countries[ip] = UNKNOWN

            if network_errors >= MAX_NETWORK_ERRORS and not service_down:
                service_down = True

                logger.critical(
                    "Geolocation service unavailable. "
                    "Remaining IPs will be retried later."
                )

                print(
                    "   Geolocation service unavailable: "
                    "remaining IPs will be retried later"
                )

        else:
            network_errors = 0
            cache[ip] = country
            countries[ip] = country

        if number % 200 == 0:
            print(f"   {number}/{len(to_locate)} IPs processed")

    for ip in unique_ips:
        if ip in cache:
            countries[ip] = cache[ip]
        elif ip not in countries:
            countries[ip] = UNKNOWN

    return countries


def add_countries(events: list, cache: dict):
    """Ajoute le pays aux tentatives echouees."""

    failed_ips = [
        event['ip']
        for event in events
        if event['status'] == 'failure' and event['ip']
    ]

    countries = geolocate_ips(failed_ips, cache)

    for event in events:
        if event['status'] == 'failure':
            event['country'] = countries.get(
                event['ip'],
                UNKNOWN
            )

    return events


if __name__ == '__main__':
    # Lancer depuis la racine du projet :
    # python -m processing.geolocation

    print("Test de geolocalisation IPinfo :")
    print("8.8.8.8 =>", geo_location("8.8.8.8"))
