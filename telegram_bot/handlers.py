"""Bot mantiqi: Telegram'dan kelgan yangilanishni (update) qayta ishlash.

Buyruqlar:
    /start o<kalit>  — mijoz: buyurtmani kuzatishni yoqish (saytdagi tugmadan)
    /start m<kod>    — usta: akkauntni ulash (kabinetdagi tugmadan)
    /buyurtmalar     — faol buyurtmalar ro'yxati
    /stop            — xabarlarni o'chirish (chatni uzish)

Tugmalar (faqat ustaga): "a:<buyurtma_id>:<amal>" — buyurtma bosqichini o'zgartirish.
Xavfsizlik: tugma faqat shu buyurtma biriktirilgan ustaning chatidan ishlaydi.
"""

import uuid

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone, translation
from django.utils.html import escape
from django.utils.translation import gettext as _

from masters.models import Master
from repair_service import workflow
from repair_service.models import ServiceRequest
from repair_service.phone import format_phone

from . import client
from .models import LinkCode


def _absolute(path):
    return settings.SITE_URL.rstrip('/') + path


def order_card(order):
    """Ustaga yuboriladigan buyurtma matni."""
    lines = [
        f'<b>#{order.pk} · {escape(order.get_status_display())}</b>',
        f'👤 {escape(order.name)}  📞 {format_phone(order.phone)}',
    ]
    if order.category:
        lines.append(f'🔧 {escape(order.category.name)}')
    if order.catalog_item:
        qty = f' × {order.quantity}' if order.quantity > 1 else ''
        estimate = order.catalog_estimate
        price = f" — {int(estimate):,} so'm".replace(',', ' ') if estimate else ''
        lines.append(f'📋 {escape(order.catalog_item.name)}{qty}{price}')
    if order.address:
        lines.append(f'📍 {escape(order.address)}')
    if order.problem_description:
        lines.append(f'📝 {escape(order.problem_description[:400])}')
    return '\n'.join(lines)


def master_buttons(order):
    """Ustaning keyingi qadami tugmasi + saytdagi sahifa havolasi."""
    row = []
    action = workflow.next_master_action(order)
    if action:
        row.append((f'✅ {action[1]}', f'a:{order.pk}:{action[0]}'))
    rows = [row] if row else []
    rows.append([(_('Saytda ochish'), _absolute(order.get_master_url()))])
    return rows


def _reply(chat_id, text, buttons=None):
    client.send_message(chat_id, text, buttons, background=False)


# ---------- /start ----------

def _link_order(chat_id, param):
    try:
        token = uuid.UUID(hex=param[1:])
    except ValueError:
        return _reply(chat_id, _("Havola noto'g'ri yoki eskirgan."))
    order = ServiceRequest.objects.filter(review_token=token).first()
    if order is None:
        return _reply(chat_id, _('Buyurtma topilmadi.'))
    order.telegram_chat_id = chat_id
    order.save(update_fields=['telegram_chat_id'])
    with translation.override(order.language or 'uz'):
        _reply(chat_id, _("✅ Buyurtma #%(id)s ulandi. Endi barcha o'zgarishlar shu yerga keladi.\n\nHozirgi holat: <b>%(status)s</b>") % {
            'id': order.pk, 'status': escape(order.get_status_display())},
            [[(_('Buyurtmani ochish'), _absolute(order.get_customer_url()))]])


def _link_master(chat_id, param):
    link = LinkCode.objects.select_related('master').filter(code=param[1:]).first()
    if link is None or not link.is_valid:
        return _reply(chat_id, _("Ulash havolasi eskirgan. Kabinetdan qaytadan «Telegram'ni ulash» ni bosing."))
    master = link.master
    Master.objects.filter(telegram_chat_id=chat_id).exclude(pk=master.pk).update(telegram_chat_id=None)
    master.telegram_chat_id = chat_id
    try:
        master.save(update_fields=['telegram_chat_id'])
    except IntegrityError:
        return _reply(chat_id, _('Bu chat boshqa akkauntga ulangan.'))
    link.used_at = timezone.now()
    link.save(update_fields=['used_at'])
    _reply(chat_id, _("✅ Salom, %(name)s! Akkauntingiz ulandi. Yangi buyurtmalar shu yerga tugmalar bilan keladi.\n\n/buyurtmalar — faol buyurtmalar\n/stop — o'chirish") % {
        'name': escape(master.full_name)})


