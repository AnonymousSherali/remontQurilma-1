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
from repair_service.models import Brand, OrderEvent, Service, ServiceRequest, Testimonial

# (slug, nomi, ruscha nomi, belgi, tavsif)
CATEGORIES = [
    ('santexnik', 'Santexnik', 'Сантехник', '🚰', "Kran, unitaz, quvur, isitish tizimi"),
    ('elektrik', 'Elektrik', 'Электрик', '⚡', "Rozetka, simlar, schyotchik, yoritish"),
    ('kir-yuvish-mashinasi', 'Kir yuvish mashinasi', 'Стиральные машины', '🧺', "Har qanday brend kir mashinalarini ta'mirlash"),
    ('muzlatgich', 'Muzlatgich', 'Холодильники', '🧊', "Muzlatgich va muzlatish kameralari"),
    ('konditsioner', 'Konditsioner', 'Кондиционеры', '❄️', "O'rnatish, tozalash, freon to'ldirish"),
    ('elektronika', 'Televizor va elektronika', 'Телевизоры и электроника', '📺', "Televizor, mikroto'lqinli pech, changyutkich"),
    ('mebel', 'Mebel ustasi', 'Сборка и ремонт мебели', '🪑', "Yig'ish, ta'mirlash, o'rnatish"),
    ('qulf-eshik', 'Eshik va qulf', 'Двери и замки', '🔑', "Qulf ochish, almashtirish, eshik o'rnatish"),
]

