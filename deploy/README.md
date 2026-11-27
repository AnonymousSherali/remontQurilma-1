# Serverga o'rnatish (Ubuntu 24.04, bitta VPS)

> **Tezroq yo'l — Docker:** loyiha ildizidagi `docker-compose.yml` sayt, PostgreSQL, Redis, soatlik
> vazifalar va HTTPS'ni (Caddy) bitta buyruq bilan ko'taradi: `docker compose up -d --build`.
> To'liq ro'yxat — `docs/ISHGA_TUSHIRISH.md`. Quyida — Docker'siz, qo'lda o'rnatish.

Sxema: **nginx** (HTTPS, statik fayllar) → **gunicorn** (Django) → **PostgreSQL** + **Redis**.
Kichik loyiha uchun 2 GB RAM, 1–2 CPU yetarli. Fayllar:

| Fayl | Vazifasi |
|---|---|
| `gunicorn.conf.py` | worker soni, taymautlar |
| `systemd/techservice.service` | gunicorn'ni xizmat sifatida ishga tushirish |
| `nginx/techservice.conf` | HTTPS, `/static/`, `/media/`, proksi |
| `cron.txt` | soatlik `process_orders`, sessiyalarni tozalash, zaxira |
| `scripts/deploy.sh` | yangi versiyani chiqarish (migrate, collectstatic, reload, healthz) |
| `scripts/backup.sh` | kunlik zaxira: `pg_dump` + yuklangan fayllar, 14 kun saqlanadi |

Hamma joyda `techservice.uz` ni o'z domeningizga almashtiring.

## 1. Paketlar va foydalanuvchi

```bash
sudo timedatectl set-timezone Asia/Tashkent
sudo apt update && sudo apt install -y python3-venv python3-dev git nginx postgresql redis-server \
    gettext certbot python3-certbot-nginx sqlite3
sudo adduser --system --group --home /srv/techservice techservice
sudo -u techservice mkdir -p /srv/techservice/{media,private_media,backups,logs}
```

## 2. Ma'lumotlar bazasi

```bash
sudo -u postgres psql -c "CREATE ROLE techservice LOGIN PASSWORD 'UZUN-TASODIFIY-PAROL';"
sudo -u postgres createdb -O techservice techservice
```

## 3. Kod va virtual muhit

```bash
sudo -u techservice git clone https://github.com/<owner>/remontQurilma-1.git /srv/techservice/app
sudo -u techservice python3 -m venv /srv/techservice/venv
cd /srv/techservice/app
sudo -u techservice /srv/techservice/venv/bin/pip install -r requirements.txt -r requirements-prod.txt
sudo -u techservice cp .env.example .env && sudo chmod 600 .env
```

`.env` da kamida:

```ini
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=...            # python3 -c "import secrets; print(secrets.token_urlsafe(50))"
DJANGO_ALLOWED_HOSTS=techservice.uz,www.techservice.uz
DJANGO_CSRF_TRUSTED_ORIGINS=https://techservice.uz,https://www.techservice.uz
SITE_URL=https://techservice.uz
DATABASE_URL=postgres://techservice:UZUN-TASODIFIY-PAROL@127.0.0.1:5432/techservice
REDIS_URL=redis://127.0.0.1:6379/1
DJANGO_MEDIA_ROOT=/srv/techservice/media
DJANGO_PRIVATE_MEDIA_ROOT=/srv/techservice/private_media
DJANGO_STATIC_ROOT=/srv/techservice/staticfiles
SMS_BACKEND=eskiz
# ... Eskiz, to'lov tizimlari, Telegram — .env.example ga qarang
```

```bash
sudo -u techservice bash -c 'set -a; source .env; set +a; \
  /srv/techservice/venv/bin/python manage.py migrate && \
  /srv/techservice/venv/bin/python manage.py setup_roles && \
  /srv/techservice/venv/bin/python manage.py collectstatic --noinput && \
  /srv/techservice/venv/bin/python manage.py createsuperuser && \
  /srv/techservice/venv/bin/python manage.py check --deploy'
```

`check --deploy` loyihaning o'z tekshiruvlarini ham bajaradi (`techservice.W001…W008`):
kesh, ma'lumotlar bazasi, SMS, SITE_URL, to'lov tizimlari, demo to'lov, oferta, maxfiy fayllar.
Hammasi tuzatilgach «System check identified no issues» chiqadi.

