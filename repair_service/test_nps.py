from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from config import stats
from telegram_bot import client as tg

from . import nps
from .models import NpsResponse, ServiceRequest
from .test_warranty import confirmed_order
from .tests import make_master


class NpsTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        tg.SENT.clear()
        self.master = make_master('Usta', '+998911111111')
        self.order = confirmed_order(self.master)

    def test_sahifada_va_bir_marta(self):
        page = self.client.get(self.order.get_customer_url())
        self.assertContains(page, "tavsiya qilasizmi")
        url = reverse('repair_service:nps_submit', args=[self.order.review_token])
        self.client.post(url, {'score': '11'})
        self.assertFalse(NpsResponse.objects.exists())
        self.client.post(url, {'score': '9', 'comment': 'Tez va sifatli'})
        self.client.post(url, {'score': '2'})                                # takror — qabul qilinmaydi
        self.assertEqual(NpsResponse.objects.get().score, 9)
        self.assertNotContains(self.client.get(self.order.get_customer_url()), 'name="score"')

    def test_tasdiqlanmagan_buyurtmada_yoq(self):
        order = ServiceRequest.objects.create(name='A', phone='+998901112233', master=self.master)
        with self.assertRaises(nps.NpsError):
            nps.submit(order, 8)

    @override_settings(TELEGRAM_CHAT_ID='-100')
    def test_norozi_mijoz_adminga(self):
        with self.captureOnCommitCallbacks(execute=True):
            nps.submit(self.order, 3, 'Usta kechikdi')
        self.assertTrue(any('Norozi mijoz' in p['text'] and 'Usta kechikdi' in p['text'] for m, p in tg.SENT))

    def test_eslatma_faqat_bepul_kanal_va_bir_marta(self):
        later = timezone.now() + timedelta(hours=25)
        self.assertEqual(nps.send_invites(later), 0)                        # Telegram yo'q — SMS yuborilmaydi
        other = confirmed_order(self.master)
        ServiceRequest.objects.filter(pk=other.pk).update(telegram_chat_id=777)
        self.assertEqual(nps.send_invites(later), 1)
        self.assertTrue(any(p.get('chat_id') == 777 and '#nps' in p['text'] for m, p in tg.SENT))
        self.assertEqual(nps.send_invites(later), 0)

    def test_statistika(self):
        for i, score in enumerate([10, 9, 8, 3]):
            nps.submit(self.order if i == 0 else confirmed_order(self.master), score)
        data = stats.collect(30)['nps']
        self.assertEqual((data['count'], data['score']), (4, 25))            # 50% − 25%
        self.client.force_login(User.objects.create_superuser('a', 'a@example.com', 'x'))
        self.assertContains(self.client.get(reverse('admin_stats')), 'Mijozlar fikri (NPS)')
        self.assertEqual(self.client.get(reverse('admin:repair_service_npsresponse_changelist')).status_code, 200)
