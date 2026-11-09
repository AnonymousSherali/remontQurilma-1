"""Buyurtma holati o'zgarganda SMS xabarnomalar.

Mijozga — usta qabul qilganda, yetib kelganda, ishni yakunlaganda.
Ustaga — yangi buyurtma kelganda va mijoz tasdiqlaganda/nizo ochganda.
SMS buyurtma yaratilgan tilda yuboriladi.
"""

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext as _

from otp.sms import send_sms

from .models import OrderEvent, ServiceRequest as SR
from .phone import format_phone


def _absolute(path):
    return settings.SITE_URL.rstrip('/') + path


def _customer_link(order):
    with translation.override(order.language or 'uz'):
        return _absolute(order.get_customer_url())


def notify_order_created(order):
    with translation.override(order.language or 'uz'):
        send_sms(order.phone, _('Buyurtmangiz #%(id)s qabul qilindi. Holatini kuzating: %(url)s') % {
            'id': order.pk, 'url': _customer_link(order)}, background=True)
    if order.master:
        notify_master_new_order(order)


def notify_master_new_order(order):
    # Usta interfeysi sayt standart tilida
    with translation.override(settings.LANGUAGE_CODE):
        send_sms(order.master.phone, _('Yangi buyurtma #%(id)s: %(name)s. Kabinet: %(url)s') % {
            'id': order.pk, 'name': order.name, 'url': _absolute(order.get_master_url())}, background=True)


def notify_status_change(order, actor):
    order = SR.objects.select_related('master').get(pk=order.pk)
    master = order.master

    if actor == OrderEvent.ACTOR_MASTER:
        with translation.override(order.language or 'uz'):
            texts = {
                SR.STATUS_ACCEPTED: _('Usta %(master)s buyurtmangizni qabul qildi. Tel: %(phone)s. %(url)s'),
                SR.STATUS_ARRIVED: _('Usta %(master)s yetib keldi. %(url)s'),
                SR.STATUS_COMPLETED: _('Usta ishni yakunladi. Natijani tasdiqlang va baholang: %(url)s'),
                SR.STATUS_CANCELLED: _('Usta buyurtmani bekor qildi. Boshqa usta topamiz: %(url)s'),
            }
            text = texts.get(order.status)
            if text:
                send_sms(order.phone, text % {
                    'master': master.full_name if master else '',
                    'phone': format_phone(master.phone) if master else '',
                    'url': _customer_link(order),
                }, background=True)

    elif actor == OrderEvent.ACTOR_CUSTOMER and master:
        with translation.override(settings.LANGUAGE_CODE):
            texts = {
                SR.STATUS_CONFIRMED: _('Mijoz #%(id)s buyurtmani tasdiqladi.'),
                SR.STATUS_CANCELLED: _('Mijoz #%(id)s buyurtmani bekor qildi.'),
                SR.STATUS_DISPUTED: _('Mijoz #%(id)s buyurtma bo\'yicha nizo ochdi. Administrator bog\'lanadi.'),
            }
            text = texts.get(order.status)
            if text:
                send_sms(master.phone, text % {'id': order.pk}, background=True)


def notify_quote(order):
    order = SR.objects.select_related('master', 'quote').get(pk=order.pk)
    with translation.override(order.language or 'uz'):
        send_sms(order.phone, _("Usta narx taklif qildi: %(amount)s so'm. Ko'rib chiqing: %(url)s") % {
            'amount': f'{int(order.quote.amount):,}'.replace(',', ' '), 'url': _customer_link(order)}, background=True)
