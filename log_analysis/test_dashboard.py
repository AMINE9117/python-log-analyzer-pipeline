"""
Tests du module serving.dashboard (partie 6) - version procédurale, sans classe.
À lancer depuis le dossier log_analysis :  python test_dashboard.py
Aucun accès Internet nécessaire. Aucune fenêtre ne s'ouvre (backend « Agg »).
Les fichiers de test sont créés dans un dossier temporaire :
storage/events.json, serving/dashboard.png et logs/ ne sont pas modifiés.
"""
import json
import os
import tempfile
from pathlib import Path

try:
    import matplotlib
    matplotlib.use("Agg")          # pas de fenêtre pendant les tests
except ImportError:
    matplotlib = None

from serving import dashboard
from storage import store

# Les logs de test vont dans un dossier temporaire (pas dans logs/)
dashboard.LOGS_DIR = Path(tempfile.mkdtemp())
store.LOGS_DIR = Path(tempfile.mkdtemp())


def make_event(status="failed", username="root", country="RU", invalid_user=False,
               ip="45.148.10.147", count=1, **changes):
    event = {
        'date': '05-24', 'heure': '01:14:01', 'ip': ip, 'username': username,
        'event_type': 'login_failed' if status == 'failed' else 'other',
        'status': status, 'invalid_user': invalid_user,
        'raw_line': 'May 24 01:14:01 ns sshd[1]: ligne de test',
        'count': count, 'program': 'sshd', 'country': country,
    }
    event.update(changes)
    return event


def new_path(name="events.json"):
    """Retourne le chemin d'un fichier dans un nouveau dossier temporaire."""
    return os.path.join(tempfile.mkdtemp(), name)


def bar_heights(ax):
    """Valeurs des barres verticales d'un graphique (graphiques 1 et 2)."""
    return [bar.get_height() for bar in ax.patches]


def bar_widths(ax):
    """Valeurs des barres horizontales d'un graphique (graphique 3)."""
    return [bar.get_width() for bar in ax.patches]


# ---------- calculs ----------

def test_failed_by_country():
    events = [
        make_event(country="RU"), make_event(country="RU"), make_event(country="FR"),
        make_event(country="Unknown"),
        make_event(country="RU", count=4),                    # « message repeated 4 times »
        make_event(status="success", country="MA"),           # une réussite n'est pas un échec
        make_event(status="info", country="CN"),              # info : même tentative, pas comptée
    ]
    assert dashboard.count_failed_by_country(events) == {"RU": 6, "FR": 1, "Unknown": 1}


def test_missing_or_empty_country_becomes_unknown():
    no_country = make_event()
    del no_country['country']
    events = [no_country, make_event(country=""), make_event(country=None), make_event(country="   "),
              make_event(country="FR")]
    assert dashboard.count_failed_by_country(events) == {"Unknown": 4, "FR": 1}


def test_success_by_user():
    events = [
        make_event(status="success", username="adminesisa", country="Unknown"),
        make_event(status="success", username="adminesisa"),
        make_event(status="success", username="amine"),
        make_event(status="success", username=""),            # utilisateur inconnu
        make_event(status="failed", username="root"),         # un échec n'est pas une réussite
    ]
    assert dashboard.count_success_by_user(events) == {"adminesisa": 2, "amine": 1, "(inconnu)": 1}


def test_failed_invalid_users():
    events = [
        make_event(username="admin", invalid_user=True),
        make_event(username="admin", invalid_user=True, count=3),
        make_event(username="test", invalid_user=True),
        make_event(username="root", invalid_user=False),                  # échec d'un utilisateur valide
        make_event(status="info", username="admin", invalid_user=True),   # ligne « Invalid user » : info
        make_event(username="", invalid_user=True),
    ]
    assert dashboard.count_failed_invalid_users(events) == {"admin": 4, "test": 1, "(inconnu)": 1}


def test_summary():
    events = [
        make_event(ip="1.1.1.1"), make_event(ip="1.1.1.1", count=2),
        make_event(ip="2.2.2.2", username="x", invalid_user=True),
        make_event(status="success", ip="10.0.0.1"), make_event(status="info", ip=""),
    ]
    assert dashboard.compute_summary(events) == {'lines': 5, 'success': 1, 'failed': 4, 'invalid': 1, 'ips': 3}


