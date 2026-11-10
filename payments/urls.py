from django.urls import path

from . import views

app_name = 'payments'

urlpatterns = [
    path('tolov/demo/<int:milestone_id>/', views.demo_checkout, name='demo_checkout'),
    path('tolov/demo/tarif/<int:purchase_id>/', views.demo_purchase, name='demo_purchase'),
    path('kabinet/tarif/', views.tariffs_page, name='tariffs'),
    path('kabinet/tarif/<slug:code>/', views.tariff_buy, name='tariff_buy'),
]
