import os
import sys

from ingestion import read
from log_config import get_logger
from processing import extract_transform
from processing import geolocation
from serving import dashboard
from serving import statistics
from storage import store

"""
Pipeline : ingestion -> extraction/transformation -> géolocalisation
           -> stockage -> statistiques -> dashboard

Utilisation :
    python main.py               lance le pipeline et affiche le dashboard
    python main.py --reprocess   retraite les logs même s'ils n'ont pas changé
    python main.py --no-show     enregistre le dashboard sans ouvrir de fenêtre
"""

logger = get_logger('main')

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def process_logs():
    """Étapes 1 à 4 : lecture, transformation, géolocalisation, sauvegarde."""
    print("1. Ingestion: reading log files...")
    rows = read.ingest(DATA_DIR)
    if not rows:
        raise RuntimeError("No log line read (see logs/ingestion.log)")
    print(f"   {len(rows)} lines read")

    print("2. Extraction and transformation...")
    events = extract_transform.transform(rows)
    print(f"   {len(events)} events extracted")

    print("3. Geolocation of failed login IPs...")
    cache = store.load_geo_cache()
    try:
        geolocation.add_countries(events, cache)
    finally:
        # Le cache est sauvegardé même si on interrompt (Ctrl+C) pendant les requêtes
        store.save_geo_cache(cache)

    print("4. Storage of processed data...")
    if not store.save_events(events, extract_transform.EVENT_FIELDS, DATA_DIR):
        print("   Warning: data could not be saved (see logs/storage.log)")
    return events


def get_events(reprocess: bool):
    """Recharge les données déjà traitées si data/ n'a pas changé, sinon retraite tout."""
    if not reprocess and store.is_up_to_date(DATA_DIR):
        print("1-4. Data already processed: loading storage/processed/events.csv")
        events = store.load_events()
        if events:
            return events
        print("   Saved data unreadable, processing again")
    return process_logs()


def print_summary(stats: dict, dashboard_file):
    print()
    print("=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Lines analysed                : {stats['total_lines']}")
    print(f"Successful logins             : {stats['successful_logins']}")
    print(f"Failed logins                 : {stats['failed_logins']}")
    print(f"Failed logins (invalid user)  : {stats['invalid_user_attempts']}")
    print(f"Distinct invalid users        : {stats['distinct_invalid_users']}")
    print(f"Distinct IP addresses         : {stats['distinct_ips']}")
    print(f"Top 3 countries (failures)    : {stats['failures_by_country'][:3]}")
    print(f"Dashboard                     : {dashboard_file}")


def run(reprocess: bool = False, show: bool = True):
    logger.info("Pipeline started")
    events = get_events(reprocess)

    print("5. Computing statistics...")
    stats = statistics.compute_statistics(events)
    store.save_statistics(stats)

    print("6. Building dashboard...")
    dashboard_file = dashboard.build_dashboard(stats, show=False)
    if dashboard_file is None:
        print("   Error: dashboard not generated (see logs/serving.log)")

    print_summary(stats, dashboard_file)
    logger.info("Pipeline finished")

    if show and dashboard_file:
        print("\nOpening dashboard (close the window to quit)...")
        dashboard.build_dashboard(stats, show=True)


if __name__ == "__main__":
    try:
        run(reprocess='--reprocess' in sys.argv, show='--no-show' not in sys.argv)
    except KeyboardInterrupt:
        logger.warning("Pipeline interrupted by user")
        print("\nInterrupted.")
    except Exception as e:
        logger.critical(f"Pipeline failed: {e}", exc_info=True)
        print(f"\nError: {e}\nDetails in logs/main.log")
        sys.exit(1)
