"""
Module serving : tableau de bord (dashboard)
in  : événements sauvegardés par storage.store (storage/events.json)
out : une figure matplotlib avec les 3 graphiques demandés et un résumé,
      enregistrée dans serving/dashboard.png puis affichée.

Champs des événements utilisés (produits par extract_transform et geolocation) :
    status        : 'success' | 'failed' | 'info'
    username      : nom d'utilisateur ('' si absent)
    invalid_user  : True si sshd indique « invalid user »
    country       : pays de l'IP (code à 2 lettres ou 'Unknown')
    ip            : adresse IP
    count         : nombre d'occurrences (> 1 pour « message repeated N times »)

Seuls les événements avec status == 'failed' ou 'success' sont comptés : les autres
lignes (Invalid user, pam_unix ...) décrivent la même tentative et ne doivent pas
être comptées une deuxième fois.
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from storage import store

try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

SERVING_DIR = Path(__file__).resolve().parent
# Dossier logs/ à la racine du projet (ne dépend pas du dossier de lancement)
LOGS_DIR = SERVING_DIR.parent / "logs"
IMAGE_FILE = SERVING_DIR / "dashboard.png"

UNKNOWN = "Unknown"          # pays introuvable
UNKNOWN_USER = "(inconnu)"   # nom d'utilisateur vide ou absent
TOP_COUNTRIES = 15           # nombre de pays affichés (les autres sont regroupés)
TOP_USERS = 10
TOP_INVALID_USERS = 10


def get_logger():
    """Retourne le logger du module (créé une seule fois, un seul handler)."""
    logger = logging.getLogger("serving")
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
            filename=LOGS_DIR / "serving.log",
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


# ---------------------------------------------------------------------------
# 1. Calcul des statistiques
# ---------------------------------------------------------------------------

def get_count(event: dict):
    """Nombre d'occurrences d'un événement (1 si la valeur est absente ou incorrecte)."""
    count = event.get('count', 1)
    if isinstance(count, int) and not isinstance(count, bool) and count > 0:
        return count
    return 1


def get_username(event: dict):
    """Nom d'utilisateur de l'événement, ou '(inconnu)' s'il est vide ou absent."""
    username = event.get('username')
    if isinstance(username, str) and username.strip():
        return username
    return UNKNOWN_USER


def count_failed_by_country(events: list):
    """Graphique 1 : {pays: nombre de tentatives échouées}."""
    counts = {}
    for event in events:
        if event.get('status') != 'failed':
            continue
        country = event.get('country')
        if not isinstance(country, str) or not country.strip():
            country = UNKNOWN
        counts[country] = counts.get(country, 0) + get_count(event)
    return counts


def count_success_by_user(events: list):
    """Graphique 2 : {utilisateur: nombre de connexions réussies}."""
    counts = {}
    for event in events:
        if event.get('status') != 'success':
            continue
        username = get_username(event)
        counts[username] = counts.get(username, 0) + get_count(event)
    return counts


def count_failed_invalid_users(events: list):
    """Graphique 3 : {utilisateur invalide: nombre de tentatives échouées}."""
    counts = {}
    for event in events:
        if event.get('status') != 'failed' or event.get('invalid_user') is not True:
            continue
        username = get_username(event)
        counts[username] = counts.get(username, 0) + get_count(event)
    return counts


def compute_summary(events: list):
    """Résumé statistique : lignes, réussites, échecs, utilisateurs invalides, IP distinctes."""
    summary = {'lines': len(events), 'success': 0, 'failed': 0, 'invalid': 0, 'ips': 0}
    ips = set()
    for event in events:
        if event.get('ip'):
            ips.add(event['ip'])
        if event.get('status') == 'success':
            summary['success'] += get_count(event)
        elif event.get('status') == 'failed':
            summary['failed'] += get_count(event)
            if event.get('invalid_user') is True:
                summary['invalid'] += get_count(event)
    summary['ips'] = len(ips)
    return summary


