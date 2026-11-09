from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from repair_service.models import ServiceRequest
from repair_service.tests import make_master

from payments import services as payments

from .forms import ReviewForm
from .geo import bounding_box, haversine_km
from .models import Category, Master, Review
from .services import search_masters

CENTER = (41.311, 69.279)  # Toshkent markazi


def verify_phone(client, phone, purpose='login'):
    """Testda SMS kod bosqichini o'tkazib yuborish: raqamni sessiyada tasdiqlangan deb belgilaymiz."""
    from django.utils import timezone
    session = client.session
    data = session.get('verified_phones', {})
    data[f'{purpose}:{phone}'] = timezone.now().timestamp()
    session['verified_phones'] = data
    session.save()


def review(master, score, **extra):
    return Review.objects.create(
        master=master, author_name='Mijoz', quality=score, punctuality=score, price=score, politeness=score, **extra,
    )


class GeoTests(TestCase):
    def test_haversine(self):
        self.assertAlmostEqual(haversine_km(*CENTER, *CENTER), 0)
        # Toshkent – Samarqand ~ 270 km
        self.assertAlmostEqual(haversine_km(41.311, 69.279, 39.654, 66.975), 270, delta=10)

    def test_bounding_box_radiusni_qamraydi(self):
        lat_min, lat_max, lng_min, lng_max = bounding_box(*CENTER, 10)
        self.assertAlmostEqual(haversine_km(lat_min, CENTER[1], *CENTER), 10, delta=0.1)
        self.assertAlmostEqual(haversine_km(CENTER[0], lng_max, *CENTER), 10, delta=0.1)


class SearchTests(TestCase):
    def setUp(self):
        self.plumber = Category.objects.create(name='Santexnik', slug='santexnik')
        self.electric = Category.objects.create(name='Elektrik', slug='elektrik')
        self.near = make_master('Yaqin', '+998911000001', 41.315, 69.280, categories=[self.plumber])
        self.mid = make_master('Orta', '+998911000002', 41.350, 69.280, categories=[self.plumber])  # ~4.3 km
        self.far = make_master('Uzoq', '+998911000003', 41.600, 69.280, categories=[self.plumber],
                               service_radius_km=50)  # ~32 km

    def test_masofa_boyicha_saralash_va_radius(self):
        names = [m.full_name for m in search_masters(lat=CENTER[0], lng=CENTER[1], radius_km=15)]
        self.assertEqual(names, ['Yaqin', 'Orta'])
        self.assertLess(search_masters(lat=CENTER[0], lng=CENTER[1])[0].distance_km, 1)

    def test_usta_oz_xizmat_radiusidan_tashqariga_korsatilmaydi(self):
        self.mid.service_radius_km = 3
        self.mid.save()
        names = [m.full_name for m in search_masters(lat=CENTER[0], lng=CENTER[1], radius_km=15)]
        self.assertEqual(names, ['Yaqin'])

    def test_kategoriya_tasdiq_va_bandlik_filtrlari(self):
        make_master('Elektrik', '+998911000004', 41.312, 69.279, categories=[self.electric])
        make_master('Tasdiqsiz', '+998911000005', 41.312, 69.279, verified=False, categories=[self.plumber])
        make_master('Band', '+998911000006', 41.312, 69.279, is_available=False, categories=[self.plumber])
        names = {m.full_name for m in search_masters(category=self.plumber, lat=CENTER[0], lng=CENTER[1])}
        self.assertEqual(names, {'Yaqin', 'Orta'})

    def test_bayes_reytingi(self):
        # 1 ta 5★ baho 20 ta 4.8★ bahodan yuqori turmasligi kerak
        for _ in range(1):
            review(self.near, 5)
        for _ in range(20):
            review(self.mid, 5)
        for _ in range(4):
            review(self.mid, 4)
        self.near.refresh_from_db()
        self.mid.refresh_from_db()
        self.assertGreater(self.near.rating_avg, self.mid.rating_avg)
        self.assertGreater(self.mid.ranking_score, self.near.ranking_score)
        ranked = search_masters(lat=CENTER[0], lng=CENTER[1], sort='rating')
        self.assertEqual(ranked[0], self.mid)

    def test_joylashuvsiz_reyting_boyicha(self):
        review(self.far, 5)
        review(self.far, 5)
        self.assertEqual(search_masters()[0], self.far)

    def test_ustalar_sahifasi_va_tuman(self):
        response = self.client.get(reverse('masters:list'), {'category': 'santexnik', 'district': 'mirobod', 'radius': 10})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['location_label'], 'Mirobod')
        self.assertContains(response, 'Yaqin')
        self.assertNotContains(response, 'Uzoq')

    def test_tuman_gpsdan_ustun(self):
        response = self.client.get(reverse('masters:list'), {'district': 'sergeli', 'lat': '41.31', 'lng': '69.28'})
        self.assertEqual(response.context['location_label'], 'Sergeli')

    def test_notogri_parametrlar_yiqitmaydi(self):
        response = self.client.get(reverse('masters:list'), {'lat': 'abc', 'lng': '999', 'radius': 'x', 'sort': 'hack'})
        self.assertEqual(response.status_code, 200)

    def test_api_yaxlitlangan_koordinata(self):
        data = self.client.get(reverse('api_masters'), {'lat': CENTER[0], 'lng': CENTER[1]}).json()
        self.assertEqual(data['count'], 2)
        first = data['results'][0]
        self.assertEqual(first['name'], 'Yaqin')
        # Aniq koordinata (41.315) oshkor qilinmaydi — 2 xonagacha (~1 km) yaxlitlangan
        self.assertNotEqual(first['lat'], 41.315)
        self.assertEqual(first['lat'], round(first['lat'], 2))
        self.assertNotIn('phone', first)


