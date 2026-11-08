import gzip
import os
import os.path as pt

from log_config import get_logger

"""
in:data
out:list of rows
 """

logger = get_logger('ingestion')

# Extensions acceptées en plus des fichiers de type "auth.log.1"
ACCEPTED_EXTENSIONS = ('.log', '.txt', '.gz')


def is_log_file(file_name: str):
    """Vrai si le fichier ressemble à un fichier de logs (auth.log, auth.log.1, x.txt, x.gz...)."""
    if file_name.startswith('.'):
        return False
    return file_name.endswith(ACCEPTED_EXTENSIONS) or '.log' in file_name


def list_log_files(path: str):
    """Retourne la liste triée des fichiers de logs présents dans le dossier `path`."""
    files = []
    for file in os.listdir(path):
        file_path = pt.join(path, file)
        if pt.isfile(file_path) and is_log_file(file):
            files.append(file_path)
        else:
            logger.info(f"Ignored (not a log file): {file_path}")
    # Ordre inverse : auth.log.4.gz (le plus ancien) ... auth.log.1 (le plus récent)
    files.sort(reverse=True)
    return files


def open_file(file_path: str):
    """Ouvre un fichier normal ou compressé (.gz) en mode texte."""
    openner = gzip.open(file_path, mode='rt', encoding="utf-8", errors='replace') if file_path.endswith(
        '.gz') else open(file_path, encoding="utf-8", errors='replace')  # operateur térnel
    return openner


def read_file(file_path: str):
    """Lit un fichier et retourne ses lignes (sans le retour à la ligne).
    En cas d'erreur, l'erreur est enregistrée et une liste vide est retournée."""
    try:
        with open_file(file_path) as f:
            rows = [row.rstrip('\n') for row in f]
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        return []
    except PermissionError:
        logger.error(f"Permission denied: {file_path}")
        return []
    except (gzip.BadGzipFile, EOFError) as e:
        logger.error(f"Corrupted compressed file {file_path}: {e}")
        return []
    except OSError as e:
        logger.error(f"Read error on {file_path}: {e}")
        return []

    if not rows:
        logger.warning(f"Empty file: {file_path}")
    else:
        logger.info(f"{len(rows)} rows read from {file_path}")
    return rows


def ingest(path: str):
    """Lit TOUS les fichiers de logs du dossier `path` et retourne la liste de toutes les lignes."""
    try:
        files = list_log_files(path)
    except FileNotFoundError:
        logger.error(f"Data directory not found: {path}")
        return []
    except NotADirectoryError:
        logger.error(f"Not a directory: {path}")
        return []
    except OSError as e:
        logger.error(f"Cannot list directory {path}: {e}")
        return []

    if not files:
        logger.warning(f"No log file found in {path}")
        return []

    rows = []
    for file_path in files:
        rows.extend(read_file(file_path))

    logger.info(f"Ingestion finished: {len(files)} files, {len(rows)} rows")
    return rows


if __name__ == "__main__":
    # Lancer depuis la racine du projet : python -m ingestion.read
    data = ingest('./data')
    if data:
        print(len(data), 'rows')
        print(data[:10])
