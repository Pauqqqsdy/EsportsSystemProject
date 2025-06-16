from django.urls import path
from app import views

urlpatterns = [
    path('create/', views.create_team, name='create_team'),
    path('<int:team_id>/', views.team_page, name='team_page'),
    path('join/<str:invite_code>/', views.join_team, name='join_team'),
    path('leave/', views.leave_team, name='leave_team'),
    path('<int:team_id>/delete/', views.delete_team, name='delete_team'),
    path('<int:team_id>/transfer/<int:new_captain_id>/', 
         views.transfer_leadership, name='transfer_leadership'),
]