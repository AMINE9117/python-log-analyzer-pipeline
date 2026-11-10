
import os
from datetime import datetime

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.ticker import FuncFormatter, MaxNLocator

from log_config import get_logger


"""
Dashboard matplotlib :
    - un bandeau d'en-tête (avec la période analysée)
    - 6 cartes d'indicateurs (le résumé statistique)
    - activité des logs par heure de la journée et par jour
    - tentatives échouées par pays
    - connexions réussies par utilisateur
    - tentatives échouées avec utilisateur invalide

La mise en page est faite dans un « canevas » de 1600 x 1364 unités
(1 unité = 1/100 de pouce, l'axe y descend) : chaque bloc est placé
avec des coordonnées simples (x, y, largeur, hauteur).
"""


logger = get_logger('serving')


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
DASHBOARD_FILE = os.path.join(OUTPUT_DIR, 'dashboard.png')


TOP_COUNTRIES = 15
TOP_INVALID_USERS = 10
TOP_USERS = 10

PROJECT_NAME = 'Log analysis pipeline'
PROJECT_CREDITS = 'Amine Nfissi  ·  ESISA  ·  Python avancé'

# ---------- MISE EN PAGE ----------

CANVAS_WIDTH = 1600
CANVAS_HEIGHT = 1364
MARGIN = 64
GAP = 20
DPI = 110           # résolution de l'image PNG
SCREEN_DPI = 72     # résolution de la fenêtre : le dashboard tient sur l'écran

# ---------- COULEURS ----------

BACKGROUND = '#F4F5F7'
CARD = '#FFFFFF'
CARD_BORDER = '#E4E4E7'
HEADER = '#18181B'
HEADER_TEXT = '#FAFAFA'
HEADER_MUTED = '#A1A1AA'
ACCENT = '#EB6834'

INK = '#18181B'         # titres et valeurs
TEXT = '#52525B'        # textes et axes
MUTED = '#71717A'       # sous-titres
GRID = '#E4E4E7'
AXIS = '#D4D4D8'
OTHERS = '#CBD5E1'      # barre « Others »

# Une seule teinte par graphique : clair = petite valeur, foncé = grande valeur
COUNTRY_COLORS = ('#F3A27A', '#B4400F')
INVALID_USER_COLORS = ('#86B6EF', '#104281')
SUCCESS_COLOR = '#1BAF7A'
# Activité dans le temps : le pic est en foncé, le reste en clair
TIME_COLOR = '#B3AAF3'
TIME_PEAK_COLOR = '#3F2F9E'
TIME_LINE_COLOR = '#6250D6'

# Couleur de la barre à gauche de chaque carte d'indicateur
KPI_COLORS = {
    'lines': '#52525B',
    'success': '#1BAF7A',
    'failure': '#EB6834',
    'invalid': '#E34948',
    'users': '#2A78D6',
    'ips': '#6250D6',
}

# Première police disponible : Segoe UI (Windows), sinon Arial, sinon celle de matplotlib
FONT_CANDIDATES = ['Segoe UI', 'Arial', 'Helvetica Neue', 'DejaVu Sans']


# ---------- OUTILS ----------

def format_number(value):
    """12345 -> '12 345'"""
    return f'{value:,}'.replace(',', ' ')


def hour_range(hour: int):
    """3 -> '03:00 – 04:00'"""
    return f'{hour:02d}:00 – {hour + 1:02d}:00'


def pick_font():
    """Retourne la première police de FONT_CANDIDATES installée sur la machine."""
    installed = {font.name for font in font_manager.fontManager.ttflist}
    for name in FONT_CANDIDATES:
        if name in installed:
            return name
    return 'sans-serif'


def blend(light: str, dark: str, ratio: float):
    """Couleur entre `light` (ratio = 0) et `dark` (ratio = 1)."""
    start = [int(light[i:i + 2], 16) for i in (1, 3, 5)]
    end = [int(dark[i:i + 2], 16) for i in (1, 3, 5)]
    mixed = [round(a + (b - a) * ratio) for a, b in zip(start, end)]
    return '#' + ''.join(f'{channel:02X}' for channel in mixed)


def shades(values: list, colors: tuple):
    """Une couleur par valeur : plus la valeur est grande, plus la couleur est foncée."""
    if not values:
        return []
    highest = max(values) or 1
    # racine carrée : les petites valeurs restent visibles à côté des grandes
    return [blend(colors[0], colors[1], (value / highest) ** 0.5) for value in values]


