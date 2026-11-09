"""Geografik hisob-kitoblar.

PostGIS kabi og'ir bog'liqliksiz ishlaydi: avval bazada "kvadrat" (bounding box)
bo'yicha tez filtrlanadi, keyin aniq masofa Python'da haversine formulasi bilan
hisoblanadi. Bir necha ming ustagacha bu yetarlicha tez.
"""

import math

EARTH_RADIUS_KM = 6371.0088
KM_PER_DEGREE_LAT = 111.32

# O'zbekiston chegarasi (taxminiy). Koordinatalar adashib almashtirilganini
# (lat <-> lng) yoki noto'g'ri kiritilganini aniqlash uchun ishlatiladi.
UZ_BOUNDS = {'lat_min': 37.1, 'lat_max': 45.6, 'lng_min': 55.9, 'lng_max': 73.2}


def haversine_km(lat1, lng1, lat2, lng2):
    """Ikki nuqta orasidagi masofa (km)."""
    lat1, lng1, lat2, lng2 = map(math.radians, (float(lat1), float(lng1), float(lat2), float(lng2)))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bounding_box(lat, lng, radius_km):
    """Markaz atrofidagi radiusni qamrab oluvchi to'rtburchak: (lat_min, lat_max, lng_min, lng_max)."""
    lat = float(lat)
    lng = float(lng)
    dlat = radius_km / KM_PER_DEGREE_LAT
    # Qutblarga yaqinlashganda kosinus nolga intiladi — bo'lishdan himoya
    dlng = radius_km / (KM_PER_DEGREE_LAT * max(math.cos(math.radians(lat)), 0.01))
    return lat - dlat, lat + dlat, lng - dlng, lng + dlng


def in_uzbekistan(lat, lng):
    b = UZ_BOUNDS
    return b['lat_min'] <= float(lat) <= b['lat_max'] and b['lng_min'] <= float(lng) <= b['lng_max']


def parse_coords(lat, lng):
    """GET parametrlaridan koordinata o'qish. Noto'g'ri bo'lsa (None, None)."""
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None, None
    return lat, lng
