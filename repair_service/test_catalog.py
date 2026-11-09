from django.core.cache import cache
from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from masters.models import Category
from masters.tests import verify_phone
from payments import services as payments

from . import workflow
from .models import Service, ServiceRequest
from .tests import AJAX, VALID, make_master


class CatalogTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')  # /ru/ ga so'rov yuborgan testlardan keyin til oqib qolmasligi uchun
        self.addCleanup(translation.activate, 'uz')
        self.plumb = Category.objects.create(name='Santexnik', name_ru='Сантехник', slug='santexnik')
        self.elec = Category.objects.create(name='Elektrik', slug='elektrik')
        self.tap = Service.objects.create(category=self.plumb, name='Kran almashtirish', name_ru='Замена крана',
                                          price_from=80000, price_type='fixed', unit='piece', duration_minutes=40,
                                          includes="Eski kranni yechish\nGermetik", is_popular=True)
        self.socket = Service.objects.create(category=self.elec, name="Rozetka o'rnatish", price_from=40000,
                                             unit='point')
        self.url = reverse('repair_service:catalog')

    def test_katalog_sahifasi_va_filtrlar(self):
        page = self.client.get(self.url)
        self.assertContains(page, 'Kran almashtirish')
        self.assertContains(page, "80\xa0000 so'm")  # uzilmas probel
        self.assertContains(page, 'Germetik')
        self.assertContains(page, '~40 daqiqa')
        only_elec = self.client.get(self.url, {'category': 'elektrik'})
        self.assertNotContains(only_elec, 'Kran almashtirish')
        self.assertContains(self.client.get(self.url, {'q': 'kran'}), 'Kran almashtirish')
        self.assertNotContains(self.client.get(self.url, {'q': 'kran'}), "Rozetka")

    def test_rus_tilida_qidiruv_va_nom(self):
        page = self.client.get('/ru/narxlar/', {'q': 'крана'})
        self.assertContains(page, 'Замена крана')
        self.assertContains(page, '~40 мин')

    def test_tanlangan_xizmat_formaga_tushadi(self):
        page = self.client.get(self.url, {'item': self.tap.pk})
        self.assertContains(page, f'name="catalog_item" value="{self.tap.pk}"')
        self.assertContains(page, 'name="quantity"')  # dona bo'yicha — miqdor so'raladi

    def test_katalogdan_buyurtma_taxminiy_narx(self):
        self.client.post(reverse('repair_service:submit_request'),
                         dict(VALID, catalog_item=self.tap.pk, quantity=3), **AJAX)
        order = ServiceRequest.objects.get()
        self.assertEqual(order.catalog_item, self.tap)
        self.assertEqual(order.category, self.plumb)  # yo'nalish xizmatdan aniqlanadi
        self.assertEqual(order.catalog_estimate, 240000)

    def test_usta_bajarmaydigan_xizmat_rad_etiladi(self):
        master = make_master(categories=[self.elec])
        response = self.client.post(reverse('repair_service:submit_request'),
                                    dict(VALID, master=master.pk, catalog_item=self.tap.pk), **AJAX)
        self.assertEqual(response.status_code, 400)
        self.assertIn('catalog_item', response.json()['errors'])

    def test_bosh_sahifada_faqat_ommabop(self):
        page = self.client.get('/')
        self.assertContains(page, 'Kran almashtirish')
        self.assertNotContains(page, "Rozetka o&#x27;rnatish")
        self.assertContains(page, self.url)

    def test_narx_korinishi(self):
        tpl = Template('{% include "partials/price.html" %}')
        render = lambda item: tpl.render(Context({'item': item})).strip()
        self.assertIn("80\xa0000 so'm", render(self.tap))
        self.assertIn('dona', render(self.tap))
        self.assertIn("40\xa0000 so'mdan", render(self.socket))
        self.assertEqual(render(Service(name='x', price_from=0)), 'Bepul')

    def test_usta_profilida_narxlar(self):
        master = make_master(categories=[self.plumb])
        page = self.client.get(reverse('masters:detail', args=[master.pk]))
        self.assertContains(page, 'Kran almashtirish')
        self.assertNotContains(page, 'Rozetka')


class QuoteDeviationTests(TestCase):
    """Usta narxi katalogdan 20% dan ko'p farq qilsa — izoh shart, mijoz farqni ko'radi."""

    def setUp(self):
        cat = Category.objects.create(name='Santexnik', slug='santexnik')
        item = Service.objects.create(category=cat, name='Kran', price_from=100000, price_type='fixed')
        self.master = make_master(categories=[cat])
        self.order = ServiceRequest.objects.create(name='M', phone='+998901112233', master=self.master,
                                                   catalog_item=item, quantity=1)
        workflow.apply(self.order, workflow.MASTER, 'accept')
        self.client.force_login(self.master.user)
        self.url = reverse('masters:quote_propose', args=[self.order.pk])

    def test_katta_farq_izohsiz_qabul_qilinmaydi(self):
        self.client.post(self.url, {'amount': 150000, 'plan': 'cash', 'note': ''})
        self.assertIsNone(payments.get_quote(self.order))
        self.client.post(self.url, {'amount': 150000, 'plan': 'cash', 'note': "Qo'shimcha quvur kerak bo'ldi"})
        self.assertEqual(payments.get_quote(self.order).amount, 150000)

    def test_kichik_farq_izohsiz_mumkin(self):
        self.client.post(self.url, {'amount': 115000, 'plan': 'cash', 'note': ''})
        self.assertEqual(payments.get_quote(self.order).amount, 115000)

    def test_usta_sahifasida_katalog_narxi_oldindan(self):
        page = self.client.get(reverse('masters:order', args=[self.order.pk]))
        self.assertContains(page, 'value="100000"')

    def test_mijoz_farqni_koradi(self):
        payments.propose_quote(self.order, 150000, 'cash', 'sabab')
        self.client.logout()
        verify_phone(self.client, self.order.phone)
        page = self.client.get(self.order.get_customer_url())
        self.assertContains(page, '50% qimmat')
        payments.propose_quote(self.order, 90000, 'cash')
        self.assertContains(self.client.get(self.order.get_customer_url()), '10% arzon')
