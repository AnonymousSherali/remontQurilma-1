"""Bazani namunaviy ma'lumotlar bilan to'ldirish.

Ishlatish:
    python manage.py seed_demo            # kategoriyalar, narxlar, brendlar, sharhlar
    python manage.py seed_demo --masters  # + demo ustalar, bajarilgan arizalar va baholar
    python manage.py seed_demo --reset    # avval eski kontentni o'chiradi

Diqqat: --masters faqat sinov/namoyish uchun. Haqiqiy saytda uydirma ustalar va
baholar ko'rsatilsa, bu iste'molchilarni chalg'itish hisoblanadi.
"""

import random
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from masters.locations import TASHKENT_DISTRICTS
from masters.models import Category, Master, Review
from repair_service.models import Brand, Service, ServiceRequest, Testimonial

CATEGORIES = [
    ('santexnik', 'Santexnik', '🚰', "Kran, unitaz, quvur, isitish tizimi"),
    ('elektrik', 'Elektrik', '⚡', "Rozetka, simlar, schyotchik, yoritish"),
    ('kir-yuvish-mashinasi', 'Kir yuvish mashinasi', '🧺', "Har qanday brend kir mashinalarini ta'mirlash"),
    ('muzlatgich', 'Muzlatgich', '🧊', "Muzlatgich va muzlatish kameralari"),
    ('konditsioner', 'Konditsioner', '❄️', "O'rnatish, tozalash, freon to'ldirish"),
    ('elektronika', 'Televizor va elektronika', '📺', "Televizor, mikroto'lqinli pech, changyutkich"),
    ('mebel', 'Mebel ustasi', '🪑', "Yig'ish, ta'mirlash, o'rnatish"),
    ('qulf-eshik', 'Eshik va qulf', '🔑', "Qulf ochish, almashtirish, eshik o'rnatish"),
]

# (kategoriya slug, nomi, narx, tavsif)
SERVICES = [
    ('kir-yuvish-mashinasi', 'Ustani chaqirish (ta\'mirlash buyurtma qilinsa)', 0, ''),
    ('kir-yuvish-mashinasi', 'Diagnostika (ta\'mirlamasdan)', 50000, ''),
    ('kir-yuvish-mashinasi', 'Kichik ta\'mir (bitta detal almashtirish)', 100000, ''),
    ('kir-yuvish-mashinasi', 'Kapital ta\'mir', 300000, ''),
    ('santexnik', 'Kran yoki smesitelni almashtirish', 80000, ''),
    ('santexnik', 'Unitaz o\'rnatish', 150000, ''),
    ('santexnik', 'Tiqilib qolgan quvurni tozalash', 100000, ''),
    ('elektrik', 'Rozetka yoki o\'chirgich o\'rnatish', 40000, 'bir dona'),
    ('elektrik', 'Lyustra o\'rnatish', 80000, ''),
    ('elektrik', 'Kvartirada simlarni almashtirish', 1500000, 'xona soniga qarab'),
    ('konditsioner', 'Konditsioner o\'rnatish', 400000, ''),
    ('konditsioner', 'Tozalash va profilaktika', 150000, ''),
]

BRANDS = [
    'Zanussi', 'Samsung', 'Candy', 'Siemens', 'LG', 'Bosch', 'Gorenje', 'Indesit',
    'Hansa', 'Electrolux', 'Beko', 'Ariston', 'Miele', 'Atlant', 'Ardo', 'Asko',
    'Daewoo', 'Brandt', 'Smeg', 'Vestel', 'Whirlpool', 'Zerowatt', 'Neff', 'Kaiser',
    'Renova', 'Haier', 'AEG',
]

TESTIMONIALS = [
    ('Dilshod Rahimov', "Usta o'sha kuni keldi va bir soatda tuzatdi. Narxi oldindan aytilgani kabi bo'ldi.", 5),
    ('Nodira Karimova', "Ikki soatda usta yetib keldi. Nasosni almashtirdi, ishi toza. Rahmat!", 5),
    ('Jasur To\'rayev', "Muammoni tushuntirib berishdi. Detal kutishga to'g'ri keldi, lekin natija yaxshi.", 4),
]

DEMO_MASTERS = [
    ('Bekzod Karimov', ['santexnik'], 9, "Quvur, isitish va kanalizatsiya bo'yicha 9 yillik tajriba."),
    ('Sardor Aliyev', ['elektrik'], 12, "Litsenziyalangan elektrik. Kvartira va ofislarda simlarni almashtirish."),
    ('Rustam Yo\'ldoshev', ['kir-yuvish-mashinasi', 'muzlatgich'], 15, "Samsung va LG servis markazida ishlaganman."),
    ('Jamshid Toshmatov', ['konditsioner', 'muzlatgich'], 7, "Konditsioner o'rnatish va freon to'ldirish."),
    ('Akmal Rahimov', ['santexnik', 'elektrik'], 5, "Kichik uy ta'mirlari: kran, rozetka, lyustra."),
    ('Ulug\'bek Nazarov', ['kir-yuvish-mashinasi'], 11, "Bosch, Electrolux, Indesit. Original ehtiyot qismlar."),
    ('Otabek Ergashev', ['elektronika'], 8, "Televizor va mikroto'lqinli pech ta'miri."),
    ('Farrux Mirzayev', ['mebel', 'qulf-eshik'], 6, "Mebel yig'ish, eshik va qulf o'rnatish."),
    ('Shoxrux Qodirov', ['santexnik'], 3, "Yosh, lekin aniq va tez ishlayman."),
    ('Doniyor Saidov', ['elektrik', 'konditsioner'], 10, "Elektr va iqlim texnikasi."),
]

