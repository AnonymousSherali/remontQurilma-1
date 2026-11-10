import base64
import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from masters.services import search_masters
from repair_service.tests import make_master

from . import services, tariffs
from .models import Milestone, Payment, Purchase
from .payables import wrap
from .tests import advance, make_order

UZUM = dict(UZUM_SERVICE_ID='777', UZUM_LOGIN='uzum', UZUM_PASSWORD='pw', UZUM_ACCOUNT_KEY='account')


@override_settings(**UZUM)
class UzumTests(TestCase):
    def setUp(self):
        order = make_order()
        advance(order, 'accept')
        services.propose_quote(order, 150000, 'on_completion')
        services.approve_quote(order)
        self.m = order.milestones.get()
        self.auth = 'Basic ' + base64.b64encode(b'uzum:pw').decode()

    def call(self, operation, body=None, auth=None, **extra):
        payload = {'serviceId': 777, 'timestamp': 1, **(body or {}), **extra}
        return self.client.post(reverse('uzum_endpoint', args=[operation]), json.dumps(payload),
                                content_type='application/json', HTTP_AUTHORIZATION=auth or self.auth)

    def account(self, key=None):
        return {'params': {'account': key or str(self.m.pk)}}

    def test_avtorizatsiya_va_service_id(self):
        bad = 'Basic ' + base64.b64encode(b'uzum:no').decode()
        r = self.call('check', self.account(), auth=bad)
        self.assertEqual((r.status_code, r.json()['errorCode']), (401, '10001'))
        r = self.call('check', self.account(), serviceId=1)
        self.assertEqual(r.json()['errorCode'], '10006')
        self.assertEqual(self.call('hack', self.account()).json()['errorCode'], '10003')

    def test_toliq_oqim(self):
        self.assertEqual(self.call('check', self.account()).json()['status'], 'OK')
        r = self.call('create', self.account(), transId='t-1', amount=15000000).json()
        self.assertEqual(r['status'], 'CREATED')
        self.assertEqual(self.call('create', self.account(), transId='t-1', amount=15000000).json()['errorCode'], '10010')
        r = self.call('confirm', transId='t-1').json()
        self.assertEqual(r['status'], 'CONFIRMED')
        self.m.refresh_from_db()
        self.assertEqual(self.m.state, 'held')
        # Takroriy confirm — xuddi shu javob, ikki marta hisoblanmaydi
        self.assertEqual(self.call('confirm', transId='t-1').json()['status'], 'CONFIRMED')
        self.assertEqual(self.call('status', transId='t-1').json()['status'], 'CONFIRMED')
        self.assertEqual(self.call('check', self.account()).json()['errorCode'], '10008')
        r = self.call('reverse', transId='t-1').json()
        self.assertEqual(r['status'], 'REVERSED')
        self.m.refresh_from_db()
        self.assertEqual(self.m.state, 'refunded')

    def test_xatolar(self):
        self.assertEqual(self.call('check', self.account('999999')).json()['errorCode'], '10007')
        self.assertEqual(self.call('create', self.account(), transId='t', amount=5).json()['errorCode'], '10011')
        self.assertEqual(self.call('confirm', transId='yoq').json()['errorCode'], '10014')
        self.assertEqual(self.call('create', self.account(), amount=15000000).json()['errorCode'], '10005')
        self.assertFalse(Payment.objects.exists())

    def test_chiqarilgan_tolovni_qaytarib_bolmaydi(self):
        self.call('create', self.account(), transId='t-1', amount=15000000)
        self.call('confirm', transId='t-1')
        Milestone.objects.filter(pk=self.m.pk).update(state='released')
        self.assertEqual(self.call('reverse', transId='t-1').json()['errorCode'], '10017')

    def test_bekor_qilingan_tranzaksiyani_tasdiqlab_bolmaydi(self):
        self.call('create', self.account(), transId='t-1', amount=15000000)
        self.call('reverse', transId='t-1')
        self.assertEqual(self.call('confirm', transId='t-1').json()['errorCode'], '10009')
        self.m.refresh_from_db()
        self.assertEqual(self.m.state, 'pending')

    def test_checkout_url(self):
        from .uzum import checkout_url
        q = parse_qs(urlparse(checkout_url(wrap(self.m), 'https://s.uz/')).query)
        self.assertEqual((q['serviceId'], q['account'], q['amount']), (['777'], [str(self.m.pk)], ['15000000']))


