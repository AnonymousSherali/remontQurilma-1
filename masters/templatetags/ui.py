from django import template
from django.utils.html import format_html, format_html_join

from repair_service.phone import format_phone

register = template.Library()


@register.filter
def phone(value):
    return format_phone(value)


@register.simple_tag
def stars(value, size=''):
    """Reytingni yulduzlar bilan chizish: 4.6 -> ★★★★½ ko'rinishida (yarim yulduz CSS bilan)."""
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        value = 0
    percent = max(0, min(100, value / 5 * 100))
    css = 'stars' + (f' stars--{size}' if size else '')
    return format_html(
        '<span class="{}" role="img" aria-label="Reyting: {} / 5">'
        '<span class="stars__fill" style="width:{}%"></span></span>',
        css, f'{value:.1f}', f'{percent:.0f}',
    )


@register.filter
def km(value):
    if value is None:
        return ''
    value = float(value)
    if value < 1:
        return f'{int(value * 1000)} m'
    return f'{value:.1f} km'


@register.simple_tag
def query_with(querystring, **kwargs):
    """Joriy GET parametrlarini saqlagan holda bittasini almashtirish (sahifalash uchun)."""
    from django.http import QueryDict
    params = QueryDict(querystring, mutable=True)
    for key, val in kwargs.items():
        params[key] = val
    return params.urlencode()


@register.simple_tag
def chips(items):
    return format_html_join('', '<span class="chip">{}</span>', ((str(i),) for i in items))


@register.filter
def tr(obj, field):
    """Bazadagi matnni joriy tilda: rus tilida `name_ru` bo'sh bo'lmasa o'shani, aks holda asl matnni."""
    from django.utils.translation import get_language
    if obj is None:
        return ''
    if (get_language() or '').startswith('ru'):
        value = getattr(obj, f'{field}_ru', '')
        if value:
            return value
    return getattr(obj, field, '')


@register.simple_tag
def telegram_order_link(order):
    """Mijoz uchun "Telegram'da kuzatish" havolasi (bot sozlanmagan bo'lsa bo'sh)."""
    from telegram_bot.client import deep_link
    return deep_link('o' + order.review_token.hex)


@register.simple_tag
def location_groups():
    """Toshkent tumanlari va viloyat shaharlari — joriy tilda, tanlov ro'yxatlari uchun."""
    from masters.locations import location_groups as groups
    return groups()


@register.simple_tag
def jsonld(data):
    """Tuzilgan ma'lumot (schema.org) — <script type="application/ld+json">. <, >, & qochiriladi."""
    import json

    from django.core.serializers.json import DjangoJSONEncoder
    from django.utils.html import _json_script_escapes
    from django.utils.safestring import mark_safe
    if not data:
        return ''
    payload = json.dumps(data, cls=DjangoJSONEncoder, ensure_ascii=False).translate(_json_script_escapes)
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')


@register.simple_tag(takes_context=True)
def url_in_language(context, code):
    """Joriy sahifaning boshqa tildagi manzili (hreflang va til almashtirish uchun)."""
    from django.urls import translate_url
    request = context['request']
    return translate_url(request.get_full_path(), code)


@register.filter
def duration(minutes):
    """90 -> "~1,5 soat", 40 -> "~40 daqiqa" (tilga qarab)."""
    from django.utils.translation import gettext as _
    if not minutes:
        return ''
    if minutes < 60:
        return _('~%(n)s daqiqa') % {'n': minutes}
    hours = minutes / 60
    text = f'{hours:.1f}'.rstrip('0').rstrip('.').replace('.', ',')
    return _('~%(n)s soat') % {'n': text}


@register.filter
def includes_for(item, lang):
    return item.includes_list(lang)


@register.filter
def absval(value):
    try:
        return abs(value)
    except TypeError:
        return value


@register.filter
def get_item(mapping, key):
    """Lug'atdan kalit bo'yicha qiymat (shablonlarda)."""
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def work_status(master):
    """«Dam olishda» / «Hozir ishlamaydi — ertaga 08:00 dan» yoki bo'sh."""
    from masters.schedule import status_label
    return status_label(master)


@register.filter
def work_summary(master):
    from masters.schedule import summary
    return summary(master)


@register.simple_tag(takes_context=True)
def ab(context, key):
    """A/B test varianti: {% ab 'kalit' as v %} — repair_service/experiments.py."""
    request = context.get('request')
    if request is None:
        return 'a'
    from repair_service.experiments import variant_for
    return variant_for(request, key)
