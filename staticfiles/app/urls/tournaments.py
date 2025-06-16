from django.urls import path
from app import views

urlpatterns = [
    path('', views.tournaments, name='tournaments'),
    path('create/', views.create_tournament, name='create_tournament'),
]