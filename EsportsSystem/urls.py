from datetime import datetime
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from app import forms, views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),  # Подключение Django admin
    # Общее
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('service_terms/', views.service_terms, name='service_terms'),
    path('privacy_policy/', views.privacy_policy, name='privacy_policy'),

    # Профиль
    path('profile/', views.profile, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/change_password/', views.change_password, name='change_password'),
    path('user/<str:username>/', views.view_profile, name='view_profile'),

    # Команда
    path('team/create/', views.create_team, name='create_team'),
    path('team/<int:team_id>/', views.team_page, name='team_page'),
    path('team/join/<str:invite_code>/', views.join_team, name='join_team'),
    path('team/leave/', views.leave_team, name='leave_team'),
    path('team/<int:team_id>/delete/', views.delete_team, name='delete_team'),
    path('team/<int:team_id>/transfer/<int:new_captain_id>/', views.transfer_leadership, name='transfer_leadership'),
    path('team/<int:team_id>/edit/', views.edit_team, name='edit_team'),
    path('team/<int:team_id>/remove/<int:member_id>/', views.remove_member, name='remove_member'),

    # Турниры
    path('tournaments/', views.tournaments, name='tournaments'),
    path('tournaments/my/', views.my_tournaments, name='my_tournaments'),
    path('tournaments/create/', views.create_tournament, name='create_tournament'),
    path('tournaments/<int:tournament_id>/', views.tournament_detail, name='tournament_detail'),
    path('tournaments/<int:tournament_id>/edit/', views.edit_tournament, name='edit_tournament'),
    path('tournaments/<int:tournament_id>/delete/', views.delete_tournament, name='delete_tournament'),
    path('tournaments/<int:tournament_id>/participate/', views.participate_tournament, name='participate_tournament'),
    path('tournaments/<int:tournament_id>/edit_roster/', views.edit_tournament_roster, name='edit_tournament_roster'),
    path('tournaments/<int:tournament_id>/remove_team/<int:team_id>/', views.remove_team_from_tournament, name='remove_team_from_tournament'),
    path('tournament/<int:tournament_id>/cancel/', views.cancel_tournament_participation, name='cancel_tournament_participation'),

    # Турнирные сетки
    path('tournaments/<int:tournament_id>/bracket/', views.tournament_bracket, name='tournament_bracket'),
    path('tournaments/<int:tournament_id>/generate_bracket/', views.generate_bracket, name='generate_bracket'),
    path('tournaments/<int:tournament_id>/manual_bracket/', views.manual_bracket_setup, name='manual_bracket_setup'),
    path('tournaments/<int:tournament_id>/stages/<int:stage_id>/edit/', views.edit_stage_format, name='edit_stage_format'),
    path('tournaments/<int:tournament_id>/stages/<int:stage_id>/complete/', views.complete_stage, name='complete_stage'),
    path('tournament/<int:tournament_id>/bracket/match/<int:match_id>/result/', views.bracket_match_result_inline, name='bracket_match_result_inline'),
    path('tournaments/<int:tournament_id>/bracket/match/<int:match_id>/score/', views.bracket_match_score_api, name='bracket_match_score_api'),

    # Матчи
    path('tournaments/<int:tournament_id>/matches/', views.tournament_matches, name='tournament_matches'),
    path('tournaments/<int:tournament_id>/matches/<int:match_id>/', views.match_detail, name='match_detail'),
    path('tournaments/<int:tournament_id>/matches/<int:match_id>/update/', views.update_match_result, name='update_match_result'),
    path('tournaments/<int:tournament_id>/matches/<int:match_id>/advanced_update/', views.advanced_match_result, name='advanced_match_result'),
    path('tournaments/<int:tournament_id>/matches/<int:match_id>/schedule/', views.edit_match_schedule, name='edit_match_schedule'),

    # Round Robin формат
    path('tournaments/<int:tournament_id>/round_robin/', views.round_robin_table, name='round_robin_table'),
    path('tournaments/<int:tournament_id>/round_robin_matches/<int:match_id>/update/', views.round_robin_match_result, name='round_robin_match_result'),

    # Аутентификация
    path('login/',
         auth_views.LoginView.as_view(
             template_name='app/auth/login.html',
             authentication_form=forms.BootstrapAuthenticationForm,
             extra_context={
                 'title': 'Войти',
                 'year': datetime.now().year,
             }
         ),
         name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
    
    # Восстановление пароля
    path('password_reset/', views.CustomPasswordResetView.as_view(), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html'
    ), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', views.CustomPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)