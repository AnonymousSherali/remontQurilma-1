"""Ishga tushirishga tayyorgarlik: production sozlamalari, integratsiyalar tekshiruvi,
ustaning hujjatlari, qayta chaqirish va SEO."""

import json
import re
import shutil
import tempfile
from datetime import timedelta
from io import BytesIO, StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import Permission, User
from django.core import checks
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation
from PIL import Image

from config.settings import database_from_url
from otp.sms import ConsoleBackend
from repair_service.models import ServiceRequest
from repair_service.test_warranty import PHONE, confirmed_order
from repair_service.tests import make_master
from telegram_bot import client as tg

from . import documents
from .models import Category, Master, MasterDocument

TMP = tempfile.mkdtemp(prefix='ts-private-')


def image_file(name='doc.jpg', color='red', exif_gps=False):
    buffer = BytesIO()
    image = Image.new('RGB', (800, 600), color)
    exif = Image.Exif()
    if exif_gps:
        exif[0x8825] = {2: (41.0, 18.0, 0.0), 4: (69.0, 16.0, 0.0)}   # GPSInfo
    image.save(buffer, format='JPEG', exif=exif)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/jpeg')


class Base(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        ConsoleBackend.sent.clear()
        tg.SENT.clear()

    def tearDown(self):
        translation.activate('uz')


# ---------- 1. Production ----------

class ProductionTests(Base):
    def test_database_url(self):
        db = database_from_url('postgres://ts:p%40ss@db.local:6432/techservice')
        self.assertEqual((db['ENGINE'], db['NAME'], db['USER'], db['PASSWORD'], db['HOST'], db['PORT']),
                         ('django.db.backends.postgresql', 'techservice', 'ts', 'p@ss', 'db.local', '6432'))
        from django.core.exceptions import ImproperlyConfigured
        with self.assertRaises(ImproperlyConfigured):
            database_from_url('mysql://x@y/z')

    def test_healthz(self):
        response = self.client.get('/healthz/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'db': 'ok', 'cache': 'ok'})
        with mock.patch('django.core.cache.cache.get', return_value=None):
            response = self.client.get('/healthz/')
        self.assertEqual((response.status_code, response.json()['cache']), (503, 'error'))

    def test_deploy_tekshiruvlari(self):
        ids = {m.id for m in checks.run_checks(include_deployment_checks=True) if m.id.startswith('techservice')}
        self.assertTrue({'techservice.W003', 'techservice.W005'} <= ids)      # testda SMS va to'lov — demo
        from config.checks import production_settings
        with override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
                               DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}):
            ids = {w.id for w in production_settings(None)}
        self.assertTrue({'techservice.W001', 'techservice.W002'} <= ids)
        with override_settings(
                CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
                DATABASES={'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'x'}},
                SMS_BACKEND='eskiz', SITE_URL='https://techservice.uz', PAYMENT_PROVIDERS='payme',
                ALLOW_DEMO_PAYMENTS=False, LEGAL_DRAFT=False):
            self.assertEqual(production_settings(None), [])

    def test_maxfiy_papka_media_ichida_bolmasin(self):
        from config.checks import production_settings
        with override_settings(MEDIA_ROOT=Path('/srv/m'), PRIVATE_MEDIA_ROOT=Path('/srv/m/private')):
            self.assertIn('techservice.W008', [w.id for w in production_settings(None)])


# ---------- 2. Integratsiyalar ----------

class IntegrationCheckTests(Base):
    def run_cmd(self, *args):
        out = StringIO()
        call_command('check_integrations', *args, stdout=out)
        return out.getvalue()

    @override_settings(PAYMENT_PROVIDERS='payme,click,uzum', PAYME_MERCHANT_ID='m1', PAYME_KEY='key&1',
                       CLICK_SERVICE_ID='10', CLICK_MERCHANT_ID='20', CLICK_SECRET_KEY='s', CLICK_MERCHANT_USER_ID='30',
                       UZUM_SERVICE_ID='77', UZUM_LOGIN='u', UZUM_PASSWORD='p')
    def test_tolov_endpointlari_kalitni_qabul_qiladi(self):
        output = self.run_cmd()
        self.assertIn('✓ Payme', output)
        self.assertIn('✓ Click', output)
        self.assertIn('! Uzum', output)
        self.assertNotRegex(output, r'(?m)^✗')
        from payments.models import Payment
        self.assertEqual(Payment.objects.count(), 0)          # hech narsa yaratilmadi

    @override_settings(PAYMENT_PROVIDERS='payme', PAYME_MERCHANT_ID='m1', PAYME_KEY='')
    def test_kalit_yoq(self):
        self.assertIn("✗ Payme      to'ldirilmagan: PAYME_KEY", self.run_cmd())
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            self.run_cmd('--fail')

    @override_settings(SMS_BACKEND='eskiz', ESKIZ_EMAIL='a@b.uz', ESKIZ_PASSWORD='x', TELEGRAM_BOT_TOKEN='1:x',
                       TELEGRAM_BOT_USERNAME='ts_bot', TELEGRAM_WEBHOOK_SECRET='s', SITE_URL='https://ts.uz')
    def test_live(self):
        def fake_api(method, payload):
            return {'getMe': {'result': {'username': 'ts_bot'}},
                    'getWebhookInfo': {'result': {'url': 'https://ts.uz/telegram/webhook/'}}}[method]

        class Resp(BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False

        with mock.patch('otp.sms.EskizBackend._token', return_value='t'), \
                mock.patch('telegram_bot.client.api', side_effect=fake_api), \
                mock.patch('urllib.request.urlopen', return_value=Resp(b'{"status": "ok"}')):
            output = self.run_cmd('--live')
        self.assertIn('Eskiz: kirish muvaffaqiyatli', output)
        self.assertIn('webhook ulangan', output)
        self.assertIn('healthz', output)
        self.assertNotRegex(output, r'(?m)^✗')


# ---------- 3. Hujjatlar ----------

@override_settings(PRIVATE_MEDIA_ROOT=Path(TMP))
class DocumentTests(Base):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.master = make_master('Usta', '+998911111111', verified=False)
        self.client.force_login(self.master.user)
        self.url = reverse('masters:documents')

    def upload(self, **extra):
        return self.client.post(self.url, {'id': image_file(exif_gps=True), 'selfie': image_file(color='blue'),
                                           **extra})

    def test_yuklash_va_tasdiqlash(self):
        self.assertContains(self.client.get(reverse('masters:dashboard')), 'Shaxsingizni tasdiqlang')
        self.client.post(self.url, {'id': image_file()})               # selfi yo'q
        self.master.refresh_from_db()
        self.assertEqual(self.master.id_status, 'none')

        self.assertRedirects(self.upload(), reverse('masters:dashboard'))
        self.master.refresh_from_db()
        self.assertEqual(self.master.id_status, 'pending')
        doc = self.master.documents.get(kind='id')
        path = Path(doc.file.path)
        self.assertTrue(str(path).startswith(TMP))                     # MEDIA_ROOT dan tashqarida
        with Image.open(path) as saved:
            self.assertNotIn(0x8825, saved.getexif())                  # GPS o'chirilgan
        with self.assertRaises(ValueError):
            doc.file.url                                               # ochiq havola yo'q
        self.assertNotContains(self.client.get(self.url), 'type="file"')  # qayta yuborib bo'lmaydi

        documents.approve(self.master)
        self.master.refresh_from_db()
        self.assertEqual((self.master.id_status, self.master.is_verified), ('approved', True))
        self.assertIn('tasdiqlandi', ConsoleBackend.sent[-1][1])
        self.assertContains(self.client.get(self.master.get_absolute_url()), 'Hujjatlari tekshirilgan')

    def test_rad_etish_va_qayta_yuklash(self):
        self.upload()
        old_path = Path(self.master.documents.get(kind='id').file.path)
        with self.assertRaises(documents.DocumentError):
            documents.reject(self.master, '')
        documents.reject(self.master, 'Rasm xira')
        self.assertIn('Rasm xira', ConsoleBackend.sent[-1][1])
        self.assertContains(self.client.get(reverse('masters:dashboard')), 'Rasm xira')
        self.upload()
        self.master.refresh_from_db()
        self.assertEqual(self.master.id_status, 'pending')
        self.assertEqual(self.master.documents.count(), 2)
        self.assertFalse(old_path.exists())                            # eski fayl o'chirildi

    def test_rasm_emas(self):
        bad = SimpleUploadedFile('x.jpg', b'not an image', content_type='image/jpeg')
        self.client.post(self.url, {'id': bad, 'selfie': image_file()})
        self.master.refresh_from_db()
        self.assertEqual((self.master.id_status, self.master.documents.count()), ('none', 0))

    def test_admin_korish_huquqi(self):
        self.upload()
        doc = self.master.documents.get(kind='id')
        url = reverse('admin:masters_master_document', args=[doc.pk])
        self.assertEqual(self.client.get(url).status_code, 302)          # usta — admin emas
        staff = User.objects.create_user('op', password='x', is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename='change_master'))
        self.client.force_login(staff)
        self.assertEqual(self.client.get(url).status_code, 403)          # hujjat ko'rish huquqi yo'q
        staff.user_permissions.add(Permission.objects.get(codename='view_masterdocument'))
        staff = User.objects.get(pk=staff.pk)
        self.client.force_login(staff)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn('private', response['Cache-Control'])

    def test_admin_qarori(self):
        self.upload()
        admin = User.objects.create_superuser('admin', 'a@example.com', 'x')
        self.client.force_login(admin)
        change = reverse('admin:masters_master_change', args=[self.master.pk])
        response = self.client.get(change)
        self.assertContains(response, reverse('admin:masters_master_document',
                                              args=[self.master.documents.first().pk]))
        form = response.context['adminform'].form
        data = {k: ('' if v is None else v) for k, v in form.initial.items() if k not in ('photo', 'user')}
        data.update({'user': self.master.user_id, 'categories': [], 'id_status': 'rejected', 'id_note': '',
                     'documents-TOTAL_FORMS': 0, 'documents-INITIAL_FORMS': 0,
                     'reviews-TOTAL_FORMS': 0, 'reviews-INITIAL_FORMS': 0})
        data = {k: v for k, v in data.items() if not hasattr(v, 'isoformat')}
        self.client.post(change, data)
        self.master.refresh_from_db()
        self.assertEqual(self.master.id_status, 'pending')               # sababsiz rad etilmaydi

        self.client.post(reverse('admin:masters_master_changelist'),
                         {'action': 'approve_documents', '_selected_action': [self.master.pk]})
        self.master.refresh_from_db()
        self.assertEqual((self.master.id_status, self.master.is_verified), ('approved', True))

    @override_settings(ID_DOCUMENTS_KEEP_DAYS=30)
    def test_eski_fayllar_ochiriladi(self):
        self.upload()
        documents.approve(self.master)
        path = Path(self.master.documents.first().file.path)
        self.assertEqual(documents.purge_old(), 0)
        Master.objects.filter(pk=self.master.pk).update(id_checked_at=timezone.now() - timedelta(days=31))
        call_command('process_orders', verbosity=0)
        self.assertEqual(MasterDocument.objects.count(), 0)
        self.assertFalse(path.exists())
        self.master.refresh_from_db()
        self.assertEqual(self.master.id_status, 'approved')               # holat saqlanadi


# ---------- 4. Qayta chaqirish ----------

class ReorderTests(Base):
    def setUp(self):
        super().setUp()
        self.cat = Category.objects.create(name='Elektrik', slug='elektrik')
        self.master = make_master('Usta', '+998911111111', categories=[self.cat])
        self.order = confirmed_order(self.master, category=self.cat, address='Chilonzor 9-12',
                                     district='chilonzor', latitude='41.275', longitude='69.204')
        self.url = reverse('repair_service:reorder', args=[self.order.review_token])
        ConsoleBackend.sent.clear()

    def test_tasdiqlanmagan_raqam(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, self.order.get_customer_url())
        self.assertNotContains(self.client.get(self.order.get_customer_url()), 'Shu ustani qayta chaqirish')

    def test_qayta_chaqirish(self):
        from masters.tests import verify_phone
        verify_phone(self.client, PHONE)
        self.assertContains(self.client.get(self.order.get_customer_url()), 'Shu ustani qayta chaqirish')
        self.assertContains(self.client.get(reverse('repair_service:my_orders')), 'Qayta chaqirish')
        self.assertContains(self.client.get(self.url), 'Chilonzor 9-12')
        self.client.post(self.url, {'problem_description': 'Rozetka'})                 # roziliksiz
        self.assertEqual(ServiceRequest.objects.count(), 1)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, {'problem_description': 'Yana bir rozetka', 'consent': 'on',
                                                   'address': 'Chilonzor 9-12', 'preferred_slot': 'evening'})
        new = ServiceRequest.objects.latest('id')
        self.assertRedirects(response, new.get_customer_url())
        self.assertEqual((new.master, new.category, new.name, new.phone, new.district, new.preferred_slot),
                         (self.master, self.cat, 'Malika', PHONE, 'chilonzor', 'evening'))
        self.assertEqual(str(new.latitude), '41.275000')
        self.assertIn('Yangi buyurtma', [t for p, t in ConsoleBackend.sent if p == self.master.phone][-1])
        self.assertTrue(new.events.filter(note__contains=f'#{self.order.pk}').exists())

    def test_usta_band_yoki_yoq(self):
        from masters.tests import verify_phone
        verify_phone(self.client, PHONE)
        Master.objects.filter(pk=self.master.pk).update(is_available=False)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse('masters:list') + '?category=elektrik', fetch_redirect_response=False)
        Master.objects.filter(pk=self.master.pk).update(is_available=True, is_verified=False)
        self.client.get(self.url)
        self.assertEqual(ServiceRequest.objects.count(), 1)

    def test_tasdiqlanmagan_buyurtma(self):
        from masters.tests import verify_phone
        order = ServiceRequest.objects.create(name='A', phone=PHONE, master=self.master)
        verify_phone(self.client, PHONE)
        self.assertEqual(self.client.get(reverse('repair_service:reorder', args=[order.review_token])).status_code,
                         404)


