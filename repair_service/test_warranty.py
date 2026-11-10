from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from masters.tests import verify_phone
from otp.sms import ConsoleBackend
from payments import services as payments

from . import photos, warranty, workflow
from .models import OrderEvent, Service, ServiceRequest, WarrantyClaim
from .tests import make_master

PHONE = '+998901112233'


def confirmed_order(master, plan='cash', days_ago=0, **extra):
    order = ServiceRequest.objects.create(name='Malika', phone=PHONE, master=master, **extra)
    workflow.apply(order, workflow.MASTER, 'accept')
    payments.propose_quote(order, 300000, plan)
    payments.approve_quote(order)
    if plan != 'cash':
        payments.mark_held(order.milestones.get())
    for action in ('arrive', 'start', 'complete'):
        workflow.apply(order, workflow.MASTER, action)
    workflow.apply(order, workflow.CUSTOMER, 'confirm')
    if days_ago:
        OrderEvent.objects.filter(order=order, status='confirmed').update(
            created_at=timezone.now() - timedelta(days=days_ago))
    order.refresh_from_db()
    return order


class WarrantyTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        self.master = make_master('Usta', '+998911111111')
        with self.captureOnCommitCallbacks(execute=True):
            self.order = confirmed_order(self.master)
        ConsoleBackend.sent.clear()
        self.url = self.order.get_customer_url()

    def tearDown(self):
        translation.activate('uz')

    def claim(self, order=None, text='Almashtirilgan kran yana oqyapti'):
        with self.captureOnCommitCallbacks(execute=True):
            return warranty.file_claim(order or self.order, text)

    def test_muddat(self):
        start, end = warranty.period(self.order)
        self.assertEqual((end - start).days, 30)
        self.assertTrue(warranty.can_claim(self.order))
        old = confirmed_order(self.master, days_ago=31)
        self.assertFalse(warranty.is_active(old))
        with self.assertRaises(warranty.WarrantyError):
            warranty.file_claim(old, 'Yana buzildi, qarab bering')

    def test_tasdiqlanmagan_buyurtmada_kafolat_yoq(self):
        order = ServiceRequest.objects.create(name='A', phone=PHONE, master=self.master)
        self.assertIsNone(warranty.period(order))
        self.assertIsNone(warranty.context(order)['warranty'])

    def test_xizmat_boyicha_muddat(self):
        item = Service.objects.create(name='Diagnostika', price_from=50000, warranty_days=0)
        order = confirmed_order(self.master, catalog_item=item)
        self.assertIsNone(warranty.period(order))
        item.warranty_days = 90
        item.save()
        order.refresh_from_db()
        self.assertEqual(warranty.days_for(order), 90)
        self.assertTrue(warranty.is_active(confirmed_order(self.master, catalog_item=item, days_ago=60)))

    def test_toliq_oqim(self):
        claim = self.claim()
        self.assertIn('Kafolat murojaati', [t for p, t in ConsoleBackend.sent if p == self.master.phone][-1])
        with self.assertRaises(warranty.WarrantyError):   # bir vaqtda bitta faol murojaat
            self.claim()
        self.assertEqual(photos.allowed_kinds(self.order, workflow.CUSTOMER), ['problem'])
        self.assertEqual(photos.allowed_kinds(self.order, workflow.MASTER), ['after'])

        with self.captureOnCommitCallbacks(execute=True):
            warranty.master_fixed(claim, 'Prokladka almashtirildi')
        self.assertIn('tuzatganini', [t for p, t in ConsoleBackend.sent if p == PHONE][-1])
        warranty.customer_resolve(claim)
        claim.refresh_from_db()
        self.assertEqual(claim.status, 'resolved')
        self.assertIsNotNone(claim.closed_at)
        self.assertEqual(photos.allowed_kinds(self.order, workflow.CUSTOMER), [])
        self.assertTrue(warranty.can_claim(self.order))    # muddat ichida yana murojaat qilish mumkin
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'confirmed')   # buyurtma holati o'zgarmaydi

    def test_eskalatsiya_faqat_ustaga_vaqt_berilgach(self):
        claim = self.claim()
        with self.assertRaises(warranty.WarrantyError):
            warranty.customer_escalate(claim)
        WarrantyClaim.objects.filter(pk=claim.pk).update(created_at=timezone.now() - timedelta(hours=49))
        warranty.customer_escalate(claim)
        claim.refresh_from_db()
        self.assertEqual(claim.status, 'escalated')
        with self.assertRaises(warranty.WarrantyError):
            warranty.master_fixed(claim)

    def test_naqd_buyurtmaga_kompensatsiya_yoq(self):
        claim = self.claim()
        warranty.master_fixed(claim)
        warranty.customer_escalate(claim)
        with self.assertRaises(warranty.WarrantyError):
            warranty.admin_decide(claim, 'compensated', 'Qaytarildi', Decimal('100000'))
        with self.assertRaises(warranty.WarrantyError):
            warranty.admin_decide(claim, 'rejected', '')
        with self.captureOnCommitCallbacks(execute=True):
            warranty.admin_decide(claim, 'rejected', 'Boshqa joydan oqyapti — kafolat holati emas')
        claim.refresh_from_db()
        self.assertEqual(claim.status, 'rejected')
        with self.assertRaises(warranty.WarrantyError):
            warranty.admin_decide(claim, 'resolved')

    @override_settings(GUARANTEE_MAX_AMOUNT=200000)
    def test_kompensatsiya_chegarasi(self):
        order = confirmed_order(self.master, plan='on_completion')
        self.assertEqual(warranty.paid_online(order), 300000)
        claim = self.claim(order)
        warranty.master_fixed(claim)
        warranty.customer_escalate(claim)
        with self.assertRaises(warranty.WarrantyError):
            warranty.admin_decide(claim, 'compensated', '', Decimal('250000'))
        warranty.admin_decide(claim, 'compensated', 'Qisman qaytarildi', Decimal('200000'))
        claim.refresh_from_db()
        self.assertEqual((claim.status, claim.compensation), ('compensated', Decimal('200000')))

    def test_avtomatik_yopish(self):
        claim = self.claim()
        warranty.master_fixed(claim)
        call_command('process_orders', verbosity=0)
        claim.refresh_from_db()
        self.assertEqual(claim.status, 'fixed')
        WarrantyClaim.objects.filter(pk=claim.pk).update(updated_at=timezone.now() - timedelta(days=8))
        call_command('process_orders', verbosity=0)
        claim.refresh_from_db()
        self.assertEqual(claim.status, 'resolved')

    def test_mijoz_sahifasi(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'id="kafolat"')
        self.assertNotContains(response, 'id="wdesc"')   # tasdiqlanmagan raqam murojaat qila olmaydi
        claim_url = reverse('repair_service:warranty_claim', args=[self.order.review_token])
        self.assertEqual(self.client.post(claim_url, {'description': 'Kran yana oqyapti'}).status_code, 404)

        verify_phone(self.client, PHONE)
        self.assertContains(self.client.get(self.url), 'id="wdesc"')
        self.client.post(claim_url, {'description': 'qisqa'})
        self.assertFalse(self.order.warranty_claims.exists())
        self.client.post(claim_url, {'description': 'Kran yana oqyapti, suv tomchilayapti'})
        claim = self.order.warranty_claims.get()
        response = self.client.get(self.url)
        self.assertContains(response, 'Kran yana oqyapti')
        self.assertNotContains(response, 'administratorga</button>')   # hali erta

        self.client.post(reverse('repair_service:warranty_action', args=[self.order.review_token, claim.pk, 'resolve']))
        claim.refresh_from_db()
        self.assertEqual(claim.status, 'resolved')

    def test_usta_sahifasi(self):
        claim = self.claim()
        self.client.force_login(self.master.user)
        self.assertContains(self.client.get(reverse('masters:dashboard')), 'kafolat murojaati')
        self.assertContains(self.client.get(self.order.get_master_url()), 'Tuzatdim')
        self.client.post(reverse('masters:warranty_fixed', args=[self.order.pk, claim.pk]), {'note': 'Tuzatildi'})
        claim.refresh_from_db()
        self.assertEqual((claim.status, claim.master_note), ('fixed', 'Tuzatildi'))

        other = make_master('Begona', '+998922222222')
        self.client.force_login(other.user)
        response = self.client.post(reverse('masters:warranty_fixed', args=[self.order.pk, claim.pk]))
        self.assertEqual(response.status_code, 404)

    def test_admin_qarori(self):
        claim = self.claim()
        warranty.master_fixed(claim)
        warranty.customer_escalate(claim)
        self.client.force_login(User.objects.create_superuser('admin', 'a@example.com', 'x'))
        url = reverse('admin:repair_service_warrantyclaim_change', args=[claim.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:repair_service_warrantyclaim_changelist')).status_code, 200)
        self.client.post(url, {'status': 'compensated', 'resolution': '', 'compensation': '50000'})
        claim.refresh_from_db()
        self.assertEqual(claim.status, 'escalated')      # naqd buyurtma — rad etiladi, saqlanmaydi
        self.client.post(url, {'status': 'rejected', 'resolution': 'Kafolat holati emas', 'compensation': ''})
        claim.refresh_from_db()
        self.assertEqual((claim.status, claim.resolution), ('rejected', 'Kafolat holati emas'))