def sort_key(item: tuple):
    """Tri : valeur décroissante, puis nom (ordre alphabétique) en cas d'égalité."""
    return (-item[1], item[0])


def sort_counts(counts: dict):
    """Retourne la liste [(nom, valeur)] triée par valeur décroissante."""
    return sorted(counts.items(), key=sort_key)


def keep_top(sorted_items: list, limit: int, other_label: str):
    """Garde les 'limit' premiers éléments et regroupe les autres dans une barre « Autres »."""
    if len(sorted_items) <= limit:
        return sorted_items
    top = sorted_items[:limit]
    others = sorted_items[limit:]
    top.append((f"{other_label} ({len(others)})", sum(value for _, value in others)))
    return top


def format_number(number: int):
    """65565 -> '65 565'."""
    return f"{number:,}".replace(",", " ")


# ---------------------------------------------------------------------------
# 2. Dessin des graphiques
# ---------------------------------------------------------------------------

def draw_empty(ax, title: str):
    """Affiche « Aucune donnée » dans un graphique sans données."""
    ax.clear()
    ax.set_title(title, fontsize=11, fontweight='bold')
    ax.text(0.5, 0.5, "Aucune donnée", ha='center', va='center',
            transform=ax.transAxes, fontsize=13, color='gray')
    ax.set_xticks([])
    ax.set_yticks([])


def plot_failed_by_country(ax, counts: dict):
    """Graphique 1 : barres verticales, pays en abscisse, tentatives échouées en ordonnée."""
    total = sum(counts.values())
    title = f"1. Tentatives échouées par pays (total : {format_number(total)})"
    if not counts:
        draw_empty(ax, title)
        return
    if list(counts) == [UNKNOWN]:
        title += "\n(aucun pays trouvé : géolocalisation non disponible)"

    items = keep_top(sort_counts(counts), TOP_COUNTRIES, "Autres")
    bars = ax.bar([name for name, _ in items], [value for _, value in items], color='tab:red')
    ax.bar_label(bars, padding=2, fontsize=8)
    ax.set_title(title, fontsize=11, fontweight='bold')
    ax.set_xlabel("Pays")
    ax.set_ylabel("Tentatives échouées")
    ax.tick_params(axis='x', rotation=45)
    ax.set_ylim(0, max(value for _, value in items) * 1.12)


def plot_success_by_user(ax, counts: dict):
    """Graphique 2 : barres verticales, utilisateurs en abscisse, connexions réussies en ordonnée."""
    total = sum(counts.values())
    title = f"2. Connexions réussies par utilisateur (total : {format_number(total)})"
    if not counts:
        draw_empty(ax, title)
        return

    items = sort_counts(counts)[:TOP_USERS]
    values = [value for _, value in items]
    bars = ax.bar([name for name, _ in items], values, color='tab:green', width=0.5)
    ax.bar_label(bars, padding=2, fontsize=9)
    ax.set_title(title, fontsize=11, fontweight='bold')
    ax.set_xlabel("Utilisateur")
    ax.set_ylabel("Connexions réussies")
    ax.tick_params(axis='x', rotation=30)
    ax.set_ylim(0, max(values) * 1.15)
    if max(values) <= 10:
        ax.set_yticks(range(0, max(values) + 2))   # graduations entières seulement


def plot_failed_invalid_users(ax, counts: dict):
    """Graphique 3 : barres horizontales des utilisateurs invalides les plus ciblés."""
    total = sum(counts.values())
    title = (f"3. Échecs avec utilisateur invalide (total : {format_number(total)}, "
             f"{format_number(len(counts))} noms distincts)")
    if not counts:
        draw_empty(ax, title)
        return

    items = sort_counts(counts)[:TOP_INVALID_USERS]
    if len(counts) > len(items):
        title += f"\n(les {len(items)} plus ciblés)"
    bars = ax.barh([name for name, _ in items], [value for _, value in items], color='tab:orange')
    ax.bar_label(bars, padding=2, fontsize=9)
    ax.invert_yaxis()                      # le plus ciblé en haut
    ax.set_title(title, fontsize=11, fontweight='bold')
    ax.set_xlabel("Tentatives échouées")
    ax.set_ylabel("Utilisateur invalide")
    ax.set_xlim(0, max(value for _, value in items) * 1.12)


