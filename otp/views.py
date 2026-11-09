from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from repair_service.phone import normalize_phone

from .models import PhoneCode
from .services import OtpError, mark_verified, send_code, verify_code

ALLOWED_PURPOSES = {PhoneCode.PURPOSE_LOGIN, PhoneCode.PURPOSE_REGISTER, PhoneCode.PURPOSE_RESET}


def _client_ip(request):
    return request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR')


def _parse(request):
    purpose = request.POST.get('purpose', PhoneCode.PURPOSE_LOGIN)
    if purpose not in ALLOWED_PURPOSES:
        purpose = PhoneCode.PURPOSE_LOGIN
    return normalize_phone(request.POST.get('phone')), purpose


@require_POST
def send_view(request):
    try:
        phone, purpose = _parse(request)
        code = send_code(phone, purpose, ip=_client_ip(request))
    except ValidationError as error:
        return JsonResponse({'ok': False, 'error': error.messages[0]}, status=400)
    except OtpError as error:
        return JsonResponse({'ok': False, 'error': str(error)}, status=429)

    data = {'ok': True, 'phone': phone}
    # Ishlab chiqishda SMS haqiqatan ketmaydi — kodni sahifada ko'rsatamiz.
    # Production'da (Eskiz yoki DEBUG=False) bu hech qachon qaytarilmaydi.
    if settings.DEBUG and getattr(settings, 'SMS_BACKEND', 'console') == 'console':
        data['debug_code'] = code
    return JsonResponse(data)


@require_POST
def verify_view(request):
    try:
        phone, purpose = _parse(request)
        verify_code(phone, request.POST.get('code'), purpose)
    except ValidationError as error:
        return JsonResponse({'ok': False, 'error': error.messages[0]}, status=400)
    except OtpError as error:
        return JsonResponse({'ok': False, 'error': str(error)}, status=400)
    mark_verified(request, phone, purpose)
    return JsonResponse({'ok': True, 'phone': phone})
