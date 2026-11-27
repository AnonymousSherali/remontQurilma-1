"""
URL configuration for TechService project.

Ommaviy sahifalar ikki tilda: o'zbekcha prefikssiz (/ustalar/), ruscha /ru/ bilan
(/ru/ustalar/). Admin, API va to'lov tizimi webhook'i til prefiksisiz.
"""
from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.decorators.cache import cache_page

from config.seo_urls import SITEMAPS, robots_txt
from config.disputes_admin import dispute_detail, dispute_list
from config.support_admin import support_list, support_thread
from config.stats import stats_view
from config.admin_perms import require_perms
from masters import views as master_views
from repair_service import analytics, pwa
from repair_service.views import healthz
from otp import views as otp_views
from payments import click, payme, uzum
from telegram_bot import views as telegram_views

urlpatterns = [
    path('healthz/', healthz, name='healthz'),
    path('robots.txt', robots_txt, name='robots_txt'),
    path('e/', analytics.beacon, name='analytics_beacon'),
    path('manifest.webmanifest', pwa.manifest, name='manifest'),
    path('sw.js', pwa.service_worker, name='service_worker'),
    path('offline/', pwa.offline, name='offline'),
    path('push/obuna/', pwa.push_subscribe, name='push_subscribe'),
    path('push/bekor/', pwa.push_unsubscribe, name='push_unsubscribe'),
    path('sitemap.xml', cache_page(60 * 60)(sitemap), {'sitemaps': SITEMAPS}, name='sitemap'),
    path('admin/yordam/', admin.site.admin_view(
        require_perms('repair_service.view_supportthread')(support_list)), name='admin_support'),
    path('admin/yordam/<int:pk>/', admin.site.admin_view(
        require_perms('repair_service.view_supportthread', 'repair_service.change_supportthread')(support_thread)), name='admin_support_thread'),
    path('admin/nizolar/', admin.site.admin_view(
        require_perms('repair_service.view_servicerequest')(dispute_list)), name='admin_disputes'),
    path('admin/nizolar/<int:pk>/', admin.site.admin_view(
        require_perms('repair_service.view_servicerequest', 'repair_service.change_servicerequest')(dispute_detail)), name='admin_dispute'),
    path('admin/statistika/', admin.site.admin_view(
        require_perms('payments.view_payment')(stats_view)), name='admin_stats'),
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
