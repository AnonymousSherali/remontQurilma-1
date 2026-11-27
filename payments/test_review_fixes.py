"""Kod tekshiruvida topilgan xatolar uchun regression testlar (pul, xavfsizlik, mantiq)."""

import base64
import json
from datetime import timedelta
from io import BytesIO, StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from repair_service import disputes, workflow
from repair_service.models import OrderEvent, ServiceRequest as SR

from . import payouts, services
from .models import Milestone, Payment, Refund
from .payables import MilestonePayable
from .tests import advance, make_order

User = get_user_model()


def approved_order(plan='on_completion', amount=150000):
    order = make_order()
    advance(order, 'accept')
    services.propose_quote(order, amount, plan)
    services.approve_quote(order)
    return order


@override_settings(PAYME_KEY='secret', PAYME_ACCOUNT_KEY='milestone_id', PAYMENT_PROVIDERS='payme')
class PaymeDoubleChargeTests(TestCase):
    def setUp(self):
        self.order = approved_order()
        self.m = self.order.milestones.get()
        self.auth = 'Basic ' + base64.b64encode(b'Paycom:secret').decode()
        self.now = int(timezone.now().timestamp() * 1000)

    def rpc(self, method, params):
        response = self.client.post(reverse('payme_endpoint'),
                                    json.dumps({'method': method, 'params': params, 'id': 1}),
                                    content_type='application/json', HTTP_AUTHORIZATION=self.auth)
        return response.json()

    def create(self, pid='p1'):
        return self.rpc('CreateTransaction', {'id': pid, 'time': self.now, 'amount': 15000000,
                                              'account': {'milestone_id': self.m.pk}})

    def test_boshqa_tizim_orqali_tolangan_bolsa_perform_rad_etiladi(self):
        self.create()
        # Shu orada boshqa tizim (masalan, Click) orqali to'landi
        Payment.objects.create(milestone=self.m, provider=Payment.PROVIDER_CLICK, provider_id='c1',
                               amount=self.m.amount_due, state=Payment.STATE_PERFORMED)
        services.mark_held(self.m)
        self.assertEqual(self.rpc('PerformTransaction', {'id': 'p1'})['error']['code'], -31008)
        self.assertEqual(Payment.objects.get(provider_id='p1').state, Payment.STATE_CREATED)

    def test_summa_ozgarsa_perform_rad_etiladi(self):
        self.create()
        Milestone.objects.filter(pk=self.m.pk).update(discount=10000)   # promo-kod keyin qo'shildi
        self.assertEqual(self.rpc('PerformTransaction', {'id': 'p1'})['error']['code'], -31008)
        self.m.refresh_from_db()
        self.assertEqual(self.m.state, Milestone.STATE_PENDING)

    def test_bekor_qilingan_buyurtmaga_tolov_olinmaydi(self):
        SR.objects.filter(pk=self.order.pk).update(status=SR.STATUS_CANCELLED)
        self.assertEqual(self.create()['error']['code'], -31050)

    def test_ikkinchi_tolov_bekor_qilinsa_bosqich_ushlanganicha_qoladi(self):
        self.create()
        self.rpc('PerformTransaction', {'id': 'p1'})
        # Xato bilan ikkinchi marta ham o'tgan to'lov (masalan, bank o'tkazmasi)
        Payment.objects.create(milestone=self.m, provider=Payment.PROVIDER_BANK, provider_id='b1',
                               amount=self.m.amount_due, state=Payment.STATE_PERFORMED)
        self.assertEqual(self.rpc('CancelTransaction', {'id': 'p1', 'reason': 5})['result']['state'], -2)
        self.m.refresh_from_db()
        self.assertEqual(self.m.state, Milestone.STATE_HELD)   # bank to'lovi hali uni moliyalashtiradi


