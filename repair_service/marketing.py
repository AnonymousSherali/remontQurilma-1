"""Marketing xabarnomalari — faqat aniq rozilik bergan mijozlarga.

- Rozilik alohida, ixtiyoriy belgi (ariza formasida yoki buyurtma sahifasida); oldindan belgilanmagan.
- Har bir xabarda obunani bekor qilish havolasi; bekor qilgan mijozga boshqa yuborilmaydi.
- Kanal eng arzonidan tanlanadi: brauzer bildirishnomasi → Telegram → SMS (yoqilgan bo'lsa).
  Har bir mijozga kampaniya bo'yicha bitta xabar.
- Faqat CAMPAIGN_HOURS oralig'ida (standart 09–21) va partiyalab (CAMPAIGN_BATCH) — cron har soatda.
- Ustalarga — xizmat xabari (yangi imkoniyatlar, qoidalar), rozilik talab qilinmaydi, obunadan chiqish yo'q.

SMS orqali reklama: Eskiz reklama matnlarini alohida tasdiqlaydi — avval kabinetda shablon qo'ying.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from .models import Campaign, CampaignDelivery, MarketingConsent, PushSubscription, ServiceRequest as SR

logger = logging.getLogger(__name__)


# ---------- Rozilik ----------

def subscribe(phone, language='uz', source=''):
    consent, created = MarketingConsent.objects.get_or_create(
        phone=phone, defaults={'language': language or 'uz', 'source': source})
    if not created and consent.unsubscribed_at:
        consent.unsubscribed_at = None
        consent.consented_at = timezone.now()
        consent.source = source
        consent.save(update_fields=['unsubscribed_at', 'consented_at', 'source'])
    return consent


def unsubscribe(phone=None, token=None):
    qs = MarketingConsent.objects.filter(unsubscribed_at__isnull=True)
    qs = qs.filter(token=token) if token else qs.filter(phone=phone)
    return qs.update(unsubscribed_at=timezone.now())


def is_subscribed(phone):
    return MarketingConsent.objects.filter(phone=phone, unsubscribed_at__isnull=True).exists()


# ---------- Auditoriya ----------

def audience(campaign, now=None):
    """Qabul qiluvchilar: [(kalit, MarketingConsent yoki Master)]."""
    from masters.models import Master
    if campaign.audience == Campaign.AUDIENCE_MASTERS:
        return [(f'm{m.pk}', m) for m in Master.objects.public().order_by('pk')]
    consents = MarketingConsent.objects.filter(unsubscribed_at__isnull=True)
    if campaign.audience == Campaign.AUDIENCE_INACTIVE:
        cutoff = (now or timezone.now()) - timedelta(days=campaign.inactive_days)
        recent = SR.objects.filter(created_at__gte=cutoff).values('phone')
        consents = consents.exclude(phone__in=recent)
    elif campaign.audience == Campaign.AUDIENCE_CATEGORY and campaign.category_id:
        consents = consents.filter(phone__in=SR.objects.filter(category_id=campaign.category_id).values('phone'))
    return [(c.phone, c) for c in consents.order_by('pk')]


def audience_size(campaign):
    return len(audience(campaign))


# ---------- Yuborish ----------

def _absolute(path):
    if not path:
        return ''
    return path if path.startswith('http') else settings.SITE_URL.rstrip('/') + path


def compose(campaign, language, unsubscribe_url=''):
    text = campaign.text_ru if language == 'ru' and campaign.text_ru else campaign.text_uz
    parts = [text.strip()]
    with translation.override(language):
        if campaign.promo_id:
            parts.append(_('Promo-kod: %(code)s') % {'code': campaign.promo.code})
        if campaign.link:
            parts.append(_absolute(campaign.link))
        if unsubscribe_url:
            parts.append(_('Obunani bekor qilish: %(url)s') % {'url': unsubscribe_url})
    return '\n'.join(parts)


def _deliver_customer(campaign, consent):
    from . import webpush
    unsub = _absolute(reverse('repair_service:unsubscribe', args=[consent.token]))
    text = compose(campaign, consent.language, unsub)
    url = _absolute(campaign.link) or settings.SITE_URL
    if campaign.use_push:
        subs = list(PushSubscription.objects.filter(phone=consent.phone))
        if subs and webpush.enabled():
            if any(webpush.send(sub, settings.SITE_INFO['name'], text, url) for sub in subs):
                return 'push', True
    if campaign.use_telegram:
        chat_id = (SR.objects.filter(phone=consent.phone, telegram_chat_id__isnull=False)
                   .order_by('-created_at').values_list('telegram_chat_id', flat=True).first())
        if chat_id:
            from telegram_bot import client
            client.send_message(chat_id, text, background=False)
            return 'telegram', True
    if campaign.use_sms:
        from otp.sms import send_sms
        try:
            send_sms(consent.phone, text)
            return 'sms', True
        except Exception:  # noqa: BLE001
            logger.exception('Kampaniya SMS yuborilmadi')
            return 'sms', False
    return '', False


def _deliver_master(campaign, master):
    from . import webpush
    text = compose(campaign, settings.LANGUAGE_CODE)
    url = _absolute(campaign.link) or _absolute(reverse('masters:dashboard'))
    if campaign.use_push and webpush.enabled():
        subs = list(master.push_subscriptions.all())
        if subs and any(webpush.send(sub, settings.SITE_INFO['name'], text, url) for sub in subs):
            return 'push', True
    if campaign.use_telegram and master.telegram_chat_id:
        from telegram_bot import client
        client.send_message(master.telegram_chat_id, text, background=False)
        return 'telegram', True
    if campaign.use_sms:
        from otp.sms import send_sms
        try:
            send_sms(master.phone, text)
            return 'sms', True
        except Exception:  # noqa: BLE001
            logger.exception('Kampaniya SMS yuborilmadi')
            return 'sms', False
    return '', False


def in_quiet_hours(now=None):
    start, end = settings.CAMPAIGN_HOURS
    hour = timezone.localtime(now or timezone.now()).hour
    return not (start <= hour < end)


def process(now=None):
    """Navbatdagi kampaniyalardan bitta partiya yuboradi. Qaytaradi: yuborilgan xabarlar soni."""
    now = now or timezone.now()
    if in_quiet_hours(now):
        return 0
    budget = settings.CAMPAIGN_BATCH
    total = 0
    campaigns = Campaign.objects.filter(status__in=(Campaign.STATUS_SCHEDULED, Campaign.STATUS_SENDING),
                                        scheduled_at__lte=now).order_by('scheduled_at')
    for campaign in campaigns:
        if budget <= 0:
            break
        Campaign.objects.filter(pk=campaign.pk, status=Campaign.STATUS_SCHEDULED).update(status=Campaign.STATUS_SENDING)
        done_keys = set(campaign.deliveries.values_list('recipient', flat=True))
        pending = [(key, obj) for key, obj in audience(campaign, now) if key not in done_keys]
        batch = pending[:budget]
        for key, obj in batch:
            try:
                with transaction.atomic():
                    delivery = CampaignDelivery.objects.create(campaign=campaign, recipient=key)
            except IntegrityError:
                continue   # parallel ishga tushgan cron allaqachon yubordi
            if campaign.audience == Campaign.AUDIENCE_MASTERS:
                channel, ok = _deliver_master(campaign, obj)
            else:
                channel, ok = _deliver_customer(campaign, obj)
            delivery.channel, delivery.ok = channel, ok
            delivery.save(update_fields=['channel', 'ok'])
            field = 'sent' if ok else ('failed' if channel else 'skipped')
            Campaign.objects.filter(pk=campaign.pk).update(**{field: F(field) + 1})
            total += 1
        budget -= len(batch)
        if len(batch) == len(pending):   # hamma qabul qiluvchiga yetdi
            Campaign.objects.filter(pk=campaign.pk).update(status=Campaign.STATUS_DONE, finished_at=now)
    return total
