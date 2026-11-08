import requests as http

from log_config import get_logger

"""
Géolocalisation des adresses IP avec le service ipinfo.io.
in : adresse IP
out: code pays (ex: 'FR', 'NL') ou 'Unknown'
"""

logger = get_logger('geolocation')

UNKNOWN = 'Unknown'
TIMEOUT = 5            # secondes
MAX_NETWORK_ERRORS = 5  # erreurs réseau consécutives avant d'abandonner le service


def is_private_ip(ip: str):
    """Vrai si l'IP est privée, locale ou mal formée (inutile de la géolocaliser)."""
    parts = ip.split('.')
    if len(parts) != 4 or not all(part.isdigit() and int(part) <= 255 for part in parts):
        return True
    first, second = int(parts[0]), int(parts[1])
    return (first in (0, 10, 127)
            or (first == 172 and 16 <= second <= 31)
            or (first == 192 and second == 168)
            or (first == 169 and second == 254)
            or first >= 224)


def geo_location(ip):
    """Retourne le code pays de l'IP, 'Unknown' si introuvable,
    ou None si le service est injoignable (on pourra réessayer plus tard)."""
    if is_private_ip(ip):
        logger.debug(f"Private or local IP, not located: {ip}")
        return UNKNOWN

    try:
        response = http.get("https://ipinfo.io/"+ip+"/json", timeout=TIMEOUT)
    except http.exceptions.Timeout:
        logger.warning(f"Timeout for {ip}")
        return None
    except http.exceptions.RequestException as e:
        logger.error(f"Network error for {ip}: {e}")
        return None

    if response.status_code != 200:
        logger.error(f"HTTP error {response.status_code} for {ip}")
        return None

    try:
        data = response.json()
    except ValueError:
        logger.error(f"Invalid JSON response for {ip}")
        return UNKNOWN

    country = data.get('country') if isinstance(data, dict) else None
    if not country:
        logger.warning(f"No country found for {ip}")
        return UNKNOWN
    return country


def geolocate_ips(ips, cache: dict):
    """Géolocalise chaque IP une seule fois. `cache` (ip -> pays) est complété au fur et à mesure.
    Si le service ne répond plus, les IP restantes sont marquées 'Unknown' sans bloquer le pipeline."""
    to_locate = sorted(ip for ip in set(ips) if ip not in cache)
    logger.info(f"{len(set(ips))} IPs, {len(to_locate)} not in cache")
    if to_locate:
        print(f"   {len(to_locate)} new IPs to locate (this may take a few minutes)...")

    countries = {}
    network_errors = 0
    service_down = False
    for number, ip in enumerate(to_locate, start=1):
        country = None if service_down else geo_location(ip)
        if country is None:
            network_errors += 1
            countries[ip] = UNKNOWN  # pas mis en cache : on réessaiera au prochain lancement
            if network_errors >= MAX_NETWORK_ERRORS and not service_down:
                service_down = True
                logger.critical("Geolocation service unavailable, remaining IPs set to Unknown")
                print("   Geolocation service unavailable: remaining IPs set to Unknown")
        else:
            network_errors = 0
            cache[ip] = country
        if number % 200 == 0:
            print(f"   {number}/{len(to_locate)} IPs located")

    for ip in set(ips):
        if ip in cache:
            countries[ip] = cache[ip]
    return countries


def add_countries(events: list, cache: dict):
    """Ajoute le pays aux tentatives échouées (seules celles-ci sont utiles au dashboard)."""
    failed_ips = [e['ip'] for e in events if e['status'] == 'failure' and e['ip']]
    countries = geolocate_ips(failed_ips, cache)
    for event in events:
        if event['status'] == 'failure':
            event['country'] = countries.get(event['ip'], UNKNOWN)
    return events


if __name__ == '__main__':
    # Lancer depuis la racine du projet : python -m processing.geolocation
    print(geo_location("88.147.152.239"))
