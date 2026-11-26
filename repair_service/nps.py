"""NPS so'rovnomasi: «Bizni do'stingizga tavsiya qilasizmi?» (0–10) + ixtiyoriy izoh.

- Qayerda: tasdiqlangan buyurtma sahifasida va bahodan keyingi sahifada.
- Eslatma: tasdiqlangandan NPS_INVITE_HOURS soat o'tgach, faqat bepul kanallar orqali (Telegram yoki
  brauzer bildirishnomasi) — SMS yuborilmaydi; bir marta.
- 0–6 baho (norozi) — administrator chatiga Telegram: tezda qo'ng'iroq qilib, muammoni hal qilish uchun.
- Statistika: NPS = (9–10 bergan foiz) − (0–6 bergan foiz), −100 … +100.
"""

from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from .models import NpsResponse, PushSubscription, ServiceRequest as SR


class NpsError(Exception):
    pass


def can_answer(order):
    return order.status == SR.STATUS_CONFIRMED and not NpsResponse.objects.filter(order=order).exists()


def submit(order, score, comment=''):
    try:
        score = int(score)
    except (TypeError, ValueError):
        raise NpsError(_("0 dan 10 gacha baho tanlang."))
    if not 0 <= score <= 10:
        raise NpsError(_("0 dan 10 gacha baho tanlang."))
    if order.status != SR.STATUS_CONFIRMED:
        raise NpsError(_("So'rovnoma buyurtma tasdiqlangandan keyin."))
    try:
        with transaction.atomic():
            response = NpsResponse.objects.create(order=order, score=score, comment=(comment or '').strip()[:1000])
    except IntegrityError:
        raise NpsError(_('Javobingiz allaqachon qabul qilingan. Rahmat!'))
    if response.group == 'detractor':
        transaction.on_commit(lambda: _alert_admin(response))
    return response


def _alert_admin(response):
    chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', '')
    if not chat_id:
        return
    from telegram_bot import client
    order = response.order
    url = settings.SITE_URL.rstrip('/') + reverse('admin:repair_service_servicerequest_change', args=[order.pk])
    client.send_message(chat_id, f'😟 Norozi mijoz (NPS {response.score}/10): #{order.pk}, {order.phone}\n'
                                 f'{response.comment[:300] or "(izohsiz)"}\n{url}')


def send_invites(now=None):
    """Tasdiqlanganiga NPS_INVITE_HOURS bo'lgan, javob bermagan mijozlarga bir martalik eslatma (bepul kanal)."""
    from . import customer_notify, webpush
    now = now or timezone.now()
    hours = getattr(settings, 'NPS_INVITE_HOURS', 24)
    sent = 0
    orders = (SR.objects.filter(status=SR.STATUS_CONFIRMED, nps_invited_at__isnull=True, nps__isnull=True,
                                updated_at__lte=now - timedelta(hours=hours),
                                updated_at__gte=now - timedelta(days=14))
              .order_by('pk')[:200])
    for order in orders:
        if not SR.objects.filter(pk=order.pk, nps_invited_at__isnull=True).update(nps_invited_at=now):
            continue
        with translation.override(order.language or 'uz'):
            text = _("Ishdan mamnunmisiz? Bizni do'stingizga tavsiya qilasizmi — 0 dan 10 gacha baholang: %(url)s") % {
                'url': customer_notify._customer_link(order) + '#nps'}
        subs = list(PushSubscription.objects.filter(phone=order.phone))
        if order.telegram_chat_id:
            from telegram_bot import client
            client.send_message(order.telegram_chat_id, text)
        elif subs:
            webpush.notify(subs, settings.SITE_INFO['name'], text, order.get_customer_url() + '#nps')
        else:
            continue   # SMS pullik — so'rovnoma sahifada ko'rinadi, alohida xabar yo'q
        sent += 1
    return sent


def summary(start):
    responses = list(NpsResponse.objects.filter(created_at__gte=start).select_related('order'))
    n = len(responses)
    if not n:
        return {'count': 0, 'score': None, 'distribution': [0] * 11, 'detractors': [], 'comments': []}
    promoters = sum(1 for r in responses if r.group == 'promoter')
    detractors = sum(1 for r in responses if r.group == 'detractor')
    distribution = [sum(1 for r in responses if r.score == i) for i in range(11)]
    return {
        'count': n, 'score': round((promoters - detractors) * 100 / n),
        'promoters': round(promoters * 100 / n), 'detractors_pct': round(detractors * 100 / n),
        'distribution': distribution, 'peak': max(distribution) or 1,
        'detractors': [r for r in responses if r.group == 'detractor' and not r.followed_up][:10],
        'comments': [r for r in responses if r.comment][:10],
    }
