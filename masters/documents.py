"""Ustaning shaxsini tasdiqlash.

Usta kabinetda pasport/ID-karta va hujjat bilan selfi yuklaydi (sertifikat — ixtiyoriy).
Fayllar MEDIA_ROOT dan tashqarida (PRIVATE_MEDIA_ROOT) saqlanadi, EXIF (GPS) o'chiriladi,
ochiq havolasi yo'q — faqat «Usta hujjatlarini ko'rish» huquqi bor administrator ko'radi.

Holat: yuklanmagan → tekshirilmoqda → tasdiqlangan / rad etilgan (qayta yuklash mumkin).
Tasdiqlanganda profil ham faollashadi (is_verified) va saytda «Hujjatlari tekshirilgan» belgisi chiqadi.
ID_DOCUMENTS_KEEP_DAYS > 0 bo'lsa, tasdiqlangandan shuncha kun o'tgach fayllar o'chiriladi
(holat saqlanadi) — keraksiz shaxsiy ma'lumotni saqlamaslik uchun.
"""

import logging
from datetime import timedelta

from django.utils.html import escape
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from repair_service.photos import process_upload

from .models import Master, MasterDocument

logger = logging.getLogger(__name__)

REQUIRED = (MasterDocument.KIND_ID, MasterDocument.KIND_SELFIE)
OPTIONAL = (MasterDocument.KIND_CERTIFICATE,)


class DocumentError(Exception):
    pass


def can_upload(master):
    return master.id_status in (Master.ID_NONE, Master.ID_REJECTED)


def submit(master, files):
    """files: {kind: UploadedFile}. Majburiy hujjatlarsiz yoki noto'g'ri faylda DocumentError."""
    if not can_upload(master):
        raise DocumentError(_("Hujjatlar allaqachon yuborilgan."))
    missing = [k for k in REQUIRED if not files.get(k)]
    if missing:
        labels = dict(MasterDocument.KIND_CHOICES)
        raise DocumentError(_('Yuklang: %(list)s') % {'list': ', '.join(str(labels[k]) for k in missing)})
    processed = {}
    for kind in REQUIRED + OPTIONAL:
        upload = files.get(kind)
        if not upload:
            continue
        try:
            processed[kind], _thumb = process_upload(upload)
        except ValidationError as error:
            raise DocumentError(f'{dict(MasterDocument.KIND_CHOICES)[kind]}: {error.messages[0]}')
    with transaction.atomic():
        master = Master.objects.select_for_update().get(pk=master.pk)
        if not can_upload(master):
            raise DocumentError(_("Hujjatlar allaqachon yuborilgan."))
        for old in master.documents.all():
            old.delete()   # rad etilgan eski fayllar (signal faylni ham o'chiradi)
        for kind, content in processed.items():
            doc = MasterDocument(master=master, kind=kind)
            doc.file.save('doc.jpg', content, save=False)
            doc.save()
        master.id_status, master.id_note, master.id_checked_at = Master.ID_PENDING, '', None
        master.save(update_fields=['id_status', 'id_note', 'id_checked_at', 'updated_at'])
    transaction.on_commit(lambda: _notify_admin(master))
    return master


def approve(master):
    master.id_status, master.id_note, master.id_checked_at = Master.ID_APPROVED, '', timezone.now()
    master.is_verified = True
    master.save(update_fields=['id_status', 'id_note', 'id_checked_at', 'is_verified', 'updated_at'])
    with translation.override(settings.LANGUAGE_CODE):
        _notify_master(master, _("Hujjatlaringiz tasdiqlandi — profilingiz saytda ko'rinadi. Kabinet: %(url)s"))


def reject(master, reason):
    reason = (reason or '').strip()
    if not reason:
        raise DocumentError("Rad etish sababini yozing — usta uni ko'radi.")
    master.id_status, master.id_note, master.id_checked_at = Master.ID_REJECTED, reason[:255], timezone.now()
    master.save(update_fields=['id_status', 'id_note', 'id_checked_at', 'updated_at'])
    with translation.override(settings.LANGUAGE_CODE):
        _notify_master(master, _("Hujjatlaringiz qabul qilinmadi: %(reason)s. Qayta yuklang: %(url)s"),
                       reason=reason)


def _absolute(path):
    return settings.SITE_URL.rstrip('/') + path


def _notify_master(master, template, **extra):
    text = template % {'url': _absolute(reverse('masters:documents')), **extra}
    from repair_service import webpush
    webpush.notify(master.push_subscriptions.all(), settings.SITE_INFO['name'], text, reverse('masters:documents'))
    if master.telegram_chat_id:
        from telegram_bot import client
        client.send_message(master.telegram_chat_id, text)
    else:
        from otp.sms import send_sms
        send_sms(master.phone, text, background=True)


def _notify_admin(master):
    chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', '')
    if not chat_id:
        return
    from telegram_bot import client
    url = _absolute(reverse('admin:masters_master_change', args=[master.pk]))
    client.send_message(chat_id, f'🪪 Usta hujjat yukladi: {escape(master.full_name)}\n{url}')


def purge_old(now=None):
    """Tasdiqlanganiga ID_DOCUMENTS_KEEP_DAYS bo'lgan ustalarning hujjat fayllarini o'chiradi."""
    days = getattr(settings, 'ID_DOCUMENTS_KEEP_DAYS', 0)
    if not days:
        return 0
    cutoff = (now or timezone.now()) - timedelta(days=days)
    docs = MasterDocument.objects.filter(master__id_status=Master.ID_APPROVED, master__id_checked_at__lte=cutoff)
    count = 0
    for doc in docs:
        doc.delete()
        count += 1
    return count
