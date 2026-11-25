from django.contrib.auth.models import Permission, User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from otp.sms import ConsoleBackend
from payments import services as payments
from payments.models import Milestone
from telegram_bot import client as tg

from . import disputes, workflow
from .models import ServiceRequest
from .tests import make_master

PHONE = '+998901112233'


def disputed_order(master, plan='thirds'):
    order = ServiceRequest.objects.create(name='Malika', phone=PHONE, master=master)
    workflow.apply(order, workflow.MASTER, 'accept')
    payments.propose_quote(order, 300000, plan)
    payments.approve_quote(order)
    for m in order.milestones.all():
        payments.mark_held(m)
    workflow.apply(order, workflow.MASTER, 'arrive')
    workflow.apply(order, workflow.MASTER, 'start')
    workflow.apply(order, workflow.CUSTOMER, 'dispute', note='Kran yana oqyapti')
    order.refresh_from_db()
    return order


class DisputeTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        tg.SENT.clear()
        self.master = make_master('Usta', '+998911111111')
        self.admin = User.objects.create_superuser('admin', 'a@example.com', 'x')

    def test_qisman_hal_qilish(self):
        order = disputed_order(self.master)
        held = list(order.milestones.filter(state='held'))
        self.assertEqual(len(held), 3)
        self.assertEqual(disputes.open_disputes()[0].dispute_reason, 'Kran yana oqyapti')
        with self.assertRaises(disputes.DisputeError):
            disputes.resolve(order, [held[0].pk], '')
        ConsoleBackend.sent.clear()
        with self.captureOnCommitCallbacks(execute=True):
            result = disputes.resolve(order, [held[0].pk], "1-qism bajarilgan")
        self.assertEqual((result['released'], result['refunded'], result['status']), (100000, 200000, 'confirmed'))
        states = list(order.milestones.order_by('position').values_list('state', flat=True))
        self.assertEqual(states, ['released', 'refunded', 'refunded'])
        sms = dict(ConsoleBackend.sent)
        self.assertIn("200 000 so'm sizga qaytariladi", sms[PHONE])
        self.assertIn("100 000 so'm", sms[self.master.phone])
        with self.assertRaises(disputes.DisputeError):
            disputes.resolve(order, [], 'yana')

    def test_hammasi_mijozga(self):
        order = disputed_order(self.master)
        disputes.resolve(order, [], 'Ish bajarilmagan')
        order.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')
        self.assertFalse(order.milestones.exclude(state='refunded').exists())

    def test_kelishildi_davom_etadi(self):
        order = disputed_order(self.master)
        self.assertEqual(disputes.status_before(order), 'in_progress')
        with self.captureOnCommitCallbacks(execute=True):
            disputes.withdraw(order, 'Usta ertaga qayta keladi')
        order.refresh_from_db()
        self.assertEqual(order.status, 'in_progress')
        self.assertTrue(order.milestones.filter(state=Milestone.STATE_HELD).exists())   # pul muzlatilgan holicha

    @override_settings(TELEGRAM_CHAT_ID='-100')
    def test_adminga_xabar(self):
        with self.captureOnCommitCallbacks(execute=True):
            disputed_order(self.master)
        texts = [p['text'] for m, p in tg.SENT if p.get('chat_id') == '-100']
        self.assertTrue(any('Nizo' in t and 'Kran yana oqyapti' in t for t in texts))

    def test_admin_sahifalari(self):
        order = disputed_order(self.master)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('admin_disputes')), 'Kran yana oqyapti')
        url = reverse('admin_dispute', args=[order.pk])
        page = self.client.get(url)
        self.assertContains(page, 'Qarorni qo')
        self.assertContains(page, 'name="release"', count=3)
        held = order.milestones.order_by('position').values_list('pk', flat=True)
        response = self.client.post(url, {'decision': 'resolve', 'release': [held[0], held[1]], 'note': 'Qisman'})
        self.assertRedirects(response, reverse('admin_disputes'))
        self.assertEqual(order.milestones.filter(state='released').count(), 2)

    def test_huquqsiz_xodim(self):
        order = disputed_order(self.master)
        staff = User.objects.create_user('op', password='x', is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename='view_servicerequest'))
        self.client.force_login(staff)
        url = reverse('admin_dispute', args=[order.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, {'decision': 'resolve', 'note': 'x'})
        order.refresh_from_db()
        self.assertEqual(order.status, 'disputed')
        self.client.force_login(self.master.user)
        self.assertEqual(self.client.get(url).status_code, 302)   # admin emas — kirish sahifasiga
