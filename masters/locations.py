"""Joylashuvlar: Toshkent tumanlari va viloyat markazlari, taxminiy markaz koordinatalari bilan.

Foydalanuvchi brauzerda joylashuvni yoqmasa yoki yoqa olmasa (masalan, HTTP
orqali kirgan bo'lsa), tuman yoki shaharni tanlab qidirishi mumkin. Koordinatalar
markazga yaqin nuqta — aniq manzil emas. Slug'lar umumiy: Toshkent tumani («chilonzor»)
yoki viloyat shahri («samarqand») — ariza, qidiruv va SEO sahifalarida bir xil ishlatiladi.

Yangi shahar qo'shish: REGIONS dagi viloyatga qator qo'shing (slug, o'zbekcha, ruscha, lat, lng).
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

# Viloyatlar va ulardagi shaharlar: (slug, o'zbekcha, ruscha, kenglik, uzunlik) — taxminiy markaz.
# Har bir shahar qidiruvda bitta «hudud» sifatida ishlaydi (kichik shaharlarni tumanlarga bo'lish shart emas).
REGIONS = [
    ("Toshkent viloyati", 'Ташкентская область', [
        ('chirchiq', 'Chirchiq', 'Чирчик', 41.4689, 69.5822),
        ('olmaliq', 'Olmaliq', 'Алмалык', 40.8447, 69.5983),
        ('angren', 'Angren', 'Ангрен', 41.0167, 70.1436),
        ('yangiyol', "Yangiyo'l", 'Янгиюль', 41.1122, 69.0472),
        ('bekobod', 'Bekobod', 'Бекабад', 40.2208, 69.2697),
    ]),
    ('Samarqand viloyati', 'Самаркандская область', [
        ('samarqand', 'Samarqand', 'Самарканд', 39.6542, 66.9597),
        ('kattaqorgon', "Kattaqo'rg'on", 'Каттакурган', 39.8989, 66.2561),
    ]),
    ('Buxoro viloyati', 'Бухарская область', [
        ('buxoro', 'Buxoro', 'Бухара', 39.7747, 64.4286),
        ('kogon', 'Kogon', 'Каган', 39.7228, 64.5517),
    ]),
    ('Andijon viloyati', 'Андижанская область', [
        ('andijon', 'Andijon', 'Андижан', 40.7821, 72.3442),
        ('asaka', 'Asaka', 'Асака', 40.6415, 72.2387),
    ]),
    ("Farg'ona viloyati", 'Ферганская область', [
        ('fargona', "Farg'ona", 'Фергана', 40.3864, 71.7864),
        ('qoqon', "Qo'qon", 'Коканд', 40.5286, 70.9425),
        ('margilon', "Marg'ilon", 'Маргилан', 40.4711, 71.7247),
    ]),
    ('Namangan viloyati', 'Наманганская область', [
        ('namangan', 'Namangan', 'Наманган', 40.9983, 71.6726),
        ('chust', 'Chust', 'Чуст', 41.0039, 71.2372),
    ]),
    ('Qashqadaryo viloyati', 'Кашкадарьинская область', [
        ('qarshi', 'Qarshi', 'Карши', 38.8606, 65.7891),
        ('shahrisabz', 'Shahrisabz', 'Шахрисабз', 39.0578, 66.8342),
    ]),
    ('Navoiy viloyati', 'Навоийская область', [
        ('navoiy', 'Navoiy', 'Навои', 40.0844, 65.3792),
        ('zarafshon', 'Zarafshon', 'Зарафшан', 41.5747, 64.2014),
    ]),
    ('Jizzax viloyati', 'Джизакская область', [
        ('jizzax', 'Jizzax', 'Джизак', 40.1158, 67.8422),
    ]),
    ('Sirdaryo viloyati', 'Сырдарьинская область', [
        ('guliston', 'Guliston', 'Гулистан', 40.4897, 68.7842),
        ('yangiyer', 'Yangiyer', 'Янгиер', 40.2750, 68.8225),
    ]),
    ('Surxondaryo viloyati', 'Сурхандарьинская область', [
        ('termiz', 'Termiz', 'Термез', 37.2242, 67.2783),
        ('denov', 'Denov', 'Денау', 38.2667, 67.8936),
    ]),
    ('Xorazm viloyati', 'Хорезмская область', [
        ('urganch', 'Urganch', 'Ургенч', 41.5500, 60.6333),
        ('xiva', 'Xiva', 'Хива', 41.3783, 60.3639),
    ]),
    ("Qoraqalpog'iston", 'Каракалпакстан', [
        ('nukus', 'Nukus', 'Нукус', 42.4619, 59.6166),
    ]),
]
REGIONAL_CITIES = [city for _uz, _ru, cities in REGIONS for city in cities]
TASHKENT_CENTER = (41.3111, 69.2797)
CITY_RADIUS_KM = 40   # shu masofada bo'lsa — usta/mijoz o'sha shaharda deb hisoblanadi

DISTRICT_CHOICES = ([(slug, name) for slug, name, _, _ in TASHKENT_DISTRICTS]
                    + [(slug, name) for slug, name, _ru, _, _ in REGIONAL_CITIES])
_BY_SLUG = {slug: (name, lat, lng) for slug, name, lat, lng in TASHKENT_DISTRICTS}
_BY_SLUG.update({slug: (name, lat, lng) for slug, name, _ru, lat, lng in REGIONAL_CITIES})
CITY_SLUGS = {slug for slug, *_rest in REGIONAL_CITIES}
_CITY_RU = {slug: ru for slug, _n, ru, _a, _b in REGIONAL_CITIES}


def district_coords(slug):
    """Tuman slug'i bo'yicha (lat, lng). Topilmasa (None, None)."""
    item = _BY_SLUG.get(slug or '')
    if not item:
        return None, None
    return item[1], item[2]


# Ruscha nomlar (SEO sahifalari va /ru/ uchun)
DISTRICT_NAMES_RU = {
    'bektemir': 'Бектемир', 'chilonzor': 'Чиланзар', 'mirobod': 'Мирабад', 'mirzo-ulugbek': 'Мирзо-Улугбек',
    'olmazor': 'Алмазар', 'sergeli': 'Сергели', 'shayxontohur': 'Шайхантахур', 'uchtepa': 'Учтепа',
    'yakkasaroy': 'Яккасарай', 'yangihayot': 'Янгихаёт', 'yashnobod': 'Яшнабад', 'yunusobod': 'Юнусабад',
}


def district_name(slug, lang=None):
    """Tuman nomi joriy tilda (lang berilmasa — faol til)."""
    item = _BY_SLUG.get(slug or '')
    if not item:
        return ''
    if lang is None:
        from django.utils.translation import get_language
        lang = get_language() or 'uz'
    if lang.startswith('ru'):
        return DISTRICT_NAMES_RU.get(slug) or _CITY_RU.get(slug, item[0])
    return item[0]


def is_city(slug):
    """Viloyat shahri (True) yoki Toshkent tumani (False)."""
    return slug in CITY_SLUGS


def location_groups(lang=None):
    """Tanlov ro'yxati uchun guruhlar: [(guruh nomi, [(slug, nom), ...]), ...] — joriy tilda."""
    from django.utils.translation import gettext as _
    from django.utils.translation import get_language
    ru = (lang or get_language() or 'uz').startswith('ru')
    groups = [(_('Toshkent shahri'), [(slug, district_name(slug, lang)) for slug, *_r in TASHKENT_DISTRICTS])]
    for name_uz, name_ru, cities in REGIONS:
        groups.append((name_ru if ru else name_uz, [(slug, district_name(slug, lang)) for slug, *_r in cities]))
    return groups


def nearest_city(lat, lng):
    """Koordinata qaysi shaharga tegishli: (slug, nom) yoki ('', 'Toshkent') / (None, '') — uzoqda."""
    from .geo import haversine_km
    if lat is None or lng is None:
        return None, ''
    lat, lng = float(lat), float(lng)
    if haversine_km(lat, lng, *TASHKENT_CENTER) <= CITY_RADIUS_KM:
        return '', 'Toshkent'
    best = min(REGIONAL_CITIES, key=lambda c: haversine_km(lat, lng, c[3], c[4]))
    if haversine_km(lat, lng, best[3], best[4]) <= CITY_RADIUS_KM:
        return best[0], best[1]
    return None, ''
