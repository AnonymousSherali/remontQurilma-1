import shutil
import tempfile
from io import BytesIO
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from masters.tests import verify_phone
from payments import services as payments

from . import photos, workflow
from .models import OrderPhoto, ServiceRequest
from .tests import make_master

MEDIA = tempfile.mkdtemp()


def jpeg(name='a.jpg', size=(2400, 1200), gps=True, orientation=None):
    """Telefon rasmiga o'xshash JPEG: GPS koordinatasi va burilish belgisi bilan."""
    image = Image.new('RGB', size, (200, 50, 50))
    exif = Image.Exif()
    exif[0x010F] = 'PhoneMaker'
    if gps:
        exif[0x8825] = {1: 'N', 2: (41.0, 18.0, 40.0), 3: 'E', 4: (69.0, 16.0, 47.0)}
    if orientation:
        exif[0x0112] = orientation
    buffer = BytesIO()
    image.save(buffer, format='JPEG', exif=exif)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/jpeg')


@override_settings(MEDIA_ROOT=MEDIA)
class ProcessUploadTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_exif_va_gps_ochiriladi_hajm_kichrayadi(self):
        full, thumb = photos.process_upload(jpeg())
        out = Image.open(BytesIO(full.read()))
        self.assertEqual(dict(out.getexif()), {})  # GPS ham, telefon modeli ham yo'q
        self.assertLessEqual(max(out.size), photos.MAX_SIDE)
        self.assertLessEqual(max(Image.open(BytesIO(thumb.read())).size), photos.THUMB_SIDE)

    def test_burilish_hisobga_olinadi(self):
        full, _ = photos.process_upload(jpeg(size=(800, 400), orientation=6))  # 90° burilgan
        out = Image.open(BytesIO(full.read()))
        self.assertEqual(out.size, (400, 800))

    def test_rasm_bolmagan_fayl(self):
        fake = SimpleUploadedFile('virus.jpg', b'<?php echo 1; ?>', content_type='image/jpeg')
        with self.assertRaises(ValidationError):
            photos.process_upload(fake)

    def test_juda_katta_fayl(self):
        upload = jpeg()
        upload.size = (photos.MAX_UPLOAD_MB + 1) * 1024 * 1024
        with self.assertRaises(ValidationError):
            photos.process_upload(upload)

    def test_gif_qabul_qilinmaydi(self):
        buffer = BytesIO()
        Image.new('RGB', (10, 10)).save(buffer, format='GIF')
        with self.assertRaises(ValidationError):
            photos.process_upload(SimpleUploadedFile('a.gif', buffer.getvalue()))


