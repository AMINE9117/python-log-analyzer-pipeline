import logging
import os
from logging.handlers import RotatingFileHandler

"""
Configuration des logs de l'application.
Chaque module (main, ingestion, processing, geolocation, storage, serving)
écrit dans son propre fichier : logs/<nom_du_module>.log
"""

LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')

LOG_FORMAT = '%(asctime)s %(msecs)03d|%(name)s|%(levelname)s|%(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


def get_logger(name: str, level: int = logging.INFO):
    """Retourne le logger du module `name`, écrit dans logs/<name>.log."""
    logger = logging.getLogger(name)

    # Le logger est déjà configuré : on ne rajoute pas un deuxième handler
    # (sinon chaque message serait écrit plusieurs fois).
    if logger.handlers:
        return logger

    os.makedirs(LOGS_DIR, exist_ok=True)

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    # Rotation par taille : au maximum 1 Mo par fichier, 5 anciens fichiers gardés
    file_handler = RotatingFileHandler(
        filename=os.path.join(LOGS_DIR, name + '.log'),
        maxBytes=1_000_000,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)

    logger.setLevel(level)
    logger.addHandler(file_handler)
    # Les messages ne remontent pas au logger racine (pas de doublon en console)
    logger.propagate = False
    return logger
