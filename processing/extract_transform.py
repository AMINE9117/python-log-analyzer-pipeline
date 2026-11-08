import re

from log_config import get_logger

"""
in : liste de lignes brutes (auth.log)
out: liste d'événements (dictionnaires)
"""

logger = get_logger('processing')

# En-tête syslog : "May  3 00:01:21 ns sshd[975159]: <message>"
HEADER_PATTERN = re.compile(
    r'^(?P<month>\w{3})\s+(?P<day>\d{1,2})\s(?P<time>\d{2}:\d{2}:\d{2})\s(?P<host>\S+)\s'
    r'(?P<process>[\w\-]+)(?:\[(?P<pid>\d+)\])?:\s(?P<message>.*)$')

IP = r'(?P<ip>\d{1,3}(?:\.\d{1,3}){3})'

# Connexion réussie : "Accepted password for adminesisa from 1.2.3.4 port 22 ssh2"
ACCEPTED_PATTERN = re.compile(
    r'^Accepted (?P<method>\S+) for (?P<user>\S+) from ' + IP + r' port (?P<port>\d+)')

# Échec avec utilisateur invalide : "Failed password for invalid user admin from 1.2.3.4 port 22 ssh2"
# (le nom peut être vide : "for invalid user  from")
FAILED_INVALID_PATTERN = re.compile(
    r'^Failed (?P<method>\S+) for invalid user (?P<user>\S*) ?from ' + IP + r' port (?P<port>\d+)')

# Échec avec utilisateur existant : "Failed password for root from 1.2.3.4 port 22 ssh2"
FAILED_PATTERN = re.compile(
    r'^Failed (?P<method>\S+) for (?P<user>\S+) from ' + IP + r' port (?P<port>\d+)')

# Annonce d'un utilisateur invalide : "Invalid user admin from 1.2.3.4 port 22"
# Ce n'est PAS une tentative à part : la ligne "Failed ... invalid user" suit.
INVALID_USER_PATTERN = re.compile(
    r'^Invalid user (?P<user>\S*) ?from ' + IP + r' port (?P<port>\d+)')

# syslog regroupe les messages identiques : "message repeated 4 times: [ Failed password ...]"
REPEATED_PATTERN = re.compile(r'^message repeated (?P<times>\d+) times: \[\s*(?P<inner>.*)\]$')

# N'importe quelle adresse IP dans le message (pour les autres événements)
ANY_IP_PATTERN = re.compile(IP)

# Ordre important : "invalid user" doit être testé avant l'échec simple
EVENT_PATTERNS = [
    ('accepted', 'success', ACCEPTED_PATTERN),
    ('failed_invalid_user', 'failure', FAILED_INVALID_PATTERN),
    ('failed', 'failure', FAILED_PATTERN),
    ('invalid_user', '', INVALID_USER_PATTERN),
]

# Colonnes d'un événement (utilisées aussi pour le fichier CSV)
EVENT_FIELDS = ['month', 'day', 'time', 'host', 'process', 'pid', 'event_type', 'status',
                'user', 'ip', 'port', 'method', 'invalid_user', 'reason', 'count', 'country']


def empty_event():
    """Événement avec toutes les colonnes vides."""
    event = {}
    for field in EVENT_FIELDS:
        event[field] = ''
    event['invalid_user'] = False
    event['count'] = 1
    return event


def failure_reason(event_type: str, method: str):
    """Motif de l'échec de connexion."""
    if event_type == 'failed_invalid_user':
        return 'invalid user'
    if method == 'password':
        return 'wrong password'
    return 'auth method refused: ' + method


def analyse_message(message: str, event: dict):
    """Identifie le type d'événement SSH et complète `event`."""
    for event_type, status, pattern in EVENT_PATTERNS:
        match = re.search(pattern, message)
        if match:
            infos = match.groupdict()
            event['event_type'] = event_type
            event['status'] = status
            event['user'] = infos['user']
            event['ip'] = infos['ip']
            event['port'] = infos['port']
            event['method'] = infos.get('method') or ''
            event['invalid_user'] = event_type in ('failed_invalid_user', 'invalid_user')
            if status == 'failure':
                event['reason'] = failure_reason(event_type, event['method'])
            return event

    # Autre événement : on garde seulement l'IP si elle existe
    event['event_type'] = 'other'
    ip_match = re.search(ANY_IP_PATTERN, message)
    if ip_match:
        event['ip'] = ip_match.group('ip')
    return event


def extract(row: str):
    """Transforme une ligne de log en événement (dictionnaire).
    Une ligne qui ne respecte pas le format syslog donne un événement 'unparsed'."""
    event = empty_event()
    match = re.search(HEADER_PATTERN, row)
    if not match:
        event['event_type'] = 'unparsed'
        return event

    header = match.groupdict()
    for field in ('month', 'day', 'time', 'host', 'process'):
        event[field] = header[field]
    event['pid'] = header['pid'] or ''
    message = header['message']

    # Messages regroupés par syslog : l'échec a eu lieu `times` fois
    repeated = re.search(REPEATED_PATTERN, message)
    if repeated:
        event['count'] = int(repeated.group('times'))
        message = repeated.group('inner')

    return analyse_message(message, event)


def transform(rows: list):
    """Transforme toutes les lignes en événements. Une ligne invalide ne bloque jamais le traitement."""
    events = []
    unparsed = 0
    for number, row in enumerate(rows, start=1):
        try:
            event = extract(row)
        except Exception as e:  # erreur inattendue sur une ligne : on la saute
            logger.error(f"Parsing error on row {number}: {e} | {row[:200]}")
            event = empty_event()
            event['event_type'] = 'unparsed'
        if event['event_type'] == 'unparsed':
            unparsed += 1
            logger.warning(f"Invalid row {number}: {row[:200]}")
        events.append(event)

    logger.info(f"{len(rows)} rows transformed, {unparsed} invalid rows")
    return events


if __name__ == "__main__":
    print(extract('May 24 01:14:12 ns sshd[1351821]: Failed password for invalid user admin '
                  'from 45.148.10.147 port 8868 ssh2'))
