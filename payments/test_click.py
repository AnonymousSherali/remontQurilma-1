import hashlib
from urllib.parse import parse_qs, urlparse

from django.test import TestCase, override_settings
from django.urls import reverse

from . import services
from .click import checkout_url
from .payables import wrap
from .models import Payment
from .tests import advance, make_order

SECRET = 'click-secret'

def sign(data, prepare_id=''):
    raw = (f"{data['click_trans_id']}{data['service_id']}{SECRET}{data['merchant_trans_id']}{prepare_id}"
           f"{data['amount']}{data['action']}{data['sign_time']}")
    return hashlib.md5(raw.encode()).hexdigest()

@override_settings(CLICK_SECRET_KEY=SECRET, CLICK_SERVICE_ID='111', CLICK_MERCHANT_ID='222', CLICK_MERCHANT_USER_ID='')
class ClickTests(TestCase):
    def setUp(self):
        order = make_order()
        advance(order, 'accept')
        services.propose_quote(order, 150000, 'on_completion')
        services.approve_quote(order)
        self.m = order.milestones.get()

    def base(self, action, **extra):
        data = {'click_trans_id': '9001', 'service_id': '111', 'click_paydoc_id': '5',
                'merchant_trans_id': str(self.m.pk), 'amount': '150000.00', 'action': str(action),
                'error': '0', 'error_note': 'Success', 'sign_time': '2026-11-09 12:00:00'}
        data.update(extra)
        return data

    def prepare(self, **extra):
        data = self.base(0, **extra)
        data.setdefault('sign_string', sign(data))
        return self.client.post(reverse('click_prepare'), data).json()

    def complete(self, prepare_id, **extra):
        data = self.base(1, merchant_prepare_id=str(prepare_id), **extra)
        data.setdefault('sign_string', sign(data, str(prepare_id)))
        return self.client.post(reverse('click_complete'), data).json()

    def test_muvaffaqiyatli_tolov(self):
        r = self.prepare()
        self.assertEqual(r['error'], 0)
        r = self.complete(r['merchant_prepare_id'])
        self.assertEqual(r['error'], 0)
        self.m.refresh_from_db()
        self.assertEqual(self.m.state, 'held')
        self.assertEqual(Payment.objects.get().provider, 'click')
        # Takroriy Complete — "allaqachon to'langan", ikkinchi marta hisoblanmaydi
        self.assertEqual(self.complete(r['merchant_confirm_id'])['error'], -4)

    def test_notogri_imzo(self):
        self.assertEqual(self.prepare(sign_string='0' * 32)['error'], -1)
        self.assertFalse(Payment.objects.exists())

    def test_notogri_summa_va_buyurtma(self):
        self.assertEqual(self.prepare(amount='100.00')['error'], -2)
        self.assertEqual(self.prepare(merchant_trans_id='999999')['error'], -5)

    def test_click_xatosi_bekor_qiladi(self):
        r = self.prepare()
        r = self.complete(r['merchant_prepare_id'], error='-5017', error_note='Insufficient funds')
        self.assertEqual(r['error'], -9)
        self.m.refresh_from_db()
        self.assertEqual(self.m.state, 'pending')
        self.assertEqual(Payment.objects.get().state, Payment.STATE_CANCELLED)

    def test_tolangan_bosqichga_qayta_prepare(self):
        services.mark_held(self.m)
        self.assertEqual(self.prepare()['error'], -4)

    def test_noma_lum_tranzaksiya(self):
        self.assertEqual(self.complete(424242)['error'], -6)

    def test_checkout_url(self):
        url = checkout_url(wrap(self.m), 'https://site.uz/b/')
        q = parse_qs(urlparse(url).query)
        self.assertTrue(url.startswith('https://my.click.uz/services/pay?'))
        self.assertEqual(q['service_id'], ['111'])
        self.assertEqual(q['transaction_param'], [str(self.m.pk)])
        self.assertEqual(q['amount'], ['150000.00'])

    @override_settings(PAYMENT_PROVIDERS='payme,click', PAYME_MERCHANT_ID='M')
    def test_mijoz_tizimni_tanlaydi(self):
        from masters.tests import verify_phone
        order = self.m.order
        verify_phone(self.client, order.phone)
        page = self.client.get(order.get_customer_url())
        self.assertContains(page, 'value="payme"')
        self.assertContains(page, 'value="click"')
        response = self.client.post(reverse('repair_service:milestone_pay', args=[order.review_token, self.m.pk]),
                                    {'provider': 'click'})
        self.assertTrue(response['Location'].startswith('https://my.click.uz/'))
        # Ro'yxatda yo'q tizim tanlansa — birlamchisiga (payme)
        response = self.client.post(reverse('repair_service:milestone_pay', args=[order.review_token, self.m.pk]),
                                    {'provider': 'hack'})
        self.assertIn('paycom.uz', response['Location'])
