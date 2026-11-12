"""Muddati o'tgan bosqichlarni avtomatik bajarish. Cron orqali har soatda ishga tushiring:

    0 * * * *  cd /srv/techservice && venv/bin/python manage.py process_orders

1) Usta "Bajarildi" deganiga AUTO_CONFIRM_HOURS bo'lgan, mijoz javob bermagan buyurtmalar tasdiqlanadi.
2) Bosqichi kelganiga AUTO_RELEASE_HOURS bo'lgan, nizo ochilmagan ushlab turilgan mablag'lar chiqariladi.
3) Usta tuzatgan, mijoz javob bermagan kafolat murojaatlari WARRANTY_AUTO_CLOSE_DAYS kundan keyin yopiladi.
4) Usta kelishiga VISIT_REMINDER_HOURS soat qolganda ikkala tomonga eslatma yuboriladi.
"""

from django.core.management.base import BaseCommand

from payments.services import auto_release
from repair_service.schedule import send_reminders
from repair_service.warranty import auto_close
from repair_service.workflow import auto_confirm


class Command(BaseCommand):
    help = "Avtomatik tasdiqlash va mablag'larni chiqarish"

    def handle(self, *args, **options):
        confirmed = auto_confirm()
        released = auto_release()
        closed = auto_close()
        reminded = send_reminders()
        self.stdout.write(f'Avtomatik tasdiqlandi: {len(confirmed)}; chiqarilgan bosqichlar: {len(released)}; '
                          f'yopilgan kafolat murojaatlari: {len(closed)}; tashrif eslatmalari: {len(reminded)}')