@override_settings(MEDIA_ROOT=MEDIA)
class OrderPhotoFlowTests(TestCase):
    def setUp(self):
        self.master = make_master()
        self.order = ServiceRequest.objects.create(name='M', phone='+998901112233', master=self.master)
        self.master_url = reverse('masters:order_photo_upload', args=[self.order.pk])
        self.customer_url = reverse('repair_service:order_photo_upload', args=[self.order.review_token])

    def upload_as_master(self, kind='before', files=None):
        self.client.force_login(self.master.user)
        return self.client.post(self.master_url, {'kind': kind, 'images': files or [jpeg()]})

    def test_usta_qabul_qilmaguncha_yuklay_olmaydi(self):
        self.upload_as_master()
        self.assertFalse(OrderPhoto.objects.exists())
        workflow.apply(self.order, workflow.MASTER, 'accept')
        self.upload_as_master('before', [jpeg('1.jpg'), jpeg('2.jpg')])
        self.assertEqual(OrderPhoto.objects.filter(kind='before', uploaded_by='master').count(), 2)
        self.assertTrue(self.order.events.filter(note__contains='2 ta rasm').exists())

    def test_mijoz_faqat_muammo_rasmi_va_sms_bilan(self):
        self.assertEqual(self.client.post(self.customer_url, {'kind': 'problem', 'images': [jpeg()]}).status_code, 404)
        verify_phone(self.client, self.order.phone)
        self.client.post(self.customer_url, {'kind': 'after', 'images': [jpeg()]})  # "keyin" — usta ishi
        self.assertFalse(OrderPhoto.objects.exists())
        self.client.post(self.customer_url, {'kind': 'problem', 'images': [jpeg()]})
        self.assertEqual(OrderPhoto.objects.get().kind, 'problem')

    def test_limit(self):
        workflow.apply(self.order, workflow.MASTER, 'accept')
        files = [jpeg(f'{i}.jpg', size=(50, 50)) for i in range(photos.MAX_PHOTOS_PER_SIDE + 3)]
        self.upload_as_master('before', files)
        self.assertEqual(OrderPhoto.objects.count(), photos.MAX_PHOTOS_PER_SIDE)

    def test_ochirish_qoidalari_va_fayl(self):
        workflow.apply(self.order, workflow.MASTER, 'accept')
        self.upload_as_master()
        photo = OrderPhoto.objects.get()
        path = Path(photo.image.path)
        self.assertTrue(path.exists())
        # Mijoz ustaning rasmini o'chira olmaydi
        verify_phone(self.client, self.order.phone)
        self.client.post(reverse('repair_service:order_photo_delete', args=[self.order.review_token, photo.pk]))
        self.assertTrue(OrderPhoto.objects.exists())
        # Usta o'zinikini o'chiradi — fayl ham o'chadi
        self.client.force_login(self.master.user)
        self.client.post(reverse('masters:order_photo_delete', args=[self.order.pk, photo.pk]))
        self.assertFalse(OrderPhoto.objects.exists())
        self.assertFalse(path.exists())

    def test_nizoda_rasmni_ochirib_bolmaydi(self):
        workflow.apply(self.order, workflow.MASTER, 'accept')
        workflow.apply(self.order, workflow.MASTER, 'arrive')
        self.upload_as_master()
        workflow.apply(self.order, workflow.CUSTOMER, 'dispute')
        photo = OrderPhoto.objects.get()
        self.client.post(reverse('masters:order_photo_delete', args=[self.order.pk, photo.pk]))
        self.assertTrue(OrderPhoto.objects.exists())  # dalil saqlanadi
        self.upload_as_master('after')  # nizoda qo'shimcha dalil yuklash mumkin
        self.assertEqual(OrderPhoto.objects.count(), 2)

    def test_buyurtma_ochirilsa_fayllar_ham(self):
        workflow.apply(self.order, workflow.MASTER, 'accept')
        self.upload_as_master()
        path = Path(OrderPhoto.objects.get().image.path)
        self.order.delete()
        self.assertFalse(path.exists())

    def complete_with_photos(self):
        workflow.apply(self.order, workflow.MASTER, 'accept')
        self.upload_as_master('before')
        workflow.apply(self.order, workflow.MASTER, 'arrive')
        payments.propose_quote(self.order, 100000, 'cash')
        payments.approve_quote(self.order)
        workflow.apply(self.order, workflow.MASTER, 'start')
        self.upload_as_master('after')
        workflow.apply(self.order, workflow.MASTER, 'complete')

    def test_portfolio_shartlari(self):
        self.complete_with_photos()
        self.assertEqual(photos.portfolio(self.master), [])  # hali tasdiqlanmagan
        workflow.apply(self.order, workflow.CUSTOMER, 'confirm')
        works = photos.portfolio(self.master)
        self.assertEqual(len(works), 1)
        self.assertEqual(len(works[0]['before']), 1)
        page = self.client.get(reverse('masters:detail', args=[self.master.pk]))
        self.assertContains(page, 'Bajarilgan ishlar')

        # Mijoz rozilikni olib qo'ydi
        verify_phone(self.client, self.order.phone)
        self.client.post(reverse('repair_service:order_portfolio_toggle', args=[self.order.review_token]))
        self.assertEqual(photos.portfolio(self.master), [])
        self.client.post(reverse('repair_service:order_portfolio_toggle', args=[self.order.review_token]))
        # Admin yashirdi
        OrderPhoto.objects.filter(kind='after').update(is_hidden=True)
        self.assertEqual(photos.portfolio(self.master), [])

    def test_tasdiqlangandan_keyin_rasm_qulflanadi(self):
        self.complete_with_photos()
        workflow.apply(self.order, workflow.CUSTOMER, 'confirm')
        photo = OrderPhoto.objects.first()
        self.client.post(reverse('masters:order_photo_delete', args=[self.order.pk, photo.pk]))
        self.assertTrue(OrderPhoto.objects.filter(pk=photo.pk).exists())
        self.upload_as_master('after')
        self.assertEqual(OrderPhoto.objects.count(), 2)

    def test_sahifalarda_galereya(self):
        workflow.apply(self.order, workflow.MASTER, 'accept')
        self.upload_as_master()
        page = self.client.get(reverse('masters:order', args=[self.order.pk]))
        self.assertContains(page, 'data-lightbox')
        self.assertContains(page, 'value="before" checked')  # ish boshlanmagan — "oldin"
        self.client.logout()
        self.assertContains(self.client.get(self.order.get_customer_url()), 'data-lightbox')
