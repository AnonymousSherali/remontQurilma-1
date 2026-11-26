from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from otp.sms import ConsoleBackend
from payments.models import Purchase
from repair_service.models import AnalyticsEvent
from repair_service.tests import make_master

from . import onboarding
from .models import Category, Master
from .tests import verify_phone

UA = {'HTTP_USER_AGENT': 'Mozilla/5.0 (Linux; Android 14) Chrome/130'}


class OnboardingTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        ConsoleBackend.sent.clear()

    def test_ustalar_sahifasi_va_manba(self):
        page = self.client.get(reverse('masters:for_masters') + '?ref=UABC12&utm_source=olx', **UA)
        self.assertContains(page, 'oylik to')
        self.assertContains(page, '30 kun bepul TOP')
        self.assertEqual(self.client.session['master_ref'], 'UABC12')
        self.assertContains(self.client.get('/'), reverse('masters:for_masters'))
        cat = Category.objects.create(name='Santexnik', slug='santexnik')
        verify_phone(self.client, '+998935557788', 'register')
        self.client.post(reverse('masters:register'), {
            'full_name': 'Yangi Usta', 'phone': '+998 (93) 555-77-88', 'password1': 'Kuchli-parol-77',
            'password2': 'Kuchli-parol-77', 'categories': [cat.pk], 'experience_years': 2, 'service_radius_km': 10,
            'latitude': '41.3111', 'longitude': '69.2799', 'consent': 'on'}, **UA)
        master = Master.objects.get(phone='+998935557788')
        self.assertEqual(master.signup_source, 'olx')
        self.assertTrue(AnalyticsEvent.objects.filter(name='master_signup').exists())

    def test_birinchi_tasdiqda_bepul_top_bir_marta(self):
        master = make_master('Yangi', '+998911111111', verified=False)
        self.assertFalse(master.is_promoted)
        master.is_verified = True
        with self.captureOnCommitCallbacks(execute=True):
            master.save()
        master.refresh_from_db()
        self.assertTrue(master.is_promoted)
        self.assertTrue(master.welcome_bonus_given)
        self.assertIn('bepul TOP', ConsoleBackend.sent[-1][1])
        until = master.promoted_until
        master.is_verified = False
        master.save()
        master.is_verified = True
        with self.captureOnCommitCallbacks(execute=True):
            master.save()
        master.refresh_from_db()
        self.assertEqual(master.promoted_until, until)
        self.assertEqual(Purchase.objects.filter(plan='welcome').count(), 1)

    def test_admin_amali_bilan_ham(self):
        master = make_master('Yangi', '+998911111111', verified=False)
        self.client.force_login(User.objects.create_superuser('a', 'a@example.com', 'x'))
        self.client.post(reverse('admin:masters_master_changelist'), {'action': 'verify', '_selected_action': [master.pk]})
        master.refresh_from_db()
        self.assertTrue(master.is_promoted)

    @override_settings(NEW_MASTER_FREE_TOP_DAYS=0)
    def test_ochirilgan(self):
        master = make_master('Yangi', '+998911111111', verified=True)
        self.assertIsNone(onboarding.grant_welcome_bonus(master))

    def test_tayyorlik_royxati(self):
        master = make_master('Usta', '+998911111111')
        data = onboarding.checklist(master)
        self.assertEqual((data['done'], data['total']), (0, 7))
        master.payout_card, master.bio = '8600123412341234', 'Santexnik, 8 yillik tajriba, quvur va kranlar ustasi.'
        master.save()
        self.assertEqual(onboarding.checklist(master)['done'], 2)
        self.client.force_login(master.user)
        self.assertContains(self.client.get(reverse('masters:dashboard')), 'tayyorlik: 2/7')
