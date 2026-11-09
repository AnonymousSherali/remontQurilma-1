from .geo import bounding_box, haversine_km
from .models import Master

DEFAULT_RADIUS_KM = 15
RADIUS_CHOICES = [3, 5, 10, 15, 25, 50]
SORT_DISTANCE = 'distance'
SORT_RATING = 'rating'


def search_masters(*, category=None, lat=None, lng=None, radius_km=DEFAULT_RADIUS_KM,
                   sort=SORT_DISTANCE, query=''):
    """Ustalarni qidirish.

    Joylashuv berilsa — radius ichidagilar masofa bo'yicha (yoki reyting bo'yicha)
    saralanadi va har biriga `distance_km` qo'shiladi. Joylashuv berilmasa —
    reyting (Bayes o'rtachasi) bo'yicha.

    Usta o'zi belgilagan xizmat radiusidan uzoqdagi mijozga ko'rsatilmaydi:
    20 km narida yashovchi mijozga "men 5 km gacha boraman" degan ustani
    taklif qilish mantiqsiz.
    """
    qs = Master.objects.public().filter(is_available=True).prefetch_related('categories')
    if category is not None:
        qs = qs.filter(categories=category)
    if query:
        qs = qs.filter(full_name__icontains=query.strip())

    if lat is None or lng is None:
        results = list(qs.distinct())
        for master in results:
            master.distance_km = None
        results.sort(key=lambda m: m.ranking_score, reverse=True)
        return results

    lat_min, lat_max, lng_min, lng_max = bounding_box(lat, lng, radius_km)
    qs = qs.filter(
        latitude__gte=lat_min, latitude__lte=lat_max,
        longitude__gte=lng_min, longitude__lte=lng_max,
    ).distinct()

    results = []
    for master in qs:
        distance = haversine_km(lat, lng, master.latitude, master.longitude)
        if distance <= radius_km and distance <= master.service_radius_km:
            master.distance_km = round(distance, 1)
            results.append(master)

    if sort == SORT_RATING:
        results.sort(key=lambda m: (-m.ranking_score, m.distance_km))
    else:
        results.sort(key=lambda m: (m.distance_km, -m.ranking_score))
    return results


def master_to_dict(master, request=None):
    """Xarita va API uchun. Aniq koordinata emas, yaxlitlangani beriladi."""
    photo = master.photo.url if master.photo else None
    if photo and request is not None:
        photo = request.build_absolute_uri(photo)
    return {
        'id': master.pk,
        'name': master.full_name,
        'initials': master.initials,
        'categories': [c.name for c in master.categories.all()],
        'rating': float(master.rating_avg),
        'reviews_count': master.reviews_count,
        'experience_years': master.experience_years,
        'distance_km': getattr(master, 'distance_km', None),
        'lat': master.public_latitude,
        'lng': master.public_longitude,
        'area': master.address,
        'photo': photo,
        'url': master.get_absolute_url(),
    }
