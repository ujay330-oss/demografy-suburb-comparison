import db
import google_api
import subprocess
import os
import threading
import concurrent.futures as cf
import yaml
import tempfile
import streamlit as st

# Path to your dbt project folder
DBT_PROJECT_DIR = os.path.join(os.path.dirname(__file__), 'dbt_transform')

def _ensure_dbt_profiles() -> str:
    """
    Creates a temporary profiles.yml from Streamlit secrets.
    Returns the path to the profiles directory.
    Works both locally (reads existing profiles.yml) and on Streamlit Cloud.
    """
    profiles_path = os.path.join(DBT_PROJECT_DIR, 'profiles.yml')

    # If profiles.yml already exists (local dev), use it
    if os.path.exists(profiles_path):
        return DBT_PROJECT_DIR

    # On Streamlit Cloud — build profiles.yml from secrets
    try:
        db_url = st.secrets['SUPABASE_URL']
        # Extract host from URL: https://xxxx.supabase.co -> db.xxxx.supabase.co
        project_ref = db_url.split('//')[1].split('.')[0]
        host = f'db.{project_ref}.supabase.co'

        profile = {
            'dbt_transform': {
                'target': 'dev',
                'outputs': {
                    'dev': {
                        'type': 'postgres',
                        'host': host,
                        'user': 'postgres',
                        'password': st.secrets['SUPABASE_DB_PASSWORD'],
                        'port': 5432,
                        'dbname': 'postgres',
                        'schema': 'public',
                        'threads': 4,
                        'sslmode': 'require'
                    }
                }
            }
        }

        with open(profiles_path, 'w') as f:
            yaml.dump(profile, f)

        return DBT_PROJECT_DIR

    except Exception as e:
        print(f'Could not create profiles.yml: {e}')
        return DBT_PROJECT_DIR


def _run_dbt_background():
    """Fires dbt in a background thread — user never waits for it."""
    try:
        run_dbt()
    except Exception as e:
        print(f"Background dbt run failed: {e}")

def run_dbt() -> bool:
    profiles_dir = _ensure_dbt_profiles()
    result = subprocess.run(
        ['dbt', 'run', '--select', 'suburbs_scores',
         '--profiles-dir', profiles_dir],
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