class MasterDetailTests(TestCase):
    def test_tasdiqlanmagan_profil_yashirin(self):
        master = make_master(verified=False)
        url = reverse('masters:detail', args=[master.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(master.user)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_profil_mezonlar_bilan(self):
        master = make_master()
        Review.objects.create(master=master, author_name='Dilnoza', quality=5, punctuality=3, price=4, politeness=5,
                              comment='Yaxshi')
        response = self.client.get(reverse('masters:detail', args=[master.pk]))
        self.assertContains(response, 'Dilnoza')
        self.assertEqual(dict(response.context['criteria'])["O'z vaqtida kelishi"], 3.0)
        self.assertNotContains(response, master.phone)  # usta raqami ommaga ko'rsatilmaydi


class RegistrationTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name='Santexnik', slug='santexnik')
        self.data = {
            'full_name': 'Test Ustaev', 'phone': '+998 (93) 555-77-88',
            'password1': 'Kuchli-parol-77', 'password2': 'Kuchli-parol-77',
            'categories': [self.cat.pk], 'experience_years': 4, 'service_radius_km': 10,
            'latitude': '41.31112345678', 'longitude': '69.27998765432',  # brauzer 6 xonadan ko'p beradi
            'consent': 'on',
        }
        verify_phone(self.client, '+998935557788', 'register')

    def test_sms_tasdiqsiz_royxatdan_otib_bolmaydi(self):
        self.client.session.flush()
        self.client.cookies.clear()
        response = self.client.post(reverse('masters:register'), self.data)
        self.assertIn('phone', response.context['form'].errors)
        self.assertFalse(Master.objects.exists())

    def test_royxatdan_otish(self):
        response = self.client.post(reverse('masters:register'), self.data)
        self.assertRedirects(response, reverse('masters:dashboard'))
        master = Master.objects.get()
        self.assertFalse(master.is_verified)
        self.assertEqual(master.phone, '+998935557788')
        self.assertEqual(master.user.username, '998935557788')
        self.assertEqual(str(master.latitude), '41.311123')

    def test_tuman_orqali_joylashuv(self):
        data = dict(self.data, latitude='', longitude='', district='chilonzor')
        self.client.post(reverse('masters:register'), data)
        self.assertAlmostEqual(float(Master.objects.get().latitude), 41.275, places=2)

    def test_joylashuvsiz_yoki_ozbekistondan_tashqari(self):
        for lat, lng in [('', ''), ('55.75', '37.61'), ('69.28', '41.31')]:  # yo'q / Moskva / almashib ketgan
            response = self.client.post(reverse('masters:register'), dict(self.data, latitude=lat, longitude=lng))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].non_field_errors())
        self.assertFalse(Master.objects.exists())

    def test_takroriy_raqam_va_parol(self):
        self.client.post(reverse('masters:register'), self.data)
        self.client.logout()
        verify_phone(self.client, '+998935557788', 'register')
        verify_phone(self.client, '+998935550000', 'register')
        verify_phone(self.client, '+998935550001', 'register')
        response = self.client.post(reverse('masters:register'), dict(self.data, phone='93 555 77 88'))
        self.assertIn('phone', response.context['form'].errors)
        response = self.client.post(reverse('masters:register'), dict(self.data, phone='+998935550000', password2='boshqa'))
        self.assertIn('password2', response.context['form'].errors)
        response = self.client.post(reverse('masters:register'), dict(
            self.data, phone='+998935550001', password1='12345678', password2='12345678'))
        self.assertIn('password1', response.context['form'].errors)

    def test_telefon_bilan_kirish(self):
        self.client.post(reverse('masters:register'), self.data)
        self.client.logout()
        response = self.client.post(reverse('masters:login'), {'username': '+998 (93) 555-77-88', 'password': 'Kuchli-parol-77'})
        self.assertRedirects(response, reverse('masters:dashboard'))


