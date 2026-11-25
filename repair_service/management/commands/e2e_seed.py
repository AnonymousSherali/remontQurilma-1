"""Brauzer testi (e2e/run.sh) uchun toza ma'lumot. Faqat DEBUG=True va nomida «e2e» bor bazada ishlaydi."""

import json
from datetime import time

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from masters.models import Category, Master
from repair_service.models import Service

MASTER_PHONE = '+998991234500'
MASTER_PASSWORD = 'E2e-parol-12345'
ADMIN = ('e2e_admin', 'E2e-admin-12345')


class Command(BaseCommand):
    help = "E2E brauzer testi uchun ma'lumot (faqat sinov bazasida)"

    def handle(self, *args, **options):
        name = str(settings.DATABASES['default']['NAME'])
        if not settings.DEBUG or 'e2e' not in name:
            raise CommandError("Faqat DEBUG=True va nomida «e2e» bor sinov bazasida ishlaydi — haqiqiy bazaga tegmaydi.")
        cat, _ = Category.objects.get_or_create(slug='santexnik', defaults={'name': 'Santexnik', 'icon': '🚰'})
        Service.objects.get_or_create(name='Kran almashtirish', defaults={
            'category': cat, 'price_from': 80000, 'price_type': 'fixed', 'is_popular': True})
        user, _ = User.objects.get_or_create(username=MASTER_PHONE.lstrip('+'))
        user.set_password(MASTER_PASSWORD)
        user.save()
        master, _ = Master.objects.get_or_create(phone=MASTER_PHONE, defaults={
            'user': user, 'full_name': 'Sinov Ustasi', 'latitude': 41.2750, 'longitude': 69.2040,
            'is_verified': True, 'id_status': 'approved', 'payout_card': '8600123412341234',
            'payout_holder': 'SINOV USTASI', 'work_from': time(0, 0), 'work_to': time(23, 59)})
        master.categories.add(cat)
        admin, _ = User.objects.get_or_create(username=ADMIN[0], defaults={'is_staff': True, 'is_superuser': True})
        admin.set_password(ADMIN[1])
        admin.save()
        self.stdout.write(json.dumps({'master_phone': MASTER_PHONE, 'master_password': MASTER_PASSWORD,
                                      'admin': ADMIN[0], 'admin_password': ADMIN[1]}))
