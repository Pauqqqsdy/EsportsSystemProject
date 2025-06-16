from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.db.models.signals import pre_delete, post_save
from django.dispatch import receiver
from datetime import timedelta
import math

class Tournament(models.Model):
    DISCIPLINE_CHOICES = [
        ('Dota 2', 'Dota 2'),
        ('CS 2', 'CS 2'),
        ('Valorant', 'Valorant'),
        ('LoL', 'League of Legends'),
    ]
    
    FORMAT_CHOICES = [
        ('1x1', '1x1'),
        ('2x2', '2x2'),
        ('3x3', '3x3'),
        ('5x5', '5x5'),
    ]
    
    TOURNAMENT_FORMAT_CHOICES = [
        ('single_elimination', 'Single Elimination'),
        ('double_elimination', 'Double Elimination'),
        ('round_robin', 'Round Robin'),
    ]
    
    TEAM_COUNT_CHOICES = [(i, str(i)) for i in range(2, 513)]
    
    LOCATION_CHOICES = [
        ('China', 'Китай'),
        ('Western Europe', 'Западная Европа'),
        ('Eastern Europe', 'Восточная Европа'),
        ('Southeast Asia', 'ЮВ Азия'),
        ('North America', 'Северная Америка'),
        ('South America', 'Южная Америка'),
    ]

    name = models.CharField(max_length=50, verbose_name="Название турнира")
    max_teams = models.IntegerField(choices=TEAM_COUNT_CHOICES, verbose_name="Максимальное количество команд")
    start_date = models.DateTimeField(verbose_name="Дата начала")
    discipline = models.CharField(max_length=50, choices=DISCIPLINE_CHOICES, verbose_name="Дисциплина")
    game_format = models.CharField(max_length=50, choices=FORMAT_CHOICES, verbose_name="Формат игры")
    tournament_format = models.CharField(max_length=50, choices=TOURNAMENT_FORMAT_CHOICES, verbose_name="Формат турнира", blank=True, null=True)
    location = models.CharField(max_length=50, choices=LOCATION_CHOICES, verbose_name="Локация")
    description = models.TextField(max_length=1000, verbose_name="Описание", blank=True, null=True)
    creator = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Создатель")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Дата создания")
    is_active = models.BooleanField(default=True, verbose_name="Активный")
    registered_teams = models.ManyToManyField(
        'Team',
        through='TournamentRegistration',
        related_name='tournaments',
        blank=True,
        verbose_name="Зарегистрированные команды"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Турнир'
        verbose_name_plural = 'Турниры'

    def __str__(self):
        return self.name

    def registered_teams_count(self):
        return self.registered_teams.count()

    def is_registered(self, team):
        return self.registered_teams.filter(pk=team.pk).exists()

    def is_creator(self, user):
        return self.creator == user

    def is_full(self):
        return self.registered_teams_count() >= self.max_teams

    def get_teams_display(self):
        return f"{self.registered_teams_count()}/{self.max_teams}"

    def clean(self):
        if self.start_date and self.start_date < timezone.now():
            raise ValidationError("Невозможно назначить турнир в уже прошедшую дату")

    def get_status(self):
        """Получить статус турнира"""
        # Если турнир в формате Round Robin
        if hasattr(self, 'round_robin_table'):
            # Проверяем, есть ли завершенные матчи
            total_matches = RoundRobinMatch.objects.filter(table=self.round_robin_table).count()
            completed_matches = RoundRobinMatch.objects.filter(table=self.round_robin_table, is_completed=True).count()
            
            if completed_matches == total_matches and total_matches > 0:
                return 'completed'
            else:
                return 'in_progress'
        
        # Если турнир в формате со скобками
        if hasattr(self, 'bracket'):
            # Проверяем, есть ли завершенные матчи
            total_matches = BracketMatch.objects.filter(stage__bracket=self.bracket).count()
            completed_matches = BracketMatch.objects.filter(stage__bracket=self.bracket, is_completed=True).count()
            
            if completed_matches == total_matches and total_matches > 0:
                return 'completed'
            else:
                return 'in_progress'
        
        # Если турнирная сетка не сформирована
        return 'planned'

    def get_status_display(self):
        """Получить отображаемое название статуса"""
        status_map = {
            'planned': 'Запланирован',
            'in_progress': 'В процессе',
            'completed': 'Завершён'
        }
        return status_map.get(self.get_status(), 'Неизвестно')


class TournamentRegistration(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    team = models.ForeignKey('Team', on_delete=models.CASCADE)
    registered_at = models.DateTimeField(auto_now_add=True)
    players = models.ManyToManyField(
        User,
        related_name='tournament_registrations',
        verbose_name="Игроки, участвующие в турнире"
    )

    class Meta:
        unique_together = ('tournament', 'team')
        verbose_name = 'Регистрация на турнир'
        verbose_name_plural = 'Регистрации на турниры'

    def __str__(self):
        return f"{self.team.name} в {self.tournament.name}"


class Team(models.Model):
    name = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Название команды",
        error_messages={
            'unique': "Команда с таким названием уже существует"
        }
    )
    avatar = models.ImageField(
        upload_to='team_avatars/',
        default='team_avatars/default_team.jpg',
        blank=True,
        null=True,
        verbose_name="Аватар команды"
    )
    captain = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='captained_teams',
        verbose_name="Капитан"
    )
    members = models.ManyToManyField(
        User,
        related_name='teams',
        blank=True,
        verbose_name="Участники"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    invite_code = models.CharField(
        max_length=32,
        unique=True,
        verbose_name="Код приглашения"
    )

    class Meta:
        verbose_name = 'Команда'
        verbose_name_plural = 'Команды'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.pk:
            if not self.invite_code:
                self.invite_code = get_random_string(32)
            super().save(*args, **kwargs)
            self.members.add(self.captain)
        else:
            super().save(*args, **kwargs)

    def member_count(self):
        if not self.pk:
            return 0
        return self.members.count()

    def is_full(self):
        return self.member_count() >= 8

    def is_captain(self, user):
        return self.captain == user

    def is_member(self, user):
        return self.members.filter(pk=user.pk).exists()

    def clean(self):
        if self.member_count() > 8:
            raise ValidationError("Команда не может содержать более 8 участников")
    def get_all_members(self):
        if not self.pk:
            return []
        members = list(self.members.all())
        if self.captain not in members:
            members.insert(0, self.captain)
        return members
    def delete_if_empty(self):
        if self.member_count() == 0:
            self.delete()
            return True
        return False


@receiver(post_save, sender=Team)
def add_captain_to_members(sender, instance, created, **kwargs):
    if created and not instance.members.filter(pk=instance.captain.pk).exists():
        instance.members.add(instance.captain)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    email_confirmed = models.BooleanField(default=False)
    avatar = models.ImageField(
        upload_to='avatars/',
        default='avatars/default.jpg',
        blank=True,
        null=True
    )
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='team_members')
    bio = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.user.username

    def can_register_for_tournament(self, tournament):
        if tournament.game_format == '1x1':
            return True
        return self.team and self.team.is_captain(self.user)


