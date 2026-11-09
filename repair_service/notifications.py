"""Yangi ariza haqida Telegram orqali xabar berish.

Sozlash (.env):
    TELEGRAM_BOT_TOKEN=123456:ABC...   (@BotFather dan)
    TELEGRAM_CHAT_ID=-100123...        (xabar boradigan guruh yoki shaxs)

Sozlanmagan bo'lsa jimgina hech narsa qilmaydi. Yuborish alohida oqimda
bajariladi — Telegram sekin javob bersa ham mijoz kutib qolmaydi.
"""

import json
import logging
import threading
import urllib.request

from django.conf import settings

from .phone import format_phone

logger = logging.getLogger(__name__)


def _send(token, chat_id, text):
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    payload = json.dumps({'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True}).encode()
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req, timeout=8).close()
    except Exception:  # tarmoq xatosi arizani buzmasligi kerak
        logger.exception('Telegram xabarini yuborib bo\'lmadi')


def notify_new_request(service_request):
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', '')
    if not (token and chat_id):
        return

    lines = [
        f'🆕 Yangi ariza #{service_request.pk}',
        f'👤 {service_request.name}',
        f'📞 {format_phone(service_request.phone)}',
    ]
    if service_request.category:
        lines.append(f"🔧 {service_request.category}")
    if service_request.master:
        lines.append(f'👷 Usta: {service_request.master}')
    if service_request.address:
        lines.append(f'📍 {service_request.address}')
    if service_request.problem_description:
        lines.append(f'📝 {service_request.problem_description[:500]}')

    threading.Thread(target=_send, args=(token, chat_id, '\n'.join(lines)), daemon=True).start()
