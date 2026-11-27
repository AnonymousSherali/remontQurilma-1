"""Payme sandbox (test.paycom.uz «Песочница») uchun tayyorgarlik.

    python manage.py payme_sandbox            # sinov buyurtmasi + to'lanmagan bosqich
    python manage.py payme_sandbox --amount 15000
    python manage.py payme_sandbox --cleanup  # sinov buyurtmalarini o'chirish

Sandbox formasiga kerak bo'ladigan qiymatlarni chiqaradi: endpoint, hisob (milestone_id) va summa
tiyinda. Faqat PAYME_TEST=True bo'lganda ishlaydi — haqiqiy kassada sinov buyurtmasi yaratilmaydi.
"""

from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.urls import reverse

from masters.models import Master
from payments import services
from payments.models import Milestone, Payment
from repair_service import workflow
from repair_service.models import ServiceRequest

SANDBOX_NAME = 'Payme sandbox'
SANDBOX_PHONE = '+998000000000'


class Command(BaseCommand):
    help = "Payme sandbox uchun sinov buyurtmasi va to'lanmagan bosqich"

    def add_arguments(self, parser):
        parser.add_argument('--amount', type=int, default=10000, help="so'mda (standart 10 000)")
        parser.add_argument('--cleanup', action='store_true', help="sinov buyurtmalarini o'chirish")

    def handle(self, *args, **options):
        if not settings.PAYME_TEST:
            raise CommandError('Faqat PAYME_TEST=True (sinov kassasi) bilan ishlaydi.')
        if options['cleanup']:
            return self.cleanup()
        master = Master.objects.filter(is_verified=True).order_by('pk').first()
        if master is None:
            raise CommandError("Tasdiqlangan usta yo'q — avval bitta ustani tasdiqlang.")
        with transaction.atomic():
            order = ServiceRequest.objects.create(name=SANDBOX_NAME, phone=SANDBOX_PHONE, master=master,
                                                  problem_description='Payme sandbox sinovi')
            workflow.apply(order, workflow.MASTER, 'accept', note=SANDBOX_NAME)
            services.propose_quote(order, Decimal(options['amount']), 'on_completion', SANDBOX_NAME)
            services.approve_quote(order)
            milestone = order.milestones.get()
        endpoint = settings.SITE_URL.rstrip('/') + reverse('payme_endpoint')
        self.stdout.write(self.style.SUCCESS('Sandbox uchun qiymatlar:'))
        self.stdout.write(f'  Endpoint:            {endpoint}')
        self.stdout.write(f'  Hisob maydoni:       {settings.PAYME_ACCOUNT_KEY} = {milestone.pk}')
        self.stdout.write(f'  Summa (tiyinda):     {int(milestone.amount_due) * 100}')
        self.stdout.write(f'  Noto\'g\'ri summa:     {int(milestone.amount_due) * 100 + 100}  (-31001 kutiladi)')
        self.stdout.write(f'  Mavjud bo\'lmagan hisob: {Milestone.objects.order_by("-pk").first().pk + 1000}'
                          '  (-31050 kutiladi)')
        self.stdout.write("Har bir to'liq sinovdan keyin yangi bosqich kerak bo'lsa — buyruqni qayta ishga tushiring.")
        self.stdout.write('Tugagach: python manage.py payme_sandbox --cleanup')

    def cleanup(self):
        orders = ServiceRequest.objects.filter(name=SANDBOX_NAME, phone=SANDBOX_PHONE)
        payments = Payment.objects.filter(milestone__order__in=orders)
        count = orders.count()
        with transaction.atomic():
            for payment in payments:
                payment.refunds.all().delete()
            payments.delete()
            for order in orders:
                for milestone in order.milestones.all():
                    milestone.refunds.all().delete()
            orders.delete()
        self.stdout.write(self.style.SUCCESS(f"O'chirildi: {count} ta sinov buyurtmasi."))
