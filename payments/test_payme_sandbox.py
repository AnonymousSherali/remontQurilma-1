"""Payme sandbox (test.paycom.uz) tekshiradigan holatlar — lokal takrori.

Har bir test sandbox'dagi bitta bandga mos keladi. Bular o'tsa, sandbox'da ham yashil bo'lishi
kutiladi; lekin haqiqiy sandbox sinovi baribir majburiy (docs/INTEGRATSIYALAR.md).
"""

import base64
import json
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from repair_service.models import ServiceRequest
from repair_service.tests import make_master

from .models import Milestone, Payment

AUTH = 'Basic ' + base64.b64encode(b'Paycom:test-key').decode()


@override_settings(PAYME_KEY='test-key', PAYME_ACCOUNT_KEY='milestone_id', PAYMENT_PROVIDERS='payme',
                   PAYME_TEST=True)
class PaymeSandboxTests(TestCase):
    def setUp(self):
        make_master()
        out = StringIO()
        call_command('payme_sandbox', '--amount', '15000', stdout=out)
        self.output = out.getvalue()
        self.m = Milestone.objects.get(order__name='Payme sandbox')
        self.now = int(timezone.now().timestamp() * 1000)

    def rpc(self, method, params, auth=AUTH, raw=None):
        body = raw if raw is not None else json.dumps({'method': method, 'params': params, 'id': 99})
        response = self.client.post(reverse('payme_endpoint'), body, content_type='application/json',
                                    HTTP_AUTHORIZATION=auth)
        self.assertEqual(response.status_code, 200)   # Payme xatolarni ham HTTP 200 bilan kutadi
        return response.json()

    def account(self, amount=1500000, account=None):
        return {'amount': amount, 'account': {'milestone_id': account if account is not None else self.m.pk}}

    def code(self, data):
        return data.get('error', {}).get('code')

    def test_buyruq_qiymatlarni_chiqaradi(self):
        self.assertIn(f'milestone_id = {self.m.pk}', self.output)
        self.assertIn('1500000', self.output)

    def test_avtorizatsiya(self):
        self.assertEqual(self.code(self.rpc('CheckPerformTransaction', self.account(), auth='')), -32504)
        bad = 'Basic ' + base64.b64encode(b'Paycom:wrong').decode()
        self.assertEqual(self.code(self.rpc('CheckPerformTransaction', self.account(), auth=bad)), -32504)
        self.assertEqual(self.code(self.rpc('CheckPerformTransaction', self.account(), auth='Basic !!!')), -32504)

    def test_json_va_metod_xatolari(self):
        self.assertEqual(self.code(self.rpc('', {}, raw='{bad json')), -32700)
        self.assertEqual(self.code(self.rpc('NoSuchMethod', {})), -32601)

    def test_summa_va_hisob(self):
        self.assertEqual(self.code(self.rpc('CheckPerformTransaction', self.account(amount=100))), -31001)
        self.assertEqual(self.code(self.rpc('CheckPerformTransaction', self.account(account=10 ** 9))), -31050)
        self.assertEqual(self.code(self.rpc('CheckPerformTransaction', self.account(account='abc'))), -31050)
        self.assertTrue(self.rpc('CheckPerformTransaction', self.account())['result']['allow'])

    def test_yaratish_bajarish_takroriy(self):
        created = self.rpc('CreateTransaction', {'id': 's1', 'time': self.now, **self.account()})['result']
        self.assertEqual(created['state'], 1)
        self.assertEqual(self.rpc('CreateTransaction', {'id': 's1', 'time': self.now, **self.account()})['result'],
                         created)
        # Hisob band — boshqa tranzaksiya
        self.assertEqual(self.code(self.rpc('CreateTransaction', {'id': 's2', 'time': self.now,
                                                                  **self.account()})), -31050)
        done = self.rpc('PerformTransaction', {'id': 's1'})['result']
        self.assertEqual(done['state'], 2)
        self.assertEqual(self.rpc('PerformTransaction', {'id': 's1'})['result'], done)   # idempotent
        # To'langan hisobga yangi to'lov ochilmaydi
        self.assertEqual(self.code(self.rpc('CheckPerformTransaction', self.account())), -31050)
        check = self.rpc('CheckTransaction', {'id': 's1'})['result']
        self.assertEqual((check['state'], check['perform_time']), (2, done['perform_time']))

    def test_bajarishdan_oldin_bekor(self):
        self.rpc('CreateTransaction', {'id': 's1', 'time': self.now, **self.account()})
        cancelled = self.rpc('CancelTransaction', {'id': 's1', 'reason': 3})['result']
        self.assertEqual(cancelled['state'], -1)
        self.assertEqual(self.rpc('CancelTransaction', {'id': 's1', 'reason': 3})['result'], cancelled)
        self.assertEqual(self.code(self.rpc('PerformTransaction', {'id': 's1'})), -31008)
        check = self.rpc('CheckTransaction', {'id': 's1'})['result']
        self.assertEqual((check['state'], check['reason']), (-1, 3))
        self.m.refresh_from_db()
        self.assertEqual(self.m.state, Milestone.STATE_PENDING)
        # Bekor qilingandan keyin hisob yana bo'sh — yangi tranzaksiya ochiladi
        self.assertEqual(self.rpc('CreateTransaction', {'id': 's2', 'time': self.now,
                                                        **self.account()})['result']['state'], 1)

    def test_bajarilgandan_keyin_bekor(self):
        self.rpc('CreateTransaction', {'id': 's1', 'time': self.now, **self.account()})
        self.rpc('PerformTransaction', {'id': 's1'})
        cancelled = self.rpc('CancelTransaction', {'id': 's1', 'reason': 5})['result']
        self.assertEqual(cancelled['state'], -2)
        self.assertEqual(self.rpc('CancelTransaction', {'id': 's1', 'reason': 5})['result'], cancelled)
        self.m.refresh_from_db()
        self.assertEqual(self.m.state, Milestone.STATE_REFUNDED)

    def test_xizmat_korsatilgan_bolsa_bekor_qilinmaydi(self):
        self.rpc('CreateTransaction', {'id': 's1', 'time': self.now, **self.account()})
        self.rpc('PerformTransaction', {'id': 's1'})
        Milestone.objects.filter(pk=self.m.pk).update(state=Milestone.STATE_RELEASED)
        self.assertEqual(self.code(self.rpc('CancelTransaction', {'id': 's1', 'reason': 5})), -31007)

    def test_mavjud_bolmagan_tranzaksiya(self):
        for method in ('PerformTransaction', 'CancelTransaction', 'CheckTransaction'):
            self.assertEqual(self.code(self.rpc(method, {'id': 'yoq', 'reason': 1})), -31003, method)

    def test_muddati_otgan(self):
        old = int((timezone.now() - timedelta(hours=13)).timestamp() * 1000)
        self.rpc('CreateTransaction', {'id': 's1', 'time': old, **self.account()})
        self.assertEqual(self.code(self.rpc('PerformTransaction', {'id': 's1'})), -31008)
        check = self.rpc('CheckTransaction', {'id': 's1'})['result']
        self.assertEqual((check['state'], check['reason']), (-1, 4))

    def test_statement(self):
        self.rpc('CreateTransaction', {'id': 's1', 'time': self.now, **self.account()})
        rows = self.rpc('GetStatement', {'from': self.now - 10, 'to': self.now + 10})['result']['transactions']
        self.assertEqual([(r['id'], r['amount'], r['account']) for r in rows],
                         [('s1', 1500000, {'milestone_id': str(self.m.pk)})])
        self.assertEqual(self.rpc('GetStatement', {'from': 0, 'to': 1})['result']['transactions'], [])

    def test_tozalash(self):
        self.rpc('CreateTransaction', {'id': 's1', 'time': self.now, **self.account()})
        call_command('payme_sandbox', '--cleanup', stdout=StringIO())
        self.assertFalse(ServiceRequest.objects.filter(name='Payme sandbox').exists())
        self.assertFalse(Payment.objects.exists())

    @override_settings(PAYME_TEST=False)
    def test_haqiqiy_kassada_ishlamaydi(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command('payme_sandbox', stdout=StringIO())
