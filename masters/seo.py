"""SEO sahifalari: yo'nalish (/ustalar/santexnik/) va yo'nalish + tuman (/ustalar/santexnik/chilonzor/).

Har bir sahifa — qidiruv natijasi + o'ziga xos ma'lumot (ustalar soni, o'rtacha baho, katalog narxlari,
qo'shni tumanlar). Ustasi yo'q sahifa «noindex» va sitemap'ga kirmaydi — bo'sh sahifalar
qidiruv tizimida saytning sifat bahosini tushiradi.
"""

from django.conf import settings
from django.db.models import Min
from django.urls import reverse
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from repair_service.models import Service

from .locations import DISTRICT_CHOICES, district_coords, district_name, is_city, nearest_city
from .models import Category
from .services import DEFAULT_RADIUS_KM, SORT_DISTANCE, SORT_RATING, search_masters


def absolute(request, path):
    return request.build_absolute_uri(path)


def category_url(category, district=''):
    if district:
        return reverse('masters:category_district', args=[category.slug, district])
    return reverse('masters:category', args=[category.slug])


def landing_results(category, district=''):
    lat, lng = district_coords(district) if district else (None, None)
    return search_masters(category=category, lat=lat, lng=lng, radius_km=DEFAULT_RADIUS_KM,
                          sort=SORT_DISTANCE if district else SORT_RATING)


def has_masters(category, district=''):
    return bool(landing_results(category, district))


def landing_context(request, category, district, results):
    cat_name = category.name_ru if (get_language() or '').startswith('ru') and category.name_ru else category.name
    place = district_name(district)
    rated = [m for m in results if m.reviews_count]
    avg = round(sum(float(m.rating_avg) for m in rated) / len(rated), 1) if rated else None
    reviews = sum(m.reviews_count for m in results)
    min_price = (Service.objects.filter(is_active=True, category=category, price_from__gt=0)
                 .aggregate(p=Min('price_from'))['p'])
    prices = (Service.objects.filter(is_active=True, category=category)
              .order_by('-is_popular', 'order')[:6])

    if place:
        # Toshkent tumani yoki viloyat shahri — so'z shakli farq qiladi
        city = is_city(district)
        place_name = (_('%(name)s shahri') if city else _('%(name)s tumani')) % {'name': place}
        place_in = (_('%(name)s shahrida') if city else _('%(name)s tumanida')) % {'name': place}
        h1 = '%s — %s' % (cat_name, place_name)
        title = _("%(category)s %(place)s: %(n)s ta usta, baholar va narxlar") % {
            'category': cat_name, 'place': place_in, 'n': len(results)}
    else:
        city, place_name = False, ''
        h1 = _('%(category)s: tekshirilgan ustalar') % {'category': cat_name}
        title = _("%(category)s: %(n)s ta tekshirilgan usta, baholar va narxlar") % {
            'category': cat_name, 'n': len(results)}
    parts = [_("%(n)s ta tekshirilgan usta") % {'n': len(results)}]
    if avg:
        parts.append(_("o'rtacha baho %(avg)s (%(reviews)s ta baho)") % {'avg': avg, 'reviews': reviews})
    if min_price:
        parts.append(_("narxlar %(price)s so'mdan") % {'price': f'{int(min_price):,}'.replace(',', ' ')})
    description = '. '.join([h1, ', '.join(parts)]) + '. ' + _("Ariza bepul, pul ish bajarilgach ustaga o'tadi.")

    crumbs = [(_('Bosh sahifa'), reverse('repair_service:index')), (_('Ustalar'), reverse('masters:list')),
              (cat_name, category_url(category))]
    if place:
        crumbs.append((place, category_url(category, district)))

    base = request.build_absolute_uri('/').rstrip('/')
    ld = [{
        '@context': 'https://schema.org', '@type': 'BreadcrumbList',
        'itemListElement': [{'@type': 'ListItem', 'position': i + 1, 'name': str(name), 'item': base + url}
                            for i, (name, url) in enumerate(crumbs)],
    }]
    if results:
        ld.append({
            '@context': 'https://schema.org', '@type': 'ItemList', 'name': h1,
            'itemListElement': [{'@type': 'ListItem', 'position': i + 1, 'url': base + m.get_absolute_url(),
                                 'name': m.full_name} for i, m in enumerate(results[:20])],
        })

    return {
        'seo': {
            'h1': h1, 'title': title, 'description': description, 'crumbs': crumbs, 'jsonld': ld,
            'canonical': absolute(request, category_url(category, district)),
            'noindex': not results, 'avg': avg, 'reviews': reviews, 'min_price': min_price,
            'place': place, 'place_name': place_name, 'is_city': city,
            'category_name': cat_name, 'prices': prices,
            'district_links': [(district_name(slug), category_url(category, slug), slug == district)
                               for slug, _name in DISTRICT_CHOICES if not is_city(slug)],
            'city_links': [(district_name(slug), category_url(category, slug), slug == district)
                           for slug, _name in DISTRICT_CHOICES if is_city(slug)],
            'category_links': [(c, category_url(c, district)) for c in
                               Category.objects.filter(is_active=True).exclude(pk=category.pk)],
        },
    }


def master_jsonld(request, master):
    """Usta profili uchun schema.org (LocalBusiness turi). Telefon va aniq manzil kiritilmaydi."""
    _slug, city = nearest_city(master.latitude, master.longitude)
    data = {
        '@context': 'https://schema.org', '@type': 'HomeAndConstructionBusiness',
        'name': master.full_name, 'url': request.build_absolute_uri(master.get_absolute_url()),
        'address': {'@type': 'PostalAddress', 'addressLocality': city or 'Toshkent', 'addressCountry': 'UZ'},
        'areaServed': master.address or city or 'Toshkent',
        'knowsAbout': [c.name for c in master.categories.all()],
    }
    if master.photo:
        data['image'] = request.build_absolute_uri(master.photo.url)
    if master.bio:
        data['description'] = master.bio[:300]
    if master.reviews_count:
        data['aggregateRating'] = {'@type': 'AggregateRating', 'ratingValue': str(master.rating_avg),
                                   'reviewCount': master.reviews_count, 'bestRating': 5, 'worstRating': 1}
    return data


def site_jsonld(request):
    base = request.build_absolute_uri('/')
    return [{
        '@context': 'https://schema.org', '@type': 'Organization', 'name': settings.SITE_INFO['name'],
        'url': base, 'logo': request.build_absolute_uri('/static/img/og.png'),
        'contactPoint': {'@type': 'ContactPoint', 'telephone': settings.SITE_INFO['phone'],
                         'contactType': 'customer service', 'areaServed': 'UZ', 'availableLanguage': ['uz', 'ru']},
    }, {
        '@context': 'https://schema.org', '@type': 'WebSite', 'name': settings.SITE_INFO['name'], 'url': base,
        'inLanguage': ['uz', 'ru'],
    }]
