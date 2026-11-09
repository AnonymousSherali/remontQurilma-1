"""Muddati o'tgan bosqichlarni avtomatik bajarish. Cron orqali har soatda ishga tushiring:

    0 * * * *  cd /srv/techservice && venv/bin/python manage.py process_orders

1) Usta "Bajarildi" deganiga AUTO_CONFIRM_HOURS bo'lgan, mijoz javob bermagan buyurtmalar tasdiqlanadi.
2) Bosqichi kelganiga AUTO_RELEASE_HOURS bo'lgan, nizo ochilmagan ushlab turilgan mablag'lar chiqariladi.
"""

from django.core.management.base import BaseCommand

from payments.services import auto_release
from repair_service.workflow import auto_confirm


class Command(BaseCommand):
    help = "Avtomatik tasdiqlash va mablag'larni chiqarish"

    def handle(self, *args, **options):
        confirmed = auto_confirm()
        released = auto_release()
        self.stdout.write(f'Avtomatik tasdiqlandi: {len(confirmed)}; chiqarilgan bosqichlar: {len(released)}')