CLIENT_NAMES = ['Malika', 'Nodira', 'Dilnoza', 'Aziz', 'Gulnora', 'Timur', 'Zarina', 'Anvar', 'Kamola', 'Sherzod']
COMMENTS = [
    "Vaqtida keldi, hammasini tushuntirib berdi.",
    "Ishi toza, narxi kelishilganidek bo'ldi.",
    "Biroz kechikdi, lekin sifatli qildi.",
    "Juda madaniyatli usta, tavsiya qilaman!",
    "",
    "Muammoni tez topdi va o'sha kuni hal qildi.",
]


class Command(BaseCommand):
    help = "Bazani namunaviy ma'lumotlar bilan to'ldiradi"

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help="Avval eski kontentni o'chiradi")
        parser.add_argument('--masters', action='store_true', help="Demo ustalar, arizalar va baholarni ham qo'shadi")

    @transaction.atomic
    def handle(self, *args, **options):
        if options['reset']:
            Service.objects.all().delete()
            Brand.objects.all().delete()
            Testimonial.objects.all().delete()
            Review.objects.all().delete()
            ServiceRequest.objects.filter(phone__startswith='+99899000').delete()
            get_user_model().objects.filter(username__startswith='99899100').delete()
            self.stdout.write(self.style.WARNING("Eski ma'lumotlar o'chirildi."))

        categories = {}
        for order, (slug, name, icon, description) in enumerate(CATEGORIES, start=1):
            categories[slug], _ = Category.objects.get_or_create(
                slug=slug, defaults={'name': name, 'icon': icon, 'description': description, 'order': order},
            )
        self.stdout.write(f'Kategoriyalar: {len(categories)}')

        created = 0
        for order, (slug, name, price, description) in enumerate(SERVICES, start=1):
            _, is_new = Service.objects.get_or_create(
                name=name,
                defaults={'category': categories[slug], 'price_from': price, 'description': description, 'order': order},
            )
            created += is_new
        self.stdout.write(f"Narxlar: {created} ta yangi")

        created = 0
        static_img = Path(settings.BASE_DIR) / 'static' / 'img'
        for order, name in enumerate(BRANDS, start=1):
            brand, is_new = Brand.objects.get_or_create(name=name, defaults={'order': order})
            logo_path = static_img / f'brand{order}.png'
            if not brand.logo and logo_path.exists():
                with logo_path.open('rb') as fh:
                    brand.logo.save(f'{name.lower()}.png', File(fh), save=True)
            created += is_new
        self.stdout.write(f"Brendlar: {created} ta yangi")

        for client_name, text, rating in TESTIMONIALS:
            Testimonial.objects.get_or_create(client_name=client_name, defaults={'text': text, 'rating': rating})

        if options['masters']:
            self._seed_masters(categories)

        self.stdout.write(self.style.SUCCESS("Namunaviy ma'lumotlar tayyor."))

    def _seed_masters(self, categories):
        rng = random.Random(42)  # har safar bir xil natija
        User = get_user_model()
        made = 0
        for i, (name, slugs, years, bio) in enumerate(DEMO_MASTERS):
            phone = f'+998991000{i:03d}'
            if Master.objects.filter(phone=phone).exists():
                continue
            _, district, lat, lng = TASHKENT_DISTRICTS[i % len(TASHKENT_DISTRICTS)]
            user = User.objects.create_user(username=phone.lstrip('+'), password='demo-parol-123', first_name=name)
            master = Master.objects.create(
                user=user, full_name=name, phone=phone, experience_years=years, bio=bio,
                address=district,
                latitude=round(lat + rng.uniform(-0.012, 0.012), 6),
                longitude=round(lng + rng.uniform(-0.012, 0.012), 6),
                service_radius_km=rng.choice([10, 15, 20]),
                is_verified=True,
            )
            master.categories.set([categories[s] for s in slugs])

            # Baholar faqat bajarilgan ariza orqali — haqiqiy oqim bilan bir xil
            for j in range(rng.randint(0, 6)):
                request = ServiceRequest.objects.create(
                    name=rng.choice(CLIENT_NAMES), phone=f'+99899000{i:02d}{j:02d}',
                    master=master, category=categories[slugs[0]], consent=True,
                    status=ServiceRequest.STATUS_COMPLETED,
                )
                base = rng.choice([3, 4, 4, 5, 5, 5])
                Review.objects.create(
                    master=master, service_request=request, author_name=request.name,
                    quality=min(5, base + rng.choice([0, 0, 1])), punctuality=max(1, base - rng.choice([0, 0, 1])),
                    price=base, politeness=min(5, base + 1), comment=rng.choice(COMMENTS),
                )
            made += 1
        self.stdout.write(f"Demo ustalar: {made} ta (parol: demo-parol-123)")
