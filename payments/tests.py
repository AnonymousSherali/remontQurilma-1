import base64
import json
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from masters.tests import verify_phone
from repair_service import workflow
from repair_service.models import ServiceRequest
from repair_service.tests import make_master

from . import services
from .models import Milestone, Payment
from .plans import split_amount


def make_order(**extra):
    master = make_master()
    order = ServiceRequest.objects.create(name='Malika', phone='+998901112233', master=master, **extra)
    return order


def advance(order, *actions, actor=workflow.MASTER):
    for action in actions:
        workflow.apply(order, actor, action)
    order.refresh_from_db()


class PlanTests(TestCase):
    def test_uchga_bolinganda_som_yoqolmaydi(self):
        parts = split_amount(Decimal('100000'), 'thirds')
        self.assertEqual([a for a, _, _ in parts], [Decimal('33333'), Decimal('33333'), Decimal('33334')])
        self.assertEqual(sum(a for a, _, _ in parts), 100000)

    def test_avans(self):
        parts = split_amount(Decimal('250000'), 'advance_30')
        self.assertEqual([(a, s) for a, _, s in parts], [(75000, 'in_progress'), (175000, 'confirmed')])

    def test_naqd_bosqichsiz(self):
        self.assertEqual(split_amount(Decimal('1'), 'cash'), [])


class EscrowFlowTests(TestCase):
    """To'liq oqim: narx -> tasdiq -> to'lov -> bosqichlar -> chiqarish."""

    def setUp(self):
        self.order = make_order()
        advance(self.order, 'accept')

    def test_uch_qismli_reja(self):
        services.propose_quote(self.order, 300000, 'thirds', 'Nasos')
        services.approve_quote(self.order)
        m1, m2, m3 = self.order.milestones.all()
        self.assertEqual(m1.fee_percent, Decimal('10'))

        advance(self.order, 'arrive')
        # 1-qism to'lanmaguncha ishni boshlab bo'lmaydi
        with self.assertRaises(workflow.WorkflowError):
            workflow.apply(self.order, workflow.MASTER, 'start')
        services.mark_held(m1)
        advance(self.order, 'start')

        # 1-qism endi chiqariladi, 2-qism hali bosqichiga yetmagan
        m1.refresh_from_db()
        self.assertTrue(services.releasable(m1))
        services.mark_held(m2)
        m2.refresh_from_db()
        self.assertFalse(services.releasable(m2))
        services.release(m1)

        advance(self.order, 'complete')
        # Mijoz oxirgi qismni to'lamaguncha tasdiqlay olmaydi
        with self.assertRaises(workflow.WorkflowError):
            workflow.apply(self.order, workflow.CUSTOMER, 'confirm')
        services.mark_held(m3)
        advance(self.order, 'confirm', actor=workflow.CUSTOMER)

        states = list(self.order.milestones.values_list('state', flat=True))
        self.assertEqual(states, ['released'] * 3)
        summary = services.summary(self.order)
        self.assertEqual(summary['released'], 300000)
        self.assertEqual(summary['master_net'], 270000)  # 10% komissiya

    def test_tasdiqlangan_narxni_ozgartirib_bolmaydi(self):
        services.propose_quote(self.order, 100000, 'on_completion')
        services.approve_quote(self.order)
        with self.assertRaises(services.PaymentError):
            services.propose_quote(self.order, 999999, 'on_completion')

    def test_nizoda_hech_narsa_chiqmaydi(self):
        services.propose_quote(self.order, 100000, 'advance_30')
        services.approve_quote(self.order)
        m1 = self.order.milestones.first()
        services.mark_held(m1)
        advance(self.order, 'arrive', 'start')
        advance(self.order, 'dispute', actor=workflow.CUSTOMER)
        m1.refresh_from_db()
        self.assertFalse(services.releasable(m1))
        self.assertEqual(services.auto_release(now=timezone.now() + timedelta(days=30)), [])
        services.refund(m1)
        m1.refresh_from_db()
        self.assertEqual(m1.state, Milestone.STATE_REFUNDED)

    def test_avtomatik_chiqarish_va_tasdiqlash(self):
        services.propose_quote(self.order, 100000, 'advance_30')
        services.approve_quote(self.order)
        m1, m2 = self.order.milestones.all()
        services.mark_held(m1)
        services.mark_held(m2)
        advance(self.order, 'arrive', 'start')
        self.assertEqual(services.auto_release(), [])  # hali 48 soat o'tmagan
        later = timezone.now() + timedelta(hours=49)
        self.assertEqual([m.pk for m in services.auto_release(now=later)], [m1.pk])

        advance(self.order, 'complete')
        self.assertEqual(workflow.auto_confirm(), [])
        done = workflow.auto_confirm(now=timezone.now() + timedelta(hours=73))
        self.assertEqual(done, [self.order])
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'confirmed')
        self.assertEqual(self.order.events.last().actor, 'system')
        m2.refresh_from_db()
        self.assertEqual(m2.state, 'released')

    def test_naqd_rejada_tolov_talab_qilinmaydi(self):
        services.propose_quote(self.order, 100000, 'cash')
        services.approve_quote(self.order)
        advance(self.order, 'arrive', 'start', 'complete')
        advance(self.order, 'confirm', actor=workflow.CUSTOMER)
        self.assertEqual(self.order.status, 'confirmed')


