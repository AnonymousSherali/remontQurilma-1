"""Mijozni to'lov sahifasiga yo'naltirish.

settings.PAYMENT_PROVIDER:
    'demo'  — saytning o'zidagi soxta to'lov sahifasi (faqat sinov/namoyish uchun!)
    'payme' — Payme checkout
"""

from django.conf import settings
from django.urls import reverse

from . import payme


def provider_name():
    return getattr(settings, 'PAYMENT_PROVIDER', 'demo')


def checkout_url(milestone, request):
    return_url = request.build_absolute_uri(milestone.order.get_customer_url())
    if provider_name() == 'payme':
        return payme.checkout_url(milestone, return_url)
    return reverse('payments:demo_checkout', args=[milestone.pk])
