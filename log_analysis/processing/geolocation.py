"""
Module de géolocalisation
in  : adresse IP (ou liste d'événements venant de extract_transform)
out : pays de l'IP (code à 2 lettres donné par ipinfo, ex. 'MA', 'FR') ou 'Unknown'

Service utilisé : https://ipinfo.io/<ip>/json
Un jeton ipinfo est facultatif : s'il existe, il est lu dans la variable
d'environnement IPINFO_TOKEN et envoyé dans l'en-tête Authorization.
"""
import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests as http

from requests import Response

# Dossier logs/ à la racine du projet (ne dépend pas du dossier de lancement)
LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"

URL = "https://ipinfo.io/"
TIMEOUT = 5                # secondes d'attente maximum par requête
UNKNOWN = "Unknown"
MAX_CONSECUTIVE_ERRORS = 3  # après 3 erreurs de suite, on arrête d'appeler le service

# Cache : une IP déjà trouvée n'est jamais redemandée au service
country_cache = {}
# État du service : nombre d'erreurs de suite et arrêt éventuel des requêtes
service_state = {'errors': 0, 'stopped': False}


def get_logger():
    """Retourne le logger du module (créé une seule fois, un seul handler)."""
    logger = logging.getLogger("geolocation")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    formatter = logging.Formatter(
        fmt='%(asctime)s|%(name)s|%(levelname)s|%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S')
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        file_handler = RotatingFileHandler(
            filename=LOGS_DIR / "geolocation.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # Impossible d'écrire le fichier de logs : on ne bloque pas le pipeline
        logger.addHandler(logging.NullHandler())
    return logger


def reset_state():
    """Vide le cache et réactive le service (utile pour relancer ou tester)."""
    country_cache.clear()
    service_state['errors'] = 0
    service_state['stopped'] = False


def parse_ipv4(ip: str):
    """Retourne les 4 nombres d'une adresse IPv4 valide, sinon None."""
    match = re.fullmatch(r'(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})', ip)
    if not match:
        return None
    parts = match.groups()
    for part in parts:
        if int(part) > 255 or (len(part) > 1 and part.startswith('0')):
            return None
    return tuple(int(part) for part in parts)


def is_valid_ip(ip: str):
    """Vrai si ip ressemble à une adresse IPv4 ou IPv6 valide."""
    if parse_ipv4(ip) is not None:
        return True
    # IPv6 : vérification simple (caractères hexadécimaux et au moins 2 « : »)
    return re.fullmatch(r'[0-9a-fA-F:]{2,39}', ip) is not None and ip.count(':') >= 2


def is_public_ip(ip: str):
    """Vrai si l'IP est valide ET publique (ni privée, ni locale, ni réservée)."""
    ipv4 = parse_ipv4(ip)
    if ipv4 is None:
        if not is_valid_ip(ip):
            return False
        # IPv6 : on écarte « :: », « ::1 », lien local, adresses privées, multicast, documentation
        ipv6 = ip.lower()
        return not (ipv6 in ('::', '::1') or ipv6.startswith(('fe8', 'fe9', 'fea', 'feb', 'fc', 'fd', 'ff', '2001:db8')))

    a, b, c, _ = ipv4
    if a == 0 or a == 10 or a == 127:           # réseau « ce réseau », privé, loopback
        return False
    if a == 100 and 64 <= b <= 127:             # CGNAT
        return False
    if a == 169 and b == 254:                   # lien local
        return False
    if a == 172 and 16 <= b <= 31:              # privé
        return False
    if a == 192 and b == 168:                   # privé
        return False
    if a == 192 and b == 0 and c in (0, 2):     # réservé / documentation
        return False
    if a == 198 and b in (18, 19):              # tests de performance
        return False
    if a == 198 and b == 51 and c == 100:       # documentation
        return False
    if a == 203 and b == 0 and c == 113:        # documentation
        return False
    if a >= 224:                                # multicast et réservé (224 à 255)
        return False
    return True


def fetch_country(ip: str):
    """Interroge ipinfo. Retourne le pays, UNKNOWN si introuvable, ou None en cas d'erreur du service."""
    logger = get_logger()
    token = os.environ.get('IPINFO_TOKEN')
    headers = {'Authorization': f'Bearer {token}'} if token else None

    try:
        response = http.get(URL + ip + "/json", headers=headers, timeout=TIMEOUT)
    except http.exceptions.Timeout:
        logger.error("Délai dépassé (%s s) pour l'IP %s", TIMEOUT, ip)
        return None
    except http.exceptions.ConnectionError as e:
        logger.error("Erreur réseau pour l'IP %s : %s", ip, type(e).__name__)
        return None
    except http.exceptions.RequestException as e:
        logger.error("Erreur de requête pour l'IP %s : %s", ip, type(e).__name__)
        return None

    if response.status_code in (401, 403, 429):
        # Jeton refusé ou limite de requêtes atteinte : inutile d'insister
        logger.error("Service refusé (HTTP %s) pour l'IP %s : arrêt des requêtes", response.status_code, ip)
        service_state['stopped'] = True
        return None
    if response.status_code in (400, 404):
        logger.warning("IP %s inconnue du service (HTTP %s)", ip, response.status_code)
        return UNKNOWN
    if response.status_code != 200:
        logger.error("Erreur HTTP %s pour l'IP %s", response.status_code, ip)
        return None

    try:
        data = response.json()
    except ValueError:
        logger.error("Réponse JSON invalide pour l'IP %s", ip)
        return None
    if not isinstance(data, dict):
        logger.error("Réponse inattendue pour l'IP %s", ip)
        return None

    country = data.get('country')
    if data.get('bogon') or not isinstance(country, str) or not re.fullmatch(r'[A-Za-z]{2}', country):
        logger.warning("Pays introuvable pour l'IP %s", ip)
        return UNKNOWN
    return country.upper()


def geo_location(ip):
    """Retourne le pays d'une IP, ou 'Unknown'. Ne lève jamais d'exception."""
    logger = get_logger()
    try:
        if not isinstance(ip, str):
            return UNKNOWN
        ip = ip.strip()

        if ip in country_cache:
            return country_cache[ip]
        if not is_valid_ip(ip):
            logger.warning("Adresse IP invalide ignorée : %r", ip)
            return UNKNOWN
        if not is_public_ip(ip):
            logger.info("IP privée, locale ou réservée non géolocalisée : %s", ip)
            country_cache[ip] = UNKNOWN
            return UNKNOWN
        if service_state['stopped']:
            return UNKNOWN

        country = fetch_country(ip)
        if country is None:
            # Erreur du service : on ne garde pas l'IP en cache pour pouvoir réessayer plus tard
            service_state['errors'] += 1
            if service_state['errors'] >= MAX_CONSECUTIVE_ERRORS and not service_state['stopped']:
                service_state['stopped'] = True
                logger.critical("Service de géolocalisation indisponible après %d erreurs de suite : "
                                "les IP restantes seront 'Unknown'", service_state['errors'])
            return UNKNOWN

        service_state['errors'] = 0
        country_cache[ip] = country
        return country
    except Exception:
        logger.exception("Erreur inattendue pendant la géolocalisation de %r", ip)
        return UNKNOWN


def get_unique_ips(events: list):
    """Retourne la liste triée des adresses IP distinctes des événements."""
    return sorted({event['ip'] for event in events or [] if event.get('ip')})


def geolocate_ips(ips: list):
    """Retourne un dictionnaire {ip: pays} (une seule requête par IP grâce au cache)."""
    return {ip: geo_location(ip) for ip in ips}


def add_country(events: list):
    """Retourne une nouvelle liste d'événements avec la clé 'country' (les événements d'origine ne sont pas modifiés)."""
    logger = get_logger()
    countries = geolocate_ips(get_unique_ips(events))
    result = []
    for event in events or []:
        new_event = dict(event)
        new_event['country'] = countries.get(event.get('ip'), UNKNOWN)
        result.append(new_event)
    logger.info("Géolocalisation terminée : %d IP distinctes, %d en cache",
                len(countries), len(country_cache))
    return result


if __name__ == '__main__':
    print(geo_location("88.147.152.239"))
    print(geo_location("192.168.1.10"))