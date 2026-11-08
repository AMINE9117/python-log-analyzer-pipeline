"""
Module de stockage
in  : liste d'événements (dictionnaires) venant de extract_transform / geolocation
out : fichier JSON sur disque (storage/events.json), relu avec load_events()

Format choisi : JSON (module json de la bibliothèque standard).
Il garde les types des données (True/False, nombres, texte) et la clé 'country'
ajoutée par geolocation.add_country().

Sécurité des données : on écrit d'abord dans un fichier temporaire (.tmp),
puis on remplace l'ancien fichier seulement si l'écriture a réussi.
Une erreur d'écriture ne détruit donc jamais les données déjà sauvegardées.
"""
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

STORAGE_DIR = Path(__file__).resolve().parent
# Dossier logs/ à la racine du projet (ne dépend pas du dossier de lancement)
LOGS_DIR = STORAGE_DIR.parent / "logs"

EVENTS_FILE = STORAGE_DIR / "events.json"
COUNTRY_CACHE_FILE = STORAGE_DIR / "country_cache.json"

# Clés produites par extract_transform.extract() (la clé 'country' est facultative)
REQUIRED_KEYS = ('date', 'heure', 'ip', 'username', 'event_type',
                 'status', 'invalid_user', 'raw_line')


def get_logger():
    """Retourne le logger du module (créé une seule fois, un seul handler)."""
    logger = logging.getLogger("storage")
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
            filename=LOGS_DIR / "storage.log",
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


def is_valid_event(event):
    """Vrai si event est un dictionnaire qui contient toutes les clés attendues."""
    return isinstance(event, dict) and all(key in event for key in REQUIRED_KEYS)


def write_json(data, file_path):
    """Écrit data en JSON de façon sûre (fichier temporaire puis remplacement). Retourne True/False."""
    logger = get_logger()
    file_path = Path(file_path)
    tmp_path = file_path.with_name(file_path.name + ".tmp")
    success = False

    try:
        os.makedirs(file_path.parent, exist_ok=True)
        with open(tmp_path, mode='w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp_path, file_path)
        success = True
    except (OSError, TypeError, ValueError) as e:
        logger.error("Erreur d'écriture de %s : %s", file_path, e)
    except Exception:
        logger.exception("Erreur inattendue pendant l'écriture de %s", file_path)

    if not success:
        # On supprime le fichier temporaire ; l'ancien fichier reste intact
        try:
            if tmp_path.exists():
                os.remove(tmp_path)
        except OSError as e:
            logger.warning("Impossible de supprimer %s : %s", tmp_path, e)
    return success


def read_json(file_path):
    """Lit un fichier JSON. Retourne son contenu, ou None si le fichier est absent ou illisible."""
    logger = get_logger()
    try:
        with open(file_path, mode='r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Fichier introuvable : %s", file_path)
    except (OSError, ValueError) as e:
        # ValueError couvre les fichiers JSON corrompus ou mal encodés
        logger.error("Erreur de lecture de %s : %s", file_path, e)
    except Exception:
        logger.exception("Erreur inattendue pendant la lecture de %s", file_path)
    return None


def save_events(events: list, file_path=EVENTS_FILE):
    """Sauvegarde les événements. Retourne True si la sauvegarde a réussi.

    - Les éléments invalides sont ignorés (et signalés dans storage.log).
    - Une liste vide n'est pas sauvegardée : le fichier existant est conservé.
    """
    logger = get_logger()
    if not isinstance(events, list):
        logger.error("save_events attend une liste, reçu : %s", type(events).__name__)
        return False

    valid_events = [event for event in events if is_valid_event(event)]
    rejected = len(events) - len(valid_events)
    if rejected:
        logger.warning("%d événements invalides ignorés (clés manquantes ou type incorrect)", rejected)
    if not valid_events:
        logger.warning("Aucun événement à sauvegarder : le fichier existant est conservé")
        return False

    if write_json(valid_events, file_path):
        logger.info("%d événements sauvegardés dans %s", len(valid_events), file_path)
        return True
    return False


def load_events(file_path=EVENTS_FILE):
    """Relit les événements sauvegardés. Retourne [] si le fichier est absent ou incorrect."""
    logger = get_logger()
    data = read_json(file_path)
    if data is None:
        return []
    if not isinstance(data, list):
        logger.error("Format incorrect dans %s : une liste était attendue", file_path)
        return []

    events = [event for event in data if is_valid_event(event)]
    if len(events) != len(data):
        logger.warning("%d éléments incorrects ignorés dans %s", len(data) - len(events), file_path)
    logger.info("%d événements lus depuis %s", len(events), file_path)
    return events


def save_country_cache(cache: dict, file_path=COUNTRY_CACHE_FILE):
    """Sauvegarde le cache {ip: pays} de geolocation pour ne pas redemander les mêmes IP au prochain lancement."""
    logger = get_logger()
    if not isinstance(cache, dict) or not cache:
        logger.warning("Cache des pays vide ou incorrect : rien à sauvegarder")
        return False
    clean_cache = {ip: country for ip, country in cache.items()
                   if isinstance(ip, str) and isinstance(country, str)}
    return write_json(clean_cache, file_path)


def load_country_cache(file_path=COUNTRY_CACHE_FILE):
    """Relit le cache {ip: pays}. Retourne {} si le fichier est absent ou incorrect."""
    logger = get_logger()
    data = read_json(file_path)
    if not isinstance(data, dict):
        if data is not None:
            logger.error("Format incorrect dans %s : un dictionnaire était attendu", file_path)
        return {}
    return {ip: country for ip, country in data.items()
            if isinstance(ip, str) and isinstance(country, str)}


if __name__ == '__main__':
    # À lancer depuis la racine du projet : python -m storage.store
    events = load_events()
    print(f"{len(events)} événements dans {EVENTS_FILE}")