class DashboardTests(TestCase):
    def setUp(self):
        self.master = make_master()
        self.other = make_master('Boshqa', '+998922222222')
        self.client.force_login(self.master.user)
        self.request = ServiceRequest.objects.create(name='Mijoz', phone='+998901112233', master=self.master)

    def action(self, pk, name):
        return self.client.post(reverse('masters:request_action', args=[pk, name]))

    def status(self):
        self.request.refresh_from_db()
        return self.request.status

    def test_bosqichlar_navbat_bilan(self):
        # Sakrab o'tib bo'lmaydi: qabul qilinmasdan "bajarildi" bo'lmaydi
        self.action(self.request.pk, 'complete')
        self.assertEqual(self.status(), 'new')
        for action, expected in [('accept', 'accepted'), ('arrive', 'arrived')]:
            self.action(self.request.pk, action)
            self.assertEqual(self.status(), expected)
        # Narx kelishilmaguncha ish boshlanmaydi
        self.action(self.request.pk, 'start')
        self.assertEqual(self.status(), 'arrived')
        payments.propose_quote(self.request, 100000, 'cash')
        payments.approve_quote(self.request)
        for action, expected in [('start', 'in_progress'), ('complete', 'completed')]:
            self.action(self.request.pk, action)
            self.assertEqual(self.status(), expected)
        # Bajarilgandan keyin usta bekor qila olmaydi va tasdiqlay olmaydi (bu mijozning ishi)
        self.action(self.request.pk, 'cancel')
        self.action(self.request.pk, 'confirm')
        self.assertEqual(self.status(), 'completed')
        self.assertEqual(
            list(self.request.events.values_list('status', flat=True)),
            ['accepted', 'arrived', 'in_progress', 'completed'],
        )

    def test_joyga_kelgach_bekor_qilib_bolmaydi(self):
        self.action(self.request.pk, 'accept')
        self.action(self.request.pk, 'arrive')
        self.action(self.request.pk, 'cancel')
        self.assertEqual(self.status(), 'arrived')

    def test_boshqa_ustaning_arizasi(self):
        foreign = ServiceRequest.objects.create(name='X', phone='+998901112234', master=self.other)
        self.assertEqual(self.action(foreign.pk, 'accept').status_code, 404)
        self.assertEqual(self.client.get(reverse('masters:order', args=[foreign.pk])).status_code, 404)
        self.action(self.request.pk, 'hack')
        self.assertEqual(self.status(), 'new')

    def test_buyurtma_sahifasida_mijoz_havolasi(self):
        payments.propose_quote(self.request, 100000, 'cash')
        payments.approve_quote(self.request)
        for a in ('accept', 'arrive', 'start', 'complete'):
            self.action(self.request.pk, a)
        response = self.client.get(reverse('masters:order', args=[self.request.pk]))
        self.assertContains(response, str(self.request.review_token))
        self.assertContains(response, 'tl--live')

    def test_bandlik(self):
        self.client.post(reverse('masters:toggle_availability'))
        self.master.refresh_from_db()
        self.assertFalse(self.master.is_available)

    def test_admin_kabinetga_kirsa_adminga(self):
        admin = get_user_model().objects.create_superuser('boss', 'b@b.uz', 'x-Parol-123')
        self.client.force_login(admin)
        self.assertRedirects(self.client.get(reverse('masters:dashboard')), reverse('admin:index'))

    def test_kirmagan_foydalanuvchi(self):
        self.client.logout()
        response = self.client.get(reverse('masters:dashboard'))
        self.assertRedirects(response, reverse('masters:login') + '?next=' + reverse('masters:dashboard'))


