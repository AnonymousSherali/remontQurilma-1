#!/usr/bin/env bash
# Yangi versiyani serverga chiqarish (server'da, techservice foydalanuvchisi nomidan):
#   sudo -u techservice /srv/techservice/app/deploy/scripts/deploy.sh
# Xato bo'lsa to'xtaydi — eski versiya ishlashda davom etadi.
set -euo pipefail

APP=/srv/techservice/app
VENV=/srv/techservice/venv
BRANCH=${BRANCH:-master}

cd "$APP"
git fetch --quiet origin "$BRANCH"
git checkout --quiet "$BRANCH"
git reset --quiet --hard "origin/$BRANCH"

"$VENV/bin/pip" install --quiet -r requirements.txt -r requirements-prod.txt
"$VENV/bin/python" manage.py check --deploy --fail-level ERROR
"$VENV/bin/python" manage.py migrate --noinput
"$VENV/bin/python" manage.py collectstatic --noinput --verbosity 0
"$VENV/bin/python" manage.py compilemessages --ignore "venv/*" --verbosity 0
"$VENV/bin/python" manage.py createcachetable

# gunicorn'ni uzilishsiz qayta yuklash (HUP — eski workerlar so'rovni tugatib chiqadi)
sudo /bin/systemctl reload techservice
sleep 2
curl --fail --silent --max-time 10 http://127.0.0.1:8000/healthz/ >/dev/null \
    && echo "✓ Yangilandi: $(git log -1 --format='%h %s')" \
    || { echo "✗ healthz javob bermadi — journalctl -u techservice ni tekshiring"; exit 1; }
