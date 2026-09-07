from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import ServiceRequest, Service, Brand, Testimonial

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
VALID = {'name': 'Ali Valiyev', 'phone': '+998 (90) 123-45-67'}


class IndexPageTests(TestCase):
    def test_index_ochiladi(self):
        response = self.client.get(reverse('repair_service:index'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'index.html')

    def test_bazadagi_xizmatlar_korsatiladi(self):
        Service.objects.create(name='Nasos almashtirish', price_from=120000)
        response = self.client.get(reverse('repair_service:index'))
        self.assertContains(response, 'Nasos almashtirish')

    def test_xizmat_bolmasa_default_narxlar_qoladi(self):
        response = self.client.get(reverse('repair_service:index'))
        self.assertContains(response, "Kapital ta'mir")

    def test_bazadagi_brendlar_korsatiladi(self):
        Brand.objects.create(name='Toshiba')
        response = self.client.get(reverse('repair_service:index'))
        self.assertContains(response, 'Toshiba')

    def test_faol_bolmagan_yozuvlar_korsatilmaydi(self):
        Brand.objects.create(name='YashirinBrend', is_active=False)
        Service.objects.create(name='YashirinXizmat', is_active=False)
        response = self.client.get(reverse('repair_service:index'))
        self.assertNotContains(response, 'YashirinBrend')
        self.assertNotContains(response, 'YashirinXizmat')

    def test_sharhlar_yulduzlari_bilan_korsatiladi(self):
        Testimonial.objects.create(client_name='Nodira', text="Zo'r ish", rating=4)
        response = self.client.get(reverse('repair_service:index'))
        self.assertContains(response, 'Nodira')
        self.assertContains(response, 'Zo&#x27;r ish')

    def test_nashr_qilinmagan_sharh_korsatilmaydi(self):
        Testimonial.objects.create(
            client_name='Yashirin', text="Ko'rinmasin", rating=1, is_published=False
        )
        response = self.client.get(reverse('repair_service:index'))
        self.assertNotContains(response, 'Yashirin')


class SubmitRequestTests(TestCase):
    def setUp(self):
        self.url = reverse('repair_service:submit_request')

    def test_togri_ariza_saqlanadi(self):
        response = self.client.post(self.url, VALID, **AJAX)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertEqual(ServiceRequest.objects.count(), 1)

        saved = ServiceRequest.objects.get()
        self.assertEqual(saved.name, 'Ali Valiyev')
        self.assertEqual(saved.status, 'new')

    def test_muammo_tavsifi_saqlanadi(self):
        payload = dict(VALID, problem_description='Suvni chiqarmayapti')
        self.client.post(self.url, payload, **AJAX)
        self.assertEqual(
            ServiceRequest.objects.get().problem_description, 'Suvni chiqarmayapti'
        )

    def test_qisqa_ism_rad_etiladi(self):
        response = self.client.post(self.url, dict(VALID, name='A'), **AJAX)
        self.assertEqual(response.status_code, 400)
        self.assertIn('name', response.json()['errors'])
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_notogri_telefon_rad_etiladi(self):
        response = self.client.post(self.url, dict(VALID, phone='8-905-123'), **AJAX)
        self.assertEqual(response.status_code, 400)
        self.assertIn('phone', response.json()['errors'])
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_notogri_email_rad_etiladi(self):
        response = self.client.post(self.url, dict(VALID, email='mavhum'), **AJAX)
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json()['errors'])

    def test_email_ixtiyoriy(self):
        response = self.client.post(self.url, dict(VALID, email=''), **AJAX)
        self.assertTrue(response.json()['success'])
        self.assertIsNone(ServiceRequest.objects.get().email)

    def test_bir_nechta_xato_birga_qaytadi(self):
        response = self.client.post(self.url, {'name': '', 'phone': ''}, **AJAX)
        errors = response.json()['errors']
        self.assertIn('name', errors)
        self.assertIn('phone', errors)

    def test_probellar_kesiladi(self):
        self.client.post(self.url, dict(VALID, name='   Ali Valiyev   '), **AJAX)
        self.assertEqual(ServiceRequest.objects.get().name, 'Ali Valiyev')

    def test_js_siz_yuborishda_natija_sahifasi(self):
        response = self.client.post(self.url, VALID)
        self.assertTemplateUsed(response, 'result.html')
        self.assertEqual(ServiceRequest.objects.count(), 1)

    def test_js_siz_xato_bosh_sahifada_korsatiladi(self):
        response = self.client.post(self.url, {'name': '', 'phone': '123'})
        self.assertTemplateUsed(response, 'index.html')
        self.assertContains(response, "Arizani yuborib bo'lmadi")
        self.assertContains(response, 'Ism kamida 2 ta belgidan')

    def test_get_soravi_rad_etiladi(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)


class TestimonialModelTests(TestCase):
    def test_yulduzlar_soni(self):
        testimonial = Testimonial.objects.create(client_name='X', text='y', rating=3)
        self.assertEqual(len(testimonial.stars_filled), 3)
        self.assertEqual(len(testimonial.stars_empty), 2)


class SeedDemoCommandTests(TestCase):
    def test_buyruq_malumot_qoshadi(self):
        call_command('seed_demo', stdout=StringIO())
        self.assertTrue(Service.objects.exists())
        self.assertTrue(Brand.objects.exists())
        self.assertTrue(Testimonial.objects.exists())

    def test_takroriy_ishga_tushirish_nusxa_yaratmaydi(self):
        call_command('seed_demo', stdout=StringIO())
        count = Service.objects.count()
        call_command('seed_demo', stdout=StringIO())
        self.assertEqual(Service.objects.count(), count)
