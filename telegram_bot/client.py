"""Telegram Bot API bilan ishlash (kutubxonasiz, urllib orqali).

Xabarlar alohida oqimda yuboriladi — Telegram sekin javob bersa ham sahifa kutmaydi.
Testlarda SENT ro'yxatiga yoziladi (TELEGRAM_BOT_TOKEN bo'sh bo'lsa).
"""

import json
import logging
import threading
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

SENT = []  # token sozlanmagan bo'lsa (dev/test) — yuborilganlar shu yerda


def enabled():
    return bool(getattr(settings, 'TELEGRAM_BOT_TOKEN', ''))


def api(method, payload):
    url = f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}'
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode() or '{}')


def _call(method, payload, background):
    if not enabled():
        SENT.append((method, payload))
        return None

    def run():
        try:
            return api(method, payload)
        except Exception:
            logger.exception('Telegram %s xatosi', method)
            return None

    if background:
        threading.Thread(target=run, daemon=True).start()
        return None
    return run()


def keyboard(rows):
    """[[(matn, callback_data | url), ...], ...] -> inline_keyboard"""
    return {'inline_keyboard': [
        [{'text': str(text), ('url' if str(data).startswith('http') else 'callback_data'): data}
         for text, data in row] for row in rows
    ]}


def send_message(chat_id, text, buttons=None, background=True):
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
    if buttons:
        payload['reply_markup'] = keyboard(buttons)
    return _call('sendMessage', payload, background)


def edit_message(chat_id, message_id, text, buttons=None):
    payload = {'chat_id': chat_id, 'message_id': message_id, 'text': text, 'parse_mode': 'HTML',
               'disable_web_page_preview': True, 'reply_markup': keyboard(buttons or [])}
    return _call('editMessageText', payload, background=True)


def answer_callback(callback_id, text=''):
    return _call('answerCallbackQuery', {'callback_query_id': callback_id, 'text': text[:200]}, background=True)


def deep_link(param):
    username = getattr(settings, 'TELEGRAM_BOT_USERNAME', '')
    return f'https://t.me/{username}?start={param}' if username else ''
