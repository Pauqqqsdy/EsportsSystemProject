from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils.translation import gettext_lazy as _
from .models import BracketMatch, BracketStage, Tournament, UserProfile, Team, RoundRobinMatch, TournamentRegistration
from django.contrib.admin import widgets
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.utils import timezone
import math

class BootstrapAuthenticationForm(AuthenticationForm):
    username = forms.CharField(max_length=16,
                               widget=forms.TextInput({
                                   'class': 'form-control',
                                   'placeholder': 'Логин'}))
    password = forms.CharField(label=_("Password"),
                               widget=forms.PasswordInput({
                                   'class': 'form-control',
                                   'placeholder':'Пароль'}))

class ExtendedUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True, 
        label="Email",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите ваш email',
            'oninvalid': "this.setCustomValidity('Email обязателен для заполнения')",
            'oninput': "this.setCustomValidity('')"
        }),
        error_messages={
            'required': 'Email обязателен для заполнения',
            'invalid': 'Введите корректный email адрес'
        }
    )
    privacy_policy = forms.BooleanField(
        required=True, 
        label="Я согласен с политикой конфиденциальности",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'oninvalid': "this.setCustomValidity('Требуется принять условия соглашения')",
            'oninput': "this.setCustomValidity('')"
        }),
        error_messages={
            'required': 'Требуется принять условия соглашения'
        }
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2', 'privacy_policy')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Придумайте логин',
                'pattern': '[a-zA-Z0-9]+',
                'maxlength': '16',
                'oninvalid': "this.setCustomValidity('Логин обязателен для заполнения')",
                'oninput': "this.setCustomValidity('')"
            }),
        }
        error_messages = {
            'username': {
                'required': 'Логин обязателен для заполнения',
                'max_length': 'Логин не должен превышать 16 символов',
                'invalid': 'Только латинские буквы и цифры'
            },
            'password1': {
                'required': 'Пароль обязателен для заполнения',
                'password_mismatch': 'Пароли не совпадают',
                'password_too_short': 'Пароль должен содержать минимум 8 символов',
                'password_too_common': 'Пароль слишком простой'
            },
            'password2': {
                'required': 'Пожалуйста, подтвердите пароль',
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget = forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Придумайте пароль',
            'required': 'required',
            'oninvalid': "this.setCustomValidity('Пароль обязателен для заполнения')",
            'oninput': "this.setCustomValidity('')"
        })
        self.fields['password2'].widget = forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Повторите пароль',
            'required': 'required',
            'oninvalid': "this.setCustomValidity('Пожалуйста, подтвердите пароль')",
            'oninput': "this.setCustomValidity('')"
        })

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise ValidationError("Пользователь с такой почтой уже зарегистрирован")
        return email

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise ValidationError("Этот никнейм уже занят")
        return username

class AvatarUploadForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['avatar']

class TeamCreationForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ['name', 'avatar']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'avatar': forms.FileInput(attrs={'class': 'form-control-file'})
        }
    
    def clean_name(self):
        name = self.cleaned_data['name']
        current_team = self.instance

        if Team.objects.filter(name__iexact=name).exclude(pk=current_team.pk).exists():
            raise forms.ValidationError("Команда с таким названием уже существует")
        return name

