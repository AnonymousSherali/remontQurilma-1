# Kir Yuvish Mashinalarini Ta'mirlash Sayti | TechService

Django frameworkida ishlab chiqilgan to'liq funktsional kir yuvish mashinalarini ta'mirlash xizmati veb-sayti.

## Loyiha haqida

TechService - bu maishiy texnikalarni, ayniqsa kir yuvish mashinalarini ta'mirlash xizmatlarini ko'rsatuvchi zamonaviy veb-sayt. Sayt mijozlarga onlayn ariza qoldirish, xizmatlar bilan tanishish va tajribali mutaxassislar bilan bog'lanish imkoniyatini beradi.

## Texnologiyalar

### Backend
- **Django 4.2.11** - Python veb-framework
- **SQLite** - Ma'lumotlar bazasi (development uchun)
- **Pillow** - Rasm fayllari bilan ishlash

### Frontend
- **HTML5, CSS3** - Zamonaviy markup va stillar
- **JavaScript (jQuery)** - Interaktiv funksiyalar
- **Bootstrap 3** - Responsive dizayn framework
- **WOW.js** - Animatsiyalar
- **jQuery Masked Input** - Telefon raqam formatlash

## Loyiha tuzilmasi

```
remontQurilma-1/
├── config/                 # Django loyihasi sozlamalari
│   ├── __init__.py
│   ├── settings.py        # Asosiy sozlamalar
│   ├── urls.py           # Asosiy URL marshrutlar
│   ├── wsgi.py           # WSGI konfiguratsiyasi
│   └── asgi.py           # ASGI konfiguratsiyasi
├── repair_service/        # Asosiy dastur (app)
│   ├── migrations/       # Ma'lumotlar bazasi migratsiyalari
│   ├── management/
│   │   └── commands/
│   │       └── seed_demo.py   # Namunaviy ma'lumot yuklash buyrug'i
│   ├── models.py         # Ma'lumotlar modellari
│   ├── views.py          # Ko'rinishlar + server validatsiyasi
│   ├── urls.py           # App URL marshrutlari
│   ├── admin.py          # Admin panel sozlamalari
│   ├── tests.py          # Testlar (21 ta)
│   └── apps.py           # App konfiguratsiyasi
├── templates/             # HTML shablonlar
│   ├── index.html        # Asosiy sahifa
│   └── result.html       # Ariza qabul qilinganligi haqida sahifa
├── static/                # Statik fayllar
│   ├── css/              # CSS stillar
│   │   ├── bootstrap.min.css
│   │   ├── style.css
│   │   ├── responsive.css
│   │   └── optimizations.css  # Sharh kartochkalari, xato uslublari, UX
│   ├── js/               # JavaScript fayllar
│   │   ├── jquery.js
│   │   ├── bootstrap.min.js
│   │   ├── main.js            # Menyu, skroll, Yandex xarita
│   │   └── optimizations.js   # AJAX forma, validatsiya, toast
│   └── img/              # Rasmlar
├── media/                 # Yuklangan fayllar (logotiplar)
├── manage.py             # Django boshqaruv skripti
├── requirements.txt      # Python bog'liqliklar
├── .env.example          # Muhit sozlamalari namunasi
└── README.md            # Ushbu fayl
```

## O'rnatish va ishga tushirish

### 1-qadam: Virtual muhitni yarating

**Linux/Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

### 2-qadam: Bog'liqliklarni o'rnating

```bash
pip install -r requirements.txt
```

### 3-qadam: Ma'lumotlar bazasi migratsiyalarini bajaring

```bash
python manage.py makemigrations
python manage.py migrate
```

### 4-qadam: Superuser (Admin) yarating

```bash
python manage.py createsuperuser
```

Ko'rsatmalarga rioya qiling va admin hisobini yarating:
- Username: o'zingizga kerakli nom
- Email: administrator@techservice.uz
- Password: xavfsiz parol kiriting

### 5-qadam: Namunaviy ma'lumotlarni yuklang (ixtiyoriy)

```bash
python manage.py seed_demo
```

Bu buyruq bazaga 6 ta xizmat, 16 ta brend va 6 ta sharh qo'shadi — sayt darhol
to'ldirilgan holda ko'rinadi. Takroran ishga tushirsangiz nusxa yaratmaydi.
Eskilarini o'chirib qayta yuklash uchun: `python manage.py seed_demo --reset`

### 6-qadam: Development serverni ishga tushiring

```bash
python manage.py runserver
```

Sayt quyidagi manzillarda ochiladi:
- **Asosiy sayt**: http://127.0.0.1:8000/
- **Admin panel**: http://127.0.0.1:8000/admin/

## Asosiy imkoniyatlar

### 🏠 Asosiy sahifa (/)

- **Responsive dizayn** - Barcha qurilmalarda (telefon, planshet, kompyuter) mukammal ko'rinadi
- **Onlayn ariza formasi** - Mijozlar to'g'ridan-to'g'ri saytdan ariza qoldirishlari mumkin
- **Xizmatlar ro'yxati** - Barcha ta'mirlash xizmatlarini ko'rish
- **Narxlar** - Shaffof narxlar tizimi
- **Brendlar** - Qo'llab-quvvatlanadigan barcha brendlar
- **Afzalliklar** - Nima uchun bizni tanlash kerakligi
- **Bog'lanish** - Telefon, email, manzil

### 📝 Ariza yuborish (/submit/)

- **AJAX orqali ishlaydi** - Sahifa yangilanmasdan ariza yuboriladi
- **Ma'lumotlar bazasiga saqlash** - Barcha arizalar bazada saqlanadi
- **Tasdiq sahifasi** - Ariza yuborilgandan keyin mijoz tasdiqlash sahifasini ko'radi
- **Avtomatik yo'naltirish** - 5 sekunddan keyin avtomatik asosiy sahifaga qaytadi

### 🔧 Admin panel (/admin/)

Admin panel orqali quyidagilarni boshqarish mumkin:

#### ✅ Arizalar (ServiceRequest)
- Barcha kelgan arizalarni ko'rish
- Holat o'zgartirish (Yangi, Jarayonda, Yakunlandi, Bekor qilindi)
- Filterlash (holat, sana, texnika turi)
- Qidiruv (ism, telefon, email)
- Admin izohlari qo'shish

#### 🛠 Xizmatlar (Service)
- Xizmatlarni qo'shish/o'chirish
- Narxlarni tahrirlash
- Ko'rsatish tartibini belgilash
- Faol/nofaol qilish

#### 💬 Sharhlar (Testimonial)
- Mijoz sharhlarini boshqarish
- Reytingni ko'rish
- Nashr qilish/yashirish
- Moderatsiya qilish

#### 🏢 Brendlar (Brand)
- Brend qo'shish/o'chirish
- Logotip yuklash
- Ko'rsatish tartibini sozlash
- Faol/nofaol qilish

## Shablon va backend bog'lanishi

Sayt kontenti bazadan olinadi, lekin **baza bo'sh bo'lsa asl dizayndagi
ma'lumotlar ko'rinib turadi**. Bu `{% for %} ... {% empty %} ... {% endfor %}`
orqali amalga oshirilgan:

| Bo'lim | Manba | Baza bo'sh bo'lganda |
|---|---|---|
| Narxlar jadvali | `Service` (faol) | Asl 6 qatorli narxlar |
| Brendlar | `Brand` (faol) | Asl 27 ta brend logotipi |
| Mijozlar sharhlari | `Testimonial` (nashr qilingan) | "Hozircha sharhlar yo'q" xabari |

Ya'ni admin paneldan xizmat yoki brend qo'shsangiz, u darhol saytda paydo
bo'ladi va statik ro'yxat o'rnini egallaydi.

## Testlar

```bash
python manage.py test repair_service
```

21 ta test qamrab oladi: sahifa ochilishi, bazadan kontent chiqishi, faol
bo'lmagan yozuvlar yashirilishi, forma validatsiyasi (ism, telefon, email),
AJAX va AJAX'siz yuborish, `seed_demo` buyrug'i.

## Ma'lumotlar bazasi modellari

### ServiceRequest - Ta'mirlash arizalari

```python
name              # Mijoz ismi
phone             # Telefon raqam (+998 formatda)
email             # Email (ixtiyoriy)
problem_description # Muammo tavsifi
appliance_type    # Texnika turi (default: "Kir yuvish mashinasi")
brand             # Brend nomi
status            # Holat (new/in_progress/completed/cancelled)
created_at        # Yaratilgan sana
updated_at        # Yangilangan sana
admin_notes       # Administrator izohlari
```

### Service - Xizmatlar

```python
name              # Xizmat nomi
description       # Tavsif
price_from        # Narx (dan)
is_active         # Faol holat
order             # Ko'rsatish tartibi
```

### Testimonial - Mijoz sharhlari

```python
client_name       # Mijoz ismi
text              # Sharh matni
rating            # Reyting (1-5)
is_published      # Nashr qilingan
created_at        # Yaratilgan sana
```

### Brand - Texnika brendlari

```python
name              # Brend nomi
logo              # Logo rasmi
is_active         # Faol holat
order             # Ko'rsatish tartibi
```

## Test ma'lumotlari qo'shish

Admin panel orqali quyidagi ma'lumotlarni qo'shishingiz mumkin:

### Xizmatlar namunasi

```
Xizmat: Diagnostika
Narx: 50000 so'm
Tavsif: To'liq diagnostika va muammoni aniqlash

Xizmat: Elektronika ta'mirlash
Narx: 100000 so'm
Tavsif: Elektron modullar va panellarni ta'mirlash

Xizmat: Mexanik ta'mirlash
Narx: 80000 so'm
Tavsif: Mexanik qismlar va yig'malar ta'mirlash
```

