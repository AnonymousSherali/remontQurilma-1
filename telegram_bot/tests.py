import json

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from otp.sms import ConsoleBackend
from repair_service import workflow
from repair_service.models import ServiceRequest
from repair_service.tests import AJAX, VALID, make_master

from . import client
from .models import LinkCode

CHAT = 555001
MASTER_CHAT = 777002


@override_settings(TELEGRAM_WEBHOOK_SECRET='s3cret', TELEGRAM_BOT_USERNAME='ts_bot', TELEGRAM_BOT_TOKEN='')
class TelegramBotTests(TestCase):
    def setUp(self):
        cache.clear()
        client.SENT.clear()
        ConsoleBackend.sent.clear()
        self.master = make_master()
        self.order = ServiceRequest.objects.create(name='Malika', phone='+998901112233', master=self.master)

    def update(self, payload, secret='s3cret'):
        return self.client.post(reverse('telegram_webhook'), json.dumps(payload), content_type='application/json',
                                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=secret)

    def message(self, chat, text):
        return self.update({'update_id': 1, 'message': {'message_id': 1, 'chat': {'id': chat}, 'text': text}})

    def press(self, chat, data):
        return self.update({'update_id': 2, 'callback_query': {
            'id': 'cb1', 'data': data, 'message': {'message_id': 9, 'chat': {'id': chat}}}})

    def last_text(self):
        return next(p['text'] for m, p in reversed(client.SENT) if m == 'sendMessage')

    def link_master(self):
        code = LinkCode.issue(self.master).code
        self.message(MASTER_CHAT, f'/start m{code}')
        self.master.refresh_from_db()

    def test_maxfiy_sarlavhasiz_rad_etiladi(self):
        self.assertEqual(self.update({}, secret='wrong').status_code, 403)

    def test_mijoz_buyurtmani_ulaydi_va_sms_orniga_telegram(self):
        self.message(CHAT, f'/start o{self.order.review_token.hex}')
        self.order.refresh_from_db()
        self.assertEqual(self.order.telegram_chat_id, CHAT)
        self.assertIn(f'#{self.order.pk}', self.last_text())
        with self.captureOnCommitCallbacks(execute=True):
            workflow.apply(self.order, workflow.MASTER, 'accept')
        self.assertIn('qabul qildi', self.last_text())
        self.assertFalse([p for p, _ in ConsoleBackend.sent if p == self.order.phone])  # SMS ketmadi

    def test_notogri_kalit(self):
        self.message(CHAT, '/start onotahex')
        self.assertFalse(ServiceRequest.objects.filter(telegram_chat_id=CHAT).exists())

    def test_usta_ulanadi_va_tugma_bilan_boshqaradi(self):
        self.link_master()
        self.assertEqual(self.master.telegram_chat_id, MASTER_CHAT)
        # Kod bir martalik
        self.assertIsNotNone(LinkCode.objects.get().used_at)

        self.press(MASTER_CHAT, f'a:{self.order.pk}:accept')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'accepted')
        edited = [p for m, p in client.SENT if m == 'editMessageText'][-1]
        self.assertIn('Qabul qilindi', edited['text'])
        self.assertIn(f'a:{self.order.pk}:arrive', json.dumps(edited['reply_markup']))

    def test_begona_chat_tugmasi_ishlamaydi(self):
        self.link_master()
        self.press(123456, f'a:{self.order.pk}:accept')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'new')

    def test_qoidalar_botda_ham_amal_qiladi(self):
        self.link_master()
        for action in ('accept', 'arrive'):
            self.press(MASTER_CHAT, f'a:{self.order.pk}:{action}')
        self.press(MASTER_CHAT, f'a:{self.order.pk}:start')  # narx kelishilmagan
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'arrived')
        answer = [p for m, p in client.SENT if m == 'answerCallbackQuery'][-1]
        self.assertIn('narx', answer['text'])

    def test_yangi_buyurtma_ustaga_tugma_bilan(self):
        self.link_master()
        client.SENT.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('repair_service:submit_request'), dict(VALID, master=self.master.pk), **AJAX)
        sent = [p for m, p in client.SENT if m == 'sendMessage' and p['chat_id'] == MASTER_CHAT][-1]
        self.assertIn('Yangi buyurtma', sent['text'])
        self.assertIn(':accept', json.dumps(sent['reply_markup']))

    def test_eskirgan_kod(self):
        from datetime import timedelta
        link = LinkCode.issue(self.master)
        LinkCode.objects.filter(pk=link.pk).update(created_at=link.created_at - timedelta(hours=1))
        self.message(MASTER_CHAT, f'/start m{link.code}')
        self.master.refresh_from_db()
        self.assertIsNone(self.master.telegram_chat_id)

    def test_buyurtmalar_va_stop(self):
        self.link_master()
        self.message(MASTER_CHAT, '/buyurtmalar')
        self.assertIn(f'#{self.order.pk}', self.last_text())
        self.message(MASTER_CHAT, '/stop')
        self.master.refresh_from_db()
        self.assertIsNone(self.master.telegram_chat_id)

    def test_kabinetdan_ulash(self):
        self.client.force_login(self.master.user)
        response = self.client.post(reverse('telegram_bot:connect'))
        self.assertTrue(response['Location'].startswith('https://t.me/ts_bot?start=m'))
        self.assertContains(self.client.get(reverse('masters:dashboard')), "Telegram")

    def test_buyurtma_sahifasida_tugma(self):
        page = self.client.get(self.order.get_customer_url())
        self.assertContains(page, f'https://t.me/ts_bot?start=o{self.order.review_token.hex}')

    def test_admin_usta_biriktirsa_xabar(self):
        from django.contrib.auth import get_user_model
        self.link_master()
        client.SENT.clear()
        order = ServiceRequest.objects.create(name='X', phone='+998901112299')
        admin = get_user_model().objects.create_superuser('a', 'a@a.uz', 'x-Parol-123')
        self.client.force_login(admin)
        data = {'name': 'X', 'phone': '+998901112299', 'master': self.master.pk, 'status': 'new', 'quantity': 1,
                'language': 'uz', 'milestones-TOTAL_FORMS': 0, 'milestones-INITIAL_FORMS': 0,
                'events-TOTAL_FORMS': 0, 'events-INITIAL_FORMS': 0,
                'photos-TOTAL_FORMS': 0, 'photos-INITIAL_FORMS': 0,
                'messages-TOTAL_FORMS': 0, 'messages-INITIAL_FORMS': 0}
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('admin:repair_service_servicerequest_change', args=[order.pk]), data)
        order.refresh_from_db()
        self.assertEqual(order.master, self.master)
        self.assertTrue([p for m, p in client.SENT if m == 'sendMessage' and p['chat_id'] == MASTER_CHAT])
