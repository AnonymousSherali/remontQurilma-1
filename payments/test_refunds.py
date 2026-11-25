import base64
import json
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from otp.sms import ConsoleBackend
from repair_service import disputes, workflow
from repair_service.models import ServiceRequest
from repair_service.tests import make_master

from . import refunds, services
from .models import Payment, Refund

PHONE = '+998901112233'


def paid_order(master, provider=Payment.PROVIDER_PAYME):
    order = ServiceRequest.objects.create(name='Malika', phone=PHONE, master=master)
    workflow.apply(order, workflow.MASTER, 'accept')
    services.propose_quote(order, 200000, 'on_completion')
    services.approve_quote(order)
    m = order.milestones.get()
    Payment.objects.create(milestone=m, provider=provider, provider_id='tx-777', amount=m.amount_due,
                           state=Payment.STATE_PERFORMED)
    services.mark_held(m)
    workflow.apply(order, workflow.MASTER, 'arrive')
    workflow.apply(order, workflow.CUSTOMER, 'dispute', note='Ish umuman qilinmadi')
    order.refresh_from_db()
    return order


class RefundTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        ConsoleBackend.sent.clear()
        self.master = make_master('Usta', '+998911111111')

    @override_settings(PAYME_KEY='secret', PAYMENT_PROVIDERS='payme')
    def test_payme_kabinetdan_bekor_qilinsa_ozi_yopiladi(self):
        order = paid_order(self.master)
        with self.captureOnCommitCallbacks(execute=True):
            disputes.resolve(order, [], 'Ish bajarilmagan')
        refund = Refund.objects.get()
        self.assertEqual((refund.status, refund.amount, refund.payment.provider_id), ('pending', 200000, 'tx-777'))
        self.assertIn('Payme Business', refunds.instructions(refund))
        # Kassir kabinetda bekor qildi → Payme CancelTransaction yuboradi
        auth = 'Basic ' + base64.b64encode(b'Paycom:secret').decode()
        with self.captureOnCommitCallbacks(execute=True):
            data = self.client.post(reverse('payme_endpoint'), json.dumps(
                {'method': 'CancelTransaction', 'id': 1, 'params': {'id': 'tx-777', 'reason': 5}}),
                content_type='application/json', HTTP_AUTHORIZATION=auth).json()
        self.assertEqual(data['result']['state'], -2)
        refund.refresh_from_db()
        self.assertEqual((refund.status, refund.method), ('done', 'provider'))
        self.assertIn("200 000 so'm qaytarildi", [t for p, t in ConsoleBackend.sent if p == PHONE][-1])

    @override_settings(CLICK_AUTO_REFUND=True, CLICK_SECRET_KEY='s', CLICK_SERVICE_ID='10', CLICK_MERCHANT_USER_ID='5')
    def test_click_api_bilan_avtomatik(self):
        order = paid_order(self.master, Payment.PROVIDER_CLICK)

        class Resp:
            def __init__(self, body): self.body = body
            def read(self): return self.body
            def __enter__(self): return self
            def __exit__(self, *a): return False

        with mock.patch('urllib.request.urlopen', return_value=Resp(b'{"error_code": 0, "payment_id": 1}')) as call:
            with self.captureOnCommitCallbacks(execute=True):
                disputes.resolve(order, [], 'Qaytarish')
        request = call.call_args[0][0]
        self.assertEqual((request.get_method(), request.full_url),
                         ('DELETE', 'https://api.click.uz/v2/merchant/payment/reversal/10/tx-777'))
        user_id, digest, stamp = request.get_header('Auth').split(':')
        import hashlib
        self.assertEqual((user_id, digest), ('5', hashlib.sha1((stamp + 's').encode()).hexdigest()))
        refund = Refund.objects.get()
        self.assertEqual((refund.status, refund.method), ('done', 'auto'))
        refund.payment.refresh_from_db()
        self.assertEqual(refund.payment.state, Payment.STATE_CANCELLED_AFTER_PERFORM)

    @override_settings(CLICK_AUTO_REFUND=True, CLICK_SECRET_KEY='s', CLICK_SERVICE_ID='10', CLICK_MERCHANT_USER_ID='5')
    def test_click_rad_etsa_qolda(self):
        order = paid_order(self.master, Payment.PROVIDER_CLICK)

        class Resp:
            def read(self): return b'{"error_code": -5017, "error_note": "Period closed"}'
            def __enter__(self): return self
            def __exit__(self, *a): return False

        with mock.patch('urllib.request.urlopen', return_value=Resp()):
            with self.captureOnCommitCallbacks(execute=True):
                disputes.resolve(order, [], 'Qaytarish')
        refund = Refund.objects.get()
        self.assertEqual(refund.status, 'failed')
        self.assertIn('-5017', refund.note)
        self.client.force_login(User.objects.create_superuser('a', 'a@example.com', 'x'))
        self.assertContains(self.client.get(reverse('admin:payments_refund_changelist')), 'tx-777')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('admin:payments_refund_changelist'),
                             {'action': 'mark_done', '_selected_action': [refund.pk]})
        refund.refresh_from_db()
        self.assertEqual((refund.status, refund.method), ('done', 'manual'))

    def test_click_avtomatik_ochiq_bolsa_navbatda_qoladi(self):
        order = paid_order(self.master, Payment.PROVIDER_CLICK)
        with mock.patch('urllib.request.urlopen') as call:
            with self.captureOnCommitCallbacks(execute=True):
                disputes.resolve(order, [], 'Qaytarish')
        call.assert_not_called()
        self.assertEqual(Refund.objects.get().status, 'pending')

    def test_demo_darhol_yopiladi_va_admin_amali(self):
        order = paid_order(self.master, Payment.PROVIDER_DEMO)
        with self.captureOnCommitCallbacks(execute=True):
            services.refund(order.milestones.get())
        self.assertEqual(Refund.objects.get().status, 'done')
        self.assertEqual(refunds.pending_count(), 0)
