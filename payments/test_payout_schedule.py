from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from otp.sms import ConsoleBackend
from repair_service.test_warranty import confirmed_order
from repair_service.tests import make_master

from . import payouts
from .models import Milestone, Payout
from .payout_providers import PROVIDERS, PayoutProvider

MONDAY = timezone.make_aware(timezone.datetime(2026, 11, 30, 10, 0))   # dushanba


class PayoutScheduleTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        ConsoleBackend.sent.clear()
        self.master = make_master('Usta', '+998911111111', payout_card='8600123412341234', payout_holder='U U')
        self.small = make_master('Kichik', '+998922222222', payout_card='9860000011112222')
        confirmed_order(self.master, plan='on_completion')          # 300 000 → ustaga 270 000
        Milestone.objects.update(released_at=MONDAY - timedelta(days=2))

    def test_haftalik_tayyorlash_va_tasdiqlash(self):
        self.assertEqual(payouts.prepare_weekly(MONDAY - timedelta(days=1)), [])    # yakshanba — yo'q
        created = payouts.prepare_weekly(MONDAY)
        self.assertEqual(len(created), 1)
        payout = created[0]
        self.assertEqual((payout.status, payout.amount, payout.master), ('prepared', 270000, self.master))
        self.assertEqual(payouts.pending(), [])                               # ikki marta to'lanmaydi
        self.assertEqual(payouts.prepare_weekly(MONDAY), [])                  # kunda bir marta
        self.assertIsNone(Milestone.objects.get().paid_out_at)
        with self.captureOnCommitCallbacks(execute=True):
            payouts.confirm(payout)
        payout.refresh_from_db()
        self.assertEqual(payout.status, 'paid')
        self.assertIsNotNone(Milestone.objects.get().paid_out_at)
        self.assertIn("270 000 so'm kartangizga (•••• 1234)", [t for p, t in ConsoleBackend.sent
                                                               if p == self.master.phone][-1])

    @override_settings(PAYOUT_MIN_AMOUNT=500000)
    def test_kichik_summa_keyingi_haftaga(self):
        self.assertEqual(payouts.prepare_weekly(MONDAY), [])
        self.assertEqual(len(payouts.pending()), 1)

    def test_yangi_chiqarilgan_kutadi_va_kartasiz_otmaydi(self):
        Milestone.objects.update(released_at=MONDAY - timedelta(hours=2))      # PAYOUT_DELAY_HOURS=24
        self.assertEqual(payouts.prepare_weekly(MONDAY), [])
        self.master.payout_card = ''
        self.master.save()
        Milestone.objects.update(released_at=MONDAY - timedelta(days=3))
        self.assertEqual(payouts.prepare_weekly(MONDAY), [])

    def test_bekor_qilish(self):
        payout = payouts.prepare_weekly(MONDAY)[0]
        self.assertTrue(payouts.cancel_prepared(payout))
        self.assertEqual(len(payouts.pending()), 1)

    def test_avtomatik_provayder(self):
        class Fake(PayoutProvider):
            name = 'fake'

            def send(self, payout):
                return 'paid', 'EXT-1', ''
        PROVIDERS['fake'] = Fake
        try:
            with override_settings(PAYOUT_PROVIDER='fake'):
                payout = payouts.prepare_weekly(MONDAY)[0]
        finally:
            PROVIDERS.pop('fake')
        payout.refresh_from_db()
        self.assertEqual((payout.status, payout.provider_ref, payout.provider), ('paid', 'EXT-1', 'fake'))

    def test_admin_va_kabinet(self):
        Milestone.objects.update(released_at=timezone.now() - timedelta(days=2))
        admin = User.objects.create_superuser('a', 'a@example.com', 'x')
        self.client.force_login(admin)
        self.client.post(reverse('admin:payments_payout_pending'), {'prepare': '1'})
        payout = Payout.objects.get()
        self.assertEqual(payout.status, 'prepared')
        self.client.post(reverse('admin:payments_payout_changelist'),
                         {'action': 'confirm_paid', '_selected_action': [payout.pk]})
        payout.refresh_from_db()
        self.assertEqual(payout.status, 'paid')
        self.client.force_login(self.master.user)
        self.assertContains(self.client.get(reverse('masters:dashboard')), "Keyingi to")
