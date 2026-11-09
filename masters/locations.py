"""Toshkent tumanlari va ularning taxminiy markaz koordinatalari.

Foydalanuvchi brauzerda joylashuvni yoqmasa yoki yoqa olmasa (masalan, HTTP
orqali kirgan bo'lsa), tumanni tanlab qidirishi mumkin. Koordinatalar tuman
markaziga yaqin nuqta — aniq manzil emas.
"""

TASHKENT_DISTRICTS = [
    ('bektemir', "Bektemir", 41.2090, 69.3340),
    ('chilonzor', "Chilonzor", 41.2750, 69.2040),
    ('mirobod', "Mirobod", 41.2900, 69.2820),
    ('mirzo-ulugbek', "Mirzo Ulug'bek", 41.3380, 69.3340),
    ('olmazor', "Olmazor", 41.3530, 69.2250),
    ('sergeli', "Sergeli", 41.2260, 69.2190),
    ('shayxontohur', "Shayxontohur", 41.3230, 69.2370),
    ('uchtepa', "Uchtepa", 41.2870, 69.1720),
    ('yakkasaroy', "Yakkasaroy", 41.2850, 69.2550),
    ('yangihayot', "Yangihayot", 41.2040, 69.1650),
    ('yashnobod', "Yashnobod", 41.2970, 69.3370),
    ('yunusobod', "Yunusobod", 41.3640, 69.2890),
]

DISTRICT_CHOICES = [(slug, name) for slug, name, _, _ in TASHKENT_DISTRICTS]
_BY_SLUG = {slug: (name, lat, lng) for slug, name, lat, lng in TASHKENT_DISTRICTS}


def district_coords(slug):
    """Tuman slug'i bo'yicha (lat, lng). Topilmasa (None, None)."""
    item = _BY_SLUG.get(slug or '')
    if not item:
        return None, None
    return item[1], item[2]


def district_name(slug):
    item = _BY_SLUG.get(slug or '')
    return item[0] if item else ''
