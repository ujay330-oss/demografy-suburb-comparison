import db
import google_api
import subprocess
import os
import threading
import concurrent.futures as cf

# Path to your dbt project folder
DBT_PROJECT_DIR = os.path.join(os.path.dirname(__file__), 'dbt_transform')

def _run_dbt_background():
    """Fires dbt in a background thread — user never waits for it."""
    try:
        run_dbt()
    except Exception as e:
        print(f"Background dbt run failed: {e}")

def run_dbt() -> bool:
    """
    Triggers dbt run programmatically after each API insert.
    Returns True if successful, False if dbt fails.
    """
    result = subprocess.run(
        ['dbt', 'run', '--select', 'suburbs_scores'],
        cwd=DBT_PROJECT_DIR,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f'dbt run failed:\n{result.stdout}\n{result.stderr}')
        return False
    print('dbt run completed successfully')
    return True


def fetch_suburb_if_needed(suburb_name: str, state: str = 'NSW') -> dict:
    name = suburb_name.strip().title()

    if db.check_suburb_exists(name):
        metrics = db.get_suburb_metrics(name)
        if metrics:
            metrics['source'] = 'cache'
            return metrics

    raw_metrics = google_api.get_google_data(name, state)

    if raw_metrics is None:
        raise ValueError(f"Suburb '{name}' could not be found in {state}.")

    with cf.ThreadPoolExecutor(max_workers=2) as executor:
        executor.submit(db.insert_raw_suburb, raw_metrics)
        executor.submit(db.insert_suburb_metrics, raw_metrics)

    thread = threading.Thread(target=_run_dbt_background, daemon=True)
    thread.start()

    db.clear_suburb_cache(name)

    metrics = db.get_suburb_metrics(name)
    metrics['source'] = 'api'
    return metrics