@receiver(pre_delete, sender=User)
def user_deleted(sender, instance, **kwargs):
    try:
        profile = instance.userprofile
        if profile.team:
            team = profile.team
            profile.team = None
            profile.save()
            
            if team.captain == instance:
                if team.member_count() > 1:
                    new_captain = team.members.exclude(pk=instance.pk).first()
                    team.captain = new_captain
                    team.save()
                else:
                    team.delete()
            elif team.member_count() == 0:
                team.delete()
    except UserProfile.DoesNotExist:
        pass

class TournamentBracket(models.Model):
    FORMAT_CHOICES = [
        ('BO1', 'Best of 1'),
        ('BO3', 'Best of 3'),
        ('BO5', 'Best of 5'),
    ]
    
    DISTRIBUTION_CHOICES = [
        ('random', 'Случайное распределение'),
        ('manual', 'Ручное распределение'),
    ]
    
    tournament = models.OneToOneField(Tournament, on_delete=models.CASCADE, related_name='bracket')
    distribution_type = models.CharField(max_length=20, choices=DISTRIBUTION_CHOICES, default='random')
    third_place_match = models.BooleanField(default=False, verbose_name="Матч за третье место")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Турнирная сетка'
        verbose_name_plural = 'Турнирные сетки'
    
    def __str__(self):
        return f"Сетка турнира {self.tournament.name}"

