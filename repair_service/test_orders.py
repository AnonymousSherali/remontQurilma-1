from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from masters.tests import verify_phone
from otp.sms import ConsoleBackend

from . import workflow
from .models import ServiceRequest
from .tests import AJAX, VALID, make_master


class CustomerOrderTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        ConsoleBackend.sent.clear()
        self.master = make_master()

    def submit(self, **extra):
        response = self.client.post(reverse('repair_service:submit_request'), dict(VALID, master=self.master.pk, **extra),
                                    **AJAX)
        return response.json(), ServiceRequest.objects.latest('pk')

    def test_ariza_kuzatish_havolasi_va_sms(self):
        with self.captureOnCommitCallbacks(execute=True):
            data, order = self.submit()
        self.assertEqual(data['track_url'], order.get_customer_url())
        texts = dict(ConsoleBackend.sent)
        self.assertIn(order.get_customer_url(), texts['+998901234567'])   # mijozga havola
        self.assertIn(order.get_master_url(), texts[self.master.phone])     # ustaga xabar
        self.assertEqual(list(order.events.values_list('status', 'actor')), [('new', 'customer')])

    def test_havola_bilan_korish_mumkin_lekin_boshqarib_bolmaydi(self):
        _, order = self.submit()
        page = self.client.get(order.get_customer_url())
        self.assertContains(page, 'data-otp')            # SMS tasdiq bloki
        self.assertNotContains(page, 'order_action')
        self.client.post(reverse('repair_service:order_action', args=[order.review_token, 'cancel']))
        order.refresh_from_db()
        self.assertEqual(order.status, 'new')

    def test_sms_bilan_bekor_qilish(self):
        _, order = self.submit()
        verify_phone(self.client, order.phone)
        self.client.post(reverse('repair_service:order_action', args=[order.review_token, 'cancel']))
        order.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')

    def test_narxsiz_ish_boshlanmaydi(self):
        _, order = self.submit()
        workflow.apply(order, workflow.MASTER, 'accept')
        workflow.apply(order, workflow.MASTER, 'arrive')
        with self.assertRaises(workflow.WorkflowError):
            workflow.apply(order, workflow.MASTER, 'start')

    def test_usta_kelgach_mijoz_bekor_qila_olmaydi_faqat_nizo(self):
        _, order = self.submit()
        workflow.apply(order, workflow.MASTER, 'accept')
        workflow.apply(order, workflow.MASTER, 'arrive')
        verify_phone(self.client, order.phone)
        self.client.post(reverse('repair_service:order_action', args=[order.review_token, 'cancel']))
        order.refresh_from_db()
        self.assertEqual(order.status, 'arrived')
        self.client.post(reverse('repair_service:order_action', args=[order.review_token, 'dispute']))
        order.refresh_from_db()
        self.assertEqual(order.status, 'disputed')

    def test_timeline(self):
        _, order = self.submit()
        workflow.apply(order, workflow.MASTER, 'accept')
        order.refresh_from_db()
        tl = workflow.timeline(order)
        self.assertEqual([s['state'] for s in tl['steps']], ['done', 'current', 'upcoming', 'upcoming', 'upcoming', 'upcoming'])
        self.assertEqual([s['actor'] for s in tl['steps']], ['customer', 'master', 'master', 'master', 'master', 'customer'])
        self.assertEqual(tl['progress'], 20)

    def test_mening_buyurtmalarim(self):
        _, order = self.submit()
        self.assertNotContains(self.client.get(reverse('repair_service:my_orders')), f'#{order.pk}')
        verify_phone(self.client, order.phone)
        self.assertContains(self.client.get(reverse('repair_service:my_orders')), order.get_customer_url())
        self.client.post(reverse('repair_service:my_orders_logout'))
        self.assertNotContains(self.client.get(reverse('repair_service:my_orders')), order.get_customer_url())

    def test_bosh_sahifada_status_timeline(self):
        response = self.client.get(reverse('repair_service:index'))
        self.assertContains(response, 'tl-section')
        self.assertContains(response, 'Joyida')
        self.assertEqual(response.content.decode().count('tl__step--customer'), 2)


class RussianTests(TestCase):
    def tearDown(self):
        translation.activate('uz')

    def test_rus_tilidagi_sahifalar(self):
        response = self.client.get('/ru/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="ru"')
        self.assertContains(response, 'Каждый шаг')
        self.assertContains(response, 'Найти мастера')
        self.assertContains(self.client.get('/ru/ustalar/'), 'Мастера')

    def test_ozbekcha_standart(self):
        response = self.client.get('/')
        self.assertContains(response, 'lang="uz"')
        self.assertContains(response, 'Har bir qadam')

    def test_rus_tilida_xatolar_va_bazadagi_nomlar(self):
        from masters.models import Category
        Category.objects.create(name='Santexnik', name_ru='Сантехник', slug='santexnik')
        self.assertContains(self.client.get('/ru/'), 'Сантехник')
        self.assertContains(self.client.get('/'), 'Santexnik')
        cache.clear()
        with translation.override('ru'):
            url = reverse('repair_service:submit_request')
        self.assertTrue(url.startswith('/ru/'))
        data = self.client.post(url, {'name': 'A', 'phone': '1', 'consent': 'on'}, **AJAX).json()
        self.assertIn('Имя должно', data['errors']['name'])

    def test_rus_tilida_ariza_tili_saqlanadi(self):
        cache.clear()
        self.client.post('/ru/submit/', VALID, **AJAX)
        self.assertEqual(ServiceRequest.objects.get().language, 'ru')
