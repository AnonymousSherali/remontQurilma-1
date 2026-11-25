"""gunicorn sozlamalari: gunicorn -c deploy/gunicorn.conf.py config.wsgi"""
import multiprocessing
import os

bind = os.environ.get('GUNICORN_BIND', '127.0.0.1:8000')
# CPU*2+1 — odatiy tavsiya; kichik VPS (1–2 GB) uchun 3–5 yetarli
workers = int(os.environ.get('GUNICORN_WORKERS', min(multiprocessing.cpu_count() * 2 + 1, 5)))
# Telegram/SMS xabarlari alohida oqimda ketadi, shuning uchun gthread
worker_class = 'gthread'
threads = int(os.environ.get('GUNICORN_THREADS', 4))
timeout = 30
graceful_timeout = 30
keepalive = 5
# Xotira sizib chiqishidan himoya: har ~1000 so'rovda worker yangilanadi
max_requests = 1000
max_requests_jitter = 100
accesslog = '-'
errorlog = '-'
# Nginx X-Forwarded-For ni qo'yadi; faqat lokal proksiga ishonamiz
forwarded_allow_ips = '127.0.0.1'