class BracketStage(models.Model):
    STAGE_TYPE_CHOICES = [
        ('upper', 'Верхняя сетка'),
        ('lower', 'Нижняя сетка'),
        ('final', 'Финал'),
        ('third_place', 'Матч за 3 место'),
        ('normal', 'Обычный этап'),
    ]
    
    bracket = models.ForeignKey(TournamentBracket, on_delete=models.CASCADE, related_name='stages')
    name = models.CharField(max_length=100)
    format = models.CharField(max_length=3, choices=TournamentBracket.FORMAT_CHOICES, default='BO3')
    stage_type = models.CharField(max_length=20, choices=STAGE_TYPE_CHOICES, default='normal')
    order = models.PositiveIntegerField()
    scheduled_time = models.DateTimeField(null=True, blank=True, verbose_name="Запланированное время")
    is_completed = models.BooleanField(default=False)

    class Meta:
        ordering = ['order']
        verbose_name = 'Этап турнира'
        verbose_name_plural = 'Этапы турнира'
    
    def __str__(self):
        return f"{self.name} - {self.bracket.tournament.name}"

class BracketMatch(models.Model):
    """Матч в турнирной сетке"""
    stage = models.ForeignKey(BracketStage, on_delete=models.CASCADE, related_name='matches')
    team1 = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='team1_matches', null=True, blank=True)
    team2 = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='team2_matches', null=True, blank=True)
    winner = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='won_matches')
    team1_score = models.PositiveIntegerField(default=0)
    team2_score = models.PositiveIntegerField(default=0)
    order = models.PositiveIntegerField()
    scheduled_time = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    is_bye = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['order']
        verbose_name = 'Матч турнирной сетки'
        verbose_name_plural = 'Матчи турнирной сетки'
    
    def __str__(self):
        return f"{self.team1.name if self.team1 else '-'} vs {self.team2.name if self.team2 else '-'}"
    
    def clean(self):
        """Валидация модели"""
        if self.winner and self.winner not in [self.team1, self.team2]:
            raise ValidationError("Победитель должен быть одной из команд в матче")
        
        if self.is_completed and not self.winner and not self.is_bye:
            raise ValidationError("Для завершенного матча должен быть указан победитель")
        
        # Валидация счета в зависимости от формата
        if self.is_completed and not self.is_bye:
            format_max_score = {
                'BO1': 1,
                'BO3': 2,
                'BO5': 3
            }[self.stage.format]
            
            if self.team1_score > format_max_score or self.team2_score > format_max_score:
                raise ValidationError(f"Счет не может быть больше {format_max_score} для формата {self.stage.format}")
            
            # Проверка на ничью в Single Elimination и Double Elimination
            if self.team1_score == self.team2_score:
                tournament_format = self.stage.bracket.tournament.tournament_format
                if tournament_format in ['single_elimination', 'double_elimination']:
                    raise ValidationError(f"В формате {tournament_format} не может быть ничьей")
            
            if max(self.team1_score, self.team2_score) != format_max_score:
                raise ValidationError(f"Победитель должен набрать {format_max_score} очков в формате {self.stage.format}")
        
        # Валидация времени матча
        if self.scheduled_time:
            # Проверяем, что время матча не пересекается с другими матчами
            match_duration = {
                'BO1': 30,  # 30 минут
                'BO3': 90,  # 1.5 часа
                'BO5': 150  # 2.5 часа
            }[self.stage.format]
            
            start_time = self.scheduled_time
            end_time = start_time + timedelta(minutes=match_duration)
            
            overlapping_matches = BracketMatch.objects.filter(
                stage__bracket=self.stage.bracket,
                scheduled_time__isnull=False,
                is_completed=False
            ).exclude(id=self.id)
            
            for match in overlapping_matches:
                match_start = match.scheduled_time
                match_end = match_start + timedelta(minutes={
                    'BO1': 30,
                    'BO3': 90,
                    'BO5': 150
                }[match.stage.format])
                
                if (start_time <= match_end and end_time >= match_start):
                    raise ValidationError(f"Время матча пересекается с матчем {match}")
    
    def save(self, *args, **kwargs):
        # Автоматически определяем победителя по счету
        if self.is_completed and not self.is_bye:
            if self.team1_score > self.team2_score:
                self.winner = self.team1
            elif self.team2_score > self.team1_score:
                self.winner = self.team2
            else:
                # В Single Elimination и Double Elimination не может быть ничьей
                tournament_format = self.stage.bracket.tournament.tournament_format
                if tournament_format in ['single_elimination', 'double_elimination']:
                    raise ValidationError(f"В формате {tournament_format} не может быть ничьей")
        
        super().save(*args, **kwargs)
        
        # Если матч завершен, обновляем следующую стадию
        if self.is_completed and not self.is_bye:
            self.update_next_stage()

    def update_next_stage(self):
        """Обновляет следующую стадию турнира"""
        if not self.winner:
            return
        
        bracket = self.stage.bracket
        loser = self.team1 if self.winner == self.team2 else self.team2
        
        # Для Single Elimination
        if bracket.tournament.tournament_format == 'single_elimination':
            # Находим следующий этап
            next_stage = BracketStage.objects.filter(
                bracket=bracket,
                stage_type__in=['normal', 'final'],
                order=self.stage.order + 1
            ).first()
            
            if not next_stage:
                next_stage = BracketStage.objects.filter(
                    bracket=bracket,
                    stage_type='final'
                ).first()
            
            if next_stage:
                # Определяем позицию в следующем матче
                match_position = math.ceil(self.order / 2)
                next_match = BracketMatch.objects.filter(
                    stage=next_stage,
                    order=match_position
                ).first()
                
                if next_match:
                    # Назначаем победителя в свободный слот
                    if next_match.team1 is None:
                        next_match.team1 = self.winner
                    elif next_match.team2 is None:
                        next_match.team2 = self.winner
                    next_match.save()
                
                # Если это матч за третье место, назначаем проигравшего
                if bracket.third_place_match and self.stage.stage_type == 'final':
                    third_place_stage = BracketStage.objects.filter(
                        bracket=bracket,
                        stage_type='third_place'
                    ).first()
                    
                    if third_place_stage:
                        third_place_match = third_place_stage.matches.first()
                        if third_place_match:
                            if third_place_match.team1 is None:
                                third_place_match.team1 = loser
                            elif third_place_match.team2 is None:
                                third_place_match.team2 = loser
                            third_place_match.save()
        
        # Для Double Elimination
        elif bracket.tournament.tournament_format == 'double_elimination':
            # Определяем, в какой сетке находится матч (верхняя или нижняя)
            is_upper_bracket = self.stage.stage_type == 'upper'
            
            if is_upper_bracket:
                # В верхней сетке победитель идет дальше по верхней сетке
                next_stage = BracketStage.objects.filter(
                    bracket=bracket,
                    stage_type='upper',
                    order=self.stage.order + 1
                ).first()
                
                if next_stage:
                    match_position = math.ceil(self.order / 2)
                    next_match = BracketMatch.objects.filter(
                        stage=next_stage,
                        order=match_position
                    ).first()
                    
                    if next_match:
                        if next_match.team1 is None:
                            next_match.team1 = self.winner
                        elif next_match.team2 is None:
                            next_match.team2 = self.winner
                        next_match.save()
                
                # Проигравший идет в нижнюю сетку
                lower_stage = BracketStage.objects.filter(
                    bracket=bracket,
                    stage_type='lower',
                    order=self.stage.order
                ).first()
                
                if lower_stage:
                    # Находим подходящий матч в нижней сетке
                    lower_match = BracketMatch.objects.filter(
                        stage=lower_stage,
                        team1__isnull=True
                    ).first()
                    
                    if not lower_match:
                        lower_match = BracketMatch.objects.filter(
                            stage=lower_stage,
                            team2__isnull=True
                        ).first()
                    
                    if lower_match:
                        if lower_match.team1 is None:
                            lower_match.team1 = loser
                        elif lower_match.team2 is None:
                            lower_match.team2 = loser
                        lower_match.save()
            
            else:
                # В нижней сетке победитель идет дальше по нижней сетке
                next_stage = BracketStage.objects.filter(
                    bracket=bracket,
                    stage_type='lower',
                    order=self.stage.order + 1
                ).first()
                
                if next_stage:
                    match_position = math.ceil(self.order / 2)
                    next_match = BracketMatch.objects.filter(
                        stage=next_stage,
                        order=match_position
                    ).first()
                    
                    if next_match:
                        if next_match.team1 is None:
                            next_match.team1 = self.winner
                        elif next_match.team2 is None:
                            next_match.team2 = self.winner
                        next_match.save()
                
                # Если это финал нижней сетки, победитель идет в гранд-финал
                if self.stage.stage_type == 'lower_final':
                    grand_final_stage = BracketStage.objects.filter(
                        bracket=bracket,
                        stage_type='grand_final'
                    ).first()
                    
                    if grand_final_stage:
                        grand_final_match = grand_final_stage.matches.first()
                        if grand_final_match:
                            if grand_final_match.team1 is None:
                                grand_final_match.team1 = self.winner
                            elif grand_final_match.team2 is None:
                                grand_final_match.team2 = self.winner
                            grand_final_match.save()


