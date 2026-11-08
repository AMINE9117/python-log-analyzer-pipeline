"""
Module d'ingestion
in  : dossier data (ou un seul fichier)
out : liste des lignes (str) de tous les fichiers de logs trouvés
"""
import gzip
import logging
import os
import os.path as pt
import re
import zlib
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Dossier logs/ à la racine du projet (ne dépend pas du dossier de lancement)
LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"

# Noms acceptés : auth.log, auth.log.1, auth.log.3.gz, notes.txt, notes.txt.gz ...
LOG_FILE_PATTERN = re.compile(r"\.(log|txt)(\.\d+)?(\.gz)?$", re.IGNORECASE)


def get_logger():
    """Retourne le logger du module (créé une seule fois, un seul handler)."""
    logger = logging.getLogger("ingestion")
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
            filename=LOGS_DIR / "ingestion.log",
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


def is_log_file(file_name: str):
    """Vrai si le nom ressemble à un fichier de logs (.log, .txt, .gz ...)."""
    return LOG_FILE_PATTERN.search(file_name) is not None


def list_log_files(path: str):
    """Retourne la liste triée des chemins de fichiers de logs de path."""
    logger = get_logger()

    if not pt.exists(path):
        logger.error("Dossier ou fichier introuvable : %s", path)
        return []

    if pt.isfile(path):
        return [path]

    try:
        names = sorted(os.listdir(path))
    except OSError as e:
        logger.error("Impossible de lister le dossier %s : %s", path, e)
        return []

    files = []
    for name in names:
        file_path = pt.join(path, name)
        if not pt.isfile(file_path):
            continue
        if is_log_file(name):
            files.append(file_path)
        else:
            logger.info("Fichier ignoré (type non pris en charge) : %s", file_path)

    if not files:
        logger.warning("Aucun fichier de logs trouvé dans : %s", path)
    return files


def open_file(file_path: str):
    """Ouvre en mode texte un fichier normal ou compressé .gz."""
    # errors='replace' : un caractère illisible ne fait pas planter la lecture
    if file_path.lower().endswith('.gz'):
        return gzip.open(file_path, mode='rt', encoding='utf-8', errors='replace')
    return open(file_path, mode='r', encoding='utf-8', errors='replace')


def read_file(file_path: str):
    """Lit un fichier et retourne ses lignes (sans retour à la ligne ni lignes vides).

    En cas d'erreur, l'erreur est enregistrée et on retourne les lignes
    déjà lues (liste vide si rien n'a pu être lu).
    """
    logger = get_logger()
    rows = []
    try:
        with open_file(file_path) as f:
            for line in f:
                line = line.rstrip("\r\n")
                if line.strip():
                    rows.append(line)
    except FileNotFoundError:
        logger.error("Fichier introuvable : %s", file_path)
    except PermissionError:
        logger.error("Permission refusée pour lire : %s", file_path)
    except (gzip.BadGzipFile, EOFError, zlib.error) as e:
        logger.error("Fichier compressé corrompu : %s (%s) - %d lignes lues avant l'erreur",
                     file_path, e, len(rows))
    except (OSError, UnicodeError) as e:
        logger.error("Erreur de lecture de %s : %s", file_path, e)
    except Exception:
        logger.exception("Erreur inattendue pendant la lecture de %s", file_path)
    else:
        if not rows:
            logger.warning("Fichier vide : %s", file_path)
    return rows


def ingest(path: str):
    """Lit tous les fichiers de logs de path et retourne la liste de toutes les lignes."""
    logger = get_logger()
    all_rows = []
    try:
        files = list_log_files(path)
        for file_path in files:
            rows = read_file(file_path)
            logger.info("%s : %d lignes lues", file_path, len(rows))
            all_rows.extend(rows)
        logger.info("Ingestion terminée : %d fichiers, %d lignes au total",
                    len(files), len(all_rows))
    except Exception:
        logger.exception("Erreur inattendue pendant l'ingestion de %s", path)
    return all_rows


if __name__ == "__main__":
    data = ingest('./data')
    print(f"{len(data)} lignes lues")
    if data:
        print(data[:10])