class TariffTests(TestCase):
    def setUp(self):
        self.master = make_master()
        self.client.force_login(self.master.user)

    def test_sahifa_va_demo_xarid(self):
        page = self.client.get(reverse('payments:tariffs'))
        self.assertContains(page, 'PRO')
        with override_settings(DEBUG=True, PAYMENT_PROVIDERS='demo'):
            response = self.client.post(reverse('payments:tariff_buy', args=['top_7']))
            purchase = Purchase.objects.get()
            self.assertRedirects(response, reverse('payments:demo_purchase', args=[purchase.pk]))
            self.client.post(reverse('payments:demo_purchase', args=[purchase.pk]))
        self.master.refresh_from_db()
        self.assertTrue(self.master.is_promoted)
        self.assertFalse(self.master.is_pro)

    def test_muddat_uzayadi_va_idempotent(self):
        p1 = tariffs.create_purchase(self.master, 'top_7')
        tariffs.activate(p1)
        tariffs.activate(p1)  # takroriy xabar muddatni ikki marta uzaytirmaydi
        self.master.refresh_from_db()
        first = self.master.promoted_until
        self.assertAlmostEqual((first - timezone.now()).days, 6, delta=1)
        tariffs.activate(tariffs.create_purchase(self.master, 'top_30'))
        self.master.refresh_from_db()
        self.assertEqual(self.master.promoted_until, first + timedelta(days=30))

    def test_boshqa_ustaning_xaridi_va_notogri_tarif(self):
        other = make_master('B', '+998933333333')
        purchase = tariffs.create_purchase(other, 'pro_30')
        with override_settings(DEBUG=True, PAYMENT_PROVIDERS='demo'):
            self.assertEqual(self.client.post(reverse('payments:demo_purchase', args=[purchase.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('payments:tariff_buy', args=['free'])).status_code, 404)

    def test_pro_komissiya(self):
        from repair_service.models import ServiceRequest
        tariffs.activate(tariffs.create_purchase(self.master, 'pro_30'))
        order = ServiceRequest.objects.create(name='M', phone='+998901112233', master=self.master)
        advance(order, 'accept')
        services.propose_quote(order, 100000, 'on_completion')
        services.approve_quote(order)
        m = order.milestones.get()
        self.assertEqual(m.fee_percent, Decimal('5'))
        self.assertEqual(m.master_amount, 95000)

    def test_top_qidiruvda_birinchi_muddat_otsa_yoq(self):
        self.master.is_available = False  # setUp'dagi usta natijaga aralashmasin
        self.master.save()
        far = make_master('Uzoq', '+998944444444', 41.33, 69.25)
        near = make_master('Yaqin', '+998955555555', 41.301, 69.25)
        names = lambda: [m.full_name for m in search_masters(lat=41.3, lng=69.25)][:2]
        self.assertEqual(names()[0], 'Yaqin')
        far.promoted_until = timezone.now() + timedelta(days=1)
        far.save()
        self.assertEqual(names()[0], 'Uzoq')
        far.promoted_until = timezone.now() - timedelta(seconds=1)
        far.save()
        self.assertEqual(names()[0], 'Yaqin')
        self.assertTrue(near.pk)

    @override_settings(PAYME_KEY='secret', PAYME_ACCOUNT_KEY='milestone_id')
    def test_payme_orqali_tarif(self):
        purchase = tariffs.create_purchase(self.master, 'pro_30')
        auth = 'Basic ' + base64.b64encode(b'Paycom:secret').decode()

        def rpc(method, params):
            return self.client.post(reverse('payme_endpoint'), json.dumps({'method': method, 'params': params, 'id': 1}),
                                    content_type='application/json', HTTP_AUTHORIZATION=auth).json()
        acc = {'amount': int(purchase.amount) * 100, 'account': {'milestone_id': f'p{purchase.pk}'}}
        self.assertTrue(rpc('CheckPerformTransaction', acc)['result']['allow'])
        rpc('CreateTransaction', {'id': 'x1', 'time': int(timezone.now().timestamp() * 1000), **acc})
        self.assertEqual(rpc('PerformTransaction', {'id': 'x1'})['result']['state'], 2)
        self.master.refresh_from_db()
        self.assertTrue(self.master.is_pro)
        # Faollashgan tarifni to'lov tizimi orqali bekor qilib bo'lmaydi
        self.assertEqual(rpc('CancelTransaction', {'id': 'x1', 'reason': 5})['error']['code'], -31007)

    @override_settings(CLICK_SECRET_KEY='k', CLICK_SERVICE_ID='1', CLICK_MERCHANT_ID='2', CLICK_MERCHANT_USER_ID='')
    def test_click_orqali_tarif(self):
        purchase = tariffs.create_purchase(self.master, 'top_7')
        data = {'click_trans_id': '5', 'service_id': '1', 'merchant_trans_id': f'p{purchase.pk}',
                'amount': f'{purchase.amount}.00', 'action': '0', 'error': '0', 'sign_time': 't'}

        def sign(d, prep=''):
            raw = f"{d['click_trans_id']}{d['service_id']}k{d['merchant_trans_id']}{prep}{d['amount']}{d['action']}{d['sign_time']}"
            return hashlib.md5(raw.encode()).hexdigest()
        r = self.client.post(reverse('click_prepare'), dict(data, sign_string=sign(data))).json()
        self.assertEqual(r['error'], 0)
        data.update(action='1', merchant_prepare_id=str(r['merchant_prepare_id']))
        r = self.client.post(reverse('click_complete'), dict(data, sign_string=sign(data, data['merchant_prepare_id']))).json()
        self.assertEqual(r['error'], 0)
        self.master.refresh_from_db()
        self.assertTrue(self.master.is_promoted)
