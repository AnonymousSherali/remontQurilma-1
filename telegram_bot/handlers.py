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
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.utils import timezone, translation
from django.utils.html import escape
from django.utils.translation import gettext as _

from masters.models import Master
from repair_service import photos as photo_rules
from repair_service import workflow
from repair_service.models import OrderPhoto, ServiceRequest
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

def open_order_card(order, master):
    """Lentadagi buyurtma: shaxsiy ma'lumotlarsiz (ism, telefon, aniq manzil buyurtma olingach ochiladi)."""
    lines = [f'<b>🆕 {_("Ochiq buyurtma")} #{order.pk}</b>']
    if order.category:
        lines.append(f'🔧 {escape(order.category.name)}')
    if order.catalog_item:
        qty = f' × {order.quantity}' if order.quantity > 1 else ''
        estimate = order.catalog_estimate
        price = f" — {int(estimate):,} so'm".replace(',', ' ') if estimate else ''
        lines.append(f'📋 {escape(order.catalog_item.name)}{qty}{price}')
    where = [w for w in (getattr(order, 'area', ''), f'{order.distance_km} km' if getattr(order, 'distance_km', None) is not None else '') if w]
    if where:
        lines.append('📍 ' + ' · '.join(where))
    if order.problem_description:
        lines.append(f'📝 {escape(order.problem_description[:300])}')
    if not master.is_pro and not getattr(order, 'claimable', True):
        lines.append('⏳ ' + _('PRO ustalar ustunligi: %(time)s dan olishingiz mumkin') % {
            'time': timezone.localtime(order.claimable_from).strftime('%H:%M')})
    return '\n'.join(lines)


# ---------- rasm ----------

ACTIVE_FOR_PHOTOS = (ServiceRequest.STATUS_ACCEPTED, ServiceRequest.STATUS_ARRIVED, ServiceRequest.STATUS_IN_PROGRESS,
                     ServiceRequest.STATUS_COMPLETED, ServiceRequest.STATUS_DISPUTED)
PENDING_PHOTOS_TTL = 15 * 60


def _photo_file_id(message):
    if message.get('photo'):
        return message['photo'][-1]['file_id']  # oxirgisi — eng katta o'lcham
    document = message.get('document') or {}
    if (document.get('mime_type') or '').startswith('image/'):
        return document['file_id']
    return None


def _attach(chat_id, order, actor, file_ids, caption=''):
    """Telegram'dan kelgan rasmlarni buyurtmaga biriktiradi (saytdagi bilan bir xil tekshiruvlar)."""
    files = []
    for file_id in file_ids:
        data = client.download_file(file_id)
        if data:
            files.append(SimpleUploadedFile('telegram.jpg', data, content_type='image/jpeg'))
    if not files:
        return _reply(chat_id, _("Rasmni yuklab bo'lmadi. Qaytadan yuboring."))
    if actor == workflow.MASTER:
        kind = OrderPhoto.KIND_AFTER if order.reached(ServiceRequest.STATUS_IN_PROGRESS) else OrderPhoto.KIND_BEFORE
    else:
        kind = OrderPhoto.KIND_PROBLEM
    added, errors = photo_rules.add_photos(order, actor, kind, files, caption)
    if added:
        workflow.record(order, order.status, actor, note=_('%(n)s ta rasm yuklandi') % {'n': added} + ' (Telegram)')
        label = dict(OrderPhoto.KIND_CHOICES)[kind]
        _reply(chat_id, _('✅ #%(id)s buyurtmaga qo\'shildi: %(n)s ta rasm («%(kind)s»)') % {
            'id': order.pk, 'n': added, 'kind': label})
    for error in errors:
        _reply(chat_id, f'⚠️ {escape(str(error))}')
    return None


