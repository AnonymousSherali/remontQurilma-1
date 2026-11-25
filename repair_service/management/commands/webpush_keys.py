"""Brauzer bildirishnomalari uchun VAPID kalitlarini yaratadi (bir marta):

    python manage.py webpush_keys

Chiqqan ikki qatorni .env ga qo'shing. Kalitni almashtirsangiz, barcha mavjud obunalar
ishlamay qoladi — foydalanuvchilar qaytadan «Bildirishnomalarni yoqish» ni bosadi.
"""

from django.core.management.base import BaseCommand

from repair_service.webpush import generate_keys


class Command(BaseCommand):
    help = 'Web Push (VAPID) kalitlarini yaratadi'

    def handle(self, *args, **options):
        public, private = generate_keys()
        self.stdout.write(f'WEBPUSH_PUBLIC_KEY={public}')
        self.stdout.write(f'WEBPUSH_PRIVATE_KEY={private}')
        self.stderr.write('Maxfiy kalitni hech kimga bermang va repozitoriyga qo\'shmang.')
