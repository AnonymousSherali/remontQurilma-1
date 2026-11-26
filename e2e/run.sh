#!/usr/bin/env bash
# To'liq ssenariyni brauzerda (Playwright) o'tkazadi: ariza → usta oladi → narx → to'lov → bosqichlar →
# tasdiqlash va baho → ustaga to'lov → kafolat → yozishma → yordam → qayta chaqirish.
# Alohida sinov bazasida (haqiqiy bazaga tegmaydi), demo to'lov va konsol SMS bilan.
#   bash e2e/run.sh            (talab: node + playwright: npm i -g playwright && npx playwright install chromium)
set -euo pipefail
cd "$(dirname "$0")/.."
WORK=$(mktemp -d)
PORT=${E2E_PORT:-8765}
export DJANGO_DEBUG=True DATABASE_URL="sqlite:///$WORK/e2e.sqlite3" DJANGO_MEDIA_ROOT="$WORK/media" \
       DJANGO_PRIVATE_MEDIA_ROOT="$WORK/private" PAYMENT_PROVIDERS=demo ALLOW_DEMO_PAYMENTS=True SMS_BACKEND=console \
       FEED_PRO_HEAD_START_MINUTES=0 SITE_URL="http://127.0.0.1:$PORT" REDIS_URL= DJANGO_CACHE= TELEGRAM_BOT_TOKEN= WEBPUSH_PRIVATE_KEY=
python manage.py migrate --noinput -v0
CREDS=$(python manage.py e2e_seed | tail -n 1)   # konsol SMS chiqishi aralashmasin
python manage.py runserver "127.0.0.1:$PORT" --noreload >"$WORK/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null; rm -rf "$WORK"' EXIT
for _ in $(seq 30); do curl -s "http://127.0.0.1:$PORT/healthz/" >/dev/null && break; sleep 0.5; done
E2E_BASE="http://127.0.0.1:$PORT" E2E_CREDS="$CREDS" NODE_PATH="${NODE_PATH:-$(npm root -g)}" node e2e/scenario.js
