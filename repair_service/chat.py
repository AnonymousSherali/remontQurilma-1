"""Buyurtma ichidagi yozishma: mijoz va usta telefon qilmasdan gaplashadi.

- Faqat ustasi bor, bekor qilinmagan buyurtmada. Tasdiqlangach CHAT_OPEN_DAYS kun ochiq
  turadi (kafolat masalalari uchun), keyin faqat o'qish mumkin.
- Mijoz tomoni SMS kod bilan tasdiqlangan bo'lishi shart (havolaning o'zi yetarli emas).
- Yangi xabar haqida: Telegram ulangan bo'lsa — har bir xabar matni bilan; aks holda SMS,
  lekin CHAT_SMS_INTERVAL_MINUTES da bir martadan ko'p emas (SMS pullik).
- Yozishmani administrator ko'radi (nizoda dalil) — bu sahifada ochiq aytilgan.
"""

from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from .models import OrderEvent, OrderMessage, ServiceRequest as SR

CUSTOMER = OrderEvent.ACTOR_CUSTOMER
MASTER = OrderEvent.ACTOR_MASTER
MAX_LENGTH = 1000
PER_MINUTE = 15


class ChatError(Exception):
    pass


def can_send(order, now=None):
    if order.master_id is None or order.status in (SR.STATUS_NEW, SR.STATUS_CANCELLED):
        return False
    if order.status == SR.STATUS_CONFIRMED:
        confirmed = (order.events.filter(status=SR.STATUS_CONFIRMED).order_by('-created_at')
                     .values_list('created_at', flat=True).first()) or order.updated_at
        return (now or timezone.now()) - confirmed <= timedelta(days=settings.CHAT_OPEN_DAYS)
    return True


def other(actor):
    return MASTER if actor == CUSTOMER else CUSTOMER


def unread_count(order, viewer):
    return order.messages.filter(sender=other(viewer), read_at__isnull=True).count()


def fetch(order, viewer, after=0):
    """Xabarlar ro'yxati; qarshi tomonning xabarlari o'qilgan deb belgilanadi."""
    order.messages.filter(sender=other(viewer), read_at__isnull=True).update(read_at=timezone.now())
    return list(order.messages.filter(pk__gt=after))


def serialize(message, viewer):
    return {
        'id': message.pk,
        'mine': message.sender == viewer,
        'sender': str(message.get_sender_display()),
        'text': message.text,
        'time': timezone.localtime(message.created_at).strftime('%d.%m %H:%M'),
    }


def send(order, actor, text):
    text = (text or '').strip()
    if not text:
        raise ChatError(_('Xabar matnini yozing.'))
    if len(text) > MAX_LENGTH:
        raise ChatError(_('Xabar %(n)s belgidan oshmasligi kerak.') % {'n': MAX_LENGTH})
    if not can_send(order):
        raise ChatError(_('Bu buyurtmada yozishma yopilgan.'))
    key = f'chat-rate:{order.pk}:{actor}'
    cache.add(key, 0, 60)
    try:
        count = cache.incr(key)
    except ValueError:
        count = 1
    if count > PER_MINUTE:
        raise ChatError(_("Juda ko'p xabar. Bir daqiqadan keyin urinib ko'ring."))
    message = OrderMessage.objects.create(order=order, sender=actor, text=text)
    transaction.on_commit(lambda: notify(message))
    return message


def notify(message):
    from . import customer_notify
    order = SR.objects.select_related('master', 'category').get(pk=message.order_id)
    to_customer = message.sender == MASTER
    has_telegram = bool(order.telegram_chat_id if to_customer else order.master and order.master.telegram_chat_id)
    if not has_telegram:
        # SMS pullik — suhbat davomida har bir xabarga yubormaymiz
        key = f'chat-sms:{order.pk}:{"c" if to_customer else "m"}'
        if not cache.add(key, 1, settings.CHAT_SMS_INTERVAL_MINUTES * 60):
            return
    preview = message.text if len(message.text) <= 200 else message.text[:197] + '…'
    if to_customer:
        with translation.override(order.language or 'uz'):
            url = customer_notify._customer_link(order) + '#chat'
            text = (_('Usta yozdi: «%(text)s»\n%(url)s') % {'text': preview, 'url': url} if has_telegram
                    else _("Usta sizga xabar yozdi. O'qish: %(url)s") % {'url': url})
            customer_notify._to_customer(order, text)
    elif order.master:
        with translation.override(settings.LANGUAGE_CODE):
            url = customer_notify._absolute(order.get_master_url()) + '#chat'
            text = (_('#%(id)s — mijoz yozdi: «%(text)s»') % {'id': order.pk, 'text': preview} if has_telegram
                    else _("#%(id)s buyurtma bo'yicha mijoz xabar yozdi. O'qish: %(url)s") % {
                        'id': order.pk, 'url': url})
            customer_notify._to_master(order, text)


def context(order, viewer, can_act=True):
    """Buyurtma sahifasi uchun. viewer — CUSTOMER yoki MASTER."""
    visible = order.master_id is not None and order.status != SR.STATUS_NEW and (
        can_send(order) or order.messages.exists())
    if not visible:
        return {'chat': None}
    return {'chat': {
        'messages': [serialize(m, viewer) for m in fetch(order, viewer)] if can_act else [],
        'can_send': can_act and can_send(order),
        'locked': not can_act,
    }}
