from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from masters.models import Category
from masters.tests import verify_phone
from otp.sms import ConsoleBackend
from payments.models import PromoCode
from telegram_bot import client as tg

from . import marketing
from .models import Campaign, MarketingConsent, ServiceRequest
from .tests import AJAX, VALID, make_master

NOON = timezone.make_aware(timezone.datetime(2026, 11, 25, 12, 0))
NIGHT = timezone.make_aware(timezone.datetime(2026, 11, 25, 23, 30))


class MarketingTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        ConsoleBackend.sent.clear()
        tg.SENT.clear()

    def campaign(self, **extra):
        defaults = dict(title='Kuz aksiyasi', text_uz='Santexnika ishlariga 15% chegirma', text_ru='Скидка 15%',
                        status=Campaign.STATUS_SCHEDULED, scheduled_at=NOON - timedelta(hours=1), use_sms=True)
        defaults.update(extra)
        return Campaign.objects.create(**defaults)

    def test_rozilik_ixtiyoriy(self):
        self.client.post(reverse('repair_service:submit_request'), VALID, **AJAX)
        self.assertFalse(MarketingConsent.objects.exists())
        cache.clear()
        self.client.post(reverse('repair_service:submit_request'), {**VALID, 'marketing': 'on'}, **AJAX)
        self.assertTrue(marketing.is_subscribed('+998901234567'))
        self.assertNotIn('name="marketing" value="on" checked', self.client.get('/').content.decode())

    def test_faqat_rozilik_berganlarga_va_bir_marta(self):
        marketing.subscribe('+998901111111')
        marketing.subscribe('+998902222222', language='ru')
        marketing.subscribe('+998903333333')
        marketing.unsubscribe(phone='+998903333333')
        c = self.campaign(promo=PromoCode.objects.create(code='KUZ15', kind='percent', value=15))
        self.assertEqual(marketing.process(NOON), 2)
        texts = dict(ConsoleBackend.sent)
        self.assertNotIn('+998903333333', texts)
        self.assertIn('KUZ15', texts['+998901111111'])
        self.assertIn('/obuna/bekor/', texts['+998901111111'])
        self.assertIn('Скидка 15%', texts['+998902222222'])
        c.refresh_from_db()
        self.assertEqual((c.status, c.sent), ('done', 2))
        self.assertEqual(marketing.process(NOON), 0)                         # takror yuborilmaydi

    def test_tinch_soatlar_va_partiya(self):
        for i in range(5):
            marketing.subscribe(f'+99890000000{i}')
        c = self.campaign()
        self.assertEqual(marketing.process(NIGHT), 0)
        with override_settings(CAMPAIGN_BATCH=3):
            self.assertEqual(marketing.process(NOON), 3)
            c.refresh_from_db()
            self.assertEqual(c.status, 'sending')
            self.assertEqual(marketing.process(NOON), 2)
        c.refresh_from_db()
        self.assertEqual((c.status, c.sent), ('done', 5))

    def test_kanal_tanlash_telegram_sms_yoq(self):
        marketing.subscribe('+998901111111')
        marketing.subscribe('+998902222222')
        ServiceRequest.objects.create(name='A', phone='+998901111111', telegram_chat_id=777)
        c = self.campaign(use_sms=False)
        marketing.process(NOON)
        c.refresh_from_db()
        self.assertEqual((c.sent, c.skipped), (1, 1))
        self.assertEqual([p['chat_id'] for m, p in tg.SENT], [777])
        self.assertFalse(ConsoleBackend.sent)                                # SMS o'chirilgan

    def test_auditoriyalar(self):
        cat = Category.objects.create(name='Elektrik', slug='elektrik')
        for phone in ('+998901111111', '+998902222222'):
            marketing.subscribe(phone)
        ServiceRequest.objects.create(name='A', phone='+998901111111', category=cat)
        self.assertEqual([k for k, _o in marketing.audience(self.campaign(audience='category', category=cat))],
                         ['+998901111111'])
        self.assertEqual([k for k, _o in marketing.audience(self.campaign(audience='inactive', inactive_days=30))],
                         ['+998902222222'])
        master = make_master('Usta', '+998911111111')
        self.assertEqual(marketing.audience(self.campaign(audience='masters')), [(f'm{master.pk}', master)])

    def test_obunani_bekor_qilish_sahifasi(self):
        consent = marketing.subscribe('+998901111111')
        url = reverse('repair_service:unsubscribe', args=[consent.token])
        self.assertContains(self.client.get(url), 'voz kechasizmi')
        self.assertTrue(marketing.is_subscribed('+998901111111'))            # GET bekor qilmaydi
        self.assertContains(self.client.post(url), 'Obuna bekor qilindi')
        self.assertFalse(marketing.is_subscribed('+998901111111'))

    def test_buyurtma_sahifasida(self):
        order = ServiceRequest.objects.create(name='A', phone='+998901111111')
        url = reverse('repair_service:marketing_toggle', args=[order.review_token])
        self.assertEqual(self.client.post(url, {'on': '1'}).status_code, 404)
        verify_phone(self.client, order.phone)
        self.client.post(url, {'on': '1'})
        self.assertTrue(marketing.is_subscribed(order.phone))
        self.client.post(url)
        self.assertFalse(marketing.is_subscribed(order.phone))

    def test_admin_va_cron(self):
        marketing.subscribe('+998901111111')
        admin = User.objects.create_superuser('a', 'a@example.com', 'x')
        self.client.force_login(admin)
        c = Campaign.objects.create(title='Yangilik', text_uz='Matn', use_sms=True)
        page = self.client.get(reverse('admin:repair_service_campaign_change', args=[c.pk]))
        self.assertContains(page, 'Obunani bekor qilish')
        self.client.post(reverse('admin:repair_service_campaign_changelist'),
                         {'action': 'schedule', '_selected_action': [c.pk]})
        c.refresh_from_db()
        self.assertEqual(c.status, 'scheduled')
        with mock.patch('repair_service.marketing.in_quiet_hours', return_value=False):
            call_command('process_orders', verbosity=0)
        c.refresh_from_db()
        self.assertEqual(c.sent, 1)
