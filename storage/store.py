
import json
import os

import pymysql
from dotenv import load_dotenv

from log_config import get_logger


"""
Sauvegarde et lecture des données traitees.

MariaDB :
    - events : evenements SSH
    - pipeline_statistics : statistiques du dashboard

Fichiers JSON :
    - state.json : etat des fichiers data/
    - geo_cache.json : cache IP -> pays
    - statistics.json : sauvegarde des statistiques
"""


logger = get_logger('storage')

load_dotenv()

STORAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(STORAGE_DIR, 'processed')

STATE_FILE = os.path.join(PROCESSED_DIR, 'state.json')
STATISTICS_FILE = os.path.join(PROCESSED_DIR, 'statistics.json')
GEO_CACHE_FILE = os.path.join(STORAGE_DIR, 'geo_cache.json')


# ---------- CONNEXION MARIADB ----------

def get_connection():
    """Ouvre une connexion a MariaDB."""

    return pymysql.connect(
        host=os.getenv('DB_HOST', '127.0.0.1'),
        port=int(os.getenv('DB_PORT', '3306')),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )


# ---------- CREATION DES TABLES ----------

def create_tables():
    """Cree les tables necessaires si elles n'existent pas."""

    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    month VARCHAR(10),
                    day VARCHAR(4),
                    time VARCHAR(16),
                    host VARCHAR(255),
                    process VARCHAR(255),
                    pid VARCHAR(20),
                    event_type VARCHAR(100),
                    status VARCHAR(50),
                    event_user VARCHAR(255),
                    ip VARCHAR(45),
                    port VARCHAR(20),
                    method VARCHAR(100),
                    invalid_user BOOLEAN,
                    reason TEXT,
                    count INT,
                    country VARCHAR(100)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_statistics (
                    id TINYINT PRIMARY KEY,
                    content LONGTEXT
                )
            """)

        connection.commit()
        logger.info("MariaDB tables are ready.")

    finally:
        connection.close()


# ---------- FICHIERS JSON ----------

def save_json(data, file_path: str):
    """Enregistre des donnees dans un fichier JSON."""

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
    """Lit un fichier JSON."""

    if not os.path.exists(file_path):
        logger.info(f"File not found, default value used: {file_path}")
        return default

    try:
        with open(file_path, encoding='utf-8') as f:
            return json.load(f)

    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Read error {file_path}: {e}")
        return default


# ---------- ETAT DES FICHIERS DATA ----------

def get_data_state(data_dir: str):
    """Retourne la taille et la date de modification des fichiers."""

    state = {}

    try:
        for file in sorted(os.listdir(data_dir)):
            path = os.path.join(data_dir, file)

            if os.path.isfile(path):
                state[file] = [
                    os.path.getsize(path),
                    os.path.getmtime(path)
                ]

    except OSError as e:
        logger.error(f"Cannot read data directory {data_dir}: {e}")

    return state


def is_up_to_date(data_dir: str, state_file: str = STATE_FILE,
                  events_file=None):
    """Verifie si les fichiers data/ ont deja ete traites."""

    saved = load_json(state_file, {})
    current = get_data_state(data_dir)

    if not current or saved.get('files') != current:
        return False

    try:
        create_tables()
        connection = get_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total FROM events")
                result = cursor.fetchone()

            return result['total'] > 0

        finally:
            connection.close()

    except pymysql.MySQLError as e:
        logger.error(f"Database check error: {e}")
        return False


# ---------- EVENEMENTS MARIADB ----------

def save_events(events: list, fields: list, data_dir: str,
                events_file=None, state_file: str = STATE_FILE):
    """Enregistre les evenements dans MariaDB."""

    try:
        create_tables()
        connection = get_connection()

        try:
            with connection.cursor() as cursor:

                cursor.execute("DELETE FROM events")

                if events:

                    sql = """
                        INSERT INTO events (
                            month, day, time, host, process, pid,
                            event_type, status, event_user, ip, port,
                            method, invalid_user, reason, count, country
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s
                        )
                    """

                    values = []

                    for event in events:

                        values.append((
                            event.get('month'),
                            event.get('day'),
                            event.get('time'),
                            event.get('host'),
                            event.get('process'),
                            str(event.get('pid') or ''),
                            event.get('event_type'),
                            event.get('status'),
                            event.get('user'),
                            event.get('ip'),
                            str(event.get('port') or ''),
                            event.get('method'),
                            bool(event.get('invalid_user', False)),
                            event.get('reason'),
                            int(event.get('count') or 1),
                            event.get('country')
                        ))

                    cursor.executemany(sql, values)

            connection.commit()

        finally:
            connection.close()

    except (pymysql.MySQLError, TypeError, ValueError) as e:
        logger.error(f"Database save error: {e}")
        return False

    logger.info(f"{len(events)} events saved in MariaDB.")

    return save_json(
        {'files': get_data_state(data_dir)},
        state_file
    )


def load_events(events_file=None):
    """Charge les evenements depuis MariaDB."""

    try:
        create_tables()
        connection = get_connection()

        try:
            with connection.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        month,
                        day,
                        time,
                        host,
                        process,
                        pid,
                        event_type,
                        status,
                        event_user AS user,
                        ip,
                        port,
                        method,
                        invalid_user,
                        reason,
                        count,
                        country
                    FROM events
                    ORDER BY id
                """)

                events = cursor.fetchall()

        finally:
            connection.close()

        for event in events:
            event['count'] = int(event['count'] or 1)
            event['invalid_user'] = bool(event['invalid_user'])

        logger.info(f"{len(events)} events loaded from MariaDB.")

        return events

    except (pymysql.MySQLError, TypeError, ValueError) as e:
        logger.error(f"Database read error: {e}")
        return []


# ---------- CACHE DE GEOLOCALISATION ----------

def load_geo_cache(file_path: str = GEO_CACHE_FILE):
    return load_json(file_path, {})


def save_geo_cache(cache: dict, file_path: str = GEO_CACHE_FILE):
    return save_json(cache, file_path)


# ---------- STATISTIQUES ----------

def save_statistics(statistics: dict, file_path: str = STATISTICS_FILE):
    """Enregistre les statistiques dans MariaDB et JSON."""

    try:
        create_tables()
        connection = get_connection()

        try:
            with connection.cursor() as cursor:

                cursor.execute("""
                    INSERT INTO pipeline_statistics (id, content)
                    VALUES (1, %s)
                    ON DUPLICATE KEY UPDATE content = VALUES(content)
                """, (
                    json.dumps(statistics, ensure_ascii=False),
                ))

            connection.commit()

        finally:
            connection.close()

    except (pymysql.MySQLError, TypeError, ValueError) as e:
        logger.error(f"Statistics database save error: {e}")
        return False

    return save_json(statistics, file_path)
