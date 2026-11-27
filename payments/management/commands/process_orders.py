"""Muddati o'tgan bosqichlarni avtomatik bajarish. Cron orqali har soatda ishga tushiring:

    5 * * * *  cd /srv/techservice/app && /srv/techservice/venv/bin/python manage.py process_orders  (deploy/cron.txt)

1) Usta "Bajarildi" deganiga AUTO_CONFIRM_HOURS bo'lgan, mijoz javob bermagan buyurtmalar tasdiqlanadi.
2) Bosqichi kelganiga AUTO_RELEASE_HOURS bo'lgan, nizo ochilmagan ushlab turilgan mablag'lar chiqariladi.
3) Usta tuzatgan, mijoz javob bermagan kafolat murojaatlari WARRANTY_AUTO_CLOSE_DAYS kundan keyin yopiladi.
4) Usta kelishiga VISIT_REMINDER_HOURS soat qolganda ikkala tomonga eslatma yuboriladi.
5) ID_DOCUMENTS_KEEP_DAYS > 0 bo'lsa, eski tasdiqlangan hujjat fayllari o'chiriladi.
6) Ustalarning ishonchlilik bali qayta hisoblanadi.
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from masters.documents import purge_old
from masters.reliability import update_all
from payments.services import auto_release
from repair_service.schedule import send_reminders
from repair_service.warranty import auto_close
from repair_service.workflow import auto_confirm


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Avtomatik tasdiqlash va mablag'larni chiqarish"

    def handle(self, *args, **options):
        from payments.payouts import prepare_weekly
        from repair_service.analytics import purge
        from repair_service.marketing import process as send_campaigns
        from repair_service.nps import send_invites

        failed = []

        def step(name, func, empty):
            # Bitta qadamdagi xato qolganlarini to'xtatmasin (har soat takrorlanadi)
            try:
                return func()
            except Exception:  # noqa: BLE001
                logger.exception('process_orders: %s xatosi', name)
                failed.append(name)
                return empty

        confirmed = step('auto_confirm', auto_confirm, [])
        released = step('auto_release', auto_release, [])
        closed = step('auto_close', auto_close, [])
        reminded = step('send_reminders', send_reminders, [])
        purged = step('purge_documents', purge_old, 0)
        rated = step('reliability', update_all, 0)
        step('analytics_purge', purge, None)
        campaign_messages = step('campaigns', send_campaigns, 0)
        step('payouts', prepare_weekly, [])
        step('nps', send_invites, [])
        self.stdout.write(f'Avtomatik tasdiqlandi: {len(confirmed)}; chiqarilgan bosqichlar: {len(released)}; '
                          f'yopilgan kafolat murojaatlari: {len(closed)}; tashrif eslatmalari: {len(reminded)}; '
                          f"o'chirilgan hujjat fayllari: {purged}; ishonchlilik yangilandi: {rated}; "
                          f"kampaniya xabarlari: {campaign_messages}")
        if failed:
            _alert_staff(failed)
            raise CommandError('Xato bilan tugagan qadamlar: ' + ', '.join(failed))


def _alert_staff(failed):
    """Administratorlar Telegram chatiga — bir xil xato haqida soatiga bir martadan ko'p emas."""
    from django.conf import settings
    from django.core.cache import cache
    chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', '')
    key = 'process_orders:alert:' + ','.join(failed)
    if not chat_id or not cache.add(key, 1, 6 * 60 * 60):
        return
    from telegram_bot import client
    client.send_message(chat_id, '🚨 Soatlik cron (process_orders) xato bilan tugadi: ' + ', '.join(failed)
                        + '\nLog: /srv/techservice/logs/cron.log (Docker: docker compose logs cron)', background=False)
