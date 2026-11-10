import json
from datetime import timedelta
from io import BytesIO

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from otp.sms import ConsoleBackend
from payments import services as payments
from repair_service import workflow
from repair_service.models import OrderPhoto, ServiceRequest
from repair_service.tests import AJAX, VALID, make_master
from telegram_bot import client

from . import feed
from .models import Category

PAST = timedelta(minutes=30)


def open_order(category=None, age=PAST, **extra):
    order = ServiceRequest.objects.create(name='Malika', phone='+998901112233', category=category,
                                          address='Chilonzor 9-kvartal, 12-uy', **extra)
    ServiceRequest.objects.filter(pk=order.pk).update(created_at=timezone.now() - age)
    order.refresh_from_db()
    return order


class FeedTests(TestCase):
    def setUp(self):
        cache.clear()
        client.SENT.clear()
        ConsoleBackend.sent.clear()
        self.plumb = Category.objects.create(name='Santexnik', slug='santexnik')
        self.elec = Category.objects.create(name='Elektrik', slug='elektrik')
        self.master = make_master('Usta', '+998911111111', 41.30, 69.25, categories=[self.plumb], service_radius_km=10)
        self.client.force_login(self.master.user)

    def ids(self, master=None):
        return [o.pk for o in feed.open_orders(master or self.master)]

    def test_yonalish_va_radius_boyicha(self):
        near = open_order(self.plumb, latitude=41.31, longitude=69.25)
        far = open_order(self.plumb, latitude=41.60, longitude=69.25)       # ~33 km
        other = open_order(self.elec, latitude=41.30, longitude=69.25)
        no_loc = open_order(self.plumb)
        no_cat = open_order(None, latitude=41.30, longitude=69.25)
        taken = open_order(self.plumb, master=make_master('B', '+998922222222'))
        ids = self.ids()
        self.assertEqual(set(ids), {near.pk, no_loc.pk, no_cat.pk})
        self.assertEqual(ids[-1], no_loc.pk)  # joylashuvsiz — oxirida
        self.assertNotIn(far.pk, ids)
        self.assertNotIn(other.pk, ids)
        self.assertNotIn(taken.pk, ids)

    def test_tasdiqlanmagan_yoki_band_usta_kormaydi(self):
        open_order(self.plumb)
        self.master.is_available = False
        self.master.save()
        self.assertEqual(self.ids(), [])

    def test_lentada_shaxsiy_malumot_yoq(self):
        open_order(self.plumb, district='chilonzor', latitude=41.30, longitude=69.25,
                   problem_description='Kran oqyapti')
        page = self.client.get(reverse('masters:feed'))
        self.assertContains(page, 'Kran oqyapti')
        self.assertContains(page, 'Chilonzor')           # tuman nomi
        self.assertNotContains(page, '12-uy')            # aniq manzil
        self.assertNotContains(page, 'Malika')
        self.assertNotContains(page, '111-22-33')

    def test_olish_va_poyga(self):
        order = open_order(self.plumb)
        rival = make_master('Raqib', '+998933333333', categories=[self.plumb])
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('masters:feed_claim', args=[order.pk]))
        order.refresh_from_db()
        self.assertRedirects(response, order.get_master_url())
        self.assertEqual((order.master, order.status), (self.master, 'accepted'))
        self.assertIn('qabul qildi', dict(ConsoleBackend.sent)[order.phone])  # mijozga xabar
        with self.assertRaises(feed.FeedError):
            feed.claim(rival, order.pk)
        # Endi usta mijoz ma'lumotlarini ko'radi
        self.assertContains(self.client.get(order.get_master_url()), '12-uy')

    def test_begona_yonalishni_olib_bolmaydi(self):
        order = open_order(self.elec)
        self.client.post(reverse('masters:feed_claim', args=[order.pk]))
        order.refresh_from_db()
        self.assertIsNone(order.master)

    def test_pro_ustunligi(self):
        order = open_order(self.plumb, age=timedelta(minutes=2))
        with self.assertRaises(feed.FeedError):
            feed.claim(self.master, order.pk)
        self.assertFalse(feed.open_orders(self.master)[0].claimable)
        self.master.pro_until = timezone.now() + timedelta(days=1)
        self.master.save()
        self.assertEqual(feed.claim(self.master, order.pk).master, self.master)

    @override_settings(ACTIVE_ORDERS_LIMIT=1)
    def test_faol_buyurtmalar_limiti(self):
        feed.claim(self.master, open_order(self.plumb).pk)
        with self.assertRaises(feed.FeedError):
            feed.claim(self.master, open_order(self.plumb).pk)

    def test_voz_kechsa_lentaga_qaytadi(self):
        order = feed.claim(self.master, open_order(self.plumb).pk)
        payments.propose_quote(order, 100000, 'cash')
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('masters:request_action', args=[order.pk, 'cancel']))
        self.assertRedirects(response, reverse('masters:dashboard'))
        order.refresh_from_db()
        self.assertEqual((order.master, order.status), (None, 'new'))
        self.assertIsNone(payments.get_quote(order))               # eski narx taklifi o'chadi
        self.assertNotIn(order.pk, self.ids())                     # voz kechgan ustaga qayta chiqmaydi
        rival = make_master('Raqib', '+998933333333', categories=[self.plumb])
        self.assertFalse(feed.open_orders(rival)[0].claimable)     # PRO ustunligi qayta boshlanadi
        self.assertIn('voz kechdi', [t for p, t in ConsoleBackend.sent if p == order.phone][-1])

    def test_tolov_qilingan_buyurtmadan_voz_kechib_bolmaydi(self):
        order = feed.claim(self.master, open_order(self.plumb).pk)
        payments.propose_quote(order, 100000, 'on_completion')
        payments.approve_quote(order)
        payments.mark_held(order.milestones.get())
        with self.assertRaises(workflow.WorkflowError):
            workflow.apply(order, workflow.MASTER, 'cancel')

    def test_ariza_joylashuvi(self):
        url = reverse('repair_service:submit_request')
        self.client.post(url, dict(VALID, district='chilonzor', latitude='55.7', longitude='37.6'), **AJAX)
        order = ServiceRequest.objects.latest('pk')
        self.assertEqual(order.district, 'chilonzor')
        self.assertAlmostEqual(float(order.latitude), 41.275, places=2)   # tuman GPS'dan ustun
        cache.clear()
        r = self.client.post(url, dict(VALID, latitude='abc', longitude='999', district='hack'), **AJAX)
        self.assertTrue(r.json()['success'])                              # noto'g'ri joylashuv arizani buzmaydi
        self.assertIsNone(ServiceRequest.objects.latest('pk').latitude)