class RoundRobinTable(models.Model):
    """Таблица для турнира Round Robin"""
    tournament = models.OneToOneField(Tournament, on_delete=models.CASCADE, related_name='round_robin_table')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Таблица Round Robin'
        verbose_name_plural = 'Таблицы Round Robin'
    
    def __str__(self):
        return f"Таблица Round Robin - {self.tournament.name}"


class RoundRobinResult(models.Model):
    """Результаты команд в турнире Round Robin"""
    table = models.ForeignKey(RoundRobinTable, on_delete=models.CASCADE, related_name='results')
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    matches_played = models.PositiveIntegerField(default=0)
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    draws = models.PositiveIntegerField(default=0)  # Добавляем поле для ничьих
    points = models.PositiveIntegerField(default=0)  # Очки (3 за победу, 1 за ничью, 0 за поражение)
    map_difference = models.IntegerField(default=0, verbose_name="Разница карт")
    
    class Meta:
        unique_together = ('table', 'team')
        ordering = ['-points', '-wins', '-draws', 'losses']  # Обновляем сортировку
        verbose_name = 'Результат команды в Round Robin'
        verbose_name_plural = 'Результаты команд в Round Robin'
    
    def __str__(self):
        return f"{self.team.name} - {self.points} очков"
    
    def get_win_rate(self):
        """Получить процент побед"""
        if self.matches_played == 0:
            return 0
        # Считаем процент побед как (победы + 0.5 * ничьи) / всего матчей * 100
        return round(((self.wins + (self.draws * 0.5)) / self.matches_played) * 100, 1)


