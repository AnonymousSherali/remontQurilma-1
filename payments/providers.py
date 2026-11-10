"""Mijozni (yoki ustani) to'lov sahifasiga yo'naltirish.

settings.PAYMENT_PROVIDERS — vergul bilan, taklif qilinadigan tizimlar:
    'demo'  — saytning o'zidagi soxta to'lov sahifasi (faqat sinov uchun!)
    'payme' — Payme        'click' — Click        'uzum' — Uzum Bank
Masalan: PAYMENT_PROVIDERS=payme,click,uzum — to'lovchi qaysi biri bilan to'lashni tanlaydi.
"""

from django.conf import settings
from django.urls import reverse

from . import click, payme, uzum
from .models import Purchase
from .payables import wrap

LABELS = {'demo': 'Demo', 'payme': 'Payme', 'click': 'Click', 'uzum': 'Uzum Bank'}


def available():
    raw = getattr(settings, 'PAYMENT_PROVIDERS', '') or getattr(settings, 'PAYMENT_PROVIDER', 'demo')
    names = [p.strip() for p in raw.split(',') if p.strip() in LABELS]
    return names or ['demo']


def provider_name():
    """Birlamchi tizim (ro'yxatdagi birinchisi)."""
    return available()[0]


def choices():
    return [(name, LABELS[name]) for name in available()]


def checkout_url(target, request, provider=None):
    """target — Milestone yoki Purchase."""
    provider = provider if provider in available() else provider_name()
    payable = wrap(target)
    return_url = request.build_absolute_uri(payable.return_path())
    if provider == 'payme':
        return payme.checkout_url(payable, return_url)
    if provider == 'click':
        return click.checkout_url(payable, return_url)
    if provider == 'uzum':
        return uzum.checkout_url(payable, return_url)
    if isinstance(target, Purchase):
        return reverse('payments:demo_purchase', args=[target.pk])
    return reverse('payments:demo_checkout', args=[target.pk])
