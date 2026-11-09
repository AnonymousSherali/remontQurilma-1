import hmac
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import client
from .handlers import handle_update
from .models import LinkCode

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def webhook(request):
    """Telegram shu manzilga POST yuboradi. Maxfiy sarlavha bilan tekshiriladi
    (setWebhook'da secret_token sifatida berilgan — telegram_webhook buyrug'i)."""
    secret = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '')
    header = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    if not secret or not hmac.compare_digest(secret, header):
        return HttpResponseForbidden()
    try:
        update = json.loads(request.body or b'{}')
        handle_update(update)
    except Exception:
        # Telegram 200 olmasa, xuddi shu yangilanishni qayta-qayta yuboraveradi
        logger.exception('Telegram update xatosi')
    return HttpResponse('ok')


@login_required
@require_POST
def connect_master(request):
    master = getattr(request.user, 'master', None)
    if master is None:
        raise Http404
    url = client.deep_link('m' + LinkCode.issue(master).code)
    if not url:
        messages.error(request, _('Telegram bot hali sozlanmagan. Administratorga murojaat qiling.'))
        return redirect('masters:dashboard')
    return redirect(url)


@login_required
@require_POST
def disconnect_master(request):
    master = getattr(request.user, 'master', None)
    if master is None:
        raise Http404
    master.telegram_chat_id = None
    master.save(update_fields=['telegram_chat_id'])
    messages.info(request, _("Telegram uzildi. Xabarlar SMS orqali keladi."))
    return redirect('masters:dashboard')
