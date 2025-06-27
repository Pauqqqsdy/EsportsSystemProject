from datetime import datetime
import random
from django.db.models import Q
from django.http import HttpRequest, JsonResponse, HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.urls import reverse
from .models import Tournament, TournamentBracket, BracketStage, BracketMatch, TournamentRegistration, UserProfile, Team, RoundRobinTable, RoundRobinMatch, RoundRobinResult
from .forms import (
    BracketGenerationForm, BracketStageForm, MatchResultForm, TeamCreationForm, 
    TournamentEditForm, TournamentForm, AvatarUploadForm, ExtendedUserCreationForm, 
    TournamentParticipationForm, User, AdvancedMatchResultForm, RoundRobinMatchResultForm,
    ManualBracketForm, MatchScheduleForm, TournamentRosterForm
)
from .bracket_features import (
    create_single_elimination_bracket, create_double_elimination_bracket, 
    create_round_robin_bracket, get_upcoming_matches, promote_winner_to_next_stage
)
from django.contrib.auth import update_session_auth_hash, login
from django.utils.crypto import get_random_string
from django.db import transaction
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.contrib.auth.views import PasswordResetView, PasswordResetConfirmView
from .statistics import update_round_robin_results
import json

class CustomPasswordResetView(PasswordResetView):
    template_name = 'registration/password_reset_form.html'
    email_template_name = 'registration/password_reset_email.txt'
    html_email_template_name = 'registration/password_reset_email.html'
    subject_template_name = 'registration/password_reset_site.txt'
    success_url = '/password_reset/done/'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['site_name'] = 'ZXC.Tournament'
        return context
    
    def form_valid(self, form):
        from django.conf import settings
        from django.contrib.sites.models import Site
        
        if hasattr(settings, 'SITE_DOMAIN'):
            current_site = Site.objects.get_current()
            current_site.domain = settings.SITE_DOMAIN
            current_site.name = getattr(settings, 'SITE_NAME', 'ZXC.Tournament')
            current_site.save()
        
        opts = {
            'use_https': getattr(settings, 'SITE_PROTOCOL', 'https') == 'https',
            'token_generator': self.token_generator,
            'from_email': getattr(self, 'from_email', None),
            'email_template_name': self.email_template_name,
            'subject_template_name': self.subject_template_name,
            'request': self.request,
            'html_email_template_name': self.html_email_template_name,
        }
        form.save(**opts)
        return super().form_valid(form)

class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'registration/password_reset_confirm.html'
    success_url = '/'
    
    def form_valid(self, form):
        user = form.save()
        
        login(self.request, user)
        
        messages.success(self.request, 'Пароль успешно изменён! Вы автоматически вошли в систему.')
        
        return HttpResponseRedirect(self.success_url)

def home(request):
    assert isinstance(request, HttpRequest)

    tournaments = Tournament.objects.filter(
        start_date__gte=timezone.now()
    ).order_by('start_date')[:6]

    return render(
        request,
        'app/index.html',
        {
            'title': 'ZXC.Tournament',
            'year': datetime.now().year,
            'tournaments': tournaments,
        }
    )
def register(request):
    if request.method == 'POST':
        form = ExtendedUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data['email']
            user.save()
            
            UserProfile.objects.create(user=user)
            
            login(request, user)
            messages.success(request, f'Добро пожаловать, {user.username}! Регистрация прошла успешно.')
            
            return redirect('home')
    else:
        form = ExtendedUserCreationForm()
    
    return render(request, 'app/auth/register.html', {
        'form': form,
        'title': 'Регистрация',
        'year': datetime.now().year,
    })

@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Пароль успешно изменен!')
            return redirect('profile')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'app/profile/change_password.html', {
        'form': form,
        'title': 'Смена пароля'
    })

def service_terms(request):
    return render(
        request,
        'app/service_terms.html',
        {
            'title': 'Пользовательское соглашение',
            'year': datetime.now().year,
        }
    )

def privacy_policy(request):
    return render(
        request,
        'app/privacy_policy.html',
        {
            'title': 'Политика конфиденциальности',
            'year': datetime.now().year,
        }
    )

@login_required
def profile(request, username=None):
    if username is None:
        profile_user = request.user
    else:
        profile_user = get_object_or_404(User, username=username)
    
    profile, created = UserProfile.objects.get_or_create(user=profile_user)
    
    is_owner = (request.user == profile_user)
    
    avatar_form = None
    if is_owner and request.method == 'POST':
        avatar_form = AvatarUploadForm(request.POST, request.FILES, instance=profile)
        if avatar_form.is_valid():
            avatar_form.save()
            return redirect('profile')
    elif is_owner:
        avatar_form = AvatarUploadForm(instance=profile)
    
    return render(request, 'app/profile/profile.html', {
        'profile_user': profile_user,
        'profile': profile,
        'is_owner': is_owner,
        'avatar_form': avatar_form,
        'title': 'Профиль',
        'year': datetime.now().year,
    })

@login_required
def edit_profile(request):
    profile = request.user.userprofile
    if request.method == 'POST':
        form = AvatarUploadForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect('profile')
    else:
        form = AvatarUploadForm(instance=profile)
    
    return render(request, 'app/profile/edit_profile.html', {
        'form': form,
        'profile': profile
    })

def view_profile(request, username):
    user = User.objects.get(username=username)
    profile = UserProfile.objects.get(user=user)
    is_owner = (request.user == user)
    
    return render(request, 'app/profile/profile.html', {
        'profile_user': user,
        'profile': profile,
        'is_owner': is_owner,
    })