class EscrowLogicTests(TestCase):
    def test_mijoz_bekor_qilsa_ushlangan_pul_qaytariladi(self):
        order = approved_order('advance_30', 200000)
        first = order.milestones.order_by('position').first()
        Payment.objects.create(milestone=first, provider=Payment.PROVIDER_DEMO, amount=first.amount_due,
                               state=Payment.STATE_PERFORMED)
        services.mark_held(first)
        with self.captureOnCommitCallbacks(execute=True):
            workflow.apply(order, workflow.CUSTOMER, 'cancel')
        first.refresh_from_db()
        self.assertEqual(first.state, Milestone.STATE_REFUNDED)
        self.assertTrue(Refund.objects.filter(milestone=first).exists())

    def test_nizodagi_buyurtma_tolanmaydi(self):
        order = approved_order()
        SR.objects.filter(pk=order.pk).update(status=SR.STATUS_DISPUTED)
        self.assertFalse(MilestonePayable(Milestone.objects.select_related('order').get(order=order)).is_pending)

    def test_eski_narxga_rozilik_qabul_qilinmaydi(self):
        order = make_order()
        advance(order, 'accept')
        quote = services.propose_quote(order, 100000, 'on_completion')
        seen = int(quote.proposed_at.timestamp())
        type(quote).objects.filter(pk=quote.pk).update(proposed_at=quote.proposed_at + timedelta(seconds=5),
                                                       amount=900000)
        with self.assertRaises(services.PaymentError):
            services.approve_quote(order, version=seen)
        self.assertFalse(order.milestones.exists())

    def test_tolov_boshlangan_bolsa_voz_kechib_bolmaydi_va_vaqt_tozalanadi(self):
        order = approved_order()
        m = order.milestones.get()
        Payment.objects.create(milestone=m, provider=Payment.PROVIDER_PAYME, provider_id='x', amount=m.amount_due)
        with self.assertRaises(workflow.WorkflowError):
            workflow.apply(order, workflow.MASTER, 'cancel')

        other = SR.objects.create(name='Ali', phone='+998901110000', master=order.master,
                                  visit_at=timezone.now() + timedelta(days=1), visit_reminded=True)
        advance(other, 'accept')
        workflow.apply(other, workflow.MASTER, 'cancel')
        other.refresh_from_db()
        self.assertIsNone(other.visit_at)
        self.assertFalse(other.visit_reminded)

    def test_qaytarilgan_bosqich_ishni_ochmaydi(self):
        order = approved_order('advance_30', 200000)
        first = order.milestones.order_by('position').first()
        Milestone.objects.filter(pk=first.pk).update(state=Milestone.STATE_REFUNDED)
        self.assertEqual([m.pk for m in services.unfunded_for(order, first.release_status)], [first.pk])

    def test_nizo_pulsiz_bolsa_tomon_tanlanadi(self):
        order = make_order()
        advance(order, 'accept', 'arrive')
        SR.objects.filter(pk=order.pk).update(status=SR.STATUS_DISPUTED)
        with self.assertRaises(disputes.DisputeError):
            disputes.resolve(order, [], 'Izoh')
        result = disputes.resolve(order, [], 'Mijoz haq', outcome='customer')
        self.assertEqual(result['status'], SR.STATUS_CANCELLED)

    def test_avtomatik_tasdiq_tizim_nomidan(self):
        order = make_order()
        advance(order, 'accept')
        services.propose_quote(order, 100000, 'cash')
        services.approve_quote(order)
        advance(order, 'arrive', 'start', 'complete')
        OrderEvent.objects.filter(order=order, status=SR.STATUS_COMPLETED).update(
            created_at=timezone.now() - timedelta(days=10))
        with mock.patch('repair_service.customer_notify.notify_status_change') as notify, \
                self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(len(workflow.auto_confirm()), 1)
        self.assertEqual(notify.call_args[0][1], OrderEvent.ACTOR_SYSTEM)
        self.assertEqual(order.events.get(status=SR.STATUS_CONFIRMED).actor, OrderEvent.ACTOR_SYSTEM)


class PayoutAndAdminTests(TestCase):
    def test_excel_formula_ishlamaydi(self):
        order = approved_order()
        master = order.master
        master.full_name = '=HYPERLINK("http://evil","x")'
        master.payout_card = '8600123412341234'
        master.save()
        Milestone.objects.filter(order=order).update(state=Milestone.STATE_RELEASED, released_at=timezone.now())
        from openpyxl import load_workbook
        sheet = load_workbook(BytesIO(payouts.pending_xlsx())).active
        self.assertEqual(sheet['A2'].data_type, 's')
        self.assertTrue(sheet['A2'].value.startswith("'="))

    def test_huquqsiz_xodim_tolovlar_sahifasini_ochmaydi(self):
        staff = User.objects.create_user('op', password='x', is_staff=True)
        self.client.force_login(staff)
        url = reverse('admin:payments_payout_pending')
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin_disputes')).status_code, 403)
        staff.user_permissions.add(Permission.objects.get(codename='view_payout'))
        staff = User.objects.get(pk=staff.pk)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {'prepare': '1'}).status_code, 403)   # o'zgartirish huquqi yo'q


class SecurityTests(TestCase):
    def test_nps_tashqi_saytga_yonaltirmaydi(self):
        order = make_order()
        SR.objects.filter(pk=order.pk).update(status=SR.STATUS_CONFIRMED)
        url = reverse('repair_service:nps_submit', args=[order.review_token])
        for target in ('//evil.example/phish', '/\\evil.example', 'https://evil.example/'):
            response = self.client.post(url, {'score': 9, 'next': target})
            self.assertFalse(response['Location'].lstrip('/').startswith(('evil', '\\', 'https')), target)

    def test_telegram_matni_qochiriladi(self):
        from repair_service import customer_notify
        from telegram_bot import client
        order = make_order()
        order.master.telegram_chat_id = 555
        order.master.save()
        client.SENT.clear()
        customer_notify._to_master(order, 'narx < 100k & tez')
        self.assertIn('narx &lt; 100k &amp; tez', client.SENT[-1][1]['text'])


class CronTests(TestCase):
    def test_bitta_qadam_xatosi_qolganlarini_toxtatmaydi(self):
        from django.core.management.base import CommandError
        with mock.patch('payments.management.commands.process_orders.update_all', side_effect=RuntimeError), \
                mock.patch('repair_service.nps.send_invites') as nps:
            with self.assertRaises(CommandError):
                call_command('process_orders', stdout=StringIO())
        nps.assert_called_once()
