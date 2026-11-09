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