def group_others(items: list, top: int):
    """Garde les `top` premiers éléments et regroupe le reste dans une barre « Others ».
    Retourne (éléments, nombre d'éléments regroupés)."""
    if len(items) <= top:
        return list(items), 0
    rest = items[top:]
    others = ('Others\n(' + str(len(rest)) + ')', sum(value for _, value in rest))
    return list(items[:top]) + [others], len(rest)


def canvas_box(x: float, y: float, width: float, height: float):
    """Position d'un bloc du canevas en fraction de la figure (pour fig.add_axes)."""
    return [x / CANVAS_WIDTH, 1 - (y + height) / CANVAS_HEIGHT,
            width / CANVAS_WIDTH, height / CANVAS_HEIGHT]


# ---------- BLOCS DU CANEVAS ----------

def draw_card(canvas, x: float, y: float, width: float, height: float):
    """Fond blanc arrondi avec une bordure fine."""
    canvas.add_patch(FancyBboxPatch(
        (x, y), width, height,
        boxstyle='round,pad=0,rounding_size=10',
        facecolor=CARD, edgecolor=CARD_BORDER, linewidth=1, zorder=1
    ))


def draw_panel_title(canvas, x: float, y: float, title: str, subtitle: str):
    """Titre et sous-titre en haut d'un panneau."""
    canvas.text(x + 28, y + 38, title, fontsize=14.5, fontweight='bold',
                color=INK, va='center', zorder=2)
    canvas.text(x + 28, y + 64, subtitle, fontsize=10, color=MUTED,
                va='center', zorder=2)


def draw_header(canvas, statistics: dict):
    """Bandeau sombre en haut du dashboard, avec la période analysée."""
    canvas.add_patch(Rectangle((0, 0), CANVAS_WIDTH, 100, facecolor=HEADER, zorder=1))
    canvas.add_patch(Rectangle((0, 100), CANVAS_WIDTH, 3, facecolor=ACCENT, zorder=1))

    period = statistics.get('period')
    details = ['auth.log files from data/', 'countries located with IPinfo']
    if period:
        details.insert(0, f"Period analysed: {period['start']} to {period['end']}")

    canvas.text(MARGIN, 40, 'SSH Log Analysis', fontsize=25, fontweight='bold',
                color=HEADER_TEXT, va='center', zorder=2)
    canvas.text(MARGIN, 74, '   ·   '.join(details),
                fontsize=11, color=HEADER_MUTED, va='center', zorder=2)

    right = CANVAS_WIDTH - MARGIN
    canvas.text(right, 40, PROJECT_NAME, fontsize=13, fontweight='bold',
                color=HEADER_TEXT, ha='right', va='center', zorder=2)
    canvas.text(right, 74, PROJECT_CREDITS, fontsize=11, color=HEADER_MUTED,
                ha='right', va='center', zorder=2)


def draw_summary(canvas, statistics: dict):
    """Résumé statistique : une rangée de 6 cartes d'indicateurs."""
    countries = [country for country, _ in statistics['failures_by_country']
                 if country != 'Unknown']
    users = statistics['successes_by_user']
    invalid = statistics['invalid_users']
    failed = statistics['failed_logins']
    share = round(100 * statistics['invalid_user_attempts'] / failed) if failed else 0

    cards = [
        ('Lines analysed', statistics['total_lines'],
         'events read from auth.log', KPI_COLORS['lines']),
        ('Successful logins', statistics['successful_logins'],
         f'{len(users)} user(s)', KPI_COLORS['success']),
        ('Failed logins', failed,
         f'from {len(countries)} countries', KPI_COLORS['failure']),
        ('Invalid-user failures', statistics['invalid_user_attempts'],
         f'{share} % of failed logins', KPI_COLORS['invalid']),
        ('Distinct invalid users', statistics['distinct_invalid_users'],
         f'most tried: {invalid[0][0]}' if invalid else 'none', KPI_COLORS['users']),
        ('Distinct IP addresses', statistics['distinct_ips'],
         'seen in all events', KPI_COLORS['ips']),
    ]

    top, height = 124, 106
    width = (CANVAS_WIDTH - 2 * MARGIN - (len(cards) - 1) * GAP) / len(cards)

    for number, (label, value, caption, color) in enumerate(cards):
        x = MARGIN + number * (width + GAP)
        draw_card(canvas, x, top, width, height)
        canvas.add_patch(FancyBboxPatch(
            (x + 14, top + 16), 4, height - 32,
            boxstyle='round,pad=0,rounding_size=2',
            facecolor=color, edgecolor='none', zorder=2
        ))
        canvas.text(x + 32, top + 27, label, fontsize=10.5, color=TEXT,
                    va='center', zorder=2)
        canvas.text(x + 32, top + 60, format_number(value), fontsize=25,
                    fontweight='bold', color=INK, va='center', zorder=2)
        canvas.text(x + 32, top + 88, caption, fontsize=9.5, color=MUTED,
                    va='center', zorder=2)


