# TechService — uy ustalari platformasi

Santexnik, elektrik, kir yuvish mashinasi, konditsioner va boshqa maishiy
yo'nalishlardagi ustalarni **joylashuv bo'yicha** topish, **ariza qoldirish**
va **mezonlar bo'yicha baholash** platformasi. Django 5.2 LTS.

## Imkoniyatlar

**Mijozlar uchun**
- Yo'nalish + joylashuv bo'yicha eng yaqin ustalar (brauzer geolokatsiyasi yoki Toshkent tumani)
- Masofa yoki reyting bo'yicha saralash, radius tanlash, xaritada ko'rish
- Usta profili: tajriba, hudud, 4 mezon bo'yicha baholar, mijozlar izohlari
- Aniq ustaga yoki umumiy ariza (operator usta biriktiradi)
- Ish tugagach maxsus havola orqali baholash: **ish sifati, o'z vaqtida kelishi, narx adolatliligi, muomala madaniyati**

**Ustalar uchun**
- Telefon raqam bilan ro'yxatdan o'tish, yo'nalishlar, ish hududi (GPS / tuman / xaritada belgilash), xizmat radiusi
- Kabinet: kelgan arizalar, holatni o'zgartirish (qabul → bajarildi / bekor), baho havolasini nusxalash yoki Telegram orqali yuborish
- "Band" rejimi — vaqtincha qidiruvdan yashirinish

**Administrator uchun** (`/admin/`, django-unfold dizayni)
- Boshqaruv paneli: yangi arizalar, tasdiq kutayotgan ustalar, 7 kunlik grafik, so'nggi arizalar
- Ustalarni tasdiqlash / yashirish, arizaga usta biriktirish, baholarni moderatsiya qilish
- Yangi ariza haqida Telegram xabari (ixtiyoriy)

## Ishonch va xavfsizlik qarorlari

| Muammo | Yechim |
|---|---|
| Soxta baholar | Baho faqat **bajarilgan ariza** uchun berilgan maxsus havola orqali, har buyurtmaga bitta |
| 1 ta 5★ bahosi bor usta 200 ta 4.8★ li ustadan yuqori chiqishi | Reyting bo'yicha saralashda **Bayes o'rtachasi** |
| Ustaning uy manzili oshkor bo'lishi | Xarita va API'da koordinata ~1 km aniqlikkacha yaxlitlanadi |
| Tekshirilmagan odamlar usta bo'lib chiqishi | Admin tasdiqlamaguncha usta qidiruvda ko'rinmaydi |
| Usta o'zi bormaydigan uzoqlikdagi mijozga ko'rinishi | Har ustaning o'z xizmat radiusi hisobga olinadi |
| Spam arizalar | Bot tuzog'i (honeypot) + bitta IP'dan 10 daqiqada 5 ta ariza |
| Shaxsga doir ma'lumotlar | Har bir formada rozilik belgisi, rozilik bazada saqlanadi |

## O'rnatish

Python 3.10+ kerak.

```bash
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Linux/Mac

pip install -r requirements.txt
copy .env.example .env           # Linux/Mac: cp .env.example .env  — keyin qiymatlarni to'ldiring
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo       # kategoriyalar, narxlar, brendlar
python manage.py runserver
```

- Sayt: http://127.0.0.1:8000/
- Ustalar: http://127.0.0.1:8000/ustalar/
- Admin: http://127.0.0.1:8000/admin/

**Namoyish uchun demo ustalar:** `python manage.py seed_demo --masters` — 10 ta usta
(Toshkent tumanlari bo'ylab), bajarilgan arizalar va baholar qo'shadi. Kirish: telefon
`+998 99 100-00-00` … `-09`, parol `demo-parol-123`. **Haqiqiy saytda ishlatmang** —
uydirma ustalar va baholar mijozlarni chalg'itadi.

### Eski versiyadan yangilash

`git pull` dan keyin `pip install -r requirements.txt` va `python manage.py migrate`
yetarli. Mavjud arizalar saqlanadi — har biriga alohida baho kaliti beriladi.

## Sahifalar

| URL | Vazifasi |
|---|---|
| `/` | Bosh sahifa: qidiruv, yo'nalishlar, top ustalar, narxlar, ariza |
| `/ustalar/?category=santexnik&district=chilonzor&radius=10&sort=rating` | Qidiruv |
| `/ustalar/<id>/` | Usta profili va ariza |
| `/ustalar/royxatdan-otish/` | Usta ro'yxatdan o'tishi |
| `/kirish/`, `/kabinet/` | Usta kabineti |
| `/baho/<kalit>/` | Mijoz bahosi |
| `/api/ustalar/?lat=41.31&lng=69.28&category=elektrik` | JSON API (mobil ilova uchun) |

## Loyiha tuzilmasi

```
config/              sozlamalar, URL'lar, admin dashboard (dashboard.py)
repair_service/      arizalar, narxlar, brendlar, bosh sahifa, Telegram xabari
  phone.py             +998 raqamlarni yagona formatga keltirish
masters/             ustalar, kategoriyalar, baholar, qidiruv
  geo.py               masofa (haversine) — PostGIS'siz
  services.py          qidiruv va saralash
  locations.py         Toshkent tumanlari koordinatalari
templates/           base.html, bosh sahifa, masters/*, admin/index.html
static/css/app.css   dizayn tizimi (framework'siz, tungi rejim bilan)
static/js/app.js     telefon maskasi, geolokatsiya, AJAX formalar, xarita (jQuery'siz)
```

## Testlar

```bash
python manage.py test
```

50 ta test: telefon formati, masofa va qidiruv (radius, xizmat radiusi, Bayes
reytingi, tuman), ro'yxatdan o'tish (takroriy raqam, O'zbekistondan tashqari
koordinata, parol), kabinet holat o'tishlari, baholash oqimi, spam himoyasi,
admin sahifalari, migratsiya va `seed_demo`.

## Production

`.env` da:
```env
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<python -c "from django.core.management.utils import get_random_secret_key as g; print(g())">
DJANGO_ALLOWED_HOSTS=techservice.uz,www.techservice.uz
DJANGO_CSRF_TRUSTED_ORIGINS=https://techservice.uz
```

`DEBUG=False` bo'lganda HTTPS'ga yo'naltirish, HSTS, Secure cookie'lar avtomatik
yoqiladi. Tekshirish: `python manage.py check --deploy`.

```bash
python manage.py collectstatic
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3
```

Nginx `/static/` → `staticfiles/`, `/media/` → `media/` ni o'zi berishi va
`X-Real-IP` sarlavhasini qo'yishi kerak (spam cheklovi shu IP bo'yicha ishlaydi).

**Muhim:**
- **HTTPS majburiy** — brauzerlar geolokatsiyani faqat HTTPS (yoki localhost) da beradi.
- Bir nechta gunicorn worker bo'lsa, `CACHES` ni Redis'ga o'tkazing (spam hisoblagichi umumiy bo'lishi uchun).
- SQLite o'rniga PostgreSQL tavsiya etiladi.
- O'zbekiston qonunchiligiga ko'ra fuqarolarning shaxsga doir ma'lumotlari
  O'zbekiston hududidagi serverlarda saqlanishi talab qilinadi — hosting tanlashda
  hisobga oling va yurist bilan tekshiring.
