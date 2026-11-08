"""
Tests du module storage (partie 5) - version procédurale, sans classe.
À lancer depuis le dossier log_analysis :  python test_storage.py
Aucun accès Internet nécessaire. Les fichiers de test sont créés dans un dossier temporaire :
storage/events.json et logs/ ne sont pas modifiés.
"""
import json
import logging
import os
import tempfile
from pathlib import Path
from unittest import mock

from storage import store

# Les logs de test vont dans un dossier temporaire (pas dans logs/)
store.LOGS_DIR = Path(tempfile.mkdtemp())


def make_event(ip="45.148.10.147", country="RU", **changes):
    event = {
        'date': '05-24', 'heure': '01:14:01', 'ip': ip, 'username': 'root',
        'event_type': 'login_failed', 'status': 'failed', 'invalid_user': False,
        'raw_line': 'May 24 01:14:01 ns sshd[1]: Failed password for root from ' + ip + ' port 8868 ssh2',
        'count': 1, 'program': 'sshd', 'country': country,
    }
    event.update(changes)
    return event


def new_path(name="events.json"):
    """Retourne le chemin d'un fichier dans un nouveau dossier temporaire."""
    return os.path.join(tempfile.mkdtemp(), name)


def test_save_and_load():
    path = new_path()
    events = [make_event(), make_event(ip="1.2.3.4", country="FR", username="admin", invalid_user=True)]
    assert store.save_events(events, path) is True
    assert store.load_events(path) == events


def test_country_key_is_kept():
    path = new_path()
    store.save_events([make_event(country="RU"), make_event(country="Unknown")], path)
    loaded = store.load_events(path)
    assert [e['country'] for e in loaded] == ["RU", "Unknown"]


def test_types_are_kept():
    path = new_path()
    store.save_events([make_event(invalid_user=True, count=4)], path)
    event = store.load_events(path)[0]
    assert event['invalid_user'] is True
    assert event['count'] == 4


def test_event_without_country_is_accepted():
    path = new_path()
    event = make_event()
    del event['country']
    assert store.save_events([event], path) is True
    assert 'country' not in store.load_events(path)[0]


def test_empty_list_does_not_erase_existing_file():
    path = new_path()
    store.save_events([make_event()], path)
    assert store.save_events([], path) is False
    assert len(store.load_events(path)) == 1


def test_empty_list_creates_no_file():
    path = new_path()
    assert store.save_events([], path) is False
    assert not os.path.exists(path)


def test_missing_file():
    assert store.load_events(new_path("inexistant.json")) == []


def test_corrupted_file():
    path = new_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write('[{"date": "05-24", ')
    assert store.load_events(path) == []


def test_wrong_json_format():
    path = new_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"pas": "une liste"}, f)
    assert store.load_events(path) == []


def test_invalid_items_are_ignored():
    path = new_path()
    events = [make_event(), "texte", None, 42, {"ip": "1.2.3.4"}]
    assert store.save_events(events, path) is True
    assert len(store.load_events(path)) == 1


def test_not_a_list():
    path = new_path()
    assert store.save_events(None, path) is False
    assert store.save_events("abc", path) is False
    assert not os.path.exists(path)


def test_write_error_keeps_old_data():
    path = new_path()
    old = [make_event(ip="9.9.9.9", country="US")]
    store.save_events(old, path)
    with mock.patch("storage.store.os.replace", side_effect=OSError("disque plein")):
        assert store.save_events([make_event(), make_event()], path) is False
    assert store.load_events(path) == old
    assert not os.path.exists(path + ".tmp")     # fichier temporaire nettoyé


def test_unserializable_data_keeps_old_data():
    path = new_path()
    old = [make_event()]
    store.save_events(old, path)
    bad = make_event(extra={1, 2, 3})             # un set n'est pas sérialisable en JSON
    assert store.save_events([bad], path) is False
    assert store.load_events(path) == old
    assert not os.path.exists(path + ".tmp")


def test_creates_missing_folder():
    path = os.path.join(tempfile.mkdtemp(), "sous", "dossier", "events.json")
    assert store.save_events([make_event()], path) is True
    assert len(store.load_events(path)) == 1


def test_accents_and_special_characters():
    path = new_path()
    event = make_event(username="é\"'\\ünï", raw_line="ligne avec accents é à ç et \ufffd")
    store.save_events([event], path)
    assert store.load_events(path) == [event]


def test_second_save_replaces_first():
    path = new_path()
    store.save_events([make_event(), make_event()], path)
    store.save_events([make_event()], path)
    assert len(store.load_events(path)) == 1


def test_country_cache():
    path = new_path("country_cache.json")
    assert store.load_country_cache(path) == {}
    assert store.save_country_cache({}, path) is False
    assert store.save_country_cache({"1.2.3.4": "FR", "10.0.0.1": "Unknown", 5: "XX"}, path) is True
    assert store.load_country_cache(path) == {"1.2.3.4": "FR", "10.0.0.1": "Unknown"}


def test_country_cache_corrupted():
    path = new_path("country_cache.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("pas du json")
    assert store.load_country_cache(path) == {}


def test_one_handler_only():
    for _ in range(5):
        store.get_logger()
    assert len(logging.getLogger("storage").handlers) == 1


def test_real_data():
    """Utilise les vrais fichiers de data/ (parties 2 et 3) et une géolocalisation simulée (partie 4)."""
    from ingestion import read
    from processing import extract_transform, geolocation

    rows = read.ingest('./data')
    if not rows:
        print("   (ignoré : dossier data/ vide ou introuvable)")
        return
    events, _ = extract_transform.extract_all(rows)
    with mock.patch.object(geolocation, "geo_location", return_value="RU"):
        events = geolocation.add_country(events)

    path = new_path()
    assert store.save_events(events, path) is True
    loaded = store.load_events(path)
    assert len(loaded) == len(events)
    assert loaded == events
    assert all('country' in e for e in loaded)
    print(f"   {len(loaded)} événements sauvegardés puis relus, fichier de {os.path.getsize(path) / 1_000_000:.1f} Mo")


TESTS = [
    test_save_and_load,
    test_country_key_is_kept,
    test_types_are_kept,
    test_event_without_country_is_accepted,
    test_empty_list_does_not_erase_existing_file,
    test_empty_list_creates_no_file,
    test_missing_file,
    test_corrupted_file,
    test_wrong_json_format,
    test_invalid_items_are_ignored,
    test_not_a_list,
    test_write_error_keeps_old_data,
    test_unserializable_data_keeps_old_data,
    test_creates_missing_folder,
    test_accents_and_special_characters,
    test_second_save_replaces_first,
    test_country_cache,
    test_country_cache_corrupted,
    test_one_handler_only,
    test_real_data,
]


def run_tests():
    """Lance tous les tests et affiche le résultat. Retourne le nombre d'échecs."""
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