class RoundRobinMatch(models.Model):
    """Матч в Round Robin турнире"""
    table = models.ForeignKey(RoundRobinTable, on_delete=models.CASCADE, related_name='matches')
    team1 = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='team1_round_robin_matches')
    team2 = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='team2_round_robin_matches')
    team1_score = models.PositiveIntegerField(default=0)
    team2_score = models.PositiveIntegerField(default=0)
    scheduled_time = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    round_number = models.PositiveIntegerField(default=1)
    
    class Meta:
        ordering = ['round_number', 'scheduled_time']
        verbose_name = 'Матч Round Robin'
        verbose_name_plural = 'Матчи Round Robin'
    
    def __str__(self):
        return f"{self.team1.name} vs {self.team2.name}"
    
    def clean(self):
        """Валидация модели"""
        if self.is_completed:
            # Проверяем, что счет соответствует формату матча
            format_max_score = {
                'BO1': 1,
                'BO3': 2,
                'BO5': 3
            }[self.table.tournament.game_format]
            
            if self.team1_score > format_max_score or self.team2_score > format_max_score:
                raise ValidationError(f"Счет не может быть больше {format_max_score} для формата {self.table.tournament.game_format}")
            
            # Проверяем, что победитель набрал нужное количество очков
            if max(self.team1_score, self.team2_score) != format_max_score:
                raise ValidationError(f"Победитель должен набрать {format_max_score} очков в формате {self.table.tournament.game_format}")
        
        # Валидация времени матча
        if self.scheduled_time:
            match_duration = {
                'BO1': 30,  # 30 минут
                'BO3': 90,  # 1.5 часа
                'BO5': 150  # 2.5 часа
            }[self.table.tournament.game_format]
            
            start_time = self.scheduled_time
            end_time = start_time + timedelta(minutes=match_duration)
            
            overlapping_matches = RoundRobinMatch.objects.filter(
                table=self.table,
                scheduled_time__isnull=False,
                is_completed=False
            ).exclude(id=self.id)
            
            for match in overlapping_matches:
                match_start = match.scheduled_time
                match_end = match_start + timedelta(minutes={
                    'BO1': 30,
                    'BO3': 90,
                    'BO5': 150
                }[self.table.tournament.game_format])
                
                if (start_time <= match_end and end_time >= match_start):
                    raise ValidationError(f"Время матча пересекается с матчем {match}")
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Обновляем результаты только если матч завершен
        if self.is_completed and not is_new:
            self.update_table_results()
    
    def update_table_results(self):
        """Обновляет результаты в таблице"""
        # Получаем результаты обеих команд
        team1_result = RoundRobinResult.objects.get(table=self.table, team=self.team1)
        team2_result = RoundRobinResult.objects.get(table=self.table, team=self.team2)
        
        # Сбрасываем статистику для обеих команд
        team1_result.matches_played = 0
        team1_result.wins = 0
        team1_result.losses = 0
        team1_result.draws = 0
        team1_result.points = 0
        
        team2_result.matches_played = 0
        team2_result.wins = 0
        team2_result.losses = 0
        team2_result.draws = 0
        team2_result.points = 0
        
        # Пересчитываем статистику на основе всех завершенных матчей
        completed_matches = RoundRobinMatch.objects.filter(
            table=self.table,
            is_completed=True
        )
        
        for match in completed_matches:
            if match.team1 == self.team1 or match.team2 == self.team1:
                team1_result.matches_played += 1
                if match.team1_score > match.team2_score:
                    team1_result.wins += 1
                    team1_result.points += 3
                elif match.team1_score < match.team2_score:
                    team1_result.losses += 1
                else:
                    team1_result.draws += 1
                    team1_result.points += 1
            
            if match.team1 == self.team2 or match.team2 == self.team2:
                team2_result.matches_played += 1
                if match.team1_score < match.team2_score:
                    team2_result.wins += 1
                    team2_result.points += 3
                elif match.team1_score > match.team2_score:
                    team2_result.losses += 1
                else:
                    team2_result.draws += 1
                    team2_result.points += 1
        
        team1_result.save()
        team2_result.save()