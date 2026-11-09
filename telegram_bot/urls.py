from django.urls import path

from . import views

app_name = 'telegram_bot'

urlpatterns = [
    path('kabinet/telegram/ulash/', views.connect_master, name='connect'),
    path('kabinet/telegram/uzish/', views.disconnect_master, name='disconnect'),
]