def draw_footer(canvas):
    """Sources et date de génération en bas du dashboard."""
    generated = datetime.now().strftime('%d/%m/%Y at %H:%M')
    canvas.text(MARGIN, CANVAS_HEIGHT - 24,
                f'Sources: auth.log files (data/)   ·   countries: IPinfo   ·   '
                f'storage: PostgreSQL   ·   generated on {generated}',
                fontsize=9, color=MUTED, va='center', zorder=2)


# ---------- GRAPHIQUES ----------

def style_axis(ax, grid_axis: str):
    """Axes discrets : grille fine, seulement l'axe de base visible."""
    ax.set_facecolor(CARD)
    for side in ('top', 'right', 'left', 'bottom'):
        ax.spines[side].set_visible(False)
    base = 'bottom' if grid_axis == 'y' else 'left'
    ax.spines[base].set_visible(True)
    ax.spines[base].set_color(AXIS)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(colors=TEXT, labelsize=9.5, length=0, pad=6)
    number_format = FuncFormatter(lambda value, _: format_number(int(value)))
    value_axis = ax.yaxis if grid_axis == 'y' else ax.xaxis
    value_axis.set_major_formatter(number_format)
    value_axis.set_major_locator(MaxNLocator(nbins=7, integer=True))


def no_data(ax):
    ax.text(0.5, 0.5, 'No data', ha='center', va='center', color=MUTED,
            fontsize=11, transform=ax.transAxes)


def label_peak(ax, x: float, y: float, text: str, ha: str = 'center'):
    """Valeur en gras au-dessus du point le plus haut."""
    ax.annotate(text, (x, y), xytext=(0, 6), textcoords='offset points',
                ha=ha, va='bottom', fontsize=9.5, fontweight='bold', color=INK)


def draw_bars(ax, items: list, xlabel: str, ylabel: str, colors: list,
              show_values: bool = True):
    """Diagramme en barres verticales.
    Avec `show_values`, la valeur est affichée au-dessus de chaque barre
    (les 3 plus grandes en gras)."""
    labels = [label for label, _ in items]
    values = [value for _, value in items]
    positions = list(range(len(items)))

    bars = ax.bar(positions, values, width=0.62, color=colors, zorder=3)
    ax.set_xticks(positions, labels)

    for rank, (bar, value) in enumerate(zip(bars, values)):
        if not show_values:
            break
        important = rank < 3 and not labels[rank].startswith('Others')
        ax.annotate(format_number(value),
                    (bar.get_x() + bar.get_width() / 2, value),
                    xytext=(0, 4), textcoords='offset points',
                    ha='center', va='bottom', fontsize=9.5,
                    color=INK if important else TEXT,
                    fontweight='bold' if important else 'normal')

    style_axis(ax, 'y')
    ax.set_xlabel(xlabel, color=TEXT, fontsize=10, labelpad=8)
    ax.set_ylabel(ylabel, color=TEXT, fontsize=10, labelpad=8)
    ax.margins(x=0.01, y=0.14)

    if not items:
        no_data(ax)


