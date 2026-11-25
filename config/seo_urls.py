"""sitemap.xml va robots.txt."""

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.http import HttpResponse
from django.urls import reverse
from django.views.decorators.cache import cache_page

from masters import seo
from masters.locations import DISTRICT_CHOICES
from masters.models import Category, Master


class I18nSitemap(Sitemap):
    """Har bir sahifa ikki tilda (o'zbekcha / ruscha), hreflang bilan."""
    i18n = True
    alternates = True
    x_default = True


class StaticSitemap(I18nSitemap):
    changefreq = 'weekly'

    def items(self):
        return ['repair_service:index', 'masters:list', 'repair_service:catalog',
                'repair_service:offer', 'repair_service:privacy']

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        return 1.0 if item == 'repair_service:index' else 0.3 if 'offer' in item or 'privacy' in item else 0.8


class CategorySitemap(I18nSitemap):
    """Yo'nalish va yo'nalish+tuman sahifalari — faqat ustasi borlari (bo'sh sahifa indekslanmaydi)."""
    changefreq = 'daily'

    def items(self):
        pages = []
        for category in Category.objects.filter(is_active=True):
            if seo.has_masters(category):
                pages.append((category, ''))
                pages.extend((category, slug) for slug, _name in DISTRICT_CHOICES if seo.has_masters(category, slug))
        return pages

    def location(self, item):
        return seo.category_url(*item)

    def priority(self, item):
        return 0.7 if item[1] else 0.9


class MasterSitemap(I18nSitemap):
    changefreq = 'weekly'
    priority = 0.6

    def items(self):
        return Master.objects.public().order_by('pk')

    def lastmod(self, master):
        return master.updated_at


SITEMAPS = {'static': StaticSitemap, 'categories': CategorySitemap, 'masters': MasterSitemap}

# Shaxsiy yoki texnik sahifalar — qidiruvga kirmaydi
PRIVATE_PATHS = ['/admin/', '/kabinet/', '/buyurtma/', '/buyurtmalarim/', '/baho/', '/kod/', '/api/',
                 '/payments/', '/tolov/', '/telegram/', '/kirish/', '/parolni-tiklash/', '/healthz/', '/i18n/', '/push/', '/offline/', '/e/']


@cache_page(60 * 60 * 24)
def robots_txt(request):
    lines = ['User-agent: *']
    for path in PRIVATE_PATHS:
        lines.append(f'Disallow: {path}')
        if path not in ('/admin/', '/api/', '/payments/', '/telegram/', '/healthz/', '/i18n/', '/kod/', '/push/',
                        '/offline/'):
            lines.append(f'Disallow: /ru{path}')
    # Shaxsiy koordinata bilan qidiruv natijalari
    lines += ['Disallow: /*?*lat=', 'Disallow: /*?*q=', '',
              f"Sitemap: {request.build_absolute_uri(reverse('sitemap'))}"]
    if getattr(settings, 'SEO_DISALLOW_ALL', False):   # sinov serveri indekslanmasin
        lines = ['User-agent: *', 'Disallow: /']
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain; charset=utf-8')