def draw_summary(ax, summary: dict):
    """Petit résumé statistique en texte."""
    ax.axis('off')
    lines = [
        ("Résumé statistique", 15, 'bold'),
        ("", 8, 'normal'),
        (f"Lignes analysées : {format_number(summary['lines'])}", 13, 'normal'),
        (f"Connexions réussies : {format_number(summary['success'])}", 13, 'normal'),
        (f"Connexions échouées : {format_number(summary['failed'])}", 13, 'normal'),
        (f"Échecs avec utilisateur invalide : {format_number(summary['invalid'])}", 13, 'normal'),
        (f"Adresses IP distinctes : {format_number(summary['ips'])}", 13, 'normal'),
    ]
    y = 0.92
    for text, size, weight in lines:
        ax.text(0.05, y, text, fontsize=size, fontweight=weight, va='top', transform=ax.transAxes)
        y -= 0.07 + size / 400


def draw_chart(draw_function, ax, data, title: str):
    """Dessine un graphique ; en cas d'erreur, on l'enregistre et les autres graphiques restent affichés."""
    try:
        draw_function(ax, data)
    except Exception:
        get_logger().exception("Erreur de génération du graphique : %s", title)
        draw_empty(ax, f"{title} (erreur, voir logs/serving.log)")


def create_dashboard(events: list):
    """Construit la figure avec les 3 graphiques et le résumé. Retourne la figure."""
    fig, axes = plt.subplots(2, 2, figsize=(15, 9))
    fig.suptitle("Log Analyzer - Tableau de bord des connexions SSH", fontsize=17, fontweight='bold')

    draw_chart(plot_failed_by_country, axes[0][0], count_failed_by_country(events),
               "1. Tentatives échouées par pays")
    draw_chart(plot_success_by_user, axes[0][1], count_success_by_user(events),
               "2. Connexions réussies par utilisateur")
    draw_chart(plot_failed_invalid_users, axes[1][0], count_failed_invalid_users(events),
               "3. Échecs avec utilisateur invalide")
    draw_chart(draw_summary, axes[1][1], compute_summary(events), "Résumé")

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    return fig


# ---------------------------------------------------------------------------
# 3. Point d'entrée du module
# ---------------------------------------------------------------------------

def run_dashboard(file_path=store.EVENTS_FILE, show=True, image_path=IMAGE_FILE):
    """Charge les événements stockés, crée le dashboard, l'enregistre en PNG et l'affiche.

    Retourne True si le dashboard a été créé, False sinon (message d'erreur affiché).
    """
    logger = get_logger()
    try:
        if plt is None:
            logger.critical("matplotlib n'est pas installé")
            print("Erreur : matplotlib n'est pas installé. Lance : uv sync")
            return False

        events = store.load_events(file_path)
        if not events:
            logger.error("Aucun événement disponible dans %s : dashboard non créé", file_path)
            print(f"Erreur : aucune donnée dans {file_path}")
            print("Lance d'abord le pipeline pour créer storage/events.json (voir logs/storage.log).")
            return False

        fig = create_dashboard(events)
        try:
            fig.savefig(image_path, dpi=120)
            logger.info("Dashboard enregistré dans %s (%d événements)", image_path, len(events))
            print(f"Dashboard enregistré : {image_path}")
        except OSError as e:
            logger.error("Impossible d'enregistrer l'image %s : %s", image_path, e)
            print("Avertissement : l'image n'a pas pu être enregistrée.")

        if show:
            plt.show()
        plt.close(fig)
        return True
    except Exception:
        logger.exception("Erreur inattendue pendant la création du dashboard")
        print("Erreur : le dashboard n'a pas pu être créé (voir logs/serving.log).")
        return False


if __name__ == '__main__':
    # À lancer depuis le dossier log_analysis : python -m serving.dashboard
    run_dashboard()
