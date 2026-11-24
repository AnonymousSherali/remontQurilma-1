#!/usr/bin/env bash
# Kunlik zaxira nusxa: ma'lumotlar bazasi + yuklangan fayllar.
#   cron: 30 3 * * *  /srv/techservice/app/deploy/scripts/backup.sh
# Tiklash: deploy/README.md -> "Zaxiradan tiklash"
set -euo pipefail
umask 077   # zaxirada shaxsiy ma'lumotlar bor — faqat egasi o'qiydi

APP=/srv/techservice/app
DEST=${BACKUP_DIR:-/srv/techservice/backups}
KEEP_DAYS=${BACKUP_KEEP_DAYS:-14}
STAMP=$(date +%Y-%m-%d_%H%M)

mkdir -p "$DEST"
set -a; source "$APP/.env"; set +a

if [[ "${DATABASE_URL:-}" == postgres* ]]; then
    pg_dump --format=custom --no-owner --dbname="$DATABASE_URL" --file="$DEST/db_$STAMP.dump"
else
    sqlite3 "$APP/db.sqlite3" ".backup '$DEST/db_$STAMP.sqlite3'"
fi

tar --create --gzip --file="$DEST/files_$STAMP.tar.gz" \
    --directory=/srv/techservice media private_media 2>/dev/null || true

# Eski nusxalarni o'chirish
find "$DEST" -type f -name 'db_*' -mtime +"$KEEP_DAYS" -delete
find "$DEST" -type f -name 'files_*' -mtime +"$KEEP_DAYS" -delete

# Server bilan birga yo'qolmasligi uchun boshqa joyga nusxalang (masalan rclone bilan):
# rclone copy "$DEST" remote:techservice-backups --max-age 25h
echo "Zaxira: $DEST/db_$STAMP.* va files_$STAMP.tar.gz"