def _photo(chat_id, message):
    file_id = _photo_file_id(message)
    caption = (message.get('caption') or '')[:200]
    master = Master.objects.filter(telegram_chat_id=chat_id).first()
    if master is None:
        order = (ServiceRequest.objects.filter(telegram_chat_id=chat_id)
                 .exclude(status__in=[ServiceRequest.STATUS_CONFIRMED, ServiceRequest.STATUS_CANCELLED])
                 .order_by('-created_at').first())
        if order is None:
            return _reply(chat_id, _("Rasm biriktiriladigan faol buyurtma yo'q."))
        return _attach(chat_id, order, workflow.CUSTOMER, [file_id], caption)

    orders = list(master.requests.filter(status__in=ACTIVE_FOR_PHOTOS).order_by('-updated_at')[:8])
    if not orders:
        return _reply(chat_id, _("Rasm biriktiriladigan faol buyurtma yo'q."))
    if len(orders) == 1:
        return _attach(chat_id, orders[0], workflow.MASTER, [file_id], caption)
    # Bir nechta faol buyurtma: rasmlarni vaqtincha eslab qolib, qaysi biriga ekanini so'raymiz
    key = f'tg-photos:{chat_id}'
    pending = cache.get(key, [])
    first = not pending
    cache.set(key, (pending + [file_id])[-photo_rules.MAX_PHOTOS_PER_SIDE:], PENDING_PHOTOS_TTL)
    if first:  # albom yuborilganda savol bir marta beriladi
        _reply(chat_id, _('Bu rasm(lar) qaysi buyurtma uchun?'),
               [[(f'#{o.pk} · {o.name} · {o.get_status_display()}', f'p:{o.pk}')] for o in orders])
    return None


def _photo_target(callback, chat_id, order_id):
    master = Master.objects.filter(telegram_chat_id=chat_id).first()
    order = master and master.requests.filter(pk=order_id, status__in=ACTIVE_FOR_PHOTOS).first()
    key = f'tg-photos:{chat_id}'
    file_ids = cache.get(key, [])
    if not order or not file_ids:
        return client.answer_callback(callback['id'], _("Rasm topilmadi yoki muddati o'tdi — qaytadan yuboring"))
    cache.delete(key)
    client.answer_callback(callback['id'], f'#{order.pk}')
    return _attach(chat_id, order, workflow.MASTER, file_ids)


# ---------- tugma bosilishi ----------

def _claim(callback, chat_id, message_id, order_id):
    from masters import feed
    master = Master.objects.filter(telegram_chat_id=chat_id).first()
    if master is None:
        return client.answer_callback(callback['id'], _("Avval kabinetda Telegram'ni ulang"))
    try:
        order = feed.claim(master, order_id)
    except feed.FeedError as error:
        return client.answer_callback(callback['id'], str(error))
    order = ServiceRequest.objects.select_related('master', 'category', 'catalog_item').get(pk=order.pk)
    client.answer_callback(callback['id'], _('Buyurtma sizniki!'))
    client.edit_message(chat_id, message_id, order_card(order), master_buttons(order))
    return None


def _callback(callback):
    chat_id = callback['message']['chat']['id']
    message_id = callback['message']['message_id']
    parts = callback.get('data', '').split(':')
    try:
        prefix, order_id = parts[0], int(parts[1])
    except (IndexError, ValueError):
        return client.answer_callback(callback['id'], _("Noma'lum amal"))
    if prefix == 'c':
        return _claim(callback, chat_id, message_id, order_id)
    if prefix == 'p':
        return _photo_target(callback, chat_id, order_id)
    order = ServiceRequest.objects.select_related('master', 'category').filter(pk=order_id).first()
    if order is None or prefix != 'a' or len(parts) != 3:
        return client.answer_callback(callback['id'], _("Noma'lum amal"))
    if not order.master or order.master.telegram_chat_id != chat_id:
        return client.answer_callback(callback['id'], _("Bu buyurtma sizga tegishli emas"))
    try:
        workflow.apply(order, workflow.MASTER, parts[2])
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
        if not chat_id:
            return None
        if _photo_file_id(message):
            return _photo(chat_id, message)
        if not text.startswith('/'):
            return None
        command = text.split()[0].split('@')[0].lower()
        if command == '/start':
            return _start(chat_id, text)
        if command in ('/buyurtmalar', '/orders', '/заказы'):
            return _orders(chat_id)
        if command == '/stop':
            return _stop(chat_id)
        return _reply(chat_id, _('Buyruqlar: /buyurtmalar, /stop. Rasm yuborsangiz — buyurtmaga biriktiriladi.'))
