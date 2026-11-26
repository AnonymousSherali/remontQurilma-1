"""Yangi ustalarni jalb qilish va ishga tayyorlash.

- Birinchi marta tasdiqlanganda — NEW_MASTER_FREE_TOP_DAYS kun bepul TOP (bir marta).
- Kabinetda «Ishni boshlashga tayyorlik» ro'yxati: rasm, o'zi haqida, hujjatlar, karta, xabarnoma kanali,
  ish vaqti, boshlang'ich kurs.
"""

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _


def grant_welcome_bonus(master):
    """Usta tasdiqlangach chaqiriladi; takroriy chaqiruv xavfsiz."""
    from payments.models import Purchase
    from payments.tariffs import KIND_TOP, activate

    from .models import Master
    days = getattr(settings, 'NEW_MASTER_FREE_TOP_DAYS', 0)
    if not days or not master.is_verified:
        return None
    if not Master.objects.filter(pk=master.pk, welcome_bonus_given=False).update(welcome_bonus_given=True):
        return None
    purchase = Purchase.objects.create(master=master, plan='welcome', kind=KIND_TOP, days=days, amount=0)
    activate(purchase)
    with translation.override(settings.LANGUAGE_CODE):
        text = _("Tabriklaymiz, profilingiz tasdiqlandi! Sizga %(days)s kun bepul TOP — qidiruvda birinchi "
                 "qatorlardasiz. Kabinet: %(url)s") % {
            'days': days, 'url': settings.SITE_URL.rstrip('/') + reverse('masters:dashboard')}

    def notify():
        if master.telegram_chat_id:
            from telegram_bot import client
            client.send_message(master.telegram_chat_id, text)
        else:
            from otp.sms import send_sms
            send_sms(master.phone, text, background=True)
    transaction.on_commit(notify)
    return purchase


def checklist(master):
    """[(bajarildimi, matn, havola)] va bajarilganlar soni."""
    from . import learning
    items = [
        (bool(master.photo), _("Profil rasmi"), reverse('masters:profile_edit')),
        (len(master.bio or '') >= 40, _("O'zingiz haqingizda (tajriba, ixtisos)"), reverse('masters:profile_edit')),
        (master.id_status == 'approved', _("Hujjatlar tasdiqlangan"), reverse('masters:documents')),
        (bool(master.payout_card), _("Pul olish uchun karta"), reverse('masters:profile_edit') + '#karta'),
        (bool(master.telegram_chat_id) or master.push_subscriptions.exists(),
         _("Telegram yoki bildirishnomalar — buyurtmani darhol bilish uchun"), reverse('masters:dashboard') + '#telegram'),
        (bool(master.work_days or master.work_from), _("Ish vaqti"), reverse('masters:work_schedule')),
        (learning.progress(master)['complete'], _("Boshlang'ich kurs"), reverse('masters:lessons')),
    ]
    done = sum(1 for ok, *_rest in items if ok)
    return {'items': items, 'done': done, 'total': len(items), 'complete': done == len(items),
            'percent': round(done * 100 / len(items))}