def draw_line(ax, items: list, xlabel: str, ylabel: str):
    """Courbe dans le temps, avec le point le plus haut mis en évidence."""
    labels = [label for label, _ in items]
    values = [value for _, value in items]
    positions = list(range(len(items)))

    style_axis(ax, 'y')
    ax.set_xlabel(xlabel, color=TEXT, fontsize=10, labelpad=8)
    ax.set_ylabel(ylabel, color=TEXT, fontsize=10, labelpad=8)
    if not any(values):
        no_data(ax)
        return

    ax.fill_between(positions, values, color=TIME_LINE_COLOR, alpha=0.10, linewidth=0, zorder=2)
    ax.plot(positions, values, color=TIME_LINE_COLOR, linewidth=2, zorder=3,
            marker='o', markersize=3.5)
    ax.set_xticks(positions, labels)
    ax.set_xlim(-0.6, len(items) - 0.4)
    ax.set_ylim(0, max(values) * 1.25)

    peak = values.index(max(values))
    ax.plot([peak], [values[peak]], marker='o', markersize=8, color=TIME_PEAK_COLOR,
            markeredgecolor=CARD, markeredgewidth=2, zorder=4)
    # Le texte part vers l'intérieur du graphique quand le pic est sur un bord
    ha = 'left' if peak < len(items) * 0.15 else 'right' if peak > len(items) * 0.85 else 'center'
    label_peak(ax, peak, values[peak], format_number(values[peak]), ha)


def draw_hbars(ax, items: list, xlabel: str, colors: list, min_slots: int = 5):
    """Diagramme en barres horizontales, la plus grande valeur en haut."""
    labels = [label for label, _ in items]
    values = [value for _, value in items]
    positions = list(range(len(items)))

    ax.barh(positions, values, height=0.62, color=colors, zorder=3)
    ax.set_yticks(positions, labels)
    ax.tick_params(axis='y', labelsize=10.5, labelcolor=INK)

    for position, value in zip(positions, values):
        ax.annotate(format_number(value), (value, position),
                    xytext=(6, 0), textcoords='offset points',
                    ha='left', va='center', fontsize=9.5, color=TEXT)

    style_axis(ax, 'x')
    ax.set_xlabel(xlabel, color=TEXT, fontsize=10, labelpad=8)

    # Peu de barres : on garde de la place autour pour qu'elles ne soient pas trop épaisses
    padding = (max(min_slots, len(items)) - len(items)) / 2
    ax.set_ylim(len(items) - 0.5 + padding, -0.5 - padding)
    ax.set_xlim(0, max(values) * 1.12 if values else 1)

    if not items:
        no_data(ax)


# ---------- PANNEAUX ----------

def draw_activity_by_hour(fig, canvas, statistics: dict, x, y, width, height):
    """Panneau : nombre de lignes de logs pour chaque heure de la journée."""
    hours = statistics.get('activity_by_hour', [])
    values = [lines for _, lines in hours]
    total = sum(values)

    subtitle = 'No dated log line'
    if total:
        busiest = values.index(max(values))
        quietest = values.index(min(values))
        subtitle = (f'Busiest hour: {hour_range(busiest)}  ·  {format_number(values[busiest])} lines '
                    f'({100 * values[busiest] / total:.1f} %)   ·   quietest: {hour_range(quietest)}')

    draw_card(canvas, x, y, width, height)
    draw_panel_title(canvas, x, y, 'Log activity by hour of day', subtitle)
    ax = fig.add_axes(canvas_box(x + 84, y + 100, width - 112, height - 164))

    colors = [TIME_COLOR] * len(hours)
    items = [(f'{hour:02d}', lines) for hour, lines in hours]
    draw_bars(ax, items, 'Hour of day', 'Log lines', colors, show_values=False)
    if total:
        ax.patches[busiest].set_color(TIME_PEAK_COLOR)
        label_peak(ax, busiest, values[busiest], format_number(values[busiest]))
    else:
        no_data(ax)


def draw_activity_by_day(fig, canvas, statistics: dict, x, y, width, height):
    """Panneau : nombre de lignes de logs par jour, avec le moment le plus chargé."""
    days = statistics.get('activity_by_day', [])
    moment = statistics.get('busiest_moment')

    subtitle = 'No dated log line'
    if days:
        busiest_day, lines = max(days, key=lambda item: item[1])
        subtitle = f'Busiest day: {busiest_day}  ·  {format_number(lines)} lines'
    if moment:
        subtitle += (f"   ·   peak: {moment['day']}, {hour_range(moment['hour'])} "
                     f"({format_number(moment['lines'])} lines)")

    draw_card(canvas, x, y, width, height)
    draw_panel_title(canvas, x, y, 'Log activity by day', subtitle)
    ax = fig.add_axes(canvas_box(x + 84, y + 100, width - 112, height - 164))

    # 'May 24' -> axe : '24', titre de l'axe : 'Day of May'
    months = []
    for label, _ in days:
        if label.split()[0] not in months:
            months.append(label.split()[0])
    items = [(label.split()[1], lines) for label, lines in days]
    draw_line(ax, items, 'Day of ' + ' – '.join(months) if months else 'Day', 'Log lines')


