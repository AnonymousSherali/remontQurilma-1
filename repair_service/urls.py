from django.urls import path
from . import views

app_name = 'repair_service'

urlpatterns = [
    path('', views.index, name='index'),
    path('submit/', views.submit_request, name='submit_request'),
    path('result/', views.result, name='result'),
]
