from django.urls import path

from . import views

app_name = 'payments'

urlpatterns = [
    path('tolov/demo/<int:milestone_id>/', views.demo_checkout, name='demo_checkout'),
]
