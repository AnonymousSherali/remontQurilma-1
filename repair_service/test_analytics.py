from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from config import stats

from . import analytics
from .models import AnalyticsEvent, ServiceRequest
from .tests import AJAX, VALID

UA = {'HTTP_USER_AGENT': 'Mozilla/5.0 (Linux; Android 14) Chrome/130'}


class AnalyticsTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')

    def test_utm_manba_arizaga_yoziladi(self):
        self.client.get('/?utm_source=Instagram&utm_medium=cpc&utm_campaign=kuz', **UA)
        self.client.get('/narxlar/', **UA)                                   # manba saqlanib qoladi
        self.client.post('/e/', {'e': 'form_start', 'p': '/'}, **UA)
        self.client.post(reverse('repair_service:submit_request'), VALID, **UA, **AJAX)
        order = ServiceRequest.objects.get()
        self.assertEqual((order.source, order.medium, order.campaign, order.landing_path),
                         ('instagram', 'cpc', 'kuz', '/'))
        names = list(AnalyticsEvent.objects.order_by('id').values_list('name', flat=True))
        self.assertEqual(names, ['page_view', 'page_view', 'form_start', 'request'])
        self.assertEqual(AnalyticsEvent.objects.values('visitor').distinct().count(), 1)

    def test_yonaltiruvchi_sayt(self):
        self.client.get('/', HTTP_REFERER='https://www.google.com/search?q=santexnik', **UA)
        self.assertEqual(AnalyticsEvent.objects.get().source, 'google')
        self.client.cookies.clear()
        self.client.get('/', HTTP_REFERER='https://t.me/some_channel', **UA)
        self.assertEqual(AnalyticsEvent.objects.latest('id').medium, 'social')
        self.client.cookies.clear()
        self.client.get('/?promo=DABC', **UA)
        self.assertEqual(AnalyticsEvent.objects.latest('id').source, 'referal')

    def test_dnt_va_botlar(self):
        self.client.get('/', HTTP_DNT='1', **UA)
        self.client.get('/', HTTP_USER_AGENT='Googlebot/2.1')
        response = self.client.get('/', HTTP_SEC_GPC='1', **UA)
        self.assertFalse(AnalyticsEvent.objects.exists())
        self.assertNotIn(analytics.VISITOR_COOKIE, response.cookies)

    def test_shaxsiy_sahifalar_kuzatilmaydi(self):
        self.client.get('/buyurtmalarim/', **UA)
        self.client.get('/kirish/', **UA)
        self.assertFalse(AnalyticsEvent.objects.exists())

    def test_soxta_cookie_va_beacon(self):
        self.client.cookies['ts_src'] = 'soxta'
        self.client.get('/', **UA)                                            # buzilgan imzo — yangisi yoziladi
        self.assertEqual(AnalyticsEvent.objects.get().source, 'direct')
        self.client.post('/e/', {'e': 'page_view'}, **UA)                    # boshqa nomlar qabul qilinmaydi
        self.client.post('/e/', {'e': 'form_start', 'p': '/'}, **UA)
        self.client.post('/e/', {'e': 'form_start', 'p': '/'}, **UA)          # takror — bitta
        self.assertEqual(AnalyticsEvent.objects.filter(name='form_start').count(), 1)

    def test_eski_hodisalar_ochiriladi(self):
        self.client.get('/', **UA)
        AnalyticsEvent.objects.update(created_at=timezone.now() - timedelta(days=200))
        call_command('process_orders', verbosity=0)
        self.assertFalse(AnalyticsEvent.objects.exists())

    def test_statistika(self):
        self.client.get('/?utm_source=telegram', **UA)
        self.client.post(reverse('repair_service:submit_request'), VALID, **UA, **AJAX)
        data = stats.collect(30)['traffic']
        row = next(r for r in data['sources'] if r['source'] == 'telegram')
        self.assertEqual((row['visits'], row['requests'], row['conversion']), (1, 1, 100.0))
        self.client.force_login(User.objects.create_superuser('a', 'a@example.com', 'x'))
        self.assertContains(self.client.get(reverse('admin_stats')), 'Saytdan arizagacha')
