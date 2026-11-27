# TechService — production obraz: gunicorn + Django. Ishlatish: docker compose up -d (docker-compose.yml)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DJANGO_STATIC_ROOT=/app/staticfiles DJANGO_MEDIA_ROOT=/data/media DJANGO_PRIVATE_MEDIA_ROOT=/data/private_media

RUN apt-get update && apt-get install -y --no-install-recommends gettext curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app

WORKDIR /app
COPY requirements.txt requirements-prod.txt ./
RUN pip install -r requirements.txt -r requirements-prod.txt
COPY . .
# collectstatic va tarjimalar obraz yig'ilganda (maxfiy kalit kerak emas)
RUN DJANGO_SECRET_KEY=build-only DJANGO_DEBUG=True python manage.py collectstatic --noinput -v0 \
    && python manage.py compilemessages -l ru -v0 \
    && mkdir -p /data/media /data/private_media && chown -R app:app /data /app

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fs http://127.0.0.1:8000/healthz/ || exit 1
# Har ishga tushganda migratsiya (bir nechta nusxa bo'lsa — alohida «migrate» xizmatiga o'tkazing)
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py createcachetable && python manage.py setup_roles && gunicorn -c deploy/gunicorn.conf.py --bind 0.0.0.0:8000 config.wsgi"]