@login_required
def create_team(request):
    if request.method == 'POST':
        form = TeamCreationForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    team = form.save(commit=False)
                    team.captain = request.user
                    
                    team.save()
                    
                    request.user.userprofile.team = team
                    request.user.userprofile.save()
                    
                    messages.success(request, f'Команда "{team.name}" успешно создана!')
                    return redirect('team_page', team_id=team.id)
                    
            except Exception as e:
                messages.error(request, f'Ошибка при создании команды: {str(e)}')
                return redirect('create_team')
    else:
        form = TeamCreationForm()
    
    return render(request, 'app/teams/create_team.html', {
        'form': form,
        'year': datetime.now().year,
    })

@login_required
def join_team(request, invite_code):
    try:
        team = Team.objects.get(invite_code=invite_code)
        user_profile = request.user.userprofile
        
        if user_profile.team:
            messages.error(request, 'Вы уже состоите в команде. Покиньте текущую команду, чтобы присоединиться к новой.')
            return redirect('profile')
            
        if team.is_full():
            messages.error(request, 'Команда уже полная')
        elif team.is_member(request.user):
            messages.warning(request, 'Вы уже в этой команде')
        else:
            team.members.add(request.user)
            user_profile.team = team
            user_profile.save()
            messages.success(request, f'Вы присоединились к команде {team.name}')
            
        return redirect('team_page', team_id=team.id)
    except Team.DoesNotExist:
        messages.error(request, 'Неверная ссылка приглашения')
        return redirect('profile')

