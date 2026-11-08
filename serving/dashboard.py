import os

import matplotlib.pyplot as plt

from log_config import get_logger

"""
Dashboard matplotlib : 3 indicateurs + un résumé statistique.
"""

logger = get_logger('serving')

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
DASHBOARD_FILE = os.path.join(OUTPUT_DIR, 'dashboard.png')

TOP_COUNTRIES = 15
TOP_INVALID_USERS = 10


def draw_bars(ax, items: list, title: str, xlabel: str, ylabel: str, color: str):
    """Diagramme en barres avec la valeur affichée au-dessus de chaque barre."""
    labels = [label for label, _ in items]
    values = [value for _, value in items]
    bars = ax.bar(labels, values, color=color)
    ax.bar_label(bars, padding=2, fontsize=8)
    ax.set_title(title, fontsize=11, fontweight='bold')
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis='x', labelrotation=45, labelsize=8)
    ax.margins(y=0.15)  # place pour les valeurs
    if not items:
        ax.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax.transAxes)


def draw_summary(ax, statistics: dict):
    """Encadré avec le résumé statistique."""
    ax.axis('off')
    lines = [
        ('Lines analysed', statistics['total_lines']),
        ('Successful logins', statistics['successful_logins']),
        ('Failed logins', statistics['failed_logins']),
        ('Failed logins (invalid user)', statistics['invalid_user_attempts']),
        ('Distinct invalid users', statistics['distinct_invalid_users']),
        ('Distinct IP addresses', statistics['distinct_ips']),
    ]
    ax.set_title('Summary', fontsize=11, fontweight='bold')
    for number, (label, value) in enumerate(lines):
        y = 0.88 - number * 0.15
        ax.text(0.05, y, label, fontsize=11, transform=ax.transAxes)
        ax.text(0.95, y, f'{value:,}'.replace(',', ' '), fontsize=11, fontweight='bold',
                ha='right', transform=ax.transAxes)


def build_dashboard(statistics: dict, output_file: str = DASHBOARD_FILE, show: bool = True):
    """Crée la figure, l'enregistre en PNG et l'affiche si `show` est vrai.
    Retourne le chemin de l'image, ou None en cas d'erreur."""
    try:
        fig, axes = plt.subplots(2, 2, figsize=(16, 10))
        fig.suptitle('SSH log analysis dashboard', fontsize=15, fontweight='bold')

        countries = statistics['failures_by_country']
        draw_bars(axes[0][0], countries[:TOP_COUNTRIES],
                  f'Failed logins by country (top {min(TOP_COUNTRIES, len(countries))} of {len(countries)})',
                  'Country', 'Failed attempts', '#d62728')

        draw_bars(axes[0][1], statistics['successes_by_user'],
                  'Successful logins by user', 'User', 'Successful logins', '#2ca02c')

        draw_bars(axes[1][0], statistics['invalid_users'][:TOP_INVALID_USERS],
                  f"Failed logins with invalid user: {statistics['invalid_user_attempts']} "
                  f"(top {TOP_INVALID_USERS} usernames)",
                  'Invalid username', 'Failed attempts', '#ff7f0e')

        draw_summary(axes[1][1], statistics)

        fig.tight_layout()
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        fig.savefig(output_file, dpi=110)
        logger.info(f"Dashboard saved in {output_file}")
    except (OSError, ValueError, KeyError) as e:
        logger.error(f"Dashboard generation error: {e}")
        plt.close('all')
        return None

    if show:
        plt.show()
    plt.close(fig)
    return output_file
