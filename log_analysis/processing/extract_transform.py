"""
Module d'extraction et de transformation
in  : liste de lignes de logs (str) retournée par ingestion.read.ingest
out : liste de dictionnaires, un par ligne reconnue

Chaque dictionnaire contient :
    date          : 'MM-JJ' (les logs syslog n'ont pas d'année), ex. '05-24'
    heure         : 'HH:MM:SS'
    ip            : adresse IP de la source ('' si absente)
    username      : nom d'utilisateur ('' si absent ou vide)
    event_type    : type d'événement (voir RULES ci-dessous)
    status        : 'success' | 'failed' | 'info'
    invalid_user  : True si sshd indique « invalid user »
    raw_line      : ligne d'origine
    count         : nombre d'occurrences (> 1 pour « message repeated N times »)
    program       : programme qui a écrit la ligne (sshd, CRON, sudo ...)

Pour compter les tentatives ÉCHOUÉES, il faut filtrer status == 'failed'
(et additionner 'count'). Les autres lignes liées à la même tentative
(Invalid user, pam_unix ...) ont le statut 'info' pour ne pas être comptées deux fois.
"""
import logging
import os
import re
from collections import Counter
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Dossier logs/ à la racine du projet (ne dépend pas du dossier de lancement)
LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
MAX_LOGGED_LINES = 50  # on n'écrit pas des milliers de lignes dans le fichier de logs

MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
    'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'}

# Adresse IPv4 ou IPv6 (groupe nommé ip)
IP = r'(?P<ip>\d{1,3}(?:\.\d{1,3}){3}|[0-9a-fA-F]*:[0-9a-fA-F:.]+)'

# Ex. : May 24 00:04:36 ns sshd[1350968]: Connection closed by 127.0.0.1 port 40940 [preauth]
HEADER_PATTERN = re.compile(
    r'^(?P<month>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s'
    r'(?P<heure>(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d)\s'
    r'(?P<host>\S+)\s(?P<program>[^\s\[:]+)(?:\[(?P<pid>\d+)\])?:\s?(?P<message>.*)$')

# Ex. : message repeated 4 times: [ Failed password for root from 1.2.3.4 port 22 ssh2]
REPEAT_PATTERN = re.compile(r'^message repeated (?P<count>\d+) times: \[ ?(?P<message>.*)\]$')

# Règles de reconnaissance des messages sshd : (event_type, status, regex).
# La première règle qui correspond est utilisée, donc l'ordre est important.
# Groupes nommés possibles : ip, user, invalid.
RULES = [
    # Connexion réussie : Accepted password for adminesisa from 10.10.33.81 port 59176 ssh2
    ('login_success', 'success', re.compile(
        r'^Accepted \S+ for (?P<user>.*?) from ' + IP + r' port \d+')),

    # Échec : Failed password for root from ...  /  Failed password for invalid user test from ...
    ('login_failed', 'failed', re.compile(
        r'^Failed \S+ for (?:(?P<invalid>invalid) user )?(?P<user>.*?) from ' + IP + r' port \d+')),

    # Avertissement sshd : Invalid user admin from 1.2.3.4 port 5 (même tentative que ci-dessus)
    ('invalid_user', 'info', re.compile(
        r'^(?P<invalid>Invalid) user (?P<user>.*?) from ' + IP + r' port \d+')),

    # error: maximum authentication attempts exceeded for root from 1.2.3.4 port 5 ssh2
    ('max_auth_exceeded', 'info', re.compile(
        r'^error: maximum authentication attempts exceeded for (?:(?P<invalid>invalid) user )?'
        r'(?P<user>.*?) from ' + IP + r' port \d+')),

    # pam_unix(sshd:auth): authentication failure; ... rhost=1.2.3.4  user=root
    ('pam_auth_failure', 'info', re.compile(
        r'^(?:pam_unix\(sshd:auth\): authentication failure|PAM \d+ more authentication failures?);'
        r'.*?\brhost=' + IP + r'?(?:\s+user=(?P<user>\S+))?')),

    # pam_unix(sshd:session): session opened for user adminesisa(uid=1000) by (uid=0)
    ('session_opened', 'info', re.compile(
        r'^pam_unix\(sshd:session\): session opened for user (?P<user>[^\s(]+)')),
    ('session_closed', 'info', re.compile(
        r'^pam_unix\(sshd:session\): session closed for user (?P<user>[^\s(]+)')),

    # Connection closed by [invalid user|authenticating user|user] X 1.2.3.4 port 5 [preauth]
    ('connection_closed', 'info', re.compile(
        r'^(?:Connection closed by|Connection reset by|Disconnected from|Disconnecting|'
        r'Received disconnect from)\s+'
        r'(?:(?:(?:(?P<invalid>invalid)|authenticating)\s)?user\s(?P<user>.*?)\s)?' + IP + r'\s+port\s+\d+')),

    # Erreurs de protocole : error: ..., fatal: ..., Unable to negotiate ..., banner exchange ...
    ('protocol_error', 'info', re.compile(
        r'^(?:error: |fatal: |Unable to negotiate|banner exchange|userauth_pubkey|'
        r'drop connection|padding error|ssh_dispatch_run_fatal|exited MaxStartups)')),
]