class CustomerPaymentViewTests(TestCase):
    def setUp(self):
        self.order = make_order()
        advance(self.order, 'accept')
        services.propose_quote(self.order, 200000, 'advance_30')
        self.url = self.order.get_customer_url()

    def test_smssiz_narxni_tasdiqlab_bolmaydi(self):
        response = self.client.post(reverse('repair_service:quote_decision', args=[self.order.review_token, 'approve']))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.order.milestones.exists())

    @override_settings(DEBUG=True, PAYMENT_PROVIDERS='demo')
    def test_narx_tolov_va_chiqarish(self):
        verify_phone(self.client, self.order.phone)
        self.client.post(reverse('repair_service:quote_decision', args=[self.order.review_token, 'approve']))
        m1 = self.order.milestones.first()
        response = self.client.post(reverse('repair_service:milestone_pay', args=[self.order.review_token, m1.pk]))
        self.assertRedirects(response, reverse('payments:demo_checkout', args=[m1.pk]))
        self.client.post(reverse('payments:demo_checkout', args=[m1.pk]))
        m1.refresh_from_db()
        self.assertEqual(m1.state, 'held')

        advance(self.order, 'arrive', 'start')
        page = self.client.get(self.url)
        self.assertContains(page, reverse('repair_service:milestone_release', args=[self.order.review_token, m1.pk]))
        self.client.post(reverse('repair_service:milestone_release', args=[self.order.review_token, m1.pk]))
        m1.refresh_from_db()
        self.assertEqual(m1.state, 'released')

    def test_demo_tolov_productionda_ochilmaydi(self):
        verify_phone(self.client, self.order.phone)
        services.approve_quote(self.order)
        m1 = self.order.milestones.first()
        self.assertEqual(self.client.get(reverse('payments:demo_checkout', args=[m1.pk])).status_code, 404)


