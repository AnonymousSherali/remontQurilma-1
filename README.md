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

## Narxlar katalogi

`/narxlar/` — platforma narxlari (Urban Company tajribasi): yo'nalish bo'yicha filtr,
qidiruv (o'zbek va rus tilida), har bir xizmat uchun:

- **qat'iy narx** yoki **"...dan"**, birlik (xizmat / dona / metr / m² / nuqta / soat);
- **taxminiy vaqt** ("~40 daqiqa") va **narxga nima kiradi** ro'yxati;
- "Buyurtma berish" — xizmat tanlangan holda ariza (miqdor bilan), taxminiy summa
  buyurtmada saqlanadi va ustaga ko'rinadi.

Usta narx taklif qilganda katalog narxi oldindan to'ldiriladi. Taklif katalogdan
**20% dan ko'p farq qilsa, sababini yozish majburiy**, mijoz esa "katalogdan 35% qimmat"
belgisini ko'radi. Katalog admin'da: **Sayt kontenti → Narxlar** (ruscha nomlar,
"Ommabop" belgisi bosh sahifaga chiqaradi). Namunaviy 27 ta xizmat: `seed_demo`.

## Ish rasmlari

- **Mijoz** buyurtma sahifasida muammo rasmini yuklaydi (SMS-tasdiqdan keyin) — usta
  kerakli ehtiyot qismni oldindan biladi.
- **Usta** "Oldin" va "Keyin" rasmlarini yuklaydi (buyurtmani qabul qilgandan keyin).
  Ish boshlanmagan bo'lsa "Oldin", boshlangan bo'lsa "Keyin" avtomatik tanlanadi.
- Tasdiqlangan buyurtmalarning "oldin/keyin" juftliklari ustaning ommaviy profilida
  **"Bajarilgan ishlar"** bo'limiga chiqadi. Mijoz buyurtma sahifasida buni o'chira oladi;
  admin nomaqbul rasmni "Ish rasmlari" bo'limida yashiradi (buyurtmada dalil sifatida qoladi).
- Xavfsizlik: faqat haqiqiy JPG/PNG/WEBP (Pillow bilan tekshiriladi), 10 MB gacha, bir
  tomonga 12 ta; **EXIF butunlay o'chiriladi** (telefon rasmidagi GPS — mijozning uy
  manzili), 1600 px gacha kichraytiriladi, fayl nomlari tasodifiy.
- Nizo ochilgan yoki tasdiqlangan buyurtmada rasmni o'chirib bo'lmaydi — dalil saqlanadi;
  lekin qo'shimcha rasm yuklash mumkin.

> Eslatma: rasmlar `media/` orqali beriladi. Fayl nomlari taxmin qilib bo'lmaydigan,
> lekin havolani bilgan odam rasmni ko'ra oladi. Kerak bo'lsa keyinroq rasmlarni
> faqat buyurtma ishtirokchilariga beradigan himoyalangan ko'rinishga o'tkazish mumkin.

## Buyurtma bosqichlari

Buyurtmachi va usta statuslarni **navbat bilan** belgilaydi; ikkalasi ham bir xil
timeline'ni ko'radi (bosh sahifada namunasi, buyurtma sahifalarida jonli holati).

| # | Kim | Holat | Shart |
|---|---|---|---|
| 01 | Buyurtmachi | Buyurtma yaratildi | — |
| 02 | Usta | Qabul qilindi | — |
| 03 | Usta | Joyida | — |
| 04 | Usta | Ishda | narx kelishilgan + shu bosqich qismi to'langan |
| 05 | Usta | Bajarildi | shu bosqich qismi to'langan (3 qismli rejada) |
| 06 | Buyurtmachi | Tasdiqlandi | oxirgi qism to'langan; baho bilan birga |

- Bosqichni sakrab o'tib bo'lmaydi; har bir o'tish vaqti bilan tarixga yoziladi.
- Usta joyga kelgach bir tomonlama bekor qila olmaydi; buyurtmachi esa faqat
  "Muammo bor" (nizo) ocha oladi — pul muzlatiladi, admin hal qiladi.
- Usta "Bajarildi" deganidan keyin buyurtmachi 72 soat javob bermasa, buyurtma
  avtomatik tasdiqlanadi (`AUTO_CONFIRM_HOURS`).

## Bosqichma-bosqich to'lov (eskrou)

Upwork'dagi *milestone*lar va YouDo'dagi "Сделка без риска" g'oyasi:

1. Usta narx va to'lov rejasini taklif qiladi; mijoz SMS-tasdiq bilan rozi bo'ladi.
2. Rejalar: **yakunda 100%**, **30% avans + 70%**, **3 teng qism**
   (boshlanganda / bajarilganda / tasdiqlanganda) yoki **naqd** (platforma kafolatisiz).
3. Mijoz to'lagan pul ustaga emas, platformada **ushlab turiladi**. Usta tegishli
   bosqichni faqat shu qism to'langandan keyin belgilay oladi — bepul ishlamaydi.
4. Bosqichga yetilgach mijoz "Bosqichni tasdiqlab, to'lash" ni bosadi yoki 48 soatdan
   keyin avtomatik chiqariladi (`AUTO_RELEASE_HOURS`). Nizo ochilsa — hech narsa chiqmaydi.
5. Platforma komissiyasi `PLATFORM_FEE_PERCENT` (standart 10%). Ustaga o'tkazilgan
   pullar admin'da "Ustaning kartasiga o'tkazildi" deb belgilanadi.

To'lov tizimlari: `PAYMENT_PROVIDERS=payme,click` — mijoz har bir bosqichni Payme yoki
Click bilan to'lashni tanlaydi. `demo` — sinov sahifasi (faqat `DEBUG=True` da).

