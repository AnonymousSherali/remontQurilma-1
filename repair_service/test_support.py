from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from otp.sms import ConsoleBackend
from telegram_bot import client as tg

from . import support
from .models import SupportMessage, SupportThread
from .tests import AJAX, make_master


class SupportTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        ConsoleBackend.sent.clear()
        tg.SENT.clear()
        self.url = reverse('repair_service:support')

    @override_settings(TELEGRAM_CHAT_ID='-100')
    def test_mehmon_yozadi_operator_javob_beradi(self):
        self.assertContains(self.client.get('/'), 'data-support-toggle')
        data = self.client.post(self.url, {'text': 'Konditsioner tozalash qancha turadi?', 'name': 'Aziz',
                                           'phone': '+998 90 111 22 33'}, **AJAX).json()
        self.assertEqual([m['text'] for m in data['messages']], ['Konditsioner tozalash qancha turadi?'])
        thread = SupportThread.objects.get()
        self.assertEqual((thread.name, thread.phone), ('Aziz', '+998901112233'))
        self.assertIn('ts_support', self.client.cookies)
        self.assertTrue(any('Yordam #' in p['text'] for m, p in tg.SENT))
        self.client.post(self.url, {'text': 'Yana bir savol'}, **AJAX)
        self.assertEqual(SupportThread.objects.count(), 1)                   # o'sha suhbat
        self.assertEqual(sum('Yordam #' in p['text'] for m, p in tg.SENT), 1)  # adminga bitta xabar

        admin = User.objects.create_superuser('a', 'a@example.com', 'x')
        operator = self.client_class()
        operator.force_login(admin)
        self.assertContains(operator.get(reverse('admin_support')), 'Aziz')
        operator.post(reverse('admin_support_thread', args=[thread.pk]), {'text': '150 000 so\'mdan'})
        self.assertIn('/yordam/', ConsoleBackend.sent[-1][1])
        self.assertEqual(support.unanswered(), [])
        fresh = self.client.get(self.url, {'after': data['messages'][0]['id']}, **AJAX).json()['messages']
        self.assertEqual(fresh[-1]['sender'], 'Operator')
        self.assertContains(self.client.get('/'), "150 000 so")                # vidjetda tarix ko'rinadi

    def test_sms_havola_boshqa_qurilmada_ochadi(self):
        self.client.post(self.url, {'text': 'Salom'}, **AJAX)
        thread = SupportThread.objects.get()
        other = self.client_class()
        page = other.get(reverse('repair_service:support_thread', args=[thread.token]))
        self.assertContains(page, 'Salom')
        other.post(self.url, {'text': 'Telefondan yozyapman'}, **AJAX)
        self.assertEqual(thread.messages.count(), 2)

    def test_usta_suhbati_telegramga_javob(self):
        master = make_master('Usta', '+998911111111', telegram_chat_id=999)
        self.client.force_login(master.user)
        self.client.post(self.url, {'text': "To'lov qachon tushadi?"}, **AJAX)
        thread = SupportThread.objects.get()
        self.assertEqual(thread.master, master)
        support.reply(thread, None, 'Dushanba kuni')
        self.assertTrue(any(p.get('chat_id') == 999 and 'Dushanba' in p['text'] for m, p in tg.SENT))

    def test_cheklovlar_va_xss(self):
        self.assertEqual(self.client.post(self.url, {'text': '   '}, **AJAX).status_code, 400)
        self.client.post(self.url, {'text': '<script>alert(1)</script>'}, **AJAX)
        self.assertNotIn('<script>alert(1)</script>', self.client.get('/').content.decode())
        for _i in range(support.PER_MINUTE):
            self.client.post(self.url, {'text': 'x'}, **AJAX)
        self.assertEqual(self.client.post(self.url, {'text': 'x'}, **AJAX).status_code, 400)
        self.client.cookies['ts_support'] = 'buzilgan'
        self.assertEqual(self.client.get(self.url, **AJAX).json()['messages'], [])

    def test_boshqa_suhbatni_oqib_bolmaydi(self):
        self.client.post(self.url, {'text': 'Maxfiy savol'}, **AJAX)
        stranger = self.client_class()
        self.assertEqual(stranger.get(self.url, **AJAX).json()['messages'], [])
        self.assertFalse(SupportMessage.objects.filter(from_staff=True).exists())
