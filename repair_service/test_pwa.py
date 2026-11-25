import json
from unittest import mock

from cryptography.hazmat.primitives.asymmetric import ec
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from masters.tests import verify_phone

from . import webpush, workflow
from .models import PushSubscription, ServiceRequest
from .tests import make_master

KEYS = webpush.generate_keys()
PUSH = {'WEBPUSH_PUBLIC_KEY': KEYS[0], 'WEBPUSH_PRIVATE_KEY': KEYS[1]}
ENDPOINT = 'https://fcm.googleapis.com/fcm/send/abc123'


def browser_keys():
    ua = ec.generate_private_key(ec.SECP256R1())
    from cryptography.hazmat.primitives import serialization
    pub = ua.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return ua, webpush.b64u_encode(pub), webpush.b64u_encode(b'0123456789abcdef')


class WebPushCryptoTests(TestCase):
    def test_rfc8291_namunasi(self):
        """RFC 8291, A ilova: belgilangan kalitlar va tuz bilan natija bayt-ma-bayt mos bo'lishi shart."""
        server = ec.derive_private_key(int.from_bytes(webpush.b64u_decode(
            'yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw'), 'big'), ec.SECP256R1())
        body = webpush.encrypt(
            b'When I grow up, I want to be a watermelon',
            'BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4',
            'BTBZMqHH6r4Tts7J_aSIgg', salt=webpush.b64u_decode('DGv6ra1nlYgDCS1FRnbzlw'), server_key=server)
        self.assertEqual(webpush.b64u_encode(body),
                         'DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6'
                         'TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN')

    @override_settings(**PUSH)
    def test_vapid_imzo(self):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
        header = webpush.vapid_headers(ENDPOINT)['Authorization']
        token, key = header[len('vapid t='):].split(', k=')
        head, claims, sig = token.split('.')
        self.assertEqual(json.loads(webpush.b64u_decode(claims))['aud'], 'https://fcm.googleapis.com')
        raw = webpush.b64u_decode(sig)
        public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), webpush.b64u_decode(key))
        public.verify(encode_dss_signature(int.from_bytes(raw[:32], 'big'), int.from_bytes(raw[32:], 'big')),
                      f'{head}.{claims}'.encode(), ec.ECDSA(hashes.SHA256()))   # xato bo'lsa — istisno

    def test_faqat_push_xizmatlari(self):
        for url in ('https://fcm.googleapis.com/x', 'https://updates.push.services.mozilla.com/wpush/v2/x',
                    'https://web.push.apple.com/x', 'https://wns2-par02p.notify.windows.com/w/?token=x'):
            self.assertTrue(webpush.endpoint_allowed(url), url)
        for url in ('http://fcm.googleapis.com/x', 'https://127.0.0.1/x', 'https://evil.com/fcm.googleapis.com',
                    'https://fcm.googleapis.com.evil.com/x', 'file:///etc/passwd', 'https://169.254.169.254/'):
            self.assertFalse(webpush.endpoint_allowed(url), url)

    @override_settings(**PUSH)
    def test_yuborish_va_eskirgan_obuna(self):
        _ua, p256dh, auth = browser_keys()
        sub = PushSubscription.objects.create(endpoint=ENDPOINT, p256dh=p256dh, auth=auth)

        class Resp:
            status = 201
            def __enter__(self): return self
            def __exit__(self, *a): return False

        with mock.patch('urllib.request.urlopen', return_value=Resp()) as urlopen:
            self.assertTrue(webpush.send(sub, 'Salom', 'Matn', '/'))
        request = urlopen.call_args[0][0]
        self.assertEqual(request.get_header('Content-encoding'), 'aes128gcm')
        self.assertTrue(request.get_header('Authorization').startswith('vapid t='))

        import urllib.error
        with mock.patch('urllib.request.urlopen', side_effect=urllib.error.HTTPError(ENDPOINT, 410, 'Gone', {}, None)):
            self.assertFalse(webpush.send(sub, 'Salom'))
        self.assertFalse(PushSubscription.objects.exists())