class ReviewFlowTests(TestCase):
    def setUp(self):
        self.master = make_master()
        self.request = ServiceRequest.objects.create(name='Malika', phone='+998901112233', master=self.master)
        self.url = reverse('masters:review', args=[self.request.review_token])
        self.data = {'quality': 5, 'punctuality': 4, 'price': 5, 'politeness': 5, 'comment': 'Zo\'r', 'author_name': 'Malika'}

    def test_yakunlanmagan_arizani_baholab_bolmaydi(self):
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.data).status_code, 403)
        self.assertFalse(Review.objects.exists())

    def test_baholash_tasdiqlaydi_va_reyting(self):
        self.request.status = 'completed'
        self.request.save()
        # Tasdiqlash pulni chiqaradi — SMS tasdiqsiz mumkin emas
        self.assertEqual(self.client.get(self.url).status_code, 403)
        verify_phone(self.client, self.request.phone)
        response = self.client.get(self.url)
        self.assertContains(response, 'Malika')  # ism oldindan to'ldirilgan
        self.client.post(self.url, self.data)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, 'confirmed')
        self.master.refresh_from_db()
        self.assertEqual(self.master.reviews_count, 1)
        self.assertEqual(str(self.master.rating_avg), '4.75')
        # Ikkinchi marta baholab bo'lmaydi
        self.client.post(self.url, dict(self.data, quality=1))
        self.assertEqual(Review.objects.count(), 1)

    def test_nashrdan_olinsa_reyting_yangilanadi(self):
        r = review(self.master, 5)
        review(self.master, 1)
        r.is_published = False
        r.save()
        self.master.refresh_from_db()
        self.assertEqual(self.master.rating_avg, 1)
        r.delete()
        self.master.refresh_from_db()
        self.assertEqual(self.master.reviews_count, 1)

    def test_baho_chegaralari_va_5_yulduz(self):
        form = ReviewForm(data=dict(self.data, quality=6))
        self.assertIn('quality', form.errors)
        self.assertEqual([c for c, _ in ReviewForm().fields['quality'].choices], [1, 2, 3, 4, 5])

    def test_notogri_kalit(self):
        self.assertEqual(self.client.get('/baho/00000000-0000-0000-0000-000000000000/').status_code, 404)
