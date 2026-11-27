from datetime import timedelta

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from payments import services as payments
from repair_service import workflow
from repair_service.models import OrderEvent, ServiceRequest
from repair_service.tests import make_master

from . import feed, reliability
from .models import Category
from .services import search_masters


def order_for(master, **extra):
    return ServiceRequest.objects.create(name='Malika', phone='+998901112233', master=master, **extra)


def accept(master):
    order = order_for(master)
    workflow.apply(order, workflow.MASTER, 'accept')
    return order


class ReliabilityTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        self.master = make_master('Usta', '+998911111111')

    def test_yangi_usta_jazolanmaydi(self):
        accept(self.master)
        score, data = reliability.compute(self.master)
        self.assertIsNone(score)
        self.assertEqual(data['accepted'], 1)
        self.assertEqual(self.master.reliability_factor, 1.0)

    def test_toza_usta_100(self):
        for _i in range(4):
            accept(self.master)
        self.assertEqual(reliability.compute(self.master)[0], 100)

    def test_voz_kechish(self):
        for _i in range(3):
            accept(self.master)
        workflow.apply(accept(self.master), workflow.MASTER, 'cancel')     # 4 qabuldan 1 tasidan voz kechdi
        score, data = reliability.compute(self.master)
        self.assertEqual((data['accepted'], data['declined']), (4, 1))
        self.assertEqual(score, round(100 - 35 * 1 / 5))
        # Voz kechish yozuvi shu ustaga tegishli (buyurtma ustasi o'zgargan bo'lsa ham)
        self.assertEqual(OrderEvent.objects.filter(status='new', actor='master').get().master, self.master)

    def test_kechikish_va_kelmaslik(self):
        now = timezone.now()
        on_time = accept(self.master)
        late = accept(self.master)
        no_show = accept(self.master)
        for order, minutes in ((on_time, 5), (late, 90)):
            ServiceRequest.objects.filter(pk=order.pk).update(visit_at=now - timedelta(hours=3))
            order.refresh_from_db()
            workflow.apply(order, workflow.MASTER, 'arrive')
            OrderEvent.objects.filter(order=order, status='arrived').update(
                created_at=order.visit_at + timedelta(minutes=minutes))
        ServiceRequest.objects.filter(pk=no_show.pk).update(visit_at=now - timedelta(hours=3))
        score, data = reliability.compute(self.master)
        self.assertEqual((data['scheduled'], data['late'], data['on_time_rate']), (3, 2, 33))
        self.assertEqual(score, round(100 - 20 * 2 / 3))

    def test_nizo_va_javob_tezligi(self):
        orders = [accept(self.master) for _i in range(4)]
        for order in orders:
            OrderEvent.objects.filter(order=order, status='accepted').update(
                created_at=order.created_at + timedelta(minutes=120))
        order = orders[0]
        payments.propose_quote(order, 100000, 'cash')
        payments.approve_quote(order)
        workflow.apply(order, workflow.MASTER, 'arrive')
        workflow.apply(order, workflow.CUSTOMER, 'dispute', note='Sifatsiz ish qilindi')
        score, data = reliability.compute(self.master)
        self.assertEqual((data['disputes'], data['response_minutes']), (1, 120))
        self.assertEqual(score, round(100 - 35 * 1 / 4 - 10 * 120 / 240))

    def test_lentadan_olish_tezlikka_kirmaydi(self):
        cat = Category.objects.create(name='Santexnik', slug='santexnik')
        self.master.categories.add(cat)
        order = ServiceRequest.objects.create(name='A', phone='+998901112233', category=cat)
        ServiceRequest.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(hours=5))
        feed.claim(self.master, order.pk)
        self.assertIsNone(reliability.compute(self.master)[1]['response_minutes'])

    @override_settings(RELIABILITY_WINDOW_DAYS=30)
    def test_eski_hodisalar_hisobga_olinmaydi(self):
        order = accept(self.master)
        workflow.apply(order, workflow.MASTER, 'cancel')
        OrderEvent.objects.filter(master=self.master).update(created_at=timezone.now() - timedelta(days=31))
        self.assertEqual(reliability.compute(self.master)[1]['declined'], 0)

    def test_qidiruvda_pastga_tushadi(self):
        good = make_master('Yaxshi', '+998922222222', 41.30, 69.25)
        bad = make_master('Ishonchsiz', '+998933333333', 41.30, 69.25)
        good.reliability, bad.reliability = 100, 20
        good.save(); bad.save()
        names = [m.full_name for m in search_masters(lat=41.30, lng=69.25) if m.pk in (good.pk, bad.pk)]
        self.assertEqual(names, ['Yaxshi', 'Ishonchsiz'])
        bad.latitude = 41.299   # biroz yaqinroq bo'lsa ham
        bad.save()
        names = [m.full_name for m in search_masters(lat=41.30, lng=69.25) if m.pk in (good.pk, bad.pk)]
        self.assertEqual(names[0], 'Yaxshi')

    def test_cron_va_sahifalar(self):
        for _i in range(3):
            accept(self.master)
        call_command('process_orders', verbosity=0)
        self.master.refresh_from_db()
        self.assertEqual(self.master.reliability, 100)
        self.client.force_login(self.master.user)
        self.assertContains(self.client.get(reverse('masters:dashboard')), 'Ishonchlilik')

    def test_ommaviy_profil_belgilari(self):
        self.master.reliability_data = {'response_minutes': 12, 'on_time_rate': 96, 'scheduled': 5}
        self.master.save()
        page = self.client.get(self.master.get_absolute_url())
        self.assertContains(page, '~12 daqiqada javob beradi')
        self.assertContains(page, 'vaqtida keladi: 96%')
