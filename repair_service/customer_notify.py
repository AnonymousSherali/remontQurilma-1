"""Buyurtma holati o'zgarganda SMS xabarnomalar.

Mijozga — usta qabul qilganda, yetib kelganda, ishni yakunlaganda.
Ustaga — yangi buyurtma kelganda va mijoz tasdiqlaganda/nizo ochganda.
SMS buyurtma yaratilgan tilda yuboriladi.
"""

from django.conf import settings
from django.urls import reverse
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


def _to_customer(order, text):
    """Telegram ulangan bo'lsa — Telegram (bepul), aks holda SMS."""
    if order.telegram_chat_id:
        from telegram_bot import client
        with translation.override(order.language or 'uz'):
            client.send_message(order.telegram_chat_id, text, [[(_('Buyurtmani ochish'), _customer_link(order))]])
    else:
        send_sms(order.phone, text, background=True)


def _to_master(order, sms_text, with_card=False):
    """Usta Telegram'ga ulangan bo'lsa — buyurtma kartasi va keyingi qadam tugmasi bilan."""
    master = order.master
    if master.telegram_chat_id:
        from telegram_bot import client
        from telegram_bot.handlers import master_buttons, order_card
        text = f'{sms_text}\n\n{order_card(order)}' if with_card else sms_text
        client.send_message(master.telegram_chat_id, text, master_buttons(order))
    else:
        send_sms(master.phone, sms_text, background=True)


def notify_order_created(order):
    with translation.override(order.language or 'uz'):
        _to_customer(order, _('Buyurtmangiz #%(id)s qabul qilindi. Holatini kuzating: %(url)s') % {
            'id': order.pk, 'url': _customer_link(order)})
    if order.master:
        notify_master_new_order(order)
    else:
        notify_open_order(order)


def notify_master_new_order(order):
    """Yangi buyurtma ustaga (saytdan to'g'ridan-to'g'ri yoki admin biriktirganda)."""
    order = SR.objects.select_related('master', 'category').get(pk=order.pk)
    # Usta interfeysi sayt standart tilida
    with translation.override(settings.LANGUAGE_CODE):
        _to_master(order, _('Yangi buyurtma #%(id)s: %(name)s. Kabinet: %(url)s') % {
            'id': order.pk, 'name': order.name, 'url': _absolute(order.get_master_url())}, with_card=True)


def notify_status_change(order, actor):
    order = SR.objects.select_related('master', 'category').get(pk=order.pk)
    master = order.master

    if actor == OrderEvent.ACTOR_MASTER:
        with translation.override(order.language or 'uz'):
            texts = {
                SR.STATUS_ACCEPTED: _('Usta %(master)s buyurtmangizni qabul qildi. Tel: %(phone)s. %(url)s'),
                SR.STATUS_ARRIVED: _('Usta %(master)s yetib keldi. %(url)s'),
                SR.STATUS_COMPLETED: _('Usta ishni yakunladi. Natijani tasdiqlang va baholang: %(url)s'),
                SR.STATUS_NEW: _('Usta buyurtmadan voz kechdi. Boshqa usta qidiryapmiz: %(url)s'),
            }
            text = texts.get(order.status)
            if text:
                _to_customer(order, text % {
                    'master': master.full_name if master else '',
                    'phone': format_phone(master.phone) if master else '',
                    'url': _customer_link(order),
                })

    elif actor == OrderEvent.ACTOR_CUSTOMER and master:
        with translation.override(settings.LANGUAGE_CODE):
            texts = {
                SR.STATUS_CONFIRMED: _('Mijoz #%(id)s buyurtmani tasdiqladi.'),
                SR.STATUS_CANCELLED: _('Mijoz #%(id)s buyurtmani bekor qildi.'),
                SR.STATUS_DISPUTED: _('Mijoz #%(id)s buyurtma bo\'yicha nizo ochdi. Administrator bog\'lanadi.'),
            }
            text = texts.get(order.status)
            if text:
                _to_master(order, text % {'id': order.pk})


def notify_quote(order):
    order = SR.objects.select_related('master', 'quote').get(pk=order.pk)
    with translation.override(order.language or 'uz'):
        _to_customer(order, _("Usta narx taklif qildi: %(amount)s so'm. Ko'rib chiqing: %(url)s") % {
            'amount': f'{int(order.quote.amount):,}'.replace(',', ' '), 'url': _customer_link(order)})


def notify_open_order(order):
    """Yangi ochiq buyurtma haqida yaqin atrofdagi ustalarga Telegram xabari ("Olish" tugmasi bilan).

    Xabarda mijozning ismi, telefoni va aniq manzili yo'q — ular buyurtma olingach ochiladi.
    """
    from masters import feed
    from telegram_bot import client
    from telegram_bot.handlers import open_order_card

    order = SR.objects.select_related('category', 'catalog_item').get(pk=order.pk)
    if order.master_id is not None or order.status != SR.STATUS_NEW:
        return
    with translation.override(settings.LANGUAGE_CODE):
        for master in feed.nearby_masters(order):
            feed._annotate(order, master)  # shu ustaga nisbatan masofa
            client.send_message(master.telegram_chat_id, open_order_card(order, master), [
                [(_('✋ Olish'), f'c:{order.pk}')],
                [(_('Ochiq buyurtmalar'), _absolute(reverse('masters:feed')))],
            ])
