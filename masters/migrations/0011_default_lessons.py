"""Boshlang'ich kurs: platforma qoidalari bo'yicha 6 ta dars (admin'da tahrirlash mumkin)."""

from django.db import migrations

LESSONS = [
    ('qanday-ishlaydi', "Platforma qanday ishlaydi", "Как работает платформа",
     "Buyurtma bosqichlari va kim nimani belgilaydi.", "Этапы заказа и кто что отмечает.",
     """Har bir buyurtma 6 bosqichdan o'tadi: mijoz yaratadi → siz qabul qilasiz → «Joyida» → «Ishda» → «Bajarildi» → mijoz tasdiqlaydi.

Bosqichlarni sakrab o'tib bo'lmaydi va har biri tarixga yoziladi — mijoz ham, siz ham bir xil tarixni ko'rasiz. Nizo bo'lsa, administrator shu tarixga qaraydi.

Buyurtmalarni ikki yo'l bilan olasiz: mijoz sizni profildan tanlaydi yoki «Ochiq buyurtmalar» lentasidan o'zingiz olasiz. Lentada mijozning ismi, telefoni va aniq manzili buyurtmani olganingizdan keyin ochiladi.

Telegram'ni ulang yoki bildirishnomalarni yoqing — yangi buyurtma haqida darhol bilasiz. Tez javob berish ishonchlilik balingizni oshiradi.""",
     """Каждый заказ проходит 6 этапов: клиент создаёт → вы принимаете → «На месте» → «В работе» → «Выполнено» → клиент подтверждает.

Этапы нельзя пропускать, каждый записывается в историю — клиент и вы видите одну и ту же историю. При споре администратор смотрит на неё.

Заказы приходят двумя путями: клиент выбирает вас в профиле или вы сами берёте из ленты «Открытые заказы». Имя, телефон и точный адрес клиента открываются после того, как вы взяли заказ.

Подключите Telegram или уведомления — узнаете о новом заказе сразу. Быстрый ответ повышает балл надёжности."""),
    ('narx-va-tolov', "Narx taklif qilish va to'lov", "Предложение цены и оплата",
     "Narx kelishilmaguncha ish boshlanmaydi; pul bosqichma-bosqich.", "Без согласованной цены работа не начинается.",
     """Muammoni ko'rib, buyurtma sahifasida narx va to'lov rejasini taklif qiling: ish yakunida to'liq, 30% avans, uch qism yoki naqd. Mijoz rozi bo'lmaguncha «Ishni boshladim» tugmasi ishlamaydi.

Mijoz katalogdan xizmat tanlagan bo'lsa, narxingiz katalogdan 20% dan ko'p farq qilsa sababini yozing — mijoz farqni ko'radi.

Onlayn to'lovda pul platformada ushlab turiladi va bosqich bajarilgach sizga o'tadi. Keyingi bosqichga o'tish uchun unga tegishli qism to'langan bo'lishi kerak — bepul ishlab qolmaysiz. Mijoz {tasdiq_soat} soat javob bermasa, buyurtma avtomatik tasdiqlanadi.

Komissiya — {komissiya}% (PRO tarifida {pro_komissiya}%). Naqd to'lovda komissiya yo'q, lekin platforma pul bo'yicha kafolat bera olmaydi.""",
     """Осмотрите проблему и предложите на странице заказа цену и план оплаты: полностью по завершении, аванс 30%, три части или наличными. Пока клиент не согласится, кнопка «Начал работу» не работает.

Если клиент выбрал услугу из каталога, а ваша цена отличается больше чем на 20%, укажите причину — клиент увидит разницу.

При онлайн-оплате деньги удерживаются платформой и переходят к вам после этапа. Чтобы перейти к следующему этапу, соответствующая часть должна быть оплачена — вы не работаете бесплатно. Если клиент не отвечает {tasdiq_soat} часов, заказ подтверждается автоматически.

Комиссия — {komissiya}% (на тарифе PRO {pro_komissiya}%). При оплате наличными комиссии нет, но платформа не гарантирует оплату."""),
    ('vaqt-va-muloqot', "Kelish vaqti va mijoz bilan muloqot", "Время приезда и общение с клиентом",
     "Vaqtni belgilang, kechiksangiz — yozing.", "Назначайте время, при опоздании — пишите.",
     """Buyurtmani qabul qilgach, kelish vaqtini belgilang — mijoz xabar oladi, ikkalangizga vaqtdan oldin eslatma boradi. Ish jadvalingizni va dam olish kunlarini «Ish vaqti» sahifasida kiriting.

Savollarni buyurtma ichidagi yozishmada bering: nima olib kelish kerak, qayerdan kirish va h.k. Nizo bo'lsa, administrator yozishmani ko'radi — va'dalarni yozma qoldiring.

Kechiksangiz yoki bora olmasangiz, oldindan yozing va vaqtni o'zgartiring. 30 daqiqadan ko'p kechikish va kelmaslik ishonchlilik balini tushiradi.""",
     """Приняв заказ, назначьте время приезда — клиент получит уведомление, перед визитом обоим придёт напоминание. Укажите график и выходные на странице «Время работы».

Вопросы задавайте в переписке внутри заказа: что привезти, как пройти и т. п. При споре администратор видит переписку — фиксируйте договорённости письменно.

Если опаздываете или не можете приехать, напишите заранее и измените время. Опоздание больше чем на 30 минут и неявка снижают балл надёжности."""),
    ('rasmlar', "Ish rasmlari", "Фото работ",
     "Oldin va keyin — portfolio va dalil.", "До и после — портфолио и доказательство.",
     """Ishdan oldin va keyin rasmga oling (saytda yoki Telegram botga yuboring). Mijoz natijani ko'radi, tasdiqlangan ishlar rasmlari profilingizdagi portfolioga chiqadi.

Nizo bo'lsa, rasmlar eng kuchli dalil. Tasdiqlangan yoki nizodagi buyurtma rasmlarini o'chirib bo'lmaydi.

Rasmlardan joylashuv ma'lumotlari (GPS) avtomatik o'chiriladi.""",
     """Фотографируйте до и после работы (на сайте или отправьте в Telegram-бот). Клиент видит результат, фото подтверждённых работ попадают в портфолио в вашем профиле.

При споре фото — главное доказательство. Фото подтверждённого или спорного заказа удалить нельзя.

Данные о местоположении (GPS) из фото удаляются автоматически."""),
    ('nizo-kafolat-ball', "Nizo, kafolat va ishonchlilik bali", "Споры, гарантия и балл надёжности",
     "Nima ballni tushiradi va kafolat qanday ishlaydi.", "Что снижает балл и как работает гарантия.",
     """Mijoz natijadan norozi bo'lsa, nizo ochadi: to'lovlar muzlaydi, administrator ikkala tomonni eshitib qaror qiladi. Ko'pincha muammoni qayta kelib tuzatish bilan kelishiladi.

Tasdiqlangan ishga {kafolat_kun} kun kafolat: o'sha muammo qaytalansa, mijoz murojaat qiladi va siz bepul tuzatasiz, so'ng «Tuzatdim» ni bosasiz.

Ishonchlilik bali (0–100) so'nggi 90 kun bo'yicha: voz kechish, nizolar, kechikish va javob tezligi. Ball qidiruvdagi o'rningizga ta'sir qiladi — kabinetda ko'rsatkichlar va maslahatlar bor.""",
     """Если клиент недоволен, он открывает спор: оплаты замораживаются, администратор выслушивает обе стороны и принимает решение. Чаще всего договариваются, что мастер приедет и исправит.

На подтверждённую работу гарантия {kafolat_kun} дней: если проблема повторится, клиент обращается, вы исправляете бесплатно и нажимаете «Исправил».

Балл надёжности (0–100) за последние 90 дней: отказы, споры, опоздания и скорость ответа. Он влияет на место в поиске — в кабинете есть показатели и советы."""),
    ('pul-olish', "Pul olish va tariflar", "Получение денег и тарифы",
     "Karta, haftalik to'lov, TOP va PRO.", "Карта, еженедельные выплаты, TOP и PRO.",
     """Profilda karta raqamingizni kiriting — usiz pul o'tkazilmaydi. Chiqarilgan mablag' har hafta ({tolov_kuni}) kartangizga o'tkaziladi; {min_tolov} so'mdan kam summa keyingi haftaga o'tadi. O'tkazilganda xabar olasiz.

Platformadan foydalanish bepul. TOP — qidiruvda birinchi qatorlar, PRO — kam komissiya, lentada ustunlik va ko'proq faol buyurtma. Do'st ustani taklif qilsangiz, u birinchi ishini bajargach sizga bepul TOP beriladi.""",
     """Укажите номер карты в профиле — без него выплаты не производятся. Выпущенные средства переводятся на карту каждую неделю ({tolov_kuni}); сумма меньше {min_tolov} сум переносится на следующую неделю. О переводе придёт уведомление.

Пользоваться платформой бесплатно. TOP — первые строки в поиске, PRO — меньшая комиссия, приоритет в ленте и больше активных заказов. Пригласите знакомого мастера — после его первого заказа вы получите TOP бесплатно."""),
]


def create(apps, schema_editor):
    Lesson = apps.get_model('masters', 'Lesson')
    for order, (slug, title, title_ru, summary, summary_ru, body, body_ru) in enumerate(LESSONS, start=1):
        Lesson.objects.get_or_create(slug=slug, defaults=dict(
            title=title, title_ru=title_ru, summary=summary, summary_ru=summary_ru, body=body, body_ru=body_ru,
            order=order * 10))


class Migration(migrations.Migration):
    dependencies = [('masters', '0010_lessons')]
    operations = [migrations.RunPython(create, migrations.RunPython.noop)]
