"""Mijozni to'lov sahifasiga yo'naltirish.

settings.PAYMENT_PROVIDERS — vergul bilan, mijozga taklif qilinadigan tizimlar:
    'demo'  — saytning o'zidagi soxta to'lov sahifasi (faqat sinov uchun!)
    'payme' — Payme checkout
    'click' — Click checkout
Masalan: PAYMENT_PROVIDERS=payme,click — mijoz qaysi biri bilan to'lashni tanlaydi.
"""

from django.conf import settings
from django.urls import reverse

from . import click, payme

LABELS = {'demo': 'Demo', 'payme': 'Payme', 'click': 'Click'}


def available():
    raw = getattr(settings, 'PAYMENT_PROVIDERS', '') or getattr(settings, 'PAYMENT_PROVIDER', 'demo')
    names = [p.strip() for p in raw.split(',') if p.strip() in LABELS]
    return names or ['demo']


def provider_name():
    """Birlamchi tizim (ro'yxatdagi birinchisi)."""
    return available()[0]


def choices():
    return [(name, LABELS[name]) for name in available()]


def checkout_url(milestone, request, provider=None):
    provider = provider if provider in available() else provider_name()
    return_url = request.build_absolute_uri(milestone.order.get_customer_url())
    if provider == 'payme':
        return payme.checkout_url(milestone, return_url)
    if provider == 'click':
        return click.checkout_url(milestone, return_url)
    return reverse('payments:demo_checkout', args=[milestone.pk])
