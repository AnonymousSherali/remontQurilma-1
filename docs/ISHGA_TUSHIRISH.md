# Ishga tushirish — qadamma-qadam

Kod tayyor; quyidagilar **sizning** qadamlaringiz (shartnoma, domen, server). Har bosqich oxirida
`python manage.py launch_check` nima qolganini ko'rsatadi.

> ⚖️ Yuridik bandlar — umumiy yo'l-yo'riq, yuridik maslahat emas. Talablar o'zgarib turadi:
> amaldagi tahririni lex.uz da va yurist bilan tekshiring.

## 1. Yuridik asos (1–2 hafta)

- [ ] Tadbirkorlik subyekti: YaTT yoki MChJ (my.gov.uz), bank hisob raqami.
- [ ] Platforma modeli bo'yicha yurist xulosasi: mijoz pulini ushlab turish (eskrou) — agentlik
      shartnomasi yoki to'lov tashkilotining «xavfsiz bitim» xizmati (README → «Bosqichma-bosqich to'lov»).
- [ ] Oferta va maxfiylik siyosatini yuristga tekshirtirish → `.env`: `LEGAL_DRAFT=False`,
      `SITE_LEGAL_NAME`, `SITE_LEGAL_INN`, `SITE_LEGAL_ADDRESS`.
- [ ] Shaxsga doir ma'lumotlar: ma'lumotlar bazasini davlat reyestrida ro'yxatdan o'tkazish va
      saqlash joyi talablarini aniqlang (ustalarning hujjat bilan selfisi biometrik ma'lumot bo'lishi mumkin).
- [ ] Ustalar bilan munosabat: ular mustaqil (YaTT / o'zini o'zi band qilgan) — soliq masalasini tushuntiring.

## 2. Shartnomalar va kalitlar (parallel, 1–3 hafta)

Odatda so'raladi: ro'yxatdan o'tganlik guvohnomasi, rahbar pasporti, bank rekvizitlari, ishlab turgan
sayt (oferta, kontaktlar, narxlar ko'rinib turgan holda). Aniq ro'yxatni har bir kompaniyadan so'rang.

| Xizmat | Nima uchun | `.env` | Tekshirish |
|---|---|---|---|
| Eskiz | SMS kodlar va xabarlar | `SMS_BACKEND=eskiz`, `ESKIZ_*`, `SMS_SENDER` | matn shablonlarini tasdiqlatish |
| Payme Business | onlayn to'lov | `PAYME_*` | sandbox — docs/INTEGRATSIYALAR.md |
| Click | onlayn to'lov, avtomatik qaytarish | `CLICK_*` | kichik haqiqiy to'lov |
| Telegram | bot va admin xabarlari | `TELEGRAM_*` | `telegram_webhook` |
| Yandex Maps (ixtiyoriy) | xarita | `YANDEX_MAPS_API_KEY` | — |

## 3. Domen va server (1 kun)

- [ ] Domen (.uz — cctld.uz dagi akkreditatsiyalangan registratorlar orqali), DNS A-yozuvi → server IP.
- [ ] Server: Ubuntu 24.04, 2 GB RAM. Ma'lumot joylashuvi talabini hisobga oling (1-bo'lim).
- [ ] O'rnatish — ikki yo'l:
  - **Docker (tavsiya, eng tez):** `docker compose up -d --build` — sayt, PostgreSQL, Redis, soatlik
    vazifalar va **HTTPS (Caddy sertifikatni o'zi oladi)**. Fayllar: `Dockerfile`, `docker-compose.yml`,
    `deploy/Caddyfile`.
  - **Qo'lda (systemd + nginx):** `deploy/README.md`.
- [ ] `createsuperuser`, `webpush_keys`, `telegram_webhook`.
- [ ] Zaxira: Docker'da `docker compose exec db pg_dump -U techservice techservice > zaxira.sql` ni cron'ga,
      qo'lda o'rnatishda — `deploy/scripts/backup.sh`. **Tiklashni bir marta sinab ko'ring.**
- [ ] Monitoring: `https://domen/healthz/` ni UptimeRobot yoki shunga o'xshash xizmatga qo'shing.

## 4. Kontent (2–3 kun)

- [ ] `seed_demo` bilan qo'shilgan demo ustalar bo'lsa — o'chiring (`seed_demo --reset`).
- [ ] Yo'nalishlar, narxlar katalogi (bozor narxlariga qarab), brendlar.
- [ ] Kontaktlar (`SITE_PHONE`, `SITE_EMAIL`, `SITE_HOURS`), `static/img/og.png` (logotip bilan).
- [ ] O'quv darslarini ko'rib chiqing (admin → O'quv darslari), video qo'shing.
- [ ] Tariflar va promo foizlarini belgilang (`.env`).

## 5. Ishga tushirishdan oldingi tekshiruv (1 kun)

- [ ] `python manage.py launch_check --live` — «✓ Hammasi tayyor».
- [ ] `bash e2e/run.sh` — 11 qadam brauzerda.
- [ ] docs/INTEGRATSIYALAR.md dagi ssenariylar haqiqiy telefonlarda (Payme sandbox, Eskiz, Telegram).
- [ ] Google Search Console va Yandex Webmaster: `https://domen/sitemap.xml`.

## 6. Birinchi haftalar

- [ ] **Avval ustalar** (taklif → mijoz emas): kamida 5–10 ta tasdiqlangan usta har yo'nalishda
      (`/ustalar-uchun/` sahifasi, `NEW_MASTER_FREE_TOP_DAYS` — birinchi oy bepul TOP).
- [ ] Keyin mijozlar: UTM bilan reklama (`?utm_source=instagram&utm_campaign=start`), statistikada natija.
- [ ] Har kuni: `/admin/` — yangi arizalar, «Yordam», nizolar; haftada: NPS izohlari, to'lovlar.
