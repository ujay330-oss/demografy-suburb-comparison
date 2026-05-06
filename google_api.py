import requests
import os
import json
import math
import concurrent.futures
import streamlit as st
from dotenv import load_dotenv
from geocoder import get_suburb_coordinates

load_dotenv()

# Search radius in metres around suburb centre
SEARCH_RADIUS = 1000
MAX_RESULTS_CAP = 100

CATEGORIES = {
    'dining_count':     ['cafe', 'coffee_shop', 'restaurant'],
    'parks_count':      ['park'],
    'wellness_count':   ['gym', 'fitness_center'],
    'childcare_count':  ['child_care_agency', 'preschool'],
    'transport_count':  ['train_station', 'subway_station', 'bus_station'],
    'shopping_count':   ['shopping_mall', 'department_store'],
    'education_count':  ['primary_school', 'secondary_school', 'university'],
    'healthcare_count': ['hospital', 'doctor', 'medical_clinic'],
}


def _get_api_key() -> str:
    """
    Gets Google API key — works both locally and on Streamlit Cloud.
    Tries Streamlit secrets first (deployed), falls back to .env (local).
    """
    try:
        return st.secrets['GOOGLE_PLACES_API_KEY']
    except Exception:
        return os.getenv('GOOGLE_PLACES_API_KEY')


def _get_offsets(lat: float, lng: float, distance_km: float = 1.8) -> list[tuple]:
    lat_offset = distance_km / 111.0
    lng_offset = distance_km / (111.0 * math.cos(math.radians(lat)))
    return [
        (lat,              lng),
        (lat + lat_offset, lng - lng_offset),
        (lat + lat_offset, lng + lng_offset),
        (lat - lat_offset, lng - lng_offset),
        (lat - lat_offset, lng + lng_offset),
    ]


def _single_call(lat: float, lng: float, place_types: list[str], api_key: str) -> set:
    """Makes one API call and returns a set of place IDs."""
    url = 'https://places.googleapis.com/v1/places:searchNearby'
    headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': api_key,
        'X-Goog-FieldMask': 'places.id'
    }
    payload = {
        'includedTypes': place_types,
        'locationRestriction': {
            'circle': {
                'center': {'latitude': lat, 'longitude': lng},
                'radius': SEARCH_RADIUS
            }
        },
        'maxResultCount': 20
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        data = response.json()
        if 'error' in data:
            return set()
        return {place['id'] for place in data.get('places', [])}
    except Exception as e:
        print(f"Request failed: {e}")
        return set()


def _search_nearby(lat: float, lng: float, place_types: list[str]) -> int:
    """
    Fires all 5 offset calls in parallel and deduplicates results.
    """
    api_key = _get_api_key()  # ← updated from os.getenv()
    points  = _get_offsets(lat, lng)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(_single_call, pt_lat, pt_lng, place_types, api_key)
            for pt_lat, pt_lng in points
        ]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    all_ids = set().union(*results)
    return min(len(all_ids), MAX_RESULTS_CAP)


def get_google_data(suburb_name: str, state: str = 'NSW') -> dict | None:
    coords = get_suburb_coordinates(suburb_name, state)
    if coords is None:
        return None

    lat, lng = coords
    metrics = {'suburb_name': suburb_name.strip().title(), 'state': state}
    metrics['latitude']  = lat
    metrics['longitude'] = lng

    # Fire all 8 categories in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_metric = {
            executor.submit(_search_nearby, lat, lng, place_types): metric_name
            for metric_name, place_types in CATEGORIES.items()
        }
        for future in concurrent.futures.as_completed(future_to_metric):
            metric_name = future_to_metric[future]
            try:
                metrics[metric_name] = future.result()
            except Exception as e:
                print(f"Error fetching {metric_name}: {e}")
                metrics[metric_name] = 0

    metrics['raw_json'] = json.dumps({
        'coordinates': {'lat': lat, 'lng': lng},
        'metrics': {k: v for k, v in metrics.items() if k.endswith('_count')}
    })

    return metrics