# Narxlar katalogi (namunaviy narxlar — haqiqiy bozor narxlariga moslab admin'da o'zgartiring).
# (kategoriya, nomi, ruscha, narx, turi, birlik, daqiqa, ommabop, "nima kiradi" (| bilan), ruscha)
SERVICES = [
    ('kir-yuvish-mashinasi', "Diagnostika (ta'mirlash buyurtma qilinsa — bepul)", 'Диагностика (бесплатно при ремонте)', 0, 'fixed', 'service', 30, False, '', ''),
    ('kir-yuvish-mashinasi', "Diagnostika (ta'mirlamasdan)", 'Диагностика (без ремонта)', 50000, 'fixed', 'service', 30, False,
     "Ustaning kelishi|Nosozlikni aniqlash|Ta'mir narxini aytish", 'Выезд мастера|Поиск неисправности|Расчёт стоимости ремонта'),
    ('kir-yuvish-mashinasi', 'Nasosni almashtirish', 'Замена сливного насоса', 180000, 'from', 'service', 60, True,
     "Eski nasosni yechish|Yangi nasosni o'rnatish|Sinov|Ehtiyot qism narxi alohida", 'Демонтаж насоса|Установка нового|Проверка|Запчасть оплачивается отдельно'),
    ('kir-yuvish-mashinasi', "Podshipnik va salnik almashtirish", 'Замена подшипников и сальника', 450000, 'from', 'service', 240, False,
     "Barabanni qismlarga ajratish|Podshipnik va salnik|Yig'ish va sinov", 'Разборка бака|Подшипники и сальник|Сборка и проверка'),
    ('kir-yuvish-mashinasi', 'Isitish elementini (TEN) almashtirish', 'Замена ТЭНа', 200000, 'from', 'service', 60, False, '', ''),
    ('santexnik', 'Kran yoki smesitelni almashtirish', 'Замена крана или смесителя', 80000, 'fixed', 'piece', 40, True,
     "Eski kranni yechish|Yangisini o'rnatish|Germetik va lenta|Oqmasligini tekshirish", 'Демонтаж старого|Установка нового|Герметик и лента|Проверка на протечку'),
    ('santexnik', "Unitaz o'rnatish", 'Установка унитаза', 250000, 'fixed', 'piece', 120, True,
     "Eski unitazni olib tashlash|O'rnatish va ulash|Germetiklash", 'Демонтаж старого|Установка и подключение|Герметизация'),
    ('santexnik', 'Tiqilgan quvurni tozalash', 'Прочистка засора', 120000, 'from', 'service', 60, True, '', ''),
    ('santexnik', "Suv isitgich (boyler) o'rnatish", 'Установка бойлера', 300000, 'from', 'piece', 120, False, '', ''),
    ('santexnik', 'Quvur almashtirish (polipropilen)', 'Замена труб (полипропилен)', 60000, 'from', 'meter', None, False,
     "Eski quvurni yechish|Payvandlash|Material narxi alohida", 'Демонтаж|Пайка|Материал оплачивается отдельно'),
    ('elektrik', "Rozetka yoki o'chirgich o'rnatish", 'Установка розетки или выключателя', 40000, 'fixed', 'point', 20, True,
     "Eski rozetkani yechish|Yangisini ulash|Kuchlanishni tekshirish", 'Демонтаж старой|Подключение новой|Проверка напряжения'),
    ('elektrik', "Lyustra o'rnatish", 'Установка люстры', 100000, 'from', 'piece', 60, True, '', ''),
    ('elektrik', 'Avtomat (UZO) almashtirish', 'Замена автомата (УЗО)', 70000, 'fixed', 'piece', 30, False, '', ''),
    ('elektrik', 'Kvartirada simlarni almashtirish', 'Замена проводки в квартире', 1500000, 'from', 'service', 960, False,
     "Shtroba ochish|Yangi kabel tortish|Schyot va avtomatlarni ulash|Material narxi alohida", 'Штробление|Прокладка кабеля|Подключение щита|Материал отдельно'),
    ('muzlatgich', 'Muzlatgich diagnostikasi', 'Диагностика холодильника', 70000, 'fixed', 'service', 40, False, '', ''),
    ('muzlatgich', "Freon to'ldirish", 'Заправка фреоном', 350000, 'from', 'service', 90, True, '', ''),
    ('muzlatgich', 'Termostatni almashtirish', 'Замена термостата', 200000, 'from', 'service', 60, False, '', ''),
    ('konditsioner', "Konditsioner o'rnatish (7–12 BTU)", 'Установка кондиционера (7–12 BTU)', 450000, 'fixed', 'piece', 180, True,
     "3 metrgacha trassa|Kronshteynlar|Vakuumlash|Ishga tushirish", 'Трасса до 3 м|Кронштейны|Вакуумирование|Запуск'),
    ('konditsioner', 'Tozalash va profilaktika', 'Чистка и профилактика', 150000, 'fixed', 'piece', 60, True,
     "Filtr va radiatorni yuvish|Drenajni tozalash|Bosimni tekshirish", 'Мойка фильтров и радиатора|Чистка дренажа|Проверка давления'),
    ('konditsioner', "Freon to'ldirish", 'Заправка фреоном', 250000, 'from', 'piece', 60, False, '', ''),
    ('elektronika', 'Televizor diagnostikasi', 'Диагностика телевизора', 60000, 'fixed', 'service', 40, False, '', ''),
    ('elektronika', "Televizorni devorga o'rnatish", 'Установка телевизора на стену', 120000, 'fixed', 'piece', 60, True, '', ''),
    ('elektronika', "Mikroto'lqinli pech ta'miri", 'Ремонт микроволновки', 150000, 'from', 'service', 60, False, '', ''),
    ('mebel', "Shkaf yig'ish", 'Сборка шкафа', 200000, 'from', 'piece', 180, True, '', ''),
    ('mebel', "Oshxona mebelini yig'ish", 'Сборка кухни', 120000, 'from', 'meter', None, False, '', ''),
    ('mebel', "Polka yoki karniz o'rnatish", 'Установка полки или карниза', 50000, 'fixed', 'piece', 30, False, '', ''),
    ('qulf-eshik', 'Eshik qulfini ochish', 'Вскрытие дверного замка', 150000, 'from', 'service', 30, True, '', ''),
    ('qulf-eshik', 'Qulf almashtirish', 'Замена замка', 120000, 'fixed', 'piece', 60, False,
     "Eski qulfni yechish|Yangisini o'rnatish|Qulf narxi alohida", 'Демонтаж старого|Установка нового|Замок оплачивается отдельно'),
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
        for order, (slug, name, name_ru, icon, description) in enumerate(CATEGORIES, start=1):
            categories[slug], _ = Category.objects.get_or_create(
                slug=slug, defaults={'name': name, 'icon': icon, 'description': description, 'order': order},
            )
            if not categories[slug].name_ru:  # eski bazalarga ham ruscha nom qo'shiladi
                categories[slug].name_ru = name_ru
                categories[slug].save(update_fields=['name_ru'])
        self.stdout.write(f'Kategoriyalar: {len(categories)}')

        created = 0
        for order, (slug, name, name_ru, price, price_type, unit, minutes, popular, includes, includes_ru) in enumerate(
                SERVICES, start=1):
            service, is_new = Service.objects.get_or_create(name=name, defaults={
                'category': categories[slug], 'price_from': price, 'price_type': price_type, 'unit': unit,
                'duration_minutes': minutes, 'is_popular': popular, 'order': order, 'name_ru': name_ru,
                'includes': includes.replace('|', '\n'), 'includes_ru': includes_ru.replace('|', '\n'),
            })
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
                    status=ServiceRequest.STATUS_CONFIRMED,
                )
                for step, actor in zip(ServiceRequest.FLOW, ['customer', 'master', 'master', 'master', 'master', 'customer']):
                    OrderEvent.objects.create(order=request, status=step, actor=actor)
                base = rng.choice([3, 4, 4, 5, 5, 5])
                Review.objects.create(
                    master=master, service_request=request, author_name=request.name,
                    quality=min(5, base + rng.choice([0, 0, 1])), punctuality=max(1, base - rng.choice([0, 0, 1])),
                    price=base, politeness=min(5, base + 1), comment=rng.choice(COMMENTS),
                )
            made += 1
        self.stdout.write(f"Demo ustalar: {made} ta (parol: demo-parol-123)")