@override_settings(**PUSH)
class PwaViewTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        webpush.SENT.clear()

    def test_manifest_sw_offline(self):
        data = json.loads(self.client.get('/manifest.webmanifest').content)
        self.assertEqual((data['display'], data['start_url'][:1]), ('standalone', '/'))
        self.assertEqual(len(data['icons']), 3)
        sw = self.client.get('/sw.js')
        self.assertEqual(sw['Content-Type'], 'application/javascript; charset=utf-8')
        self.assertEqual(sw['Service-Worker-Allowed'], '/')
        self.assertIn(b"'/offline/'".replace(b"'", b'"'), sw.content)
        self.assertContains(self.client.get('/offline/'), "Internet aloqasi yo'q")
        home = self.client.get('/').content.decode()
        self.assertIn('rel="manifest"', home)
        self.assertIn(f'name="webpush-key" content="{KEYS[0]}"', home)

    def sub_payload(self, **extra):
        _ua, p256dh, auth = browser_keys()
        return json.dumps({'subscription': {'endpoint': ENDPOINT, 'keys': {'p256dh': p256dh, 'auth': auth}}, **extra})

    def test_usta_obunasi_va_xabar(self):
        master = make_master('Usta', '+998911111111')
        url = reverse('push_subscribe')
        self.assertEqual(self.client.post(url, self.sub_payload(), content_type='application/json').status_code, 403)
        self.client.force_login(master.user)
        bad = json.dumps({'subscription': {'endpoint': 'https://evil.com/x', 'keys': {'p256dh': 'a', 'auth': 'b'}}})
        self.assertEqual(self.client.post(url, bad, content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(url, self.sub_payload(), content_type='application/json').status_code, 200)
        self.assertEqual(PushSubscription.objects.get().master, master)
        self.assertContains(self.client.get(reverse('masters:dashboard')), 'data-push')

        order = ServiceRequest.objects.create(name='Malika', phone='+998901112233', master=master)
        with mock.patch('repair_service.webpush.enabled', return_value=False):  # tarmoqqa chiqmasin
            from .customer_notify import notify_master_new_order
            notify_master_new_order(order)
        self.assertEqual(webpush.SENT[-1][0], ENDPOINT)
        self.assertIn('Yangi buyurtma', webpush.SENT[-1][1]['body'])
        self.assertTrue(webpush.SENT[-1][1]['url'].endswith(order.get_master_url()))

        self.client.post(reverse('push_unsubscribe'), json.dumps({'endpoint': ENDPOINT}), content_type='application/json')
        self.assertFalse(PushSubscription.objects.exists())

    def test_mijoz_obunasi(self):
        master = make_master('Usta', '+998911111111')
        order = ServiceRequest.objects.create(name='Malika', phone='+998901112233', master=master)
        url = reverse('push_subscribe')
        payload = self.sub_payload(scope='customer', token=str(order.review_token))
        self.assertEqual(self.client.post(url, payload, content_type='application/json').status_code, 403)
        self.assertEqual(self.client.post(url, self.sub_payload(scope='customer', token='yaroqsiz'),
                                          content_type='application/json').status_code, 403)
        verify_phone(self.client, order.phone)
        self.assertContains(self.client.get(order.get_customer_url()), 'data-scope="customer"')
        self.assertEqual(self.client.post(url, payload, content_type='application/json').status_code, 200)
        self.assertEqual(PushSubscription.objects.get().phone, order.phone)
        with mock.patch('repair_service.webpush.enabled', return_value=False):
            with self.captureOnCommitCallbacks(execute=True):
                workflow.apply(order, workflow.MASTER, 'accept')
        self.assertIn('qabul qildi', webpush.SENT[-1][1]['body'])

    @override_settings(WEBPUSH_PUBLIC_KEY='', WEBPUSH_PRIVATE_KEY='')
    def test_kalitsiz_ochiq(self):
        self.assertEqual(self.client.post(reverse('push_subscribe'), self.sub_payload(),
                                          content_type='application/json').status_code, 404)
        self.assertNotIn('webpush-key', self.client.get('/').content.decode())

    def test_kalit_buyrugi(self):
        from io import StringIO

        from django.core.management import call_command
        out = StringIO()
        call_command('webpush_keys', stdout=out, stderr=StringIO())
        lines = dict(line.split('=', 1) for line in out.getvalue().split())
        self.assertEqual(len(webpush.b64u_decode(lines['WEBPUSH_PUBLIC_KEY'])), 65)
        self.assertEqual(len(webpush.b64u_decode(lines['WEBPUSH_PRIVATE_KEY'])), 32)