# ---------- 5. SEO ----------

class SeoTests(Base):
    def setUp(self):
        super().setUp()
        self.cat = Category.objects.create(name='Santexnik', name_ru='Сантехник', slug='santexnik')
        self.empty = Category.objects.create(name='Mebel', slug='mebel')
        self.master = make_master('Usta', '+998911111111', 41.275, 69.204, categories=[self.cat], service_radius_km=3)

    def page(self, url):
        response = self.client.get(url)
        body = response.content.decode()
        canonical = re.search(r'rel="canonical" href="([^"]+)"', body)
        return response, body, canonical.group(1) if canonical else None

    def test_yonalish_va_tuman_sahifalari(self):
        response, body, canonical = self.page('/ustalar/santexnik/chilonzor/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Santexnik — Chilonzor tumani', body)
        self.assertIn('<title>Santexnik Chilonzor tumanida: 1 ta usta', body)
        self.assertEqual(canonical, 'http://testserver/ustalar/santexnik/chilonzor/')
        self.assertNotIn('noindex', body)
        data = [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', body, re.S)]
        self.assertEqual(data[0][0]['@type'], 'BreadcrumbList')
        self.assertIn('Usta', body)
        self.assertIn('href="/ustalar/santexnik/yunusobod/"', body)        # boshqa tumanlar
        _r, body_ru, _c = self.page('/ru/ustalar/santexnik/chilonzor/')
        self.assertIn('Чиланзар', body_ru)

    def test_bosh_sahifa_noindex(self):
        _r, body, _c = self.page('/ustalar/mebel/')
        self.assertIn('noindex', body)
        self.assertEqual(self.client.get('/ustalar/santexnik/yoq-tuman/').status_code, 404)
        self.assertEqual(self.client.get('/ustalar/yoq/').status_code, 404)
        self.assertEqual(self.client.get('/ustalar/royxatdan-otish/').status_code, 200)

    def test_qidiruv_canonical(self):
        _r, body, canonical = self.page('/ustalar/?category=santexnik&district=chilonzor&sort=rating')
        self.assertEqual(canonical, 'http://testserver/ustalar/santexnik/chilonzor/')
        _r, body, _c = self.page('/ustalar/?lat=41.3&lng=69.2')
        self.assertIn('noindex', body)

    def test_sitemap_va_robots(self):
        body = self.client.get('/sitemap.xml').content.decode()
        self.assertIn('http://testserver/ustalar/santexnik/chilonzor/', body)
        self.assertIn('http://testserver/ru/ustalar/santexnik/', body)
        self.assertIn(f'http://testserver{self.master.get_absolute_url()}', body)
        self.assertIn('hreflang="x-default"', body)
        self.assertNotIn('/ustalar/mebel/', body)                         # ustasiz — kiritilmaydi
        self.assertNotIn('/ustalar/santexnik/sergeli/', body)              # ustaning radiusidan (3 km) tashqari
        robots = self.client.get('/robots.txt').content.decode()
        self.assertIn('Disallow: /kabinet/', robots)
        self.assertIn('Sitemap: http://testserver/sitemap.xml', robots)
        cache.clear()
        with override_settings(SEO_DISALLOW_ALL=True):
            self.assertEqual(self.client.get('/robots.txt').content.decode(), 'User-agent: *\nDisallow: /\n')

    def test_usta_profili_jsonld(self):
        self.master.reviews_count, self.master.rating_avg = 3, '4.70'
        self.master.save()
        _r, body, canonical = self.page(self.master.get_absolute_url())
        data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', body, re.S).group(1))
        self.assertEqual(data['@type'], 'HomeAndConstructionBusiness')
        self.assertEqual(data['aggregateRating']['reviewCount'], 3)
        self.assertNotIn('telephone', data)                                # telefon oshkor qilinmaydi
        self.assertEqual(canonical, f'http://testserver{self.master.get_absolute_url()}')

    def test_jsonld_xss(self):
        self.master.full_name = '</script><script>alert(1)</script>'
        self.master.save()
        _r, body, _c = self.page(self.master.get_absolute_url())
        self.assertNotIn('</script><script>alert(1)', body)

    def test_og_va_footer(self):
        _r, body, _c = self.page('/')
        self.assertIn('og:image', body)
        self.assertIn('/static/img/og.png', body)
        self.assertIn('href="/ustalar/santexnik/"', body)                  # footer ichki havolasi
        self.assertIn('"@type": "Organization"', body)