# ---------- DASHBOARD ----------

def build_dashboard(statistics: dict, output_file: str = DASHBOARD_FILE, show: bool = True):
    """Crée la figure, l'enregistre en PNG et l'affiche si `show` est vrai.
    Retourne le chemin de l'image, ou None en cas d'erreur."""
    try:
        with plt.rc_context({'font.family': pick_font()}):
            fig = plt.figure(figsize=(CANVAS_WIDTH / 100, CANVAS_HEIGHT / 100),
                             dpi=SCREEN_DPI, facecolor=BACKGROUND)
            if fig.canvas.manager is not None:
                fig.canvas.manager.set_window_title('SSH log analysis dashboard')

            # Canevas : un axe invisible qui couvre toute la figure
            canvas = fig.add_axes([0, 0, 1, 1])
            canvas.set_xlim(0, CANVAS_WIDTH)
            canvas.set_ylim(CANVAS_HEIGHT, 0)
            canvas.axis('off')

            draw_header(canvas, statistics)
            draw_summary(canvas, statistics)

            # Rangée 1 : activité des logs dans le temps
            half = (CANVAS_WIDTH - 2 * MARGIN - GAP) / 2
            draw_activity_by_hour(fig, canvas, statistics, MARGIN, 254, half, 320)
            draw_activity_by_day(fig, canvas, statistics, MARGIN + half + GAP, 254, half, 320)

            # Rangée 2 : tentatives échouées par pays
            countries = statistics['failures_by_country']
            items, grouped = group_others(countries, TOP_COUNTRIES)
            failed = statistics['failed_logins']
            top3 = sum(value for _, value in countries[:3])
            subtitle = f'{len(countries)} countries'
            if failed:
                subtitle += f'   ·   the top 3 send {round(100 * top3 / failed)} % of all failures'
            if grouped:
                subtitle += f'   ·   the {grouped} smallest are grouped in "Others"'

            x, y, width, height = MARGIN, 598, CANVAS_WIDTH - 2 * MARGIN, 340
            draw_card(canvas, x, y, width, height)
            draw_panel_title(canvas, x, y, 'Failed logins by country', subtitle)
            colors = shades([value for _, value in items], COUNTRY_COLORS)
            if grouped:
                colors[-1] = OTHERS
            ax = fig.add_axes(canvas_box(x + 92, y + 96, width - 124, height - 168))
            draw_bars(ax, items, 'Country (ISO code)', 'Failed attempts', colors)

            # Rangée 3 : connexions réussies par utilisateur
            users = statistics['successes_by_user'][:TOP_USERS]
            x, y, width, height = MARGIN, 962, 500, 350
            draw_card(canvas, x, y, width, height)
            draw_panel_title(
                canvas, x, y, 'Successful logins by user',
                f"{statistics['successful_logins']} successful login(s) for "
                f"{len(statistics['successes_by_user'])} user(s)"
            )
            ax = fig.add_axes(canvas_box(x + 130, y + 100, width - 190, height - 164))
            draw_hbars(ax, users, 'Successful logins', [SUCCESS_COLOR] * len(users))

            # Rangée 3 : tentatives échouées avec utilisateur invalide
            invalid = statistics['invalid_users'][:TOP_INVALID_USERS]
            x = MARGIN + 500 + GAP
            width = CANVAS_WIDTH - MARGIN - x
            draw_card(canvas, x, y, width, height)
            draw_panel_title(
                canvas, x, y,
                f"Failed logins with invalid user: {format_number(statistics['invalid_user_attempts'])}",
                f"Top {len(invalid)} of {format_number(statistics['distinct_invalid_users'])} "
                f"usernames that do not exist on the server"
            )
            ax = fig.add_axes(canvas_box(x + 130, y + 100, width - 200, height - 164))
            draw_hbars(ax, invalid, 'Failed attempts',
                       shades([value for _, value in invalid], INVALID_USER_COLORS))

            draw_footer(canvas)

            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            fig.savefig(output_file, dpi=DPI, facecolor=BACKGROUND)
        logger.info(f"Dashboard saved in {output_file}")

    except (OSError, ValueError, KeyError) as e:
        logger.error(f"Dashboard generation error: {e}")
        plt.close('all')
        return None

    if show:
        plt.show()

    plt.close(fig)
    return output_file
