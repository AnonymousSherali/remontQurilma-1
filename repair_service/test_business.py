from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from masters.tests import verify_phone
from payments import services as payments
from payments.models import Payment

from . import business, workflow
from .models import ServiceRequest
from .tests import AJAX, VALID, make_master

BANK = {'name': 'TechService', 'phone': '+998901234567', 'email': 'info@techservice.uz', 'address': 'Toshkent',
        'telegram': '', 'hours': '', 'legal_name': '«TechService» MChJ', 'legal_inn': '305123456',
        'legal_address': 'Toshkent, Chilonzor', 'bank_name': 'Kapitalbank', 'bank_account': '20208000900123456001',
        'bank_mfo': '01158', 'vat_percent': '12'}


@override_settings(SITE_INFO=BANK)
class BusinessTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        self.master = make_master('Usta', '+998911111111')

    def order(self):
        order = ServiceRequest.objects.create(name='Hisobchi', phone='+998901112233', master=self.master,
                                              company_name='«Baraka Savdo» MChJ', company_inn='301234567')
        workflow.apply(order, workflow.MASTER, 'accept')
        payments.propose_quote(order, 1120000, 'on_completion', 'Elektr tarmog\'ini ta\'mirlash')
        payments.approve_quote(order)
        return order

    def test_arizada_tashkilot(self):
        bad = self.client.post(reverse('repair_service:submit_request'),
                               {**VALID, 'company_name': 'Baraka', 'company_inn': '12345'}, **AJAX)
        self.assertEqual(bad.status_code, 400)
        self.assertIn('company_inn', bad.json()['errors'])
        cache.clear()
        self.client.post(reverse('repair_service:submit_request'),
                         {**VALID, 'company_name': 'Baraka Savdo', 'company_inn': '301 234 567'}, **AJAX)
        order = ServiceRequest.objects.get()
        self.assertTrue(order.is_business)
        self.assertEqual(order.company_inn, '301234567')

    def test_schyot_bank_otkazmasi_va_dalolatnoma(self):
        order = self.order()
        verify_phone(self.client, order.phone)
        page = self.client.get(order.get_customer_url())
        self.assertContains(page, 'value="bank"')
        m = order.milestones.get()
        response = self.client.post(reverse('repair_service:milestone_pay', args=[order.review_token, m.pk]),
                                    {'provider': 'bank'})
        self.assertRedirects(response, reverse('repair_service:invoice', args=[order.review_token, m.pk]))
        invoice = self.client.get(response.url).content.decode()
        for text in (f'TS-{order.pk}-1', '20208000900123456001', '01158', '301234567', '1\xa0120\xa0000',
                     'QQS 12%: 120\xa0000'):
            self.assertIn(text, invoice)
        payment = Payment.objects.get(provider='bank')
        self.assertEqual(payment.state, Payment.STATE_CREATED)
        # Admin: pul tushdi
        admin = self.client_class()
        admin.force_login(User.objects.create_superuser('a', 'a@example.com', 'x'))
        admin.post(reverse('admin:payments_payment_changelist'),
                   {'action': 'confirm_bank_transfer', '_selected_action': [payment.pk]})
        m.refresh_from_db()
        self.assertEqual(m.state, 'held')
        self.assertContains(self.client.get(response.url), 'doc-stamp')     # «To'langan» belgisi
        self.assertEqual(self.client.get(reverse('repair_service:act', args=[order.review_token])).status_code, 404)
        for action in ('arrive', 'start', 'complete'):
            workflow.apply(order, workflow.MASTER, action)
        workflow.apply(order, workflow.CUSTOMER, 'confirm')
        act = self.client.get(reverse('repair_service:act', args=[order.review_token]))
        self.assertContains(act, 'dalolatnomasi')
        self.assertContains(act, '«Baraka Savdo» MChJ')

    def test_jismoniy_shaxsga_yoq(self):
        order = ServiceRequest.objects.create(name='A', phone='+998901112233', master=self.master)
        workflow.apply(order, workflow.MASTER, 'accept')
        payments.propose_quote(order, 100000, 'on_completion')
        payments.approve_quote(order)
        verify_phone(self.client, order.phone)
        self.assertNotContains(self.client.get(order.get_customer_url()), 'value="bank"')
        m = order.milestones.get()
        self.assertEqual(self.client.get(reverse('repair_service:invoice', args=[order.review_token, m.pk])).status_code,
                         404)

    @override_settings(SITE_INFO={**BANK, 'bank_account': ''})
    def test_rekvizitsiz_ochiq(self):
        self.assertFalse(business.bank_enabled())
        order = self.order()
        with self.assertRaises(business.BusinessError):
            business.request_transfer(order.milestones.get())

    @override_settings(SITE_INFO={**BANK, 'vat_percent': ''})
    def test_qqssiz(self):
        self.assertEqual(business.vat(1000), (None, None))
