from collections import Counter

from log_config import get_logger

"""
Calcul des statistiques du dashboard à partir des événements.
Chaque événement compte `count` fois (lignes "message repeated N times").
"""

logger = get_logger('serving')


def sort_counter(counter: Counter):
    """Liste de (clé, valeur) triée par valeur décroissante puis par clé."""
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))


def failures_by_country(events: list):
    """Indicateur 1 : tentatives échouées par pays."""
    counter = Counter()
    for event in events:
        if event['status'] == 'failure':
            counter[event['country'] or 'Unknown'] += event['count']
    return sort_counter(counter)


def successes_by_user(events: list):
    """Indicateur 2 : connexions réussies par utilisateur."""
    counter = Counter()
    for event in events:
        if event['event_type'] == 'accepted':
            counter[event['user']] += event['count']
    return sort_counter(counter)


def invalid_user_failures(events: list):
    """Indicateur 3 : tentatives échouées avec utilisateur invalide, par nom d'utilisateur.
    Seules les lignes "Failed ... for invalid user" sont comptées : la ligne
    "Invalid user ..." qui les précède décrit la même tentative."""
    counter = Counter()
    for event in events:
        if event['event_type'] == 'failed_invalid_user':
            counter[event['user'] or '(empty)'] += event['count']
    return sort_counter(counter)


MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def month_number(month: str):
    """'May' -> 5 (0 si le mois est inconnu)."""
    return MONTHS.index(month) + 1 if month in MONTHS else 0


def dated_events(events: list):
    """Événements qui ont une date et une heure (les lignes 'unparsed' n'en ont pas)."""
    return [event for event in events if event['month'] and event['day'] and event['time']]


def activity_by_hour(events: list):
    """Indicateur 4 : nombre de lignes de logs pour chaque heure de la journée (0 à 23)."""
    counter = Counter(int(event['time'][:2]) for event in dated_events(events))
    return [(hour, counter[hour]) for hour in range(24)]


def activity_by_day(events: list):
    """Indicateur 5 : nombre de lignes de logs par jour, dans l'ordre du calendrier."""
    counter = Counter((event['month'], int(event['day'])) for event in dated_events(events))
    days = sorted(counter, key=lambda key: (month_number(key[0]), key[1]))
    return [(f'{month} {day}', counter[(month, day)]) for month, day in days]


def busiest_moment(events: list):
    """L'heure précise (jour + heure) où il y a eu le plus de lignes de logs."""
    counter = Counter((event['month'], int(event['day']), int(event['time'][:2]))
                      for event in dated_events(events))
    if not counter:
        return None
    (month, day, hour), lines = sort_counter(counter)[0]
    return {'day': f'{month} {day}', 'hour': hour, 'lines': lines}


def analysed_period(events: list):
    """Première et dernière date des logs.
    L'année n'est pas écrite dans auth.log : on trie par mois, jour puis heure."""
    dates = [(month_number(event['month']), int(event['day']), event['time'], event['month'])
             for event in dated_events(events)]
    if not dates:
        return None
    first, last = min(dates), max(dates)
    return {'start': f'{first[3]} {first[1]} {first[2][:5]}',
            'end': f'{last[3]} {last[1]} {last[2][:5]}'}


def compute_statistics(events: list):
    """Toutes les statistiques nécessaires au dashboard."""
    by_country = failures_by_country(events)
    by_user = successes_by_user(events)
    invalid = invalid_user_failures(events)

    statistics = {
        'total_lines': len(events),
        'successful_logins': sum(count for _, count in by_user),
        'failed_logins': sum(count for _, count in by_country),
        'invalid_user_attempts': sum(count for _, count in invalid),
        'distinct_invalid_users': len(invalid),
        'distinct_ips': len({event['ip'] for event in events if event['ip']}),
        'failures_by_country': by_country,
        'successes_by_user': by_user,
        'invalid_users': invalid,
        'activity_by_hour': activity_by_hour(events),
        'activity_by_day': activity_by_day(events),
        'busiest_moment': busiest_moment(events),
        'period': analysed_period(events),
    }
    logger.info(f"Statistics computed: {statistics['failed_logins']} failures, "
                f"{statistics['successful_logins']} successes")
    return statistics
