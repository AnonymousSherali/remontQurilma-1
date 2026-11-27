"""«Yordam» vidjeti: sayt tashrifchisi (mijoz yoki usta) operator bilan yozishadi.

- Akkaunt shart emas: suhbat kaliti httponly cookie'da (ts_support). Usta kirgan bo'lsa — suhbat ustaga bog'lanadi.
- Birinchi xabarda ixtiyoriy ism va telefon — operator javobini SMS havola bilan olish uchun.
- Operator admin'da (/admin/yordam/) javob beradi; yangi xabar haqida administrator chatiga Telegram
  (suhbat boshida yoki 10 daqiqa jimlikdan keyin — har xabarga emas).
- Javob tashrifchiga: sayt ochiq bo'lsa — vidjetda; usta bo'lsa — Telegram/bildirishnoma; telefon
  qoldirilgan bo'lsa — SMS havola (/yordam/<kalit>/, suhbatni istalgan qurilmada ochadi).
"""

from datetime import timedelta

from django.utils.html import escape
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from .models import SupportMessage, SupportThread
from .phone import normalize_phone

COOKIE = 'ts_support'
COOKIE_AGE = 60 * 60 * 24 * 60
PER_MINUTE = 10


class SupportError(Exception):
    pass


def thread_for(request):
    token = request.COOKIES.get(COOKIE, '')
    if not token:
        return None
    try:
        return SupportThread.objects.filter(token=token).first()
    except Exception:  # noqa: BLE001 — buzilgan cookie
        return None


def serialize(message, viewer_staff=False):
    mine = message.from_staff == viewer_staff
    return {'id': message.pk, 'mine': mine,
            'sender': str(_('Operator')) if message.from_staff else (message.thread.name or str(_('Mijoz'))),
            'text': message.text, 'time': timezone.localtime(message.created_at).strftime('%d.%m %H:%M')}


def post_visitor(request, thread, text, name='', phone=''):
    text = (text or '').strip()
    if not text:
        raise SupportError(_('Xabar matnini yozing.'))
    if len(text) > 1000:
        raise SupportError(_('Xabar %(n)s belgidan oshmasligi kerak.') % {'n': 1000})
    ip = request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR', '')
    key = f'support-rate:{ip}'
    cache.add(key, 0, 60)
    try:
        if cache.incr(key) > PER_MINUTE:
            raise SupportError(_("Juda ko'p xabar. Bir daqiqadan keyin urinib ko'ring."))
    except ValueError:
        pass
    master = getattr(request.user, 'master', None) if request.user.is_authenticated else None
    if thread is None:
        try:
            phone = normalize_phone(phone) if phone else ''
        except Exception:  # noqa: BLE001
            phone = ''
        thread = SupportThread.objects.create(name=(name or '').strip()[:100], phone=phone, master=master,
                                              page=(request.META.get('HTTP_REFERER') or '')[:200])
    previous = thread.messages.filter(from_staff=False).order_by('-created_at').first()
    message = SupportMessage.objects.create(thread=thread, text=text)
    SupportThread.objects.filter(pk=thread.pk).update(last_message_at=message.created_at, is_closed=False)
    if previous is None or message.created_at - previous.created_at > timedelta(minutes=10):
        _notify_staff(thread, text)
    return thread, message


def reply(thread, user, text):
    text = (text or '').strip()
    if not text:
        raise SupportError('Javob matnini yozing.')
    message = SupportMessage.objects.create(thread=thread, text=text[:1000], from_staff=True, staff=user)
    thread.messages.filter(from_staff=False, read_at__isnull=True).update(read_at=timezone.now())
    SupportThread.objects.filter(pk=thread.pk).update(last_message_at=message.created_at)
    _notify_visitor(thread, text)
    return message


def unanswered():
    """Operator javobini kutayotgan suhbatlar (oxirgi xabar mijozdan)."""
    result = []
    for thread in SupportThread.objects.filter(is_closed=False).prefetch_related('messages')[:200]:
        last = list(thread.messages.all())[-1:] or [None]
        if last[0] is not None and not last[0].from_staff:
            result.append(thread)
    return result


def _absolute(path):
    return settings.SITE_URL.rstrip('/') + path


def _notify_staff(thread, text):
    chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', '')
    if not chat_id:
        return
    from telegram_bot import client
    who = thread.name or (thread.master.full_name if thread.master_id else '') or thread.phone or 'mehmon'
    url = _absolute(reverse('admin_support_thread', args=[thread.pk]))
    client.send_message(chat_id, f'💬 Yordam #{thread.pk} — {escape(who)}:\n{escape(text[:300])}\n{url}')


def _notify_visitor(thread, text):
    link = _absolute(reverse('repair_service:support_thread', args=[thread.token]))
    with translation.override(settings.LANGUAGE_CODE):
        message = _('Operator javob berdi: «%(text)s»\n%(url)s') % {
            'text': text if len(text) <= 200 else text[:197] + '…', 'url': link}
    if thread.master_id:
        from . import webpush
        master = thread.master
        webpush.notify(master.push_subscriptions.all(), settings.SITE_INFO['name'], message, link)
        if master.telegram_chat_id:
            from telegram_bot import client
            client.send_message(master.telegram_chat_id, escape(message))
            return
    if thread.phone:
        from otp.sms import send_sms
        with translation.override(settings.LANGUAGE_CODE):
            sms = _("Operator javob berdi. O'qish: %(url)s") % {'url': link}
        send_sms(thread.phone, sms, background=True)
