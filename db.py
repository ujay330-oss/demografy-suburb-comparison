import os
from supabase import create_client, Client
from dotenv import load_dotenv
import streamlit as st

load_dotenv()  # Reads your .env file

def get_client() -> Client:
    """Creates and returns a Supabase client."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in .env")
    return create_client(url, key)

def check_suburb_exists(suburb_name: str) -> bool:
    """Returns True if the suburb is already in our database."""
    client = get_client()
    name = suburb_name.strip().title()  # Normalise: "bondi" -> "Bondi"
    result = client.table("suburbs_raw")\
                   .select("suburb_name")\
                   .eq("suburb_name", name)\
                   .execute()
    return len(result.data) > 0

@st.cache_data(ttl=3600)  # cache for 1 hour
def get_suburb_metrics(suburb_name: str) -> dict | None:
    """Fetches metrics for a suburb"""
    client = get_client()
    name = suburb_name.strip().title()
    result = client.table("suburbs_scores")\
                   .select("*")\
                   .eq("suburb_name", name)\
                   .execute()
    if result.data:
        return result.data[0]
    return None

def clear_suburb_cache(suburb_name: str) -> None:
    """Clears Streamlit cache after a new suburb is inserted."""
    get_suburb_metrics.clear()


def insert_raw_suburb(metrics: dict) -> None:
    client = get_client()
    client.table('suburbs_raw').upsert({
        'suburb_name': metrics['suburb_name'],
        'state':       metrics.get('state', 'NSW'),
        'raw_json':    metrics.get('raw_json', '{}'),
        'latitude':    metrics.get('latitude'),
        'longitude':   metrics.get('longitude'),
    }).execute()


def insert_suburb_metrics(metrics: dict) -> None:
    client = get_client()
    client.table('suburbs_metrics').upsert({
        'suburb_name':      metrics['suburb_name'],
        'state':            metrics.get('state', 'NSW'),
        'dining_count':     metrics.get('dining_count', 0),
        'parks_count':      metrics.get('parks_count', 0),
        'wellness_count':   metrics.get('wellness_count', 0),
        'childcare_count':  metrics.get('childcare_count', 0),
        'transport_count':  metrics.get('transport_count', 0),
        'shopping_count':   metrics.get('shopping_count', 0),
        'education_count':  metrics.get('education_count', 0),
        'healthcare_count': metrics.get('healthcare_count', 0),
    }).execute()

