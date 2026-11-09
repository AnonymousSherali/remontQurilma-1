"""Yuklangan rasmlarni xavfsiz va yengil qilish.

- faqat haqiqiy rasm (JPEG, PNG, WEBP) qabul qilinadi — Pillow bilan tekshiriladi;
- telefon burilishi (EXIF Orientation) hisobga olinadi, so'ng BARCHA EXIF olib tashlanadi:
  telefon rasmlarida GPS koordinata bo'ladi, ya'ni mijozning uy manzili oshkor bo'lardi;
- katta tomoni 1600 px gacha kichraytiriladi, 400 px li kichik nusxa yaratiladi;
- hammasi JPEG ga o'giriladi (bir xil format, kichik hajm).
"""

from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.translation import gettext as _
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_MB = 10
MAX_SIDE = 1600
THUMB_SIDE = 400
ALLOWED_FORMATS = {'JPEG', 'PNG', 'WEBP', 'MPO'}  # MPO — ba'zi telefonlarning JPEG varianti
MAX_PHOTOS_PER_SIDE = 12  # bitta buyurtmaga usta 12 ta, mijoz 12 ta


def _encode(image, side):
    copy = image.copy()
    copy.thumbnail((side, side), Image.LANCZOS)
    buffer = BytesIO()
    copy.save(buffer, format='JPEG', quality=85, optimize=True, progressive=True)  # exif berilmaydi
    return ContentFile(buffer.getvalue())


def process_upload(upload):
    """Qaytaradi: (asosiy_rasm, kichik_nusxa) ContentFile'lar. Noto'g'ri fayl -> ValidationError."""
    if upload.size > MAX_UPLOAD_MB * 1024 * 1024:
        raise ValidationError(_('Rasm hajmi %(mb)s MB dan oshmasligi kerak') % {'mb': MAX_UPLOAD_MB})
    try:
        with Image.open(upload) as probe:
            probe.verify()  # buzilgan yoki rasm bo'lmagan faylni aniqlaydi
        upload.seek(0)
        image = Image.open(upload)
        if image.format not in ALLOWED_FORMATS:
            raise ValidationError(_('Faqat JPG, PNG yoki WEBP rasm yuklang'))
        if image.width * image.height > 60_000_000:  # "dekompressiya bombasi"dan himoya
            raise ValidationError(_('Rasm juda katta'))
        image = ImageOps.exif_transpose(image).convert('RGB')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValidationError(_('Bu fayl rasm emas yoki buzilgan'))
    return _encode(image, MAX_SIDE), _encode(image, THUMB_SIDE)


# ---------- Kim, qachon ----------

def _models():
    from .models import OrderEvent, OrderPhoto, ServiceRequest as SR
    return OrderEvent, OrderPhoto, SR


def allowed_kinds(order, actor):
    """Shu tomon hozir qaysi turdagi rasmni yuklay oladi (bo'sh — yuklay olmaydi)."""
    OrderEvent, OrderPhoto, SR = _models()
    if actor == OrderEvent.ACTOR_CUSTOMER and order.status in (
            SR.STATUS_NEW, SR.STATUS_ACCEPTED, SR.STATUS_ARRIVED, SR.STATUS_IN_PROGRESS,
            SR.STATUS_COMPLETED, SR.STATUS_DISPUTED):
        return [OrderPhoto.KIND_PROBLEM]
    if actor == OrderEvent.ACTOR_MASTER and order.status in (
            SR.STATUS_ACCEPTED, SR.STATUS_ARRIVED, SR.STATUS_IN_PROGRESS, SR.STATUS_COMPLETED, SR.STATUS_DISPUTED):
        return [OrderPhoto.KIND_BEFORE, OrderPhoto.KIND_AFTER]
    return []


def can_delete(photo, actor):
    """O'z rasmini o'chirish mumkin — tasdiqlangan yoki nizodagi buyurtmada emas (dalil saqlanadi)."""
    OrderEvent, OrderPhoto, SR = _models()
    return photo.uploaded_by == actor and photo.order.status not in (SR.STATUS_CONFIRMED, SR.STATUS_DISPUTED)


def add_photos(order, actor, kind, files, caption=''):
    """Bir nechta rasmni qo'shadi. Qaytaradi: (qo'shilganlar soni, xatolar ro'yxati)."""
    OrderEvent, OrderPhoto, SR = _models()
    if kind not in allowed_kinds(order, actor):
        return 0, [_("Hozir bu turdagi rasm yuklab bo'lmaydi")]
    left = MAX_PHOTOS_PER_SIDE - order.photos.filter(uploaded_by=actor).count()
    errors = []
    if len(files) > left:
        errors.append(_("Bitta buyurtmaga ko'pi bilan %(n)s ta rasm") % {'n': MAX_PHOTOS_PER_SIDE})
        files = files[:max(left, 0)]
    added = 0
    for upload in files:
        try:
            full, thumb = process_upload(upload)
        except ValidationError as error:
            errors.append(f'{upload.name}: {error.messages[0]}')
            continue
        photo = OrderPhoto(order=order, kind=kind, uploaded_by=actor, caption=caption[:200])
        photo.image.save('photo.jpg', full, save=False)
        photo.thumbnail.save('thumb.jpg', thumb, save=False)
        photo.save()
        added += 1
    return added, errors


def portfolio(master, limit=6):
    """Ustaning ommaviy portfoliosi: tasdiqlangan buyurtmalar bo'yicha "oldin/keyin" juftliklari.

    Faqat: buyurtma tasdiqlangan, mijoz portfolioga rozi, admin yashirmagan.
    """
    OrderEvent, OrderPhoto, SR = _models()
    photos = OrderPhoto.objects.filter(
        order__master=master, order__status=SR.STATUS_CONFIRMED, order__photos_in_portfolio=True,
        kind__in=[OrderPhoto.KIND_BEFORE, OrderPhoto.KIND_AFTER], is_hidden=False,
    ).select_related('order', 'order__catalog_item', 'order__category').order_by('-order__updated_at', 'created_at')
    works = {}
    for photo in photos:
        work = works.setdefault(photo.order_id, {'order': photo.order, 'before': [], 'after': []})
        work[photo.kind].append(photo)
    # Faqat "keyin" rasmi bor ishlar — natijasiz portfolio ma'nosiz
    return [w for w in works.values() if w['after']][:limit]
