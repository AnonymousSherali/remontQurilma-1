from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from masters.models import Category, Master, Review

from .models import Brand, Service, ServiceRequest, Testimonial
from .phone import format_phone, normalize_phone

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
VALID = {'name': 'Ali Valiyev', 'phone': '+998 (90) 123-45-67', 'consent': 'on'}


def make_master(name='Usta', phone='+998911111111', lat=41.3, lng=69.25, verified=True, categories=(), **extra):
    user = get_user_model().objects.create_user(username=phone.lstrip('+'), password='x-Parol-123')
    master = Master.objects.create(
        user=user, full_name=name, phone=phone, latitude=lat, longitude=lng, is_verified=verified, **extra,
    )
    master.categories.set(categories)
    return master


class PhoneTests(TestCase):
    def test_turli_yozilishlar_bir_xil_saqlanadi(self):
        for raw in ['+998 (90) 123-45-67', '998901234567', '90 123 45 67', '+998901234567']:
            self.assertEqual(normalize_phone(raw), '+998901234567')

    def test_notogri_raqam(self):
        for raw in ['', '12345', '+7 900 123 45 67', '+9989012345678']:
            with self.assertRaises(ValidationError):
                normalize_phone(raw)

    def test_formatlash(self):
        self.assertEqual(format_phone('+998901234567'), '+998 90 123-45-67')
        self.assertEqual(format_phone('noma\'lum'), 'noma\'lum')