@override_settings(TELEGRAM_WEBHOOK_SECRET='s', TELEGRAM_BOT_USERNAME='b', TELEGRAM_BOT_TOKEN='')
class TelegramFeedAndPhotoTests(TestCase):
    CHAT = 9001

    def setUp(self):
        cache.clear()
        client.SENT.clear()
        client.FILES.clear()
        self.cat = Category.objects.create(name='Santexnik', slug='santexnik')
        self.master = make_master('Usta', '+998911111111', 41.30, 69.25, categories=[self.cat])
        self.master.telegram_chat_id = self.CHAT
        self.master.save()
        buffer = BytesIO()
        Image.new('RGB', (300, 200), (10, 120, 200)).save(buffer, format='JPEG')
        client.FILES['f1'] = client.FILES['f2'] = buffer.getvalue()

    def update(self, payload):
        return self.client.post(reverse('telegram_webhook'), json.dumps(payload), content_type='application/json',
                                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='s')

    def photo(self, chat, file_id='f1', caption=None):
        message = {'message_id': 1, 'chat': {'id': chat}, 'photo': [{'file_id': 'small'}, {'file_id': file_id}]}
        if caption:
            message['caption'] = caption
        return self.update({'message': message})

    def press(self, data):
        return self.update({'callback_query': {'id': 'cb', 'data': data,
                                               'message': {'message_id': 5, 'chat': {'id': self.CHAT}}}})

    def texts(self):
        return [p['text'] for m, p in client.SENT if m == 'sendMessage']

    def test_yangi_ochiq_buyurtma_xabari_va_olish(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('repair_service:submit_request'),
                             dict(VALID, category=self.cat.pk, address='Maxfiy 7-uy', problem_description='Kran'), **AJAX)
        order = ServiceRequest.objects.get()
        sent = [p for m, p in client.SENT if m == 'sendMessage' and p['chat_id'] == self.CHAT][-1]
        self.assertIn('Ochiq buyurtma', sent['text'])
        self.assertNotIn('Maxfiy', sent['text'])
        self.assertNotIn('Ali', sent['text'])
        self.assertIn(f'c:{order.pk}', json.dumps(sent['reply_markup']))

        self.press(f'c:{order.pk}')                       # PRO emas, 10 daqiqa o'tmagan
        order.refresh_from_db()
        self.assertIsNone(order.master)
        ServiceRequest.objects.filter(pk=order.pk).update(created_at=timezone.now() - PAST)
        self.press(f'c:{order.pk}')
        order.refresh_from_db()
        self.assertEqual(order.master, self.master)
        edited = [p for m, p in client.SENT if m == 'editMessageText'][-1]
        self.assertIn('Maxfiy 7-uy', edited['text'])      # olgandan keyin manzil ochiladi

    def test_usta_rasmi_bosqichga_qarab(self):
        order = ServiceRequest.objects.create(name='M', phone='+998901112233', master=self.master)
        workflow.apply(order, workflow.MASTER, 'accept')
        self.photo(self.CHAT, caption='Eski kran')
        photo = OrderPhoto.objects.get()
        self.assertEqual((photo.kind, photo.uploaded_by, photo.caption), ('before', 'master', 'Eski kran'))
        workflow.apply(order, workflow.MASTER, 'arrive')
        payments.propose_quote(order, 1000, 'cash')
        payments.approve_quote(order)
        workflow.apply(order, workflow.MASTER, 'start')
        self.photo(self.CHAT, 'f2')
        self.assertEqual(OrderPhoto.objects.filter(kind='after').count(), 1)

    def test_bir_nechta_buyurtmada_soraydi(self):
        orders = []
        for i in range(2):
            o = ServiceRequest.objects.create(name=f'M{i}', phone=f'+99890111220{i}', master=self.master)
            workflow.apply(o, workflow.MASTER, 'accept')
            orders.append(o)
        self.photo(self.CHAT, 'f1')
        self.photo(self.CHAT, 'f2')                       # albom: savol bir marta
        self.assertFalse(OrderPhoto.objects.exists())
        self.assertEqual(sum('qaysi buyurtma' in t for t in self.texts()), 1)
        self.press(f'p:{orders[0].pk}')
        self.assertEqual(OrderPhoto.objects.filter(order=orders[0]).count(), 2)
        self.press(f'p:{orders[1].pk}')                   # navbat bo'shagan — hech narsa qo'shilmaydi
        self.assertEqual(OrderPhoto.objects.count(), 2)

    def test_mijoz_rasmi_va_begona(self):
        order = ServiceRequest.objects.create(name='M', phone='+998901112233', telegram_chat_id=555)
        self.photo(555)
        self.assertEqual(OrderPhoto.objects.get().kind, 'problem')
        self.assertEqual(OrderPhoto.objects.get().order, order)
        self.photo(424242)                                # ulanmagan chat
        self.assertEqual(OrderPhoto.objects.count(), 1)

    def test_buzilgan_fayl(self):
        order = ServiceRequest.objects.create(name='M', phone='+998901112233', master=self.master)
        workflow.apply(order, workflow.MASTER, 'accept')
        client.FILES['bad'] = b'not an image'
        self.photo(self.CHAT, 'bad')
        self.assertFalse(OrderPhoto.objects.exists())
