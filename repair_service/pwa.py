"""PWA: telefonda «ilova» sifatida o'rnatish (manifest, service worker, oflayn sahifa) va push obunalar."""

import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST

from otp import services as otp

from . import webpush
from .models import PushSubscription, ServiceRequest


def _assets_version():
    """Statik fayllar o'zgarsa — service worker keshi yangilanadi (har deploy'da avtomatik)."""
    # Barcha statik fayllar (rasm, ikonka ham): nomlari xeshlanmagan, shuning uchun keshni shu versiya yangilaydi
    import hashlib
    root = Path(settings.BASE_DIR) / 'static'
    digest = hashlib.sha1()
    for path in sorted(p for p in root.rglob('*') if p.is_file()):
        stat = path.stat()
        digest.update(f'{path.relative_to(root)}:{int(stat.st_mtime)}:{stat.st_size};'.encode())
    return digest.hexdigest()[:12]


@cache_control(max_age=3600)
def manifest(request):
    name = settings.SITE_INFO['name']
    data = {
        'name': f'{name} — ustalar', 'short_name': name, 'lang': 'uz', 'dir': 'ltr',
        'start_url': '/?source=pwa', 'scope': '/', 'display': 'standalone',
        'theme_color': '#059669', 'background_color': '#f6f8fb',
        'description': "Uyingiz uchun ishonchli ustalar: santexnik, elektrik, maishiy texnika.",
        'icons': [
            {'src': static('img/icons/icon-192.png'), 'sizes': '192x192', 'type': 'image/png'},
            {'src': static('img/icons/icon-512.png'), 'sizes': '512x512', 'type': 'image/png'},
            {'src': static('img/icons/maskable-512.png'), 'sizes': '512x512', 'type': 'image/png',
             'purpose': 'maskable'},
        ],
        'shortcuts': [
            {'name': 'Usta topish', 'url': '/ustalar/'},
            {'name': 'Mening buyurtmalarim', 'url': '/buyurtmalarim/'},
            {'name': 'Usta kabineti', 'url': '/kabinet/'},
        ],
    }
    return HttpResponse(json.dumps(data, ensure_ascii=False), content_type='application/manifest+json')


def service_worker(request):
    response = render(request, 'pwa/sw.js', {
        'version': _assets_version(),
        'precache_json': json.dumps([static('css/app.css'), static('js/app.js'), static('img/icons/icon-192.png'),
                                     '/offline/']),
    }, content_type='application/javascript; charset=utf-8')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'   # brauzer har safar yangi versiyani tekshiradi
    return response


def offline(request):
    return render(request, 'pwa/offline.html')


# ---------- Push obuna ----------

def _owner(request, data):
    """Obuna kimga tegishli: (master, phone). Ruxsat bo'lmasa None."""
    master = getattr(request.user, 'master', None) if request.user.is_authenticated else None
    if master is not None and data.get('scope') != 'customer':
        return master, ''
    token = data.get('token') or ''
    try:
        order = ServiceRequest.objects.get(review_token=token)
    except (ServiceRequest.DoesNotExist, ValueError, ValidationError):   # noto'g'ri UUID ham
        return None
    if not otp.is_verified(request, order.phone):
        return None
    return None, order.phone


@require_POST
def push_subscribe(request):
    if not webpush.enabled():
        raise Http404
    try:
        data = json.loads(request.body or b'{}')
        sub = data['subscription']
        endpoint, p256dh, auth = sub['endpoint'], sub['keys']['p256dh'], sub['keys']['auth']
    except (ValueError, KeyError, TypeError):
        return JsonResponse({'ok': False}, status=400)
    if not webpush.endpoint_allowed(endpoint) or len(p256dh) > 200 or len(auth) > 100 or len(endpoint) > 1000:
        return JsonResponse({'ok': False}, status=400)
    owner = _owner(request, data)
    if owner is None:
        return JsonResponse({'ok': False}, status=403)
    master, phone = owner
    PushSubscription.objects.update_or_create(endpoint=endpoint, defaults={
        'p256dh': p256dh, 'auth': auth, 'master': master, 'phone': phone,
        'user_agent': request.headers.get('User-Agent', '')[:200]})
    return JsonResponse({'ok': True})


@require_POST
def push_unsubscribe(request):
    try:
        endpoint = json.loads(request.body or b'{}')['endpoint']
    except (ValueError, KeyError, TypeError):
        return JsonResponse({'ok': False}, status=400)
    PushSubscription.objects.filter(endpoint=endpoint).delete()   # manzilni faqat o'sha brauzer biladi
    return JsonResponse({'ok': True})