@override_settings(PAYME_KEY='secret', PAYME_ACCOUNT_KEY='milestone_id', PAYMENT_PROVIDERS='payme')
class PaymeTests(TestCase):
    def setUp(self):
        order = make_order()
        advance(order, 'accept')
        services.propose_quote(order, 150000, 'on_completion')
        services.approve_quote(order)
        self.m = order.milestones.get()
        self.auth = 'Basic ' + base64.b64encode(b'Paycom:secret').decode()

    def rpc(self, method, params, auth=None):
        response = self.client.post(
            reverse('payme_endpoint'), json.dumps({'method': method, 'params': params, 'id': 7}),
            content_type='application/json', HTTP_AUTHORIZATION=auth or self.auth,
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def account(self, amount=None):
        return {'amount': amount if amount is not None else 150000 * 100, 'account': {'milestone_id': self.m.pk}}

    def test_avtorizatsiya(self):
        bad = 'Basic ' + base64.b64encode(b'Paycom:wrong').decode()
        self.assertEqual(self.rpc('CheckPerformTransaction', self.account(), auth=bad)['error']['code'], -32504)

    def test_notogri_summa_va_hisob(self):
        self.assertEqual(self.rpc('CheckPerformTransaction', self.account(100))['error']['code'], -31001)
        params = {'amount': 15000000, 'account': {'milestone_id': 999999}}
        self.assertEqual(self.rpc('CheckPerformTransaction', params)['error']['code'], -31050)

    def test_toliq_tolov_va_bekor_qilish(self):
        self.assertTrue(self.rpc('CheckPerformTransaction', self.account())['result']['allow'])
        now = int(timezone.now().timestamp() * 1000)
        created = self.rpc('CreateTransaction', {'id': 'p1', 'time': now, **self.account()})['result']
        self.assertEqual(created['state'], 1)
        # Takroriy CreateTransaction xuddi shu javobni qaytaradi
        self.assertEqual(self.rpc('CreateTransaction', {'id': 'p1', 'time': now, **self.account()})['result'], created)
        # Shu bosqich uchun boshqa tranzaksiya ochib bo'lmaydi
        self.assertEqual(self.rpc('CreateTransaction', {'id': 'p2', 'time': now, **self.account()})['error']['code'], -31050)

        performed = self.rpc('PerformTransaction', {'id': 'p1'})['result']
        self.assertEqual(performed['state'], 2)
        self.m.refresh_from_db()
        self.assertEqual(self.m.state, 'held')
        self.assertEqual(self.rpc('CheckTransaction', {'id': 'p1'})['result']['state'], 2)

        cancelled = self.rpc('CancelTransaction', {'id': 'p1', 'reason': 5})['result']
        self.assertEqual(cancelled['state'], -2)
        self.m.refresh_from_db()
        self.assertEqual(self.m.state, 'refunded')

        rows = self.rpc('GetStatement', {'from': now - 1000, 'to': now + 1000})['result']['transactions']
        self.assertEqual([r['id'] for r in rows], ['p1'])

    def test_chiqarilgan_tolovni_bekor_qilib_bolmaydi(self):
        now = int(timezone.now().timestamp() * 1000)
        self.rpc('CreateTransaction', {'id': 'p1', 'time': now, **self.account()})
        self.rpc('PerformTransaction', {'id': 'p1'})
        Milestone.objects.filter(pk=self.m.pk).update(state='released')
        self.assertEqual(self.rpc('CancelTransaction', {'id': 'p1', 'reason': 5})['error']['code'], -31007)

    def test_eskirgan_tranzaksiya(self):
        old = int((timezone.now() - timedelta(hours=13)).timestamp() * 1000)
        self.rpc('CreateTransaction', {'id': 'p1', 'time': old, **self.account()})
        self.assertEqual(self.rpc('PerformTransaction', {'id': 'p1'})['error']['code'], -31008)
        self.assertEqual(Payment.objects.get().state, -1)

    def test_checkout_url(self):
        from .payables import wrap
        from .payme import checkout_url
        with override_settings(PAYME_MERCHANT_ID='MID', PAYME_TEST=False):
            url = checkout_url(wrap(self.m), 'https://site.uz/x')
        decoded = base64.b64decode(url.rsplit('/', 1)[1]).decode()
        self.assertEqual(decoded, f'm=MID;ac.milestone_id={self.m.pk};a=15000000;c=https://site.uz/x')
        self.assertTrue(url.startswith('https://checkout.paycom.uz/'))
