from django.urls import path
from app import views

urlpatterns = [
    path('', views.profile, name='profile'),
    path('edit/', views.edit_profile, name='edit_profile'),
    path('change_password/', views.change_password, name='change_password'),
    path('user/<str:username>/', views.view_profile, name='view_profile'),
]