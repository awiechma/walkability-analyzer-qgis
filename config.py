# -------------------------------------------------
# OpenRouteService API Key
# -------------------------------------------------
ORS_API_KEY = "YOUR_API_KEY"

# -------------------------------------------------
# Münster Stadtteile (Name: [lat, lon])
# -------------------------------------------------
MUENSTER_DISTRICTS = {
    "Centrum": [51.9606649, 7.6261347],
    "Hiltrup": [51.904280, 7.645285],
    "Kinderhaus": [51.993970, 7.604899],
    "Gievenbeck": [51.969137, 7.571855],
    "Mauritz": [51.966858, 7.656349],
    "Roxel": [51.951325, 7.536030],
    "Albachten": [51.919932, 7.527410],
    "Gremmendorf": [51.929478, 7.671827],
    "Angelmodde": [51.918257, 7.703526],
    "Wolbeck": [51.917677, 7.728329],
    "Berg Fidel": [51.925186, 7.622256],
    "Coerde": [51.992041, 7.648306],
    "Handorf": [51.989163, 7.704291],
    "Amelsbüren": [51.881082, 7.608525],
    "Sprakel": [52.036572, 7.616059]
}

# -------------------------------------------------
# Service-Kategorien für die Analyse
# -------------------------------------------------

SERVICE_CATEGORIES = {
    "Supermarkt": {"weight": 0.25},
    "Apotheke": {"weight": 0.20},
    "Arzt": {"weight": 0.20},
    "Schule": {"weight": 0.15},
    "Restaurant": {"weight": 0.10},
    "Bank": {"weight": 0.10},
}

# -------------------------------------------------
# URLs
# -------------------------------------------------
ORS_BASE_URL = "https://api.openrouteservice.org/v2"
ORS_ISOCHRONE_URL = f"{ORS_BASE_URL}/isochrones/foot-walking"
ORS_GEOCODE_URL = f"{ORS_BASE_URL}/geocode/search"

# Nominatim für Geocoding
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# -------------------------------------------------
# Validierung
# -------------------------------------------------
MIN_COORDINATE_PRECISION = 4
COORDINATE_BOUNDS = {
    'lat_min': -90,
    'lat_max': 90,
    'lon_min': -180,
    'lon_max': 180
}

# -------------------------------------------------
# Hilfsfunktionen
# -------------------------------------------------
def is_valid_coordinate(lat, lon):
    """Validiere Koordinaten"""
    try:
        lat = float(lat)
        lon = float(lon)
        if not (COORDINATE_BOUNDS['lat_min'] <= lat <= COORDINATE_BOUNDS['lat_max']):
            return False
        if not (COORDINATE_BOUNDS['lon_min'] <= lon <= COORDINATE_BOUNDS['lon_max']):
            return False
        return True
    except (ValueError, TypeError):
        return False

def get_service_icon(service_type):
    """Hole Icon für Service-Typ"""
    if service_type in SERVICE_CATEGORIES:
        return SERVICE_CATEGORIES[service_type].get('icon', '📍')
    else:
        return '📍'