class TournamentForm(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = ['name', 'max_teams', 'start_date', 'discipline', 
                 'game_format', 'tournament_format', 'location', 'description']
        widgets = {
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super(TournamentForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})
        tournament_format_choices = [('', '--------')] + list(Tournament.TOURNAMENT_FORMAT_CHOICES)
        self.fields['tournament_format'].choices = tournament_format_choices
        if self.instance and self.instance.pk:
            self.fields['discipline'].disabled = True
            self.fields['game_format'].disabled = True
        if 'discipline' in self.data:
            try:
                discipline = self.data.get('discipline')
                self.update_game_format_choices(discipline)
            except (ValueError, TypeError):
                pass
        elif self.instance.pk:
            self.update_game_format_choices(self.instance.discipline)
        # Динамические choices для max_teams
        t_format = self.data.get('tournament_format') or (self.instance.tournament_format if self.instance else None)
        if t_format == 'round_robin':
            self.fields['max_teams'].choices = [(i, str(i)) for i in range(2, 21)]
        else:
            self.fields['max_teams'].choices = [(i, str(i)) for i in [2, 4, 8, 16, 32, 64, 128, 256, 512]]
    
    def update_game_format_choices(self, discipline):
        if discipline == 'Dota 2':
            self.fields['game_format'].choices = [
                ('1x1', '1x1'),
                ('5x5', '5x5'),
            ]
        elif discipline in ['CS 2', 'LoL']:
            self.fields['game_format'].choices = [
                ('1x1', '1x1'),
                ('2x2', '2x2'),
                ('5x5', '5x5'),
            ]
        elif discipline == 'Valorant':
            self.fields['game_format'].choices = [
                ('1x1', '1x1'),
                ('2x2', '2x2'),
                ('3x3', '3x3'),
                ('5x5', '5x5'),
            ]
    
    def clean_start_date(self):
        start_date = self.cleaned_data.get('start_date')
        if start_date and start_date < timezone.now():
            raise forms.ValidationError("Невозможно назначить турнир в уже прошедшую дату")
        return start_date
    
    def clean_tournament_format(self):
        tournament_format = self.cleaned_data.get('tournament_format')
        if not tournament_format:
            raise forms.ValidationError("Необходимо выбрать формат турнира")
        return tournament_format

class TournamentParticipationForm(forms.Form):
    def __init__(self, *args, **kwargs):
        team = kwargs.pop('team', None)
        game_format = kwargs.pop('game_format', None)
        super().__init__(*args, **kwargs)
        
        if team and game_format:
            members = team.members.all()
            required_players = {
                '1x1': 1,
                '2x2': 2,
                '3x3': 3,
                '5x5': 5
            }.get(game_format, 1)
            
            self.fields['players'] = forms.ModelMultipleChoiceField(
                queryset=members,
                widget=forms.CheckboxSelectMultiple,
                label=f"Выберите {required_players} игрока(ов)",
                required=True
            )
            
            self.required_players = required_players
    
    def clean_players(self):
        players = self.cleaned_data.get('players', [])
        if len(players) != self.required_players:
            raise forms.ValidationError(f"Необходимо выбрать ровно {self.required_players} игрока(ов)")
        return players

class TournamentEditForm(TournamentForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Отключаем поля, которые нельзя менять после создания
        self.fields['discipline'].disabled = True
        self.fields['game_format'].disabled = True
        self.fields['tournament_format'].disabled = True
        
        # Обновляем choices для max_teams в зависимости от формата турнира
        if self.instance and self.instance.tournament_format:
            if self.instance.tournament_format == 'round_robin':
                self.fields['max_teams'].choices = [(i, str(i)) for i in range(2, 21)]
            else:
                self.fields['max_teams'].choices = [(i, str(i)) for i in [2, 4, 8, 16, 32, 64, 128, 256, 512]]
    
    def clean(self):
        cleaned_data = super().clean()
        # Проверяем, что max_teams не меньше текущего количества зарегистрированных команд
        if 'max_teams' in cleaned_data:
            current_teams_count = self.instance.registered_teams_count()
            if cleaned_data['max_teams'] < current_teams_count:
                raise ValidationError(f"Невозможно установить меньшее количество команд, чем уже зарегистрировано ({current_teams_count})")
        return cleaned_data

class BracketGenerationForm(forms.Form):
    FORMAT_CHOICES = [
        ('BO1', 'Best of 1'),
        ('BO3', 'Best of 3'),
        ('BO5', 'Best of 5'),
    ]
    
    def __init__(self, *args, tournament=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tournament = tournament
        
        if tournament:
            # Добавляем поле для матча за 3 место только для Single Elimination
            if tournament.tournament_format == 'single_elimination':
                self.fields['third_place_match'] = forms.BooleanField(
                    required=False,
                    label='Провести матч за третье место',
                    initial=False
                )
            
            # Для Round Robin добавляем выбор формата игр
            if tournament.tournament_format == 'round_robin':
                self.fields['default_format'] = forms.ChoiceField(
                    choices=self.FORMAT_CHOICES,
                    label='Формат игр',
                    initial='BO3',
                    widget=forms.Select(attrs={'class': 'form-control'})
                )
            else:
                # Для других форматов добавляем форматы для каждого этапа динамически
                team_count = tournament.registered_teams.count()
                if team_count >= 2:
                    # Используем тот же алгоритм, что и в bracket_features.py
                    if tournament.tournament_format == 'single_elimination':
                        # Для Single Elimination используем улучшенный алгоритм
                        total_rounds = max(1, math.ceil(math.log2(team_count))) if team_count > 1 else 1
                        
                        teams_in_round = team_count
                        for round_number in range(1, total_rounds + 1):
                            matches_in_round = math.ceil(teams_in_round / 2) if teams_in_round > 1 else 0
                            
                            if matches_in_round == 0:
                                continue
                            
                            # Определяем название этапа
                            if round_number == total_rounds:
                                stage_name = "Финал"
                            elif round_number == total_rounds - 1 and total_rounds > 1:
                                stage_name = "Полуфиналы" if matches_in_round > 1 else "Полуфинал"
                            else:
                                stage_name = self.get_stage_name_by_round(round_number, total_rounds, matches_in_round)
                            
                            field_name = f'format_round_{round_number}'
                            self.fields[field_name] = forms.ChoiceField(
                                choices=self.FORMAT_CHOICES,
                                label=f'Формат для {stage_name}',
                                initial=self.get_default_format(matches_in_round * 2),  # Приблизительное количество команд для этапа
                                widget=forms.Select(attrs={'class': 'form-control'})
                            )
                            
                            teams_in_round = matches_in_round
                    
                    elif tournament.tournament_format == 'double_elimination':
                        # Для Double Elimination упрощаем для малых турниров
                        if team_count <= 3:
                            # Для малых турниров создаем упрощенную форму
                            self.fields['format_round_1'] = forms.ChoiceField(
                                choices=self.FORMAT_CHOICES,
                                label='Формат для начальных матчей',
                                initial='BO3',
                                widget=forms.Select(attrs={'class': 'form-control'})
                            )
                            self.fields['format_round_2'] = forms.ChoiceField(
                                choices=self.FORMAT_CHOICES,
                                label='Формат для гранд-финала',
                                initial='BO5',
                                widget=forms.Select(attrs={'class': 'form-control'})
                            )
                        else:
                            # Для больших турниров используем старую логику
                            current_round = team_count
                            round_number = 1
                            
                            while current_round >= 2:
                                stage_name = self.get_stage_name(current_round)
                                field_name = f'format_round_{round_number}'
                                
                                self.fields[field_name] = forms.ChoiceField(
                                    choices=self.FORMAT_CHOICES,
                                    label=f'Формат для {stage_name}',
                                    initial=self.get_default_format(current_round),
                                    widget=forms.Select(attrs={'class': 'form-control'})
                                )
                                
                                current_round = current_round // 2
                                round_number += 1
    
    def get_stage_name_by_round(self, round_number, total_rounds, matches_count):
        """Получает название этапа по номеру раунда и общему количеству раундов"""
        if round_number == total_rounds:
            return "Финал"
        elif round_number == total_rounds - 1:
            return "Полуфиналы" if matches_count > 1 else "Полуфинал"
        elif round_number == total_rounds - 2:
            return "Четвертьфиналы" if matches_count > 1 else "Четвертьфинал"
        else:
            return f"Раунд {round_number}"
    
    def get_stage_name(self, team_count):
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
    
    def get_default_format(self, team_count):
        if team_count <= 4:
            return 'BO3'
        elif team_count <= 8:
            return 'BO3'
        else:
            return 'BO1'


class ManualBracketForm(forms.Form):
    """Форма для ручного распределения команд в турнирной сетке"""
    
    def __init__(self, *args, teams=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        if teams:
            team_choices = [('', '---')] + [(team.id, team.name) for team in teams]
            
            # Создаем поля для каждой позиции в первом раунде
            positions_count = len(teams)
            for i in range(positions_count):
                self.fields[f'position_{i+1}'] = forms.ChoiceField(
                    choices=team_choices,
                    label=f'Позиция {i+1}',
                    required=True,
                    widget=forms.Select(attrs={'class': 'form-control'})
                )
    
    def clean(self):
        cleaned_data = super().clean()
        selected_teams = []
        
        for field_name, team_id in cleaned_data.items():
            if field_name.startswith('position_') and team_id:
                if team_id in selected_teams:
                    raise forms.ValidationError(f"Команда не может быть выбрана дважды")
                selected_teams.append(team_id)
        
        return cleaned_data


class AdvancedMatchResultForm(forms.ModelForm):
    """Расширенная форма для ввода результатов матча с учетом формата"""
    
    class Meta:
        model = BracketMatch
        fields = ['team1_score', 'team2_score']
        widgets = {
            'team1_score': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'team2_score': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.instance and self.instance.stage:
            stage_format = self.instance.stage.format
            
            # Устанавливаем максимальные значения в зависимости от формата
            max_score = {
                'BO1': 1,
                'BO3': 2,
                'BO5': 3
            }.get(stage_format, 3)
            
            self.fields['team1_score'].widget.attrs['max'] = max_score
            self.fields['team2_score'].widget.attrs['max'] = max_score
            
            # Добавляем метки с названиями команд
            if self.instance.team1:
                self.fields['team1_score'].label = f"Счет команды {self.instance.team1.name}"
            if self.instance.team2:
                self.fields['team2_score'].label = f"Счет команды {self.instance.team2.name}"
    
    def clean(self):
        cleaned_data = super().clean()
        team1_score = cleaned_data.get('team1_score', 0)
        team2_score = cleaned_data.get('team2_score', 0)
        
        if not self.instance or not self.instance.stage:
            return cleaned_data
        
        stage_format = self.instance.stage.format
        
        # Проверяем корректность счета в зависимости от формата
        if stage_format == 'BO1':
            if (team1_score + team2_score) != 1:
                raise forms.ValidationError("В формате BO1 общий счет должен быть 1")
            if max(team1_score, team2_score) != 1:
                raise forms.ValidationError("В формате BO1 победитель должен иметь счет 1")
        
        elif stage_format == 'BO3':
            if max(team1_score, team2_score) > 2:
                raise forms.ValidationError("В формате BO3 максимальный счет 2")
            if max(team1_score, team2_score) < 2:
                raise forms.ValidationError("В формате BO3 победитель должен выиграть минимум 2 игры")
            if team1_score == team2_score:
                raise forms.ValidationError("В матче должен быть определен победитель")
        
        elif stage_format == 'BO5':
            if max(team1_score, team2_score) > 3:
                raise forms.ValidationError("В формате BO5 максимальный счет 3")
            if max(team1_score, team2_score) < 3:
                raise forms.ValidationError("В формате BO5 победитель должен выиграть минимум 3 игры")
            if team1_score == team2_score:
                raise forms.ValidationError("В матче должен быть определен победитель")
        
        return cleaned_data


class RoundRobinMatchResultForm(forms.ModelForm):
    """Форма для результатов матчей Round Robin"""
    
    bo1_score = forms.ChoiceField(
        choices=[('1-0', '1-0'), ('0-1', '0-1')],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'style': 'width: 110px;'})
    )
    
    bo3_score = forms.ChoiceField(
        choices=[('2-0', '2-0'), ('0-2', '0-2'), ('2-1', '2-1'), ('1-2', '1-2')],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'style': 'width: 110px;'})
    )
    
    bo5_score = forms.ChoiceField(
        choices=[('3-0', '3-0'), ('0-3', '0-3'), ('3-1', '3-1'), ('1-3', '1-3'), ('3-2', '3-2'), ('2-3', '2-3')],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'style': 'width: 110px;'})
    )
    
    class Meta:
        model = RoundRobinMatch
        fields = ['team1_score', 'team2_score']
        widgets = {
            'team1_score': forms.HiddenInput(),
            'team2_score': forms.HiddenInput(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.instance:
            # Устанавливаем начальные значения для полей выбора счета
            if self.instance.format == 'BO1':
                score = f"{self.instance.team1_score}-{self.instance.team2_score}"
                self.fields['bo1_score'].initial = score
            elif self.instance.format == 'BO3':
                score = f"{self.instance.team1_score}-{self.instance.team2_score}"
                self.fields['bo3_score'].initial = score
            elif self.instance.format == 'BO5':
                score = f"{self.instance.team1_score}-{self.instance.team2_score}"
                self.fields['bo5_score'].initial = score
    
    def clean(self):
        cleaned_data = super().clean()
        
        if not self.instance:
            return cleaned_data
        
        match_format = self.instance.format
        score_field = f'bo{match_format[2]}_score'
        score = cleaned_data.get(score_field)
        
        if not score:
            raise forms.ValidationError("Выберите счет матча")
        
        team1_score, team2_score = map(int, score.split('-'))
        
        # Проверяем корректность счета в зависимости от формата
        if match_format == 'BO1':
            if (team1_score + team2_score) != 1:
                raise forms.ValidationError("В формате BO1 общий счет должен быть 1")
        elif match_format == 'BO3':
            if max(team1_score, team2_score) > 2:
                raise forms.ValidationError("В формате BO3 максимальный счет 2")
            if max(team1_score, team2_score) < 2:
                raise forms.ValidationError("В формате BO3 победитель должен выиграть минимум 2 игры")
        elif match_format == 'BO5':
            if max(team1_score, team2_score) > 3:
                raise forms.ValidationError("В формате BO5 максимальный счет 3")
            if max(team1_score, team2_score) < 3:
                raise forms.ValidationError("В формате BO5 победитель должен выиграть минимум 3 игры")
        
        if team1_score == team2_score:
            raise forms.ValidationError("В матче должен быть определен победитель")
        
        # Устанавливаем значения для скрытых полей
        cleaned_data['team1_score'] = team1_score
        cleaned_data['team2_score'] = team2_score
        
        return cleaned_data


class MatchScheduleForm(forms.Form):
    """Форма для изменения времени проведения матча"""
    scheduled_time = forms.DateTimeField(
        label='Время проведения',
        widget=forms.DateTimeInput(attrs={
            'type': 'datetime-local',
            'class': 'form-control'
        }),
        required=True
    )
    
    def clean_scheduled_time(self):
        scheduled_time = self.cleaned_data.get('scheduled_time')
        if scheduled_time and scheduled_time < timezone.now():
            raise forms.ValidationError("Нельзя назначить матч на прошедшее время")
        return scheduled_time

class BracketStageForm(forms.ModelForm):
    class Meta:
        model = BracketStage
        fields = ['name', 'format']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'format': forms.Select(attrs={'class': 'form-control'}),
        }

class MatchResultForm(forms.ModelForm):
    class Meta:
        model = BracketMatch
        fields = ['winner']
        widgets = {
            'winner': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fields['winner'].queryset = Team.objects.filter(
                id__in=[self.instance.team1_id, self.instance.team2_id]
            )

class TournamentRosterForm(forms.ModelForm):
    class Meta:
        model = TournamentRegistration
        fields = ['players']
        widgets = {
            'players': forms.SelectMultiple(attrs={'class': 'form-select'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.team:
            # Ограничиваем выбор только игроками команды
            self.fields['players'].queryset = self.instance.team.players.all()
            
            # Добавляем подсказку о количестве игроков
            tournament = self.instance.tournament
            if tournament.tournament_format == 'single_elimination':
                if tournament.game_format == '1x1':
                    self.fields['players'].help_text = 'Выберите 1 игрока'
                elif tournament.game_format == '2x2':
                    self.fields['players'].help_text = 'Выберите 2 игрока'
                elif tournament.game_format == '3x3':
                    self.fields['players'].help_text = 'Выберите 3 игрока'
                elif tournament.game_format == '5x5':
                    self.fields['players'].help_text = 'Выберите 5 игроков'

    def clean_players(self):
        players = self.cleaned_data['players']
        tournament = self.instance.tournament
        
        # Проверяем количество выбранных игроков в зависимости от формата
        if tournament.game_format == '1x1' and players.count() != 1:
            raise forms.ValidationError('Для формата 1x1 нужно выбрать ровно 1 игрока')
        elif tournament.game_format == '2x2' and players.count() != 2:
            raise forms.ValidationError('Для формата 2x2 нужно выбрать ровно 2 игрока')
        elif tournament.game_format == '3x3' and players.count() != 3:
            raise forms.ValidationError('Для формата 3x3 нужно выбрать ровно 3 игрока')
        elif tournament.game_format == '5x5' and players.count() != 5:
            raise forms.ValidationError('Для формата 5x5 нужно выбрать ровно 5 игроков')
            
        return players