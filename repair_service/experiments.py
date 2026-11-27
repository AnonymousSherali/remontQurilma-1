"""A/B testlar: tashrifchini variantlarga teng taqsimlash va natijani o'lchash.

Ishlatish:
  1) admin → A/B testlar: kalit (masalan «ariza_tugmasi»), variantlar «a,b», «Faol»;
  2) shablonda:  {% load ui %}{% ab 'ariza_tugmasi' as v %}{% if v == 'b' %}…{% else %}…{% endif %}
Bir tashrifchi har doim bir xil variantni ko'radi (tasodifiy tashrifchi ID'dan hisoblanadi).
Natija: forma boshlash va ariza yuborish ulushi, nazorat variantiga nisbatan statistik ahamiyat
(ikki ulush uchun z-test). Test faol bo'lmasa yoki g'olib tanlangan bo'lsa — hamma bitta variantni ko'radi.
«Do Not Track» va botlar testda qatnashmaydi (ular nazorat variantini ko'radi).
"""

import hashlib
import math

from django.core.cache import cache
from django.db import IntegrityError
from django.db.models import F, OuterRef, Subquery

from .models import AnalyticsEvent, Experiment, ExperimentExposure


def _experiment(key):
    cache_key = f'experiment:{key}'
    exp = cache.get(cache_key)
    if exp is None:
        exp = Experiment.objects.filter(key=key).first() or False
        cache.set(cache_key, exp, 60)
    return exp or None


def assign(key, visitor):
    exp = _experiment(key)
    if exp is None:
        return 'a'
    variants = exp.variant_list
    if exp.winner:
        return exp.winner
    if not exp.is_active or not visitor:
        return variants[0]
    digest = int(hashlib.sha256(f'{key}:{visitor}'.encode()).hexdigest(), 16)
    return variants[digest % len(variants)]


def variant_for(request, key):
    """Shablon tegi uchun: variant va (faol test bo'lsa) qatnashganlik qaydi."""
    visitor = getattr(request, 'ts_visitor', '') or ''
    variant = assign(key, visitor)
    exp = _experiment(key)
    if exp is not None and exp.is_active and not exp.winner and visitor:
        seen_key = f'exposed:{exp.pk}:{visitor}'
        if not cache.get(seen_key):
            try:
                ExperimentExposure.objects.get_or_create(experiment_id=exp.pk, visitor=visitor,
                                                         defaults={'variant': variant})
            except IntegrityError:
                pass
            cache.set(seen_key, 1, 60 * 60 * 24)
    return variant


def _z_test(conv_a, n_a, conv_b, n_b):
    """Ikki ulush farqi uchun ikki tomonlama p-qiymat (normal yaqinlashuv)."""
    if not n_a or not n_b:
        return None
    pooled = (conv_a + conv_b) / (n_a + n_b)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
    if se == 0:
        return None
    z = (conv_b / n_b - conv_a / n_a) / se
    return round(math.erfc(abs(z) / math.sqrt(2)), 4)


def results(exp):
    """Har bir variant: qatnashganlar, forma boshlaganlar, ariza yuborganlar, ulushlar va p-qiymat."""
    rows = []
    for variant in exp.variant_list:
        exposures = exp.exposures.filter(variant=variant)
        n = exposures.count()

        def converted(name):
            # Pastki so'rov (katta IN-ro'yxatsiz) va faqat variantni ko'rgandan KEYINGI harakat
            first_seen = exposures.filter(visitor=OuterRef('visitor')).values('created_at')[:1]
            return (AnalyticsEvent.objects.filter(name=name, visitor__in=exposures.values('visitor'))
                    .annotate(seen=Subquery(first_seen)).filter(created_at__gte=F('seen'))
                    .values('visitor').distinct().count()) if n else 0
        starts = converted(AnalyticsEvent.FORM_START)
        requests_n = converted(AnalyticsEvent.REQUEST)
        rows.append({'variant': variant, 'visitors': n, 'starts': starts, 'requests': requests_n,
                     'start_rate': round(starts * 100 / n, 1) if n else None,
                     'request_rate': round(requests_n * 100 / n, 1) if n else None})
    control = rows[0] if rows else None
    for row in rows[1:]:
        row['p_value'] = _z_test(control['requests'], control['visitors'], row['requests'], row['visitors'])
        row['significant'] = row['p_value'] is not None and row['p_value'] < 0.05 and \
            min(control['visitors'], row['visitors']) >= 100
        if control['request_rate'] and row['request_rate'] is not None:
            row['lift'] = round((row['request_rate'] - control['request_rate']) * 100 / control['request_rate'], 1)
    return rows
