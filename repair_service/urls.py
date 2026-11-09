from django.urls import path

from . import order_views, views

app_name = 'repair_service'

urlpatterns = [
    path('', views.index, name='index'),
    path('submit/', views.submit_request, name='submit_request'),
    path('result/', views.result, name='result'),
    path('narxlar/', views.catalog, name='catalog'),

    # Buyurtmachi: kuzatish va boshqarish
    path('buyurtma/<uuid:token>/', order_views.order_detail, name='order'),
    path('buyurtma/<uuid:token>/amal/<slug:action>/', order_views.order_action, name='order_action'),
    path('buyurtma/<uuid:token>/narx/<slug:decision>/', order_views.quote_decision, name='quote_decision'),
    path('buyurtma/<uuid:token>/tolov/<int:milestone_id>/', order_views.milestone_pay, name='milestone_pay'),
    path('buyurtma/<uuid:token>/chiqarish/<int:milestone_id>/', order_views.milestone_release,
         name='milestone_release'),
    path('buyurtmalarim/', order_views.my_orders, name='my_orders'),
    path('buyurtmalarim/chiqish/', order_views.my_orders_logout, name='my_orders_logout'),
]