def test_bad_count_values():
    for bad in (0, -3, "4", None, 2.5, True):
        assert dashboard.get_count({'count': bad}) == 1
    assert dashboard.get_count({}) == 1
    assert dashboard.get_count({'count': 7}) == 7


def test_sort_and_top():
    items = dashboard.sort_counts({"b": 2, "a": 2, "c": 5, "d": 1})
    assert items == [("c", 5), ("a", 2), ("b", 2), ("d", 1)]       # valeur décroissante, puis ordre alphabétique
    assert dashboard.keep_top(items, 4, "Autres") == items
    assert dashboard.keep_top(items, 2, "Autres") == [("c", 5), ("a", 2), ("Autres (2)", 3)]


def test_format_number():
    assert dashboard.format_number(65565) == "65 565"
    assert dashboard.format_number(7) == "7"


# ---------- figure ----------

def test_dashboard_with_all_categories():
    if dashboard.plt is None:
        print("   (ignoré : matplotlib n'est pas installé)")
        return
    events = [make_event(country="RU"), make_event(country="RU"), make_event(country="Unknown"),
              make_event(username="admin", invalid_user=True, country="CN"),
              make_event(status="success", username="adminesisa")]
    fig = dashboard.create_dashboard(events)
    assert len(fig.axes) == 4
    assert bar_heights(fig.axes[0]) == [2, 1, 1]      # RU: 2, CN: 1, Unknown: 1
    assert bar_heights(fig.axes[1]) == [1]            # adminesisa
    assert bar_widths(fig.axes[2]) == [1]             # admin (utilisateur invalide)
    assert "pays" in fig.axes[0].get_title()
    dashboard.plt.close(fig)


def test_dashboard_empty_list():
    if dashboard.plt is None:
        return
    fig = dashboard.create_dashboard([])
    assert len(fig.axes) == 4
    for ax in fig.axes[:3]:
        assert len(ax.patches) == 0       # aucune barre, mais « Aucune donnée » affiché
    dashboard.plt.close(fig)


def test_dashboard_only_unknown_country():
    if dashboard.plt is None:
        return
    fig = dashboard.create_dashboard([make_event(country="Unknown"), make_event(country="Unknown")])
    assert bar_heights(fig.axes[0]) == [2]
    assert "géolocalisation non disponible" in fig.axes[0].get_title()
    dashboard.plt.close(fig)


def test_dashboard_events_without_country_key():
    if dashboard.plt is None:
        return
    event = make_event()
    del event['country']
    fig = dashboard.create_dashboard([event])
    assert bar_heights(fig.axes[0]) == [1]
    dashboard.plt.close(fig)


def test_dashboard_only_failures_no_success():
    if dashboard.plt is None:
        return
    fig = dashboard.create_dashboard([make_event(), make_event(username="x", invalid_user=True)])
    assert len(fig.axes[1].patches) == 0      # graphique 2 vide mais présent
    assert bar_widths(fig.axes[2]) == [1]
    dashboard.plt.close(fig)


def test_many_countries_are_grouped():
    if dashboard.plt is None:
        return
    events = [make_event(country=f"C{i:02d}") for i in range(30)]
    fig = dashboard.create_dashboard(events)
    assert len(bar_heights(fig.axes[0])) == dashboard.TOP_COUNTRIES + 1      # 15 pays + « Autres »
    assert sum(bar_heights(fig.axes[0])) == 30                                # rien n'est perdu
    dashboard.plt.close(fig)


def test_one_broken_chart_does_not_stop_the_others():
    if dashboard.plt is None:
        return
    original = dashboard.plot_success_by_user

    def broken(ax, counts):
        raise ValueError("erreur simulée")

    dashboard.plot_success_by_user = broken
    try:
        fig = dashboard.create_dashboard([make_event(), make_event(status="success", username="a")])
    finally:
        dashboard.plot_success_by_user = original
    assert bar_heights(fig.axes[0]) == [1]     # graphique 1 toujours dessiné
    dashboard.plt.close(fig)
    log_file = dashboard.LOGS_DIR / "serving.log"
    assert "Erreur de génération du graphique" in log_file.read_text(encoding="utf-8")


# ---------- fichiers ----------

def test_run_with_valid_file():
    if dashboard.plt is None:
        return
    json_path = new_path()
    image_path = new_path("dashboard.png")
    assert store.save_events([make_event(), make_event(status="success", username="a")], json_path)
    assert dashboard.run_dashboard(json_path, show=False, image_path=image_path) is True
    assert os.path.getsize(image_path) > 1000


