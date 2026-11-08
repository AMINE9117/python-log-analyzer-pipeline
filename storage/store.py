import csv
import json
import os

from log_config import get_logger

"""
Sauvegarde et lecture des données traitées.

storage/
├── geo_cache.json          cache ip -> pays (évite de refaire les requêtes HTTP)
└── processed/
    ├── events.csv          un événement par ligne de log
    ├── state.json          taille et date des fichiers de data/ déjà traités
    └── statistics.json     statistiques du dashboard
"""

logger = get_logger('storage')

STORAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(STORAGE_DIR, 'processed')
EVENTS_FILE = os.path.join(PROCESSED_DIR, 'events.csv')
STATE_FILE = os.path.join(PROCESSED_DIR, 'state.json')
STATISTICS_FILE = os.path.join(PROCESSED_DIR, 'statistics.json')
GEO_CACHE_FILE = os.path.join(STORAGE_DIR, 'geo_cache.json')


# ---------- fichiers JSON ----------

def save_json(data, file_path: str):
    """Écrit `data` dans un fichier JSON. Retourne True si tout s'est bien passé."""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except (OSError, TypeError) as e:
        logger.error(f"Save error {file_path}: {e}")
        return False
    logger.info(f"Saved {file_path}")
    return True


def load_json(file_path: str, default):
    """Lit un fichier JSON. Retourne `default` si le fichier est absent ou corrompu."""
    if not os.path.exists(file_path):
        logger.info(f"File not found, default value used: {file_path}")
        return default
    try:
        with open(file_path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Read error {file_path}: {e}")
        return default


# ---------- état des fichiers de data/ ----------

def get_data_state(data_dir: str):
    """Taille et date de modification de chaque fichier de `data_dir`."""
    state = {}
    try:
        for file in sorted(os.listdir(data_dir)):
            path = os.path.join(data_dir, file)
            if os.path.isfile(path):
                state[file] = [os.path.getsize(path), os.path.getmtime(path)]
    except OSError as e:
        logger.error(f"Cannot read data directory {data_dir}: {e}")
    return state


def is_up_to_date(data_dir: str, state_file: str = STATE_FILE, events_file: str = EVENTS_FILE):
    """Vrai si les fichiers de data/ n'ont pas changé depuis le dernier traitement."""
    if not os.path.exists(events_file):
        return False
    saved = load_json(state_file, {})
    current = get_data_state(data_dir)
    return bool(current) and saved.get('files') == current


# ---------- événements (CSV) ----------

def save_events(events: list, fields: list, data_dir: str,
                events_file: str = EVENTS_FILE, state_file: str = STATE_FILE):
    """Sauvegarde les événements en CSV puis l'état des fichiers de data/."""
    try:
        os.makedirs(os.path.dirname(events_file), exist_ok=True)
        with open(events_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(events)
    except (OSError, csv.Error, ValueError) as e:
        logger.error(f"Save error {events_file}: {e}")
        return False
    logger.info(f"{len(events)} events saved in {events_file}")
    return save_json({'files': get_data_state(data_dir)}, state_file)


def load_events(events_file: str = EVENTS_FILE):
    """Relit les événements sauvegardés (en remettant les bons types)."""
    events = []
    try:
        with open(events_file, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                row['count'] = int(row['count'] or 1)
                row['invalid_user'] = row['invalid_user'] == 'True'
                events.append(row)
    except (OSError, csv.Error, ValueError, KeyError) as e:
        logger.error(f"Read error {events_file}: {e}")
        return []
    logger.info(f"{len(events)} events loaded from {events_file}")
    return events


# ---------- cache de géolocalisation et statistiques ----------

def load_geo_cache(file_path: str = GEO_CACHE_FILE):
    return load_json(file_path, {})


def save_geo_cache(cache: dict, file_path: str = GEO_CACHE_FILE):
    return save_json(cache, file_path)


def save_statistics(statistics: dict, file_path: str = STATISTICS_FILE):
    return save_json(statistics, file_path)