| Tizim | Manzil (kabinetda ko'rsatiladi) |
|---|---|
| Payme Merchant API | `/payments/payme/` (hisob maydoni: `milestone_id`) |
| Click Shop API | `/payments/click/prepare/` va `/payments/click/complete/` |

**Ikkala integratsiya ham rasmiy hujjat asosida yozilgan va protokol testlari bilan
qoplangan, lekin haqiqiy sinov muhitida (Payme sandbox, Click test vositasi)
tekshirilmagan** — ishga tushirishdan oldin o'sha yerdagi barcha testlardan o'tkazing.

Avtomatik tasdiqlash va chiqarish uchun cron (har soatda):

```bash
0 * * * *  cd /srv/techservice && venv/bin/python manage.py process_orders
```

> ⚖️ Platforma hisobida boshqa shaxs (usta) uchun pul ushlab turish to'lov
> xizmatlari bo'yicha qonunchilikka (ZRU-578 "To'lovlar va to'lov tizimlari
> to'g'risida") tegishli bo'lishi mumkin. Ishga tushirishdan oldin yurist bilan
> agentlik shartnomasi yoki litsenziyalangan to'lov tashkilotining "xavfsiz bitim"
> xizmatidan foydalanish masalasini aniqlang.

## SMS tasdiqlash

`otp` ilovasi: 6 xonali kod, 5 daqiqa amal qiladi, 5 ta urinish, bir raqamga
60 soniyada 1 / soatiga 5 ta, bir IP'dan soatiga 20 ta. Kod bazada xesh holida.

Qayerda ishlatiladi: usta ro'yxatdan o'tishi, ustaning parolni tiklashi,
buyurtmachining "Mening buyurtmalarim"ga kirishi va buyurtmadagi har qanday amal
(narxga rozilik, to'lov, tasdiqlash, bekor qilish). Buyurtma havolasi faqat
**ko'rish** imkonini beradi — havola begona qo'lga tushsa ham pul harakatlanmaydi.

`SMS_BACKEND=console` — kod server konsoliga chiqadi (va `DEBUG=True` da sahifada
ko'rsatiladi). `SMS_BACKEND=eskiz` — Eskiz.uz orqali haqiqiy SMS. Eskiz SMS
matnlarini shablon sifatida oldindan moderatsiyadan o'tkazishni talab qiladi.

Xabarnomalar: mijozga — ariza qabul qilinganda (kuzatish havolasi bilan), usta
qabul qilganda, yetib kelganda, ishni yakunlaganda, narx taklif qilganda; ustaga —
yangi buyurtma, mijoz tasdiqlaganda yoki nizo ochganda.

## Telegram bot

Bitta bot ikki vazifani bajaradi (admin'ga yangi ariza xabari ham shu bot orqali):

- **Buyurtmachi** buyurtma sahifasida «Telegram'da kuzatish» ni bosadi — bot buyurtmaga
  ulanadi va holat o'zgarishlari **SMS o'rniga Telegram'ga** keladi (SMS pulini tejaydi).
- **Usta** kabinetda «Telegram'ni ulash» ni bosadi (bir martalik kod, 30 daqiqa).
  Yangi buyurtmalar Telegram'ga **tugmalar bilan** keladi: «Qabul qilish» → «Joyga yetib
  keldim» → … — saytga kirmasdan boshqaradi. Barcha qoidalar (navbat, narx, to'lov)
  botda ham amal qiladi; tugma faqat shu buyurtma ustasining chatidan ishlaydi.
- Buyruqlar: `/buyurtmalar`, `/stop` (uzish — xabarlar yana SMS'ga qaytadi).

Sozlash: @BotFather'da bot yarating, `.env` ga `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`,
`TELEGRAM_WEBHOOK_SECRET` yozing, saytni HTTPS'da ishga tushirib bir marta:

```bash
python manage.py telegram_webhook
```

## Tillar

O'zbekcha (standart, `/ustalar/`) va ruscha (`/ru/ustalar/`). Sarlavhadagi UZ/RU
tugmasi bilan almashtiriladi; qidiruv tizimlari uchun `hreflang` qo'yilgan.
Kategoriya va narx nomlarining ruscha varianti admin'da `… (ruscha)` maydonlarida.
Mijozga SMS buyurtma qaysi tilda berilgan bo'lsa, o'sha tilda yuboriladi.

Matnlarni o'zgartirgach:

```bash
python manage.py makemessages -l ru   # GNU gettext kerak
# locale/ru/LC_MESSAGES/django.po ni tahrirlang
python manage.py compilemessages -l ru
```

Kompilyatsiya qilingan `django.mo` repozitoriyda bor — Windows'da gettext o'rnatish shart emas.

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

137 ta test: telefon formati, masofa va qidiruv, ro'yxatdan o'tish, buyurtma
bosqichlari (navbat, bekor qilish qoidalari, avtomatik tasdiqlash), eskrou
(rejalar, bosqichlar, nizo, avtomatik chiqarish), Payme protokoli, SMS kod
(muddat, urinishlar, cheklovlar, Eskiz), rus tili, admin sahifalari, Click protokoli, Telegram bot (ulash, tugmalar, xavfsizlik).

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
- Shaxsga doir ma'lumotlar: 2026-yil 27-martdan kuchga kirgan o'zgartirishlarga
  ko'ra O'zbekistonda saqlash majburiyati asosan biometrik va genetik ma'lumotlarga
  qoldirilgan; boshqalarini chet elda saqlash shartlar bilan ruxsat etilgan.
  Hosting tanlashdan oldin amaldagi tahririni lex.uz da va yurist bilan tekshiring.
- `process_orders` ni cron'ga qo'shing (yuqoriga qarang).
