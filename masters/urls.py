from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = 'masters'

urlpatterns = [
    path('ustalar/', views.master_list, name='list'),
    path('ustalar/<int:pk>/', views.master_detail, name='detail'),
    path('ustalar/royxatdan-otish/', views.register, name='register'),

    path('kirish/', views.MasterLoginView.as_view(), name='login'),
    path('parolni-tiklash/', views.password_reset, name='password_reset'),
    path('chiqish/', LogoutView.as_view(), name='logout'),

    path('kabinet/', views.dashboard, name='dashboard'),
    path('kabinet/ochiq/', views.feed_list, name='feed'),
    path('kabinet/ochiq/<int:pk>/olish/', views.feed_claim, name='feed_claim'),
    path('kabinet/profil/', views.profile_edit, name='profile_edit'),
    path('kabinet/holat/', views.toggle_availability, name='toggle_availability'),
    path('kabinet/buyurtma/<int:pk>/', views.order_detail, name='order'),
    path('kabinet/buyurtma/<int:pk>/narx/', views.quote_propose, name='quote_propose'),
    path('kabinet/buyurtma/<int:pk>/rasm/', views.order_photo_upload, name='order_photo_upload'),
    path('kabinet/buyurtma/<int:pk>/rasm/<int:photo_id>/ochirish/', views.order_photo_delete,
         name='order_photo_delete'),
    path('kabinet/buyurtma/<int:pk>/kafolat/<int:claim_id>/', views.warranty_fixed, name='warranty_fixed'),
    path('kabinet/ariza/<int:pk>/<slug:action>/', views.request_action, name='request_action'),

    path('baho/<uuid:token>/', views.review_create, name='review'),
]