class IndexPageTests(TestCase):
    def test_bosh_sahifa_bosh_bazada_ochiladi(self):
        response = self.client.get(reverse('repair_service:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kapital ta'mir")  # zaxira narxlar
        self.assertNotContains(response, 'tekshirilgan usta</div>')  # 0 ta usta — da'vo yo'q

    def test_bazadagi_kontent_korsatiladi(self):
        cat = Category.objects.create(name='Santexnik', slug='santexnik', icon='🚰')
        Service.objects.create(name='Kran almashtirish', price_from=80000, category=cat)
        Brand.objects.create(name='Toshiba')
        make_master('Bekzod Karimov', categories=[cat])
        response = self.client.get(reverse('repair_service:index'))
        self.assertContains(response, 'Kran almashtirish')
        self.assertContains(response, 'Toshiba')
        self.assertContains(response, 'Bekzod Karimov')
        self.assertContains(response, '?category=santexnik')

    def test_faol_bolmagan_va_tasdiqlanmaganlar_korinmaydi(self):
        Brand.objects.create(name='YashirinBrend', is_active=False)
        Service.objects.create(name='YashirinXizmat', is_active=False)
        make_master('Tekshirilmagan Usta', verified=False)
        response = self.client.get(reverse('repair_service:index'))
        for text in ('YashirinBrend', 'YashirinXizmat', 'Tekshirilmagan Usta'):
            self.assertNotContains(response, text)

    def test_haqiqiy_baho_bolsa_qolda_kiritilgan_sharh_chiqmaydi(self):
        Testimonial.objects.create(client_name='Qolda Yozilgan', text='...', rating=5)
        response = self.client.get(reverse('repair_service:index'))
        self.assertContains(response, 'Qolda Yozilgan')

        master = make_master()
        Review.objects.create(master=master, author_name='Haqiqiy Mijoz', quality=5, punctuality=5, price=5, politeness=5)
        response = self.client.get(reverse('repair_service:index'))
        self.assertContains(response, 'Haqiqiy Mijoz')
        self.assertNotContains(response, 'Qolda Yozilgan')


class SubmitRequestTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse('repair_service:submit_request')

    def test_togri_ariza_saqlanadi(self):
        response = self.client.post(self.url, dict(VALID, problem_description='Kran oqyapti'), **AJAX)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        saved = ServiceRequest.objects.get()
        self.assertEqual(saved.phone, '+998901234567')  # yagona formatda
        self.assertEqual(saved.problem_description, 'Kran oqyapti')
        self.assertTrue(saved.consent)
        self.assertIsNone(saved.email)

    def test_roziliksiz_qabul_qilinmaydi(self):
        data = dict(VALID)
        data.pop('consent')
        response = self.client.post(self.url, data, **AJAX)
        self.assertEqual(response.status_code, 400)
        self.assertIn('consent', response.json()['errors'])

    def test_validatsiya_xatolari(self):
        response = self.client.post(self.url, {'name': 'A', 'phone': '555', 'email': 'x', 'consent': 'on'}, **AJAX)
        errors = response.json()['errors']
        self.assertEqual(set(errors), {'name', 'phone', 'email'})
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_bot_tuzogi(self):
        response = self.client.post(self.url, dict(VALID, website='http://spam.example'), **AJAX)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ServiceRequest.objects.count(), 0)

    @override_settings(REQUEST_RATE_LIMIT=2)
    def test_spam_cheklovi(self):
        for _ in range(2):
            self.assertEqual(self.client.post(self.url, VALID, **AJAX).status_code, 200)
        self.assertEqual(self.client.post(self.url, VALID, **AJAX).status_code, 429)

    def test_aniq_ustaga_ariza(self):
        cat = Category.objects.create(name='Elektrik', slug='elektrik')
        master = make_master(categories=[cat])
        response = self.client.post(self.url, dict(VALID, master=master.pk), **AJAX)
        self.assertIn(master.full_name, response.json()['message'])
        saved = ServiceRequest.objects.get()
        self.assertEqual(saved.master, master)
        self.assertEqual(saved.category, cat)  # yo'nalish ustanikidan olinadi

    def test_ustaga_boshqa_yonalish_arizasi_tuzatiladi(self):
        plumber = Category.objects.create(name='Santexnik', slug='santexnik')
        electrician = Category.objects.create(name='Elektrik', slug='elektrik')
        master = make_master(categories=[plumber])
        self.client.post(self.url, dict(VALID, master=master.pk, category=electrician.pk), **AJAX)
        self.assertEqual(ServiceRequest.objects.get().category, plumber)

    def test_tasdiqlanmagan_yoki_band_ustaga_ariza_berilmaydi(self):
        hidden = make_master(phone='+998911111112', verified=False)
        busy = make_master(phone='+998911111113', is_available=False)
        for master in (hidden, busy):
            response = self.client.post(self.url, dict(VALID, master=master.pk), **AJAX)
            self.assertEqual(response.status_code, 400)
            self.assertIn('master', response.json()['errors'])
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_js_siz_yuborish(self):
        ok = self.client.post(self.url, VALID)
        self.assertTemplateUsed(ok, 'result.html')
        bad = self.client.post(self.url, {'name': '', 'phone': '1'})
        self.assertEqual(bad.status_code, 400)
        self.assertContains(bad, "Arizani yuborib bo'lmadi", status_code=400)

    def test_get_rad_etiladi(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)


class AdminTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('admin', 'a@a.uz', 'Admin-parol-1')
        self.client.force_login(self.admin)

    def test_admin_sahifalari_ochiladi(self):
        master = make_master()
        request = ServiceRequest.objects.create(name='X', phone='+998901112233', master=master, status='completed')
        urls = [
            reverse('admin:index'),
            reverse('admin:repair_service_servicerequest_changelist'),
            reverse('admin:repair_service_servicerequest_change', args=[request.pk]),
            reverse('admin:masters_master_changelist'),
            reverse('admin:masters_master_change', args=[master.pk]),
            reverse('admin:masters_review_changelist'),
            reverse('admin:masters_category_changelist'),
            reverse('admin:auth_user_changelist'),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_dashboard_korsatkichlari(self):
        make_master(verified=False)
        ServiceRequest.objects.create(name='X', phone='+998901112233')
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'Tasdiq kutayotgan ustalar')
        kpis = {k['title']: k['value'] for k in response.context['kpis']}
        self.assertEqual(kpis['Yangi arizalar'], 1)
        self.assertEqual(kpis['Tasdiq kutayotgan ustalar'], 1)
        self.assertEqual(response.context['chart_days'][-1]['count'], 1)

    def test_ustani_tasdiqlash_amali(self):
        master = make_master(verified=False)
        self.client.post(reverse('admin:masters_master_changelist'), {
            'action': 'verify', '_selected_action': [master.pk],
        })
        master.refresh_from_db()
        self.assertTrue(master.is_verified)


class SeedDemoCommandTests(TestCase):
    def test_buyruq_va_takrorlanmaslik(self):
        call_command('seed_demo', '--masters', stdout=StringIO())
        counts = (Category.objects.count(), Service.objects.count(), Master.objects.count(), Review.objects.count())
        self.assertTrue(all(counts))
        call_command('seed_demo', '--masters', stdout=StringIO())
        self.assertEqual(
            counts,
            (Category.objects.count(), Service.objects.count(), Master.objects.count(), Review.objects.count()),
        )
        # Demo baholar ham faqat bajarilgan ariza orqali
        self.assertFalse(Review.objects.filter(service_request__isnull=True).exists())