def test_run_with_missing_file():
    assert dashboard.run_dashboard(new_path("absent.json"), show=False, image_path=new_path("x.png")) is False


def test_run_with_corrupted_json():
    json_path = new_path()
    with open(json_path, "w", encoding="utf-8") as f:
        f.write('[{"status": "failed", ')
    assert dashboard.run_dashboard(json_path, show=False, image_path=new_path("x.png")) is False


def test_run_with_empty_json_list():
    json_path = new_path()
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump([], f)
    assert dashboard.run_dashboard(json_path, show=False, image_path=new_path("x.png")) is False


def test_run_with_wrong_json_format():
    json_path = new_path()
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"pas": "une liste"}, f)
    assert dashboard.run_dashboard(json_path, show=False, image_path=new_path("x.png")) is False


def test_image_write_error_does_not_crash():
    if dashboard.plt is None:
        return
    json_path = new_path()
    store.save_events([make_event()], json_path)
    bad_image_path = os.path.join(tempfile.mkdtemp(), "dossier_inexistant", "dashboard.png")
    assert dashboard.run_dashboard(json_path, show=False, image_path=bad_image_path) is True


# ---------- données réelles et règles du projet ----------

def test_real_data():
    """Données réelles de data/ (parties 2 et 3), pays simulés (pas d'Internet)."""
    if dashboard.plt is None:
        return
    from ingestion import read
    from processing import extract_transform

    rows = read.ingest('./data')
    if not rows:
        print("   (ignoré : dossier data/ vide ou introuvable)")
        return
    events, _ = extract_transform.extract_all(rows)
    countries = ["CN", "US", "RU", "FR", "DE", "Unknown"]
    for event in events:
        event['country'] = countries[sum(map(ord, event['ip'])) % len(countries)] if event['ip'] else "Unknown"

    json_path = new_path()
    assert store.save_events(events, json_path)
    loaded = store.load_events(json_path)
    assert dashboard.count_failed_by_country(loaded) and sum(dashboard.count_failed_by_country(loaded).values()) == 16361
    assert dashboard.count_success_by_user(loaded) == {"adminesisa": 1}
    assert sum(dashboard.count_failed_invalid_users(loaded).values()) == 3253
    summary = dashboard.compute_summary(loaded)
    assert summary['lines'] == 65565 and summary['ips'] == 3453
    assert dashboard.run_dashboard(json_path, show=False, image_path=new_path("dashboard.png")) is True
    print("   16 361 échecs, 1 réussite, 3 253 échecs avec utilisateur invalide, 3 453 IP distinctes")


def test_no_class_in_dashboard_and_tests():
    """Le professeur interdit les classes : on vérifie qu'aucune ligne ne commence par « class »."""
    for path in (dashboard.__file__, __file__):
        with open(path, encoding="utf-8") as f:
            for number, line in enumerate(f, start=1):
                assert not line.lstrip().startswith("class "), f"{path} ligne {number} : {line.strip()}"


TESTS = [
    test_failed_by_country,
    test_missing_or_empty_country_becomes_unknown,
    test_success_by_user,
    test_failed_invalid_users,
    test_summary,
    test_bad_count_values,
    test_sort_and_top,
    test_format_number,
    test_dashboard_with_all_categories,
    test_dashboard_empty_list,
    test_dashboard_only_unknown_country,
    test_dashboard_events_without_country_key,
    test_dashboard_only_failures_no_success,
    test_many_countries_are_grouped,
    test_one_broken_chart_does_not_stop_the_others,
    test_run_with_valid_file,
    test_run_with_missing_file,
    test_run_with_corrupted_json,
    test_run_with_empty_json_list,
    test_run_with_wrong_json_format,
    test_image_write_error_does_not_crash,
    test_real_data,
    test_no_class_in_dashboard_and_tests,
]


def run_tests():
    """Lance tous les tests et affiche le résultat. Retourne le nombre d'échecs."""
    if dashboard.plt is None:
        print("matplotlib n'est pas installé : les tests de graphiques sont ignorés (uv sync pour l'installer)\n")
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"[OK]    {test.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"[ECHEC] {test.__name__} {e}")
        except Exception as e:
            failures += 1
            print(f"[ERREUR] {test.__name__} : {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} tests réussis")
    return failures


if __name__ == '__main__':
    raise SystemExit(1 if run_tests() else 0)