@login_required
def team_page(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    is_member = team.is_member(request.user)
    is_captain = team.is_captain(request.user)
    
    return render(request, 'app/teams/team_page.html', {
        'team': team,
        'is_member': is_member,
        'is_captain': is_captain,
        'invite_link': request.build_absolute_uri(
            reverse('join_team', kwargs={'invite_code': team.invite_code})),
        'year': datetime.now().year,
    })

@login_required
def leave_team(request):
    user_profile = request.user.userprofile
    if user_profile.team:
        team = user_profile.team
        
        if team.is_captain(request.user):
            messages.error(request, 'Вы не можете покинуть команду будучи капитаном. Для выхода из команды передайте лидерство другому участнику или удалите команду.')
            return redirect('team_page', team_id=team.id)
        
        team.members.remove(request.user)
        user_profile.team = None
        user_profile.save()
        
        messages.success(request, 'Вы вышли из команды')
            
    return redirect('profile')

@login_required
def delete_team(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    if not team.is_captain(request.user):
        messages.error(request, 'Только капитан может удалить команду')
        return redirect('team_page', team_id=team.id)
    
    team.delete()
    messages.success(request, 'Команда успешно удалена')
    return redirect('profile')

@login_required
def edit_team(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    if not team.is_captain(request.user):
        messages.error(request, 'Только капитан может редактировать команду')
        return redirect('team_page', team_id=team.id)

    if request.method == 'POST':
        form = TeamCreationForm(request.POST, request.FILES, instance=team)
        if form.is_valid():
            form.save()
            messages.success(request, 'Команда успешно обновлена')
            return redirect('team_page', team_id=team.id)
    else:
        form = TeamCreationForm(instance=team)
    
    return render(request, 'app/teams/edit_team.html', {
        'form': form,
        'team': team,
        'year': datetime.now().year,
    })

@login_required
def remove_member(request, team_id, member_id):
    team = get_object_or_404(Team, id=team_id)
    member = get_object_or_404(User, id=member_id)
    
    if not team.is_captain(request.user):
        messages.error(request, 'Только капитан может удалять участников')
        return redirect('team_page', team_id=team.id)
    
    if member == request.user:
        messages.error(request, 'Вы не можете удалить себя из команды. Для выхода из команды передайте лидерство другому участнику или удалите команду.')
        return redirect('team_page', team_id=team.id)
    
    if not team.is_member(member):
        messages.error(request, 'Этот пользователь не состоит в вашей команде')
        return redirect('team_page', team_id=team.id)
    
    team.members.remove(member)
    member.userprofile.team = None
    member.userprofile.save()
    messages.success(request, f'Участник {member.username} удален из команды')
    
    return redirect('team_page', team_id=team.id)

@login_required
def transfer_leadership(request, team_id, new_captain_id):
    team = get_object_or_404(Team, id=team_id)
    if not team.is_captain(request.user):
        messages.error(request, 'Только капитан может передать лидерство')
        return redirect('team_page', team_id=team.id)
    
    new_captain = get_object_or_404(User, id=new_captain_id)
    if not team.is_member(new_captain):
        messages.error(request, 'Новый капитан должен быть участником команды')
        return redirect('team_page', team_id=team.id)
    
    team.captain = new_captain
    team.save()
    messages.success(request, f'Лидерство передано {new_captain.username}')
    return redirect('team_page', team_id=team.id)

def tournaments(request):
    # Получаем параметры фильтрации
    selected_discipline = request.GET.get('discipline')
    selected_game_format = request.GET.get('game_format')
    selected_region = request.GET.get('region')
    selected_status = request.GET.get('status')

    # Базовый запрос
    tournaments = Tournament.objects.all()

    # Применяем фильтры
    if selected_discipline:
        tournaments = tournaments.filter(discipline=selected_discipline)
    if selected_game_format:
        tournaments = tournaments.filter(game_format=selected_game_format)
    if selected_region:
        tournaments = tournaments.filter(location=selected_region)
    if selected_status:
        # Фильтрация по статусу
        if selected_status == 'upcoming':
            tournaments = [t for t in tournaments if t.get_status() == 'planned']
        elif selected_status == 'in_progress':
            tournaments = [t for t in tournaments if t.get_status() == 'in_progress']
        elif selected_status == 'completed':
            tournaments = [t for t in tournaments if t.get_status() == 'completed']

    # Получаем списки для выпадающих меню
    disciplines = Tournament.DISCIPLINE_CHOICES
    game_formats = Tournament.FORMAT_CHOICES
    regions = Tournament.LOCATION_CHOICES

    return render(request, 'app/tournaments/tournaments.html', {
        'tournaments': tournaments,
        'disciplines': disciplines,
        'game_formats': game_formats,
        'regions': regions,
        'selected_discipline': selected_discipline,
        'selected_game_format': selected_game_format,
        'selected_region': selected_region,
        'selected_status': selected_status,
        'year': datetime.now().year,
    })

@login_required
def create_tournament(request):
    if request.method == 'POST':
        form = TournamentForm(request.POST)
        if form.is_valid():
            tournament = form.save(commit=False)
            tournament.creator = request.user
            try:
                tournament.full_clean()
                tournament.save()
                messages.success(request, 'Турнир успешно создан!')
                return redirect('tournaments')
            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, error)
    else:
        form = TournamentForm()
    return render(request, 'app/tournaments/create_tournament.html', {
        'form': form,
        'year': datetime.now().year,
    })

def tournament_detail(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    is_creator = tournament.is_creator(request.user) if request.user.is_authenticated else False
    user_team = None
    is_registered = False
    
    if request.user.is_authenticated and hasattr(request.user, 'userprofile'):
        if tournament.game_format == '1x1':
            is_registered = tournament.registered_teams.filter(
                Q(captain=request.user) | Q(members=request.user)
            ).exists()
        else:
            user_team = request.user.userprofile.team
            if user_team:
                is_registered = tournament.is_registered(user_team)

    registered_count = tournament.registered_teams.count()
    
    # Получаем статус турнира и предстоящие матчи
    tournament_status = tournament.get_status()
    tournament_status_display = tournament.get_status_display()
    upcoming_matches = get_upcoming_matches(tournament)
    
    context = {
        'tournament': tournament,
        'is_creator': is_creator,
        'user_team': user_team,
        'is_registered': is_registered,
        'registered_teams': tournament.registered_teams.all(),
        'registered_count': registered_count,
        'tournament_status': tournament_status,
        'tournament_status_display': tournament_status_display,
        'upcoming_matches': upcoming_matches[:5],  # Первые 5 предстоящих матчей
        'year': datetime.now().year,
    }
    
    return render(request, 'app/tournaments/tournament_detail.html', context)

@login_required
def edit_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    if not tournament.is_creator(request.user):
        messages.error(request, 'Только создатель может редактировать турнир')
        return redirect('tournament_detail', tournament_id=tournament.id)
    
    # Проверяем, есть ли уже сформированная сетка
    if hasattr(tournament, 'bracket') or hasattr(tournament, 'round_robin_table'):
        messages.error(request, 'Нельзя редактировать турнир, так как турнирная сетка уже сформирована')
        return redirect('tournament_detail', tournament_id=tournament.id)
    
    if request.method == 'POST':
        form = TournamentEditForm(request.POST, instance=tournament)
        if form.is_valid():
            form.save()
            messages.success(request, 'Турнир успешно обновлен')
            return redirect('tournament_detail', tournament_id=tournament.id)
    else:
        form = TournamentEditForm(instance=tournament)
    
    return render(request, 'app/tournaments/edit_tournament.html', {
        'form': form,
        'tournament': tournament,
        'year': datetime.now().year,
    })

@login_required
def participate_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    user_profile = request.user.userprofile
    
    # Проверяем, есть ли уже сформированная сетка
    if hasattr(tournament, 'bracket') or hasattr(tournament, 'round_robin_table'):
        messages.error(request, 'Нельзя зарегистрироваться на турнир, так как турнирная сетка уже сформирована')
        return redirect('tournament_detail', tournament_id=tournament.id)
    
    if tournament.game_format == '1x1':
        # Проверяем, есть ли у пользователя команда
        team = user_profile.team
        if not team:
            # Проверяем, есть ли команда с таким именем и капитаном этим пользователем
            from app.models import Team
            team_qs = Team.objects.filter(name=request.user.username)
            if team_qs.exists():
                team_obj = team_qs.first()
                if team_obj.captain == request.user:
                    team = team_obj
                else:
                    messages.error(request, 'Команда с вашим никнеймом уже существует и принадлежит другому пользователю. Пожалуйста, измените никнейм или обратитесь к администратору.')
                    return redirect('tournament_detail', tournament_id=tournament.id)
            else:
                team = Team.objects.create(
                    name=request.user.username,
                    captain=request.user
                )
            user_profile.team = team
            user_profile.save()
        
        # Проверяем, не зарегистрирован ли уже пользователь
        if tournament.is_registered(team):
            messages.warning(request, 'Вы уже зарегистрированы на этот турнир')
            return redirect('tournament_detail', tournament_id=tournament.id)
        
        if tournament.registered_teams_count() >= tournament.max_teams:
            messages.error(request, 'Турнир уже заполнен')
            return redirect('tournament_detail', tournament_id=tournament.id)
        
        # Регистрируем команду на турнир
        tournament.registered_teams.add(team)
        registration = TournamentRegistration.objects.get(tournament=tournament, team=team)
        registration.players.add(request.user)
        
        messages.success(request, 'Вы успешно зарегистрированы на турнир!')
        return redirect('tournament_detail', tournament_id=tournament.id)
    
    if not user_profile.team:
        messages.error(request, 'Для участия в этом турнире вам нужно состоять в команде')
        return redirect('tournament_detail', tournament_id=tournament.id)
    
    team = user_profile.team
    if not team.is_captain(request.user):
        messages.error(request, 'Только капитан может зарегистрировать команду на турнир')
        return redirect('tournament_detail', tournament_id=tournament.id)
    
    if tournament.is_registered(team):
        messages.warning(request, 'Ваша команда уже зарегистрирована на этот турнир')
        return redirect('tournament_detail', tournament_id=tournament.id)
    
    if tournament.registered_teams_count() >= tournament.max_teams:
        messages.error(request, 'Турнир уже заполнен')
        return redirect('tournament_detail', tournament_id=tournament.id)
    
    if request.method == 'POST':
        form = TournamentParticipationForm(request.POST, team=team, game_format=tournament.game_format)
        if form.is_valid():
            tournament.registered_teams.add(team)
            registration = TournamentRegistration.objects.get(tournament=tournament, team=team)
            registration.players.set(form.cleaned_data['players'])
            messages.success(request, 'Ваша команда успешно зарегистрирована на турнир!')
            return redirect('tournament_detail', tournament_id=tournament.id)
    else:
        form = TournamentParticipationForm(team=team, game_format=tournament.game_format)
    
    return render(request, 'app/tournaments/participate_tournament.html', {
        'form': form,
        'tournament': tournament,
        'team': team,
        'year': datetime.now().year,
    })

@login_required
def my_tournaments(request):
    user_teams = Team.objects.filter(Q(captain=request.user) | Q(members=request.user)).distinct()
    participating_tournaments = Tournament.objects.filter(
        registered_teams__in=user_teams,
        is_active=True
    ).order_by('start_date')
    
    created_tournaments = Tournament.objects.filter(
        creator=request.user,
        is_active=True
    ).order_by('start_date')
    
    return render(request, 'app/tournaments/my_tournaments.html', {
        'participating_tournaments': participating_tournaments,
        'created_tournaments': created_tournaments,
        'title': 'Мои турниры',
        'year': datetime.now().year,
    })

@require_POST
def remove_team_from_tournament(request, tournament_id, team_id):
    from django.db import models
    from app.models import BracketMatch, RoundRobinMatch, RoundRobinResult
    try:
        tournament = get_object_or_404(Tournament, id=tournament_id)
        team = get_object_or_404(Team, id=team_id)
        
        if not tournament.is_creator(request.user):
            return JsonResponse({'success': False, 'error': 'Только создатель может удалять команды'}, status=403)
        
        if not tournament.is_registered(team):
            return JsonResponse({'success': False, 'error': 'Эта команда не зарегистрирована на турнир'}, status=400)
        
        # Проверяем, есть ли уже сформированная сетка
        if hasattr(tournament, 'bracket') or hasattr(tournament, 'round_robin_table'):
            return JsonResponse({
                'success': False, 
                'error': 'Нельзя удалить команду, так как турнирная сетка уже сформирована'
            }, status=400)
        
        tournament.registered_teams.remove(team)
        
        if tournament.game_format == '1x1' and (not hasattr(team.captain, 'userprofile') or team.captain.userprofile.team != team):
            team.delete()
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@require_POST
def delete_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    if not tournament.is_creator(request.user):
        return JsonResponse({'success': False, 'error': 'Только создатель может удалить турнир'}, status=403)
    
    if tournament.game_format == '1x1':
        for team in tournament.registered_teams.all():
            if not hasattr(team.captain, 'userprofile') or team.captain.userprofile.team != team:
                team.delete()
    
    tournament.delete()
    return JsonResponse({'success': True})

def create_bracket_stages(bracket, teams):
    team_count = len(teams)
    current_round = team_count
    round_number = 1
    
    while current_round >= 2:
        stage_name = get_stage_name(current_round)
        stage = BracketStage.objects.create(
            bracket=bracket,
            name=stage_name,
            format=get_default_format(current_round),
            order=round_number
        )
        
        matches_in_round = current_round // 2
        for i in range(matches_in_round):
            team1 = teams[i*2] if i*2 < len(teams) else None
            team2 = teams[i*2+1] if i*2+1 < len(teams) else None
            
            BracketMatch.objects.create(
                stage=stage,
                team1=team1,
                team2=team2,
                order=i+1
            )
        
        current_round = matches_in_round
        round_number += 1

@login_required
def generate_bracket(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    if not tournament.is_creator(request.user):
        messages.error(request, 'Только создатель турнира может формировать сетку')
        return redirect('tournament_detail', tournament_id=tournament.id)
    
    teams_count = tournament.registered_teams.count()
    
    if teams_count < 2:
        messages.error(request, f'Формирование турнирной сетки доступно от двух участников и больше. Сейчас зарегистрировано: {teams_count}')
        return redirect('tournament_detail', tournament_id=tournament.id)
    
    if request.method == 'POST':
        form = BracketGenerationForm(request.POST, tournament=tournament)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    teams = list(tournament.registered_teams.all())
                    random.shuffle(teams)  # Случайное перемешивание команд
                    
                    # Собираем форматы для этапов
                    stage_formats = {}
                    for field_name, value in form.cleaned_data.items():
                        if field_name.startswith('format_round_'):
                            stage_formats[field_name] = value
                    
                    # Создаем сетку в зависимости от формата турнира
                    if tournament.tournament_format == 'single_elimination':
                        third_place_match = form.cleaned_data.get('third_place_match', False)
                        bracket = create_single_elimination_bracket(
                            tournament, teams, 'random', 
                            third_place_match, stage_formats
                        )
                    elif tournament.tournament_format == 'double_elimination':
                        bracket = create_double_elimination_bracket(
                            tournament, teams, 'random', stage_formats
                        )
                    elif tournament.tournament_format == 'round_robin':
                        create_round_robin_bracket(tournament, teams)
                    
                    messages.success(request, 'Турнирная сетка успешно создана!')
                    return redirect('tournament_bracket', tournament_id=tournament.id)
                    
            except Exception as e:
                messages.error(request, f'Ошибка при создании сетки: {str(e)}')
    else:
        form = BracketGenerationForm(tournament=tournament)
    
    return render(request, 'app/tournaments/generate_bracket.html', {
        'form': form,
        'tournament': tournament,
        'year': datetime.now().year,
    })

def get_stage_name(team_count):
    stages = {
        2: 'Финал',
        4: 'Полуфиналы',
        8: 'Четвертьфиналы',
        16: '1/8 финала',
        32: '1/16 финала',
        64: '1/32 финала',
        128: '1/64 финала',
        256: '1/128 финала',
        512: '1/256 финала'
    }
    return stages.get(team_count, f'Раунд на {team_count} команд')

def get_default_format(team_count):
    if team_count <= 4:
        return 'BO3'
    elif team_count <= 8:
        return 'BO3'
    else:
        return 'BO1'

@login_required
def tournament_bracket(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    is_creator = tournament.is_creator(request.user) if request.user.is_authenticated else False
    context = {
        'tournament': tournament,
        'is_creator': is_creator,
        'year': datetime.now().year,
    }
    if tournament.tournament_format == 'round_robin':
        return redirect('round_robin_table', tournament_id=tournament.id)
    else:
        bracket = getattr(tournament, 'bracket', None)
        context['bracket'] = bracket
        if bracket:
            # Формируем данные для jQuery Bracket
            stages = list(bracket.stages.order_by('order'))
            
            if stages:
                # Получаем команды из первого раунда
                first_stage = stages[0]
                first_stage_matches = list(first_stage.matches.order_by('order'))
                
                # Создаем список команд для первого раунда
                teams = []
                for match in first_stage_matches:
                    team1 = match.team1.name if match.team1 else 'TBD'
                    team2 = match.team2.name if match.team2 else 'TBD'
                    teams.append([team1, team2])
                
                # Создаем результаты для всех раундов
                results = []
                for stage in stages:
                    stage_matches = list(stage.matches.order_by('order'))
                    round_results = []
                    for match in stage_matches:
                        if match.is_completed:
                            score1 = match.team1_score
                            score2 = match.team2_score
                        else:
                            score1 = None
                            score2 = None
                        round_results.append([score1, score2])
                    results.append(round_results)
                
                # Создаем данные для jquery-bracket
                bracket_data = {
                    'teams': teams,
                    'results': results
                }
                
                print(json.dumps(bracket_data, ensure_ascii=False, indent=2))
                context['bracket_data'] = json.dumps(bracket_data, ensure_ascii=False)
            
            upcoming_matches = get_upcoming_matches(tournament)
            context['upcoming_matches'] = upcoming_matches[:5]
            # Формы для незавершённых матчей
            match_forms = {}
            for stage in bracket.stages.all():
                for match in stage.matches.all():
                    if not match.is_completed and match.team1 and match.team2:
                        match_forms[match.id] = AdvancedMatchResultForm(instance=match)
            context['match_forms'] = match_forms
    return render(request, 'app/tournaments/tournament_bracket.html', context)

@login_required
def edit_stage_format(request, tournament_id, stage_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    stage = get_object_or_404(BracketStage, id=stage_id, bracket__tournament=tournament)
    
    if not tournament.is_creator(request.user):
        messages.error(request, 'Только создатель турнира может изменять формат этапа')
        return redirect('tournament_bracket', tournament_id=tournament.id)
    
    if request.method == 'POST':
        form = BracketStageForm(request.POST, instance=stage)
        if form.is_valid():
            form.save()
            messages.success(request, 'Формат этапа успешно обновлен')
            return redirect('tournament_bracket', tournament_id=tournament.id)
    else:
        form = BracketStageForm(instance=stage)
    
    return render(request, 'app/tournaments/edit_stage_format.html', {
        'form': form,
        'tournament': tournament,
        'stage': stage,
        'year': datetime.now().year,
    })

@login_required
def update_match_result(request, tournament_id, match_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    match = get_object_or_404(BracketMatch, id=match_id, stage__bracket__tournament=tournament)
    
    if not tournament.is_creator(request.user):
        messages.error(request, 'Только создатель турнира может обновлять результаты')
        return redirect('tournament_bracket', tournament_id=tournament.id)

    if not match.team1 or not match.team2:
        messages.error(request, 'Обе команды должны быть определены для матча')
        return redirect('tournament_bracket', tournament_id=tournament.id)
    
    if request.method == 'POST':
        form = MatchResultForm(request.POST, instance=match)
        if form.is_valid():
            match = form.save(commit=False)
            match.is_completed = True
            match.save()
            
            promote_winner_to_next_stage(match)
            
            messages.success(request, 'Результат матча обновлен')
            return redirect('tournament_bracket', tournament_id=tournament.id)
    else:
        form = MatchResultForm(instance=match)
    
    return render(request, 'app/tournaments/matches/update_match_result.html', {
        'form': form,
        'tournament': tournament,
        'match': match,
        'year': datetime.now().year,
    })

# promote_winner_to_next_stage function moved to bracket_features.py

@login_required
def complete_stage(request, tournament_id, stage_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    stage = get_object_or_404(BracketStage, id=stage_id, bracket__tournament=tournament)
    
    if not tournament.is_creator(request.user):
        messages.error(request, 'Только создатель турнира может завершать этапы')
        return redirect('tournament_bracket', tournament_id=tournament.id)
    
    incomplete_matches = stage.matches.filter(is_completed=False).exists()
    if incomplete_matches:
        messages.error(request, 'Не все матчи этого этапа завершены')
        return redirect('tournament_bracket', tournament_id=tournament.id)
    
    stage.is_completed = True
    stage.save()
    
    messages.success(request, f'Этап "{stage.name}" успешно завершен')
    return redirect('tournament_bracket', tournament_id=tournament.id)

@login_required
def cancel_tournament_participation(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    user_profile = request.user.userprofile

    # Проверяем, есть ли уже сформированная сетка
    if hasattr(tournament, 'bracket') or hasattr(tournament, 'round_robin_table'):
        messages.error(request, 'Нельзя отменить участие в турнире, так как турнирная сетка уже сформирована')
        return redirect('tournament_detail', tournament_id=tournament.id)

    if tournament.game_format == '1x1':
        user_team = tournament.registered_teams.filter(captain=request.user).first()
        if not user_team:
            messages.warning(request, 'Вы не зарегистрированы на этот турнир')
            return redirect('tournament_detail', tournament_id=tournament.id)
        
        tournament.registered_teams.remove(user_team)
        
        if not hasattr(user_team.captain, 'userprofile') or user_team.captain.userprofile.team != user_team:
            user_team.delete()
        
        messages.success(request, 'Вы успешно отменили участие в турнире')
        return redirect('tournament_detail', tournament_id=tournament.id)

    team = user_profile.team

    if not team or not team.is_captain(request.user):
        messages.error(request, 'Только капитан может отменить регистрацию команды')
        return redirect('team_page', team_id=team.id if team else 0)

    try:
        registration = TournamentRegistration.objects.get(tournament=tournament, team=team)
        registration.delete()
        messages.success(request, 'Вы успешно отменили регистрацию вашей команды')
    except TournamentRegistration.DoesNotExist:
        messages.warning(request, 'Команда не была зарегистрирована на этот турнир')

    return redirect('tournament_detail', tournament_id=tournament.id)

@login_required
def manual_bracket_setup(request, tournament_id):
    """Ручное распределение команд в турнирной сетке"""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    if not tournament.is_creator(request.user):
        messages.error(request, 'Только создатель турнира может настраивать сетку')
        return redirect('tournament_detail', tournament_id=tournament.id)
    
    teams = list(tournament.registered_teams.all())
    
    if request.method == 'POST':
        form = ManualBracketForm(request.POST, teams=teams)
        if form.is_valid():
            try:
                # Создаем список команд в порядке, выбранном пользователем
                ordered_teams = []
                for i in range(len(teams)):
                    team_id = form.cleaned_data[f'position_{i+1}']
                    team = Team.objects.get(id=team_id)
                    ordered_teams.append(team)
                
                # Создаем сетку с упорядоченными командами
                stage_formats = {}  # Можно добавить выбор форматов позже
                
                if tournament.tournament_format == 'single_elimination':
                    create_single_elimination_bracket(
                        tournament, ordered_teams, 'manual', False, stage_formats
                    )
                elif tournament.tournament_format == 'double_elimination':
                    create_double_elimination_bracket(
                        tournament, ordered_teams, 'manual', stage_formats
                    )
                elif tournament.tournament_format == 'round_robin':
                    create_round_robin_bracket(tournament, ordered_teams)
                
                messages.success(request, 'Турнирная сетка с ручным распределением команд создана!')
                return redirect('tournament_bracket', tournament_id=tournament.id)
                
            except Exception as e:
                messages.error(request, f'Ошибка при создании сетки: {str(e)}')
    else:
        form = ManualBracketForm(teams=teams)
    
    return render(request, 'app/tournaments/manual_bracket_setup.html', {
        'form': form,
        'tournament': tournament,
        'teams': teams,
        'year': datetime.now().year,
    })

@login_required
def advanced_match_result(request, tournament_id, match_id):
    """Расширенная форма для ввода результатов матча с учетом счета (Single/Double Elimination)"""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    match = get_object_or_404(BracketMatch, id=match_id, stage__bracket__tournament=tournament)
    
    if not tournament.is_creator(request.user):
        messages.error(request, 'Только создатель турнира может обновлять результаты')
        return redirect('tournament_bracket', tournament_id=tournament.id)

    if not match.team1 or not match.team2:
        messages.error(request, 'Обе команды должны быть определены для матча')
        return redirect('tournament_bracket', tournament_id=tournament.id)
    
    # Используем форму AdvancedMatchResultForm для single/double elimination (ввод счёта)
    if request.method == 'POST':
        form = AdvancedMatchResultForm(request.POST, instance=match)
        if form.is_valid():
            match = form.save(commit=False)
            match.is_completed = True
            match.save()
            # Победитель определяется автоматически в save()
            promote_winner_to_next_stage(match)
            messages.success(request, 'Результат матча обновлен')
            return redirect('tournament_bracket', tournament_id=tournament.id)
    else:
        form = AdvancedMatchResultForm(instance=match)
    
    return render(request, 'app/tournaments/matches/advanced_match_result.html', {
        'form': form,
        'tournament': tournament,
        'match': match,
        'year': datetime.now().year,
    })

@login_required
def round_robin_match_result(request, tournament_id, match_id):
    match = get_object_or_404(RoundRobinMatch, id=match_id)
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    # Проверяем, является ли пользователь создателем турнира
    if tournament.creator != request.user:
        messages.error(request, 'У вас нет прав для редактирования результатов матча')
        return redirect('tournament_detail', tournament_id=tournament_id)
    
    if request.method == 'POST':
        # Получаем счет из POST данных
        score = None
        if match.format == 'BO1':
            score = request.POST.get('bo1_score')
        elif match.format == 'BO3':
            score = request.POST.get('bo3_score')
        elif match.format == 'BO5':
            score = request.POST.get('bo5_score')
        
        if score:
            # Разбиваем счет на победы каждой команды
            team1_score, team2_score = map(int, score.split('-'))
            
            # Обновляем результат матча
            match.team1_score = team1_score
            match.team2_score = team2_score
            match.is_completed = True
            match.save()
            
            # Обновляем результаты в таблице
            update_round_robin_results(match)
            
            messages.success(request, 'Результат матча успешно обновлен')
        else:
            messages.error(request, 'Неверный формат счета')
    
    return redirect('round_robin_table', tournament_id=tournament_id)

@login_required
def round_robin_table(request, tournament_id):
    """Отображение таблицы Round Robin"""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    if tournament.tournament_format != 'round_robin':
        messages.error(request, 'Этот турнир не использует формат Round Robin')
        return redirect('tournament_detail', tournament_id=tournament.id)
    
    table = getattr(tournament, 'round_robin_table', None)
    is_creator = tournament.is_creator(request.user) if request.user.is_authenticated else False
    
    # Получаем предстоящие матчи
    upcoming_matches = []
    if table:
        upcoming_matches = table.matches.filter(
            is_completed=False,
            scheduled_time__isnull=False
        ).order_by('scheduled_time')[:10]
    
    return render(request, 'app/tournaments/round_robin_table.html', {
        'tournament': tournament,
        'table': table,
        'is_creator': is_creator,
        'upcoming_matches': upcoming_matches,
        'year': datetime.now().year,
    })

@login_required 
def tournament_matches(request, tournament_id):
    """Страница со всеми матчами турнира"""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    upcoming_matches = get_upcoming_matches(tournament)
    matches_by_stage = {}
    
    # Группируем матчи по стадиям
    if tournament.tournament_format == 'round_robin':
        if hasattr(tournament, 'round_robin_table'):
            all_matches = tournament.round_robin_table.matches.all()
            if all_matches:
                matches_by_stage['Round Robin'] = all_matches
    else:
        if hasattr(tournament, 'bracket'):
            for stage in tournament.bracket.stages.all().order_by('order'):
                stage_matches = stage.matches.all()
                if stage_matches:
                    matches_by_stage[stage.name] = stage_matches
    
    context = {
        'tournament': tournament,
        'upcoming_matches': upcoming_matches,
        'matches_by_stage': matches_by_stage,
        'year': datetime.now().year,
    }
    
    return render(request, 'app/tournaments/matches/tournament_matches.html', context)

@login_required
def match_detail(request, tournament_id, match_id):
    """Детальная страница матча"""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    # Пытаемся найти матч в обычной сетке или в Round Robin
    match = None
    match_type = None
    
    try:
        match = BracketMatch.objects.get(id=match_id, stage__bracket__tournament=tournament)
        match_type = 'bracket'
    except BracketMatch.DoesNotExist:
        try:
            match = RoundRobinMatch.objects.get(id=match_id, table__tournament=tournament)
            match_type = 'round_robin'
        except RoundRobinMatch.DoesNotExist:
            messages.error(request, 'Матч не найден')
            return redirect('tournament_detail', tournament_id=tournament.id)
    
    is_creator = tournament.is_creator(request.user) if request.user.is_authenticated else False
    
    context = {
        'tournament': tournament,
        'match': match,
        'match_type': match_type,
        'is_creator': is_creator
    }
    
    return render(request, 'app/tournaments/matches/match_detail.html', context)

@login_required
def edit_match_schedule(request, tournament_id, match_id):
    """Изменение времени проведения матча"""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    if not tournament.is_creator(request.user):
        messages.error(request, 'Только создатель турнира может изменять расписание')
        return redirect('tournament_detail', tournament_id=tournament.id)
    
    # Определяем тип матча
    match = None
    match_type = None
    
    try:
        match = BracketMatch.objects.get(id=match_id, stage__bracket__tournament=tournament)
        match_type = 'bracket'
    except BracketMatch.DoesNotExist:
        try:
            match = RoundRobinMatch.objects.get(id=match_id, table__tournament=tournament)
            match_type = 'round_robin'
        except RoundRobinMatch.DoesNotExist:
            messages.error(request, 'Матч не найден')
            return redirect('tournament_detail', tournament_id=tournament.id)
    
    # Проверяем, не завершен ли матч
    if match.is_completed:
        messages.error(request, 'Нельзя изменить время уже сыгранного матча')
        return redirect('match_detail', tournament_id=tournament.id, match_id=match.id)
    
    if request.method == 'POST':
        form = MatchScheduleForm(request.POST)
        if form.is_valid():
            match.scheduled_time = form.cleaned_data['scheduled_time']
            match.save()
            
            messages.success(request, 'Время матча успешно обновлено')
            return redirect('match_detail', tournament_id=tournament.id, match_id=match.id)
    else:
        form = MatchScheduleForm(initial={'scheduled_time': match.scheduled_time})
    
    return render(request, 'app/tournaments/matches/edit_match_schedule.html', {
        'form': form,
        'tournament': tournament,
        'match': match,
        'match_type': match_type,
        'year': datetime.now().year,
    })

@login_required
def generate_round_robin(request, tournament_id):
    """Генерирует матчи для турнира в формате Round Robin"""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    # Проверяем, является ли пользователь создателем турнира
    if request.user != tournament.creator:
        messages.error(request, 'Только создатель турнира может генерировать матчи')
        return redirect('tournament_detail', tournament_id=tournament_id)
    
    # Проверяем формат турнира
    if tournament.tournament_format != 'round_robin':
        messages.error(request, 'Эта функция доступна только для турниров в формате Round Robin')
        return redirect('tournament_detail', tournament_id=tournament_id)
    
    # Проверяем, есть ли уже сгенерированные матчи
    if hasattr(tournament, 'round_robin_table'):
        messages.error(request, 'Матчи для этого турнира уже сгенерированы')
        return redirect('tournament_detail', tournament_id=tournament_id)
    
    # Проверяем, есть ли хотя бы 2 команды
    if tournament.teams.count() < 2:
        messages.error(request, 'Для генерации матчей необходимо минимум 2 команды')
        return redirect('tournament_detail', tournament_id=tournament_id)
    
    try:
        # Создаем турнирную таблицу и матчи
        table = create_round_robin_bracket(tournament)
        messages.success(request, 'Матчи успешно сгенерированы')
        return redirect('round_robin_table', tournament_id=tournament_id)
    except Exception as e:
        messages.error(request, f'Ошибка при генерации матчей: {str(e)}')
        return redirect('tournament_detail', tournament_id=tournament_id)

@login_required
def edit_tournament_roster(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    # Проверяем, является ли пользователь капитаном команды
    try:
        team = Team.objects.get(captain=request.user)
    except Team.DoesNotExist:
        messages.error(request, 'Вы не являетесь капитаном команды')
        return redirect('tournament_detail', tournament_id=tournament_id)
    
    # Проверяем, зарегистрирована ли команда на турнир
    try:
        registration = TournamentRegistration.objects.get(tournament=tournament, team=team)
    except TournamentRegistration.DoesNotExist:
        messages.error(request, 'Ваша команда не зарегистрирована на этот турнир')
        return redirect('tournament_detail', tournament_id=tournament_id)
    
    if request.method == 'POST':
        form = TournamentRosterForm(request.POST, instance=registration)
        if form.is_valid():
            form.save()
            messages.success(request, 'Состав команды успешно обновлен')
            return redirect('tournament_detail', tournament_id=tournament_id)
    else:
        form = TournamentRosterForm(instance=registration)
    
    return render(request, 'app/tournaments/edit_tournament_roster.html', {
        'tournament': tournament,
        'team': team,
        'form': form,
        'year': datetime.now().year,
    })

@login_required
def bracket_match_result_inline(request, tournament_id, match_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    match = get_object_or_404(BracketMatch, id=match_id, stage__bracket__tournament=tournament)
    if not tournament.is_creator(request.user):
        messages.error(request, 'Только создатель турнира может обновлять результаты')
        return redirect('tournament_bracket', tournament_id=tournament.id)
    if not match.team1 or not match.team2:
        messages.error(request, 'Обе команды должны быть определены для матча')
        return redirect('tournament_bracket', tournament_id=tournament.id)
    if request.method == 'POST':
        form = AdvancedMatchResultForm(request.POST, instance=match)
        if form.is_valid():
            match = form.save(commit=False)
            match.is_completed = True
            match.save()
            promote_winner_to_next_stage(match)
            messages.success(request, 'Результат матча обновлен')
        else:
            # Сохраняем ошибки формы во временное хранилище
            request.session['inline_form_errors'] = form.errors.get_json_data()
    return redirect('tournament_bracket', tournament_id=tournament.id)

@login_required
@require_POST
def bracket_match_score_api(request, tournament_id, match_id):
    from app.models import BracketMatch
    match = get_object_or_404(BracketMatch, id=match_id, stage__bracket__tournament_id=tournament_id)
    tournament = match.stage.bracket.tournament
    if not tournament.is_creator(request.user):
        return JsonResponse({'error': 'Нет прав'}, status=403)
    try:
        team1_score = int(request.POST.get('team1_score'))
        team2_score = int(request.POST.get('team2_score'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Некорректный счет'}, status=400)
    match_format = match.stage.format or 'BO1'
    win_score = {'BO1': 1, 'BO3': 2, 'BO5': 3}.get(match_format, 1)
    if team1_score < 0 or team2_score < 0 or (team1_score < win_score and team2_score < win_score):
        return JsonResponse({'error': 'Счет не соответствует формату'}, status=400)
    if not (
        (team1_score == win_score and team2_score < win_score) or
        (team2_score == win_score and team1_score < win_score)
    ):
        return JsonResponse({'error': f'Победитель должен набрать {win_score}, а проигравший меньше'}, status=400)
    match.team1_score = team1_score
    match.team2_score = team2_score
    match.is_completed = True
    match.winner = match.team1 if team1_score > team2_score else match.team2
    match.save()
    promote_winner_to_next_stage(match)
    return JsonResponse({
        'success': True,
        'winner': match.winner.name,
        'team1_score': team1_score,
        'team2_score': team2_score
    })