def _start(chat_id, text):
    parts = text.split(maxsplit=1)
    param = parts[1].strip() if len(parts) > 1 else ''
    if param.startswith('o'):
        return _link_order(chat_id, param)
    if param.startswith('m'):
        return _link_master(chat_id, param)
    _reply(chat_id, _("Assalomu alaykum! Bu %(site)s boti.\n\n• Buyurtmachilar: buyurtma sahifasidagi «Telegram'da kuzatish» tugmasini bosing.\n• Ustalar: kabinetda «Telegram'ni ulash» tugmasini bosing.") % {
        'site': escape(settings.SITE_INFO.get('name', ''))},
        [[(_('Saytga o\'tish'), settings.SITE_URL)]])


# ---------- /buyurtmalar, /stop ----------

def _orders(chat_id):
    master = Master.objects.filter(telegram_chat_id=chat_id).first()
    if master:
        active = master.requests.filter(status__in=ServiceRequest.OPEN_STATUSES).select_related('category')[:10]
        if not active:
            return _reply(chat_id, _("Faol buyurtmalar yo'q."))
        for order in active:
            _reply(chat_id, order_card(order), master_buttons(order))
        return None
    orders = ServiceRequest.objects.filter(telegram_chat_id=chat_id).order_by('-created_at')[:10]
    if not orders:
        return _reply(chat_id, _("Ulangan buyurtmalar yo'q."))
    for order in orders:
        with translation.override(order.language or 'uz'):
            _reply(chat_id, f'#{order.pk} · <b>{escape(order.get_status_display())}</b>',
                   [[(_('Buyurtmani ochish'), _absolute(order.get_customer_url()))]])
    return None


def _stop(chat_id):
    Master.objects.filter(telegram_chat_id=chat_id).update(telegram_chat_id=None)
    ServiceRequest.objects.filter(telegram_chat_id=chat_id).update(telegram_chat_id=None)
    _reply(chat_id, _("Xabarlar o'chirildi. Endi xabarlar SMS orqali keladi."))


# ---------- tugma bosilishi ----------

def _callback(callback):
    chat_id = callback['message']['chat']['id']
    message_id = callback['message']['message_id']
    try:
        prefix, order_id, action = callback.get('data', '').split(':')
        order = ServiceRequest.objects.select_related('master', 'category').get(pk=int(order_id))
    except (ValueError, ServiceRequest.DoesNotExist):
        return client.answer_callback(callback['id'], _("Noma'lum amal"))
    if prefix != 'a' or not order.master or order.master.telegram_chat_id != chat_id:
        return client.answer_callback(callback['id'], _("Bu buyurtma sizga tegishli emas"))
    try:
        workflow.apply(order, workflow.MASTER, action)
    except workflow.WorkflowError as error:
        return client.answer_callback(callback['id'], str(error))
    order.refresh_from_db()
    client.answer_callback(callback['id'], order.get_status_display())
    client.edit_message(chat_id, message_id, order_card(order), master_buttons(order))
    return None


def handle_update(update):
    with translation.override(settings.LANGUAGE_CODE):
        if 'callback_query' in update:
            return _callback(update['callback_query'])
        message = update.get('message') or {}
        text = (message.get('text') or '').strip()
        chat_id = (message.get('chat') or {}).get('id')
        if not chat_id or not text.startswith('/'):
            return None
        command = text.split()[0].split('@')[0].lower()
        if command == '/start':
            return _start(chat_id, text)
        if command in ('/buyurtmalar', '/orders', '/заказы'):
            return _orders(chat_id)
        if command == '/stop':
            return _stop(chat_id)
        return _reply(chat_id, _('Buyruqlar: /buyurtmalar, /stop'))