# Pour les erreurs de protocole, l'IP est après « with » ou « from » (parfois entre crochets)
PROTOCOL_IP_PATTERN = re.compile(r'(?:with|from)\s+\[?' + IP)


def get_logger():
    """Retourne le logger du module (créé une seule fois, un seul handler)."""
    logger = logging.getLogger("processing")
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
            filename=LOGS_DIR / "processing.log",
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


def classify_message(message: str):
    """Analyse le message d'une ligne sshd : type, statut, IP, utilisateur."""
    result = {'event_type': 'other', 'status': 'info', 'ip': '',
              'username': '', 'invalid_user': False, 'count': 1}

    # « message repeated N times: [ ... ] » : on analyse le message à l'intérieur
    repeat = re.match(REPEAT_PATTERN, message)
    if repeat:
        result['count'] = int(repeat.group('count'))
        message = repeat.group('message')

    for event_type, status, pattern in RULES:
        match = re.search(pattern, message)
        if match:
            groups = match.groupdict()
            result['event_type'] = event_type
            result['status'] = status
            result['ip'] = groups.get('ip') or ''
            result['username'] = groups.get('user') or ''
            result['invalid_user'] = groups.get('invalid') is not None
            break

    if result['event_type'] == 'protocol_error':
        match = re.search(PROTOCOL_IP_PATTERN, message)
        if match:
            result['ip'] = match.group('ip')
    return result


def extract(row: str):
    """Transforme une ligne de log en dictionnaire. Retourne None si la ligne n'est pas reconnue."""
    if not isinstance(row, str):
        return None
    line = row.strip()

    match = re.match(HEADER_PATTERN, line)
    if not match:
        return None
    header = match.groupdict()

    month = MONTHS.get(header['month'])
    day = int(header['day'])
    if month is None or not 1 <= day <= 31:
        return None

    # Seules les lignes de sshd sont analysées en détail
    if header['program'] == 'sshd':
        details = classify_message(header['message'])
    else:
        details = {'event_type': 'other', 'status': 'info', 'ip': '',
                   'username': '', 'invalid_user': False, 'count': 1}

    return {
        'date': f"{month}-{day:02d}",
        'heure': header['heure'],
        'ip': details['ip'],
        'username': details['username'],
        'event_type': details['event_type'],
        'status': details['status'],
        'invalid_user': details['invalid_user'],
        'raw_line': line,
        'count': details['count'],
        'program': header['program'],
    }


def extract_all(rows: list):
    """Transforme toutes les lignes. Retourne (liste des événements, nombre de lignes non reconnues)."""
    logger = get_logger()
    events = []
    unrecognized = 0

    for row in rows or []:
        try:
            event = extract(row)
        except Exception:
            logger.exception("Erreur inattendue pendant l'analyse de la ligne : %s", row)
            event = None

        if event is None:
            unrecognized += 1
            if unrecognized <= MAX_LOGGED_LINES:
                logger.warning("Ligne non reconnue : %s", row)
        else:
            events.append(event)

    if unrecognized > MAX_LOGGED_LINES:
        logger.warning("%d autres lignes non reconnues non détaillées",
                       unrecognized - MAX_LOGGED_LINES)
    logger.info("Extraction terminée : %d événements, %d lignes non reconnues",
                len(events), unrecognized)
    return events, unrecognized


if __name__ == '__main__':
    # À lancer depuis la racine du projet : python -m processing.extract_transform
    from ingestion import read

    rows = read.ingest('./data')
    events, unrecognized = extract_all(rows)
    print(f"{len(rows)} lignes lues, {len(events)} événements, {unrecognized} lignes non reconnues")
    for event_type, number in Counter(e['event_type'] for e in events).most_common():
        print(f"  {event_type}: {number}")