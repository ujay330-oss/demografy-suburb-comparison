import requests
import os
from dotenv import load_dotenv

load_dotenv()

def get_suburb_coordinates(suburb_name: str, state: str = 'NSW') -> tuple[float, float] | None:
    """
    Returns (latitude, longitude) for a suburb, or None if not found.
    Example: get_suburb_coordinates('Bondi', 'NSW') -> (-33.8915, 151.2767)
    """
    api_key = os.getenv('GOOGLE_PLACES_API_KEY')
    address = f'{suburb_name}, {state}, Australia'
    url = 'https://maps.googleapis.com/maps/api/geocode/json'
    params = {'address': address, 'key': api_key}

    response = requests.get(url, params=params)
    data = response.json()

    if data['status'] == 'OK' and data['results']:
        location = data['results'][0]['geometry']['location']
        return location['lat'], location['lng']

    return None  # Suburb not found or API error