### Brendlar namunasi

```
- Samsung
- LG
- Bosch
- Ariston
- Indesit
- Candy
- Whirlpool
- Beko
```

## Production uchun sozlash

### 1. .env faylini yarating

`.env.example` faylini nusxalab `.env` yarating:

```bash
cp .env.example .env
```

Keyin `.env` faylini tahrirlang:

```env
DJANGO_SECRET_KEY=o-zgingizning-xavfsiz-maxfiy-kalitingiz-bu-yerda
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=techservice.uz,www.techservice.uz
DJANGO_CSRF_TRUSTED_ORIGINS=https://techservice.uz
```

### 2. Xavfsiz SECRET_KEY yaratish

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

`.env` fayli `config/settings.py` tomonidan avtomatik o'qiladi — qo'shimcha
kutubxona kerak emas. Serverda haqiqiy muhit o'zgaruvchisi o'rnatilgan bo'lsa,
u `.env` dagi qiymatdan ustun turadi.

### 3. Xavfsizlik sozlamalari avtomatik yoqiladi

`DJANGO_DEBUG=False` bo'lganda quyidagilar o'zi yoqiladi:
HTTPS'ga yo'naltirish, HSTS (1 yil), `Secure` cookie'lar, `X-Frame-Options: DENY`,
`nosniff` va reverse-proxy orqasida HTTPS ni to'g'ri aniqlash.

Tekshirish:

```bash
python manage.py check --deploy
```

### 4. PostgreSQL ma'lumotlar bazasini sozlang (tavsiya etiladi)

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'techservice_db',
        'USER': 'postgres_user',
        'PASSWORD': 'xavfsiz_parol',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

### 5. Statik fayllarni to'plang

```bash
python manage.py collectstatic
```

### 6. WSGI server o'rnating (Gunicorn)

```bash
pip install gunicorn
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

### 7. Nginx konfiguratsiyasi (namuna)

```nginx
server {
    listen 80;
    server_name techservice.uz www.techservice.uz;

    location /static/ {
        alias /path/to/remontQurilma-1/staticfiles/;
    }

    location /media/ {
        alias /path/to/remontQurilma-1/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Xavfsizlik

### CSRF himoyasi
- Barcha formalar CSRF token bilan himoyalangan
- `{% csrf_token %}` har bir formada ishlatilgan

### Ma'lumotlar validatsiyasi
- Server tomonida barcha ma'lumotlar tekshiriladi
- Email formati validatsiyasi
- Telefon raqam formatlash

### Parollar
- Django standart parol validatori ishlatiladi
- Minimal uzunlik, murakkablik talablari

## Muammolarni hal qilish

### Migration xatolari

Agar migration xatolari yuzaga kelsa:

```bash
# Barcha migratsiyalarni o'chirish
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc" -delete

# Yangi migratsiya yaratish
python manage.py makemigrations
python manage.py migrate
```

### Static fayllar yuklanmayapti

Development rejimda:
```python
# settings.py da DEBUG = True bo'lishi kerak
DEBUG = True
```

Production rejimda:
```bash
python manage.py collectstatic --noinput
```

### Admin panel kirib bo'lmayapti

Superuser qayta yarating:
```bash
python manage.py createsuperuser
```

## Qo'llanma

### Yangi xizmat qo'shish

1. Admin panelga kiring: http://127.0.0.1:8000/admin/
2. "Xizmatlar" bo'limiga o'ting
3. "Xizmat qo'shish" tugmasini bosing
4. Ma'lumotlarni to'ldiring va saqlang

### Arizani ko'rib chiqish

1. Admin panelga kiring
2. "Ta'mirlash arizalari" bo'limiga o'ting
3. Kerakli arizani tanlang
4. Holatni o'zgartiring va izoh qo'shing
5. Saqlang

### Logo yuklash

1. Admin panelda "Brendlar" bo'limiga o'ting
2. Brendni tanlang yoki yangi qo'shing
3. "Logo" maydoniga rasm yuklang (PNG, JPG, SVG)
4. Saqlang

## Texnik qo'llab-quvvatlash

Savol va takliflar uchun:
- **Email**: info@techservice.uz
- **Telefon**: +998 90 123-45-67
- **Manzil**: Toshkent shahar, Amir Temur ko'chasi

## Litsenziya

© 2024 TechService. Barcha huquqlar himoyalangan.

---

**Ishlab chiqildi**: Django 4.2.11
**Til**: Python 3.8+
**Dizayn**: Bootstrap 3 + Custom CSS
**Lokalizatsiya**: O'zbek tili
**Vaqt mintaqasi**: Asia/Tashkent (UTC+5)