## 4. gunicorn, nginx, HTTPS

```bash
sudo cp deploy/systemd/techservice.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now techservice
curl http://127.0.0.1:8000/healthz/        # {"status": "ok", "db": "ok", "cache": "ok"}

sudo cp deploy/nginx/techservice.conf /etc/nginx/sites-available/techservice
sudo ln -s /etc/nginx/sites-available/techservice /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
# Sertifikat olinguncha 443-blokni vaqtincha izohga oling, keyin:
sudo certbot --nginx -d techservice.uz -d www.techservice.uz
sudo nginx -t && sudo systemctl reload nginx
sudo chown -R techservice:www-data /srv/techservice/staticfiles /srv/techservice/media
```

`deploy.sh` gunicorn'ni qayta yuklashi uchun (`/etc/sudoers.d/techservice`):

```
techservice ALL=NOPASSWD: /bin/systemctl reload techservice
```

## 5. Cron va zaxira

```bash
sudo -u techservice crontab -e     # deploy/cron.txt dagi qatorlarni qo'shing
```

Zaxira server bilan birga yo'qolmasligi uchun `backup.sh` oxiridagi `rclone` qatorini
yoqing (Google Drive, S3, boshqa server). **Zaxirani oyda bir marta tiklab ko'ring.**

### Zaxiradan tiklash

```bash
sudo systemctl stop techservice
sudo -u postgres dropdb techservice && sudo -u postgres createdb -O techservice techservice
sudo -u techservice pg_restore --no-owner --dbname="$DATABASE_URL" /srv/techservice/backups/db_YYYY-MM-DD_HHMM.dump
sudo -u techservice tar -xzf /srv/techservice/backups/files_YYYY-MM-DD_HHMM.tar.gz -C /srv/techservice
sudo systemctl start techservice
```

## 6. Integratsiyalar

```bash
python manage.py telegram_webhook          # Telegram botni ulash
python manage.py check_integrations        # sozlamalarni tekshirish
python manage.py check_integrations --live # Eskiz, Telegram va saytning o'ziga haqiqiy so'rov
```

Payme / Click / Uzum sinov muhitida tekshirish tartibi — `docs/INTEGRATSIYALAR.md`.

## 7. Yangilash

```bash
sudo -u techservice /srv/techservice/app/deploy/scripts/deploy.sh
```

## Monitoring

1. **Sayt ishlayaptimi** — [UptimeRobot](https://uptimerobot.com) (bepul) da yangi monitor:
   turi *HTTP(s) — Keyword*, manzil `https://techservice.uz/healthz/`, kalit so'z `"ok"`,
   interval 5 daqiqa, ogohlantirish — Telegram yoki email. 503 = baza yoki kesh ishlamayapti.
2. **Saytdagi xatolar** — [sentry.io](https://sentry.io) da *Django* loyihasi oching, DSN ni
   `.env` ga `SENTRY_DSN=...` qilib yozing va qayta ishga tushiring (`sentry-sdk`
   `requirements-prod.txt` da bor). Telefon, IP va cookie yuborilmaydi (`send_default_pii=False`).
   Tekshirish: `python manage.py shell -c "import sentry_sdk; sentry_sdk.capture_message('sinov')"`.
3. **Soatlik cron** — biror qadam xato bersa, `TELEGRAM_CHAT_ID` chatiga «🚨 process_orders xato
   bilan tugadi» xabari keladi (bir xil xato — 6 soatda bir marta), qolgan qadamlar baribir bajariladi.
4. Loglar: `journalctl -u techservice -p err -f`; cron: `/srv/techservice/logs/cron.log`
   (Docker: `docker compose logs -f web cron`).

`python manage.py launch_check` Sentry va Telegram ulanmagan bo'lsa ogohlantiradi.

## Ma'lumotlar joylashuvi

2026-yil 27-martdan kuchga kirgan o'zgartirishlarga ko'ra O'zbekistonda saqlash majburiyati
asosan **biometrik va genetik** ma'lumotlarga qoldirilgan. Ustalarning hujjat bilan selfisi
(yuz tasviri) biometrik ma'lumot hisoblanishi mumkin — u holda `PRIVATE_MEDIA_ROOT` mahalliy
serverda bo'lishi kerak. Hosting tanlashdan oldin amaldagi tahririni lex.uz da va yurist bilan tekshiring.
