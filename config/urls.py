"""
URL configuration for TechService project.

Ommaviy sahifalar ikki tilda: o'zbekcha prefikssiz (/ustalar/), ruscha /ru/ bilan
(/ru/ustalar/). Admin, API va to'lov tizimi webhook'i til prefiksisiz.
"""
from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from config.stats import stats_view
from masters import views as master_views
from otp import views as otp_views
from payments import click, payme, uzum
from telegram_bot import views as telegram_views

urlpatterns = [
    path('admin/statistika/', admin.site.admin_view(stats_view), name='admin_stats'),
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),  # tilni almashtirish (set_language)
    path('api/ustalar/', master_views.api_masters, name='api_masters'),
    path('payments/payme/', payme.endpoint, name='payme_endpoint'),
    path('payments/click/prepare/', click.prepare, name='click_prepare'),
    path('payments/click/complete/', click.complete, name='click_complete'),
    path('payments/uzum/<slug:operation>/', uzum.endpoint, name='uzum_endpoint'),
    path('telegram/webhook/', telegram_views.webhook, name='telegram_webhook'),
    path('kod/yuborish/', otp_views.send_view, name='otp_send'),
    path('kod/tasdiqlash/', otp_views.verify_view, name='otp_verify'),
]

urlpatterns += i18n_patterns(
    path('', include('masters.urls')),
    path('', include('payments.urls')),
    path('', include('telegram_bot.urls')),
    path('', include('repair_service.urls')),
    prefix_default_language=False,
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
