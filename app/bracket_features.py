import random
import math
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from .models import (
    Tournament, TournamentBracket, BracketStage, BracketMatch,
    RoundRobinTable, RoundRobinMatch, RoundRobinResult, Team
)


def create_single_elimination_bracket(tournament, teams, distribution_type='random', 
                                     third_place_match=False, stage_formats=None):
    """Создает турнирную сетку Single Elimination с корректной поддержкой bye"""
    if distribution_type == 'random':
        teams = list(teams)
        random.shuffle(teams)

    with transaction.atomic():
        if hasattr(tournament, 'bracket'):
            tournament.bracket.delete()
        bracket = TournamentBracket.objects.create(
            tournament=tournament,
            distribution_type=distribution_type,
            third_place_match=third_place_match
        )
        
        # Определяем длительность матча в зависимости от формата
        def get_match_duration(format_type):
            return {
                'BO1': 30,  # 30 минут
                'BO3': 90,  # 1.5 часа
                'BO5': 150  # 2.5 часа
            }[format_type]
        
        current_time = tournament.start_date
        round_teams = list(teams)
        total_rounds = 0
        rounds_team_counts = []
        n = len(round_teams)
        while n > 1:
            rounds_team_counts.append(n)
            n = math.ceil(n / 2)
            total_rounds += 1
        
        stage_names = []
        for i, count in enumerate(rounds_team_counts):
            if i == total_rounds - 1:
                stage_names.append(("Финал", 'final'))
            elif i == total_rounds - 2:
                stage_names.append(("Полуфинал", 'normal'))
            elif i == total_rounds - 3:
                stage_names.append(("Четвертьфинал", 'normal'))
            else:
                stage_names.append((f"Раунд {i+1}", 'normal'))
        
        bye_teams = []
        for round_number, (stage_name, stage_type) in enumerate(stage_names, 1):
            # Определяем формат матча для текущего раунда
            stage_format = 'BO3'  # По умолчанию
            if stage_formats and f'format_round_{round_number}' in stage_formats:
                stage_format = stage_formats[f'format_round_{round_number}']
            
            # Создаем этап
            stage = BracketStage.objects.create(
                bracket=bracket,
                name=stage_name,
                format=stage_format,
                stage_type=stage_type,
                order=round_number,
                scheduled_time=current_time
            )
            
            if round_number == 1:
                # Первый раунд: создаём матчи для всех пар, лишний — в bye_teams
                matches = []
                i = 0
                while i < len(round_teams):
                    team1 = round_teams[i]
                    team2 = round_teams[i+1] if i+1 < len(round_teams) else None
                    if team2:
                        match = BracketMatch.objects.create(
                            stage=stage,
                            team1=team1,
                            team2=team2,
                            order=len(matches)+1,
                            scheduled_time=current_time + timedelta(minutes=30*len(matches)),
                            is_bye=False
                        )
                        matches.append(match)
                    else:
                        bye_teams.append(team1)
                    i += 2
            else:
                # Следующие раунды: создаем матчи с учетом bye-команд
                matches_count = math.ceil((len(round_teams) + len(bye_teams)) / 2)
                matches = []
                
                # Создаем матчи для текущего раунда
                for i in range(matches_count):
                    match = BracketMatch.objects.create(
                        stage=stage,
                        order=i+1,
                        scheduled_time=current_time + timedelta(minutes=i * (get_match_duration(stage_format) + 30))
                    )
                    matches.append(match)
                
                # Назначаем bye-команды в первый свободный слот следующего раунда
                if bye_teams:
                    for idx, team in enumerate(bye_teams):
                        if idx < len(matches):
                            match = matches[idx]
                            match.team1 = team
                            match.is_bye = True
                            match.winner = team
                            match.is_completed = True
                            match.save()
                    bye_teams = []
            
            # Обновляем время для следующего раунда
            current_time += timedelta(hours=math.ceil(get_match_duration(stage_format) / 60) + 1)
            round_teams = []
        
        # Создаем матч за третье место, если нужно
        if third_place_match and total_rounds > 1:
            create_third_place_match(bracket, current_time)
        
        return bracket


def create_double_elimination_bracket(tournament, teams, distribution_type='random',
                                    stage_formats=None):
    """Создает турнирную сетку Double Elimination с динамическими стадиями и поддержкой bye"""
    if distribution_type == 'random':
        teams = list(teams)
        random.shuffle(teams)
    with transaction.atomic():
        if hasattr(tournament, 'bracket'):
            tournament.bracket.delete()
        bracket = TournamentBracket.objects.create(
            tournament=tournament,
            distribution_type=distribution_type
        )
        team_count = len(teams)
        current_time = tournament.start_date
        upper_rounds = []
        n = team_count
        while n > 1:
            upper_rounds.append(n)
            n = math.ceil(n / 2)
        total_upper = len(upper_rounds)
        upper_stage_objs = []
        for round_number, teams_in_round in enumerate(upper_rounds, 1):
            matches_in_round = math.ceil(teams_in_round / 2)
            if matches_in_round == 0:
                continue
            if round_number == total_upper:
                stage_name = "Верхний финал"
            elif round_number == total_upper - 1:
                stage_name = "Верхний полуфинал"
            else:
                stage_name = f"Верхний раунд {round_number}"
            stage_format = 'BO3'
            if stage_formats and f'format_round_{round_number}' in stage_formats:
                stage_format = stage_formats[f'format_round_{round_number}']
            stage = BracketStage.objects.create(
                bracket=bracket,
                name=stage_name,
                format=stage_format,
                stage_type='upper',
                order=round_number,
                scheduled_time=current_time
            )
            if round_number == 1:
                create_matches_for_stage(stage, teams, matches_in_round, current_time)
            else:
                create_empty_matches_for_stage(stage, matches_in_round, current_time)
            upper_stage_objs.append(stage)
            current_time += timedelta(hours=2)
        lower_rounds = max(1, len(upper_rounds) - 1)
        for i in range(lower_rounds):
            stage_name = f"Нижний раунд {i+1}" if lower_rounds > 1 else "Нижний полуфинал"
            stage = BracketStage.objects.create(
                bracket=bracket,
                name=stage_name,
                format='BO3',
                stage_type='lower',
                order=100 + i + 1,
                scheduled_time=current_time
            )
            create_empty_matches_for_stage(stage, 1, current_time)
            current_time += timedelta(hours=2)
        grand_final = BracketStage.objects.create(
            bracket=bracket,
            name="Гранд-финал",
            format='BO5',
            stage_type='final',
            order=200,
            scheduled_time=current_time
        )
        BracketMatch.objects.create(
            stage=grand_final,
            order=1,
            scheduled_time=current_time
        )
        return bracket


def create_round_robin_bracket(tournament, teams=None):
    """Создает турнирную таблицу и матчи для формата Round Robin"""
    # Удаляем существующую таблицу, если она есть
    RoundRobinTable.objects.filter(tournament=tournament).delete()
    
    # Создаем новую таблицу
    table = RoundRobinTable.objects.create(tournament=tournament)
    
    # Получаем команды турнира, если они не переданы
    if teams is None:
        teams = list(tournament.teams.all())
    else:
        teams = list(teams)
    
    # Создаем результаты для всех команд
    for team in teams:
        RoundRobinResult.objects.create(
            table=table,
            team=team,
            wins=0,
            losses=0,
            draws=0,
            points=0
        )
    
    # Определяем формат матча на основе формата турнира
    match_format = 'BO1'  # По умолчанию
    if tournament.tournament_format == 'BO3':
        match_format = 'BO3'
    elif tournament.tournament_format == 'BO5':
        match_format = 'BO5'
    
    # Определяем длительность матча в зависимости от формата
    match_duration = {
        'BO1': 30,  # 30 минут
        'BO3': 90,  # 1.5 часа
        'BO5': 150  # 2.5 часа
    }[match_format]
    
    # Создаем все возможные пары матчей
    matches = []
    for i, team1 in enumerate(teams):
        for team2 in teams[i+1:]:
            matches.append((team1, team2))
    
    # Перемешиваем матчи для случайного распределения
    random.shuffle(matches)
    
    # Определяем количество раундов
    num_teams = len(teams)
    num_rounds = num_teams - 1 if num_teams % 2 == 0 else num_teams
    
    # Распределяем матчи по раундам
    current_time = tournament.start_date
    round_number = 1
    
    while matches:
        # Определяем количество матчей в текущем раунде
        matches_in_round = min(len(matches), num_teams // 2)
        
        # Создаем матчи для текущего раунда
        for i in range(matches_in_round):
            team1, team2 = matches.pop(0)
            
            # Создаем матч
            match = RoundRobinMatch.objects.create(
                table=table,
                team1=team1,
                team2=team2,
                round_number=round_number,
                format=match_format,
                scheduled_time=current_time + timedelta(minutes=i * (match_duration + 30))  # +30 минут на подготовку
            )
        
        # Переходим к следующему раунду
        round_number += 1
        current_time += timedelta(hours=math.ceil(match_duration / 60) + 1)  # +1 час на перерыв между раундами
    
    return table


def create_upper_bracket(bracket, teams, start_time, stage_formats=None):
    """Создает верхнюю сетку для Double Elimination"""
    team_count = len(teams)
    current_round = team_count
    round_number = 1
    current_time = start_time
    
    while current_round >= 2:
        stage_name = f"Верхняя сетка - {get_stage_name(current_round)}"
        stage_format = 'BO3'
        
        if stage_formats and f'format_round_{round_number}' in stage_formats:
            stage_format = stage_formats[f'format_round_{round_number}']
        
        stage = BracketStage.objects.create(
            bracket=bracket,
            name=stage_name,
            format=stage_format,
            stage_type='upper',
            order=round_number,
            scheduled_time=current_time
        )
        
        matches_in_round = current_round // 2
        create_matches_for_stage(stage, teams, matches_in_round, current_time)
        
        current_round = matches_in_round
        round_number += 1
        current_time += timedelta(hours=2)


def create_lower_bracket(bracket, team_count, start_time, stage_formats=None):
    """Создает нижнюю сетку для Double Elimination (упрощенная версия)"""
    lower_rounds = max(2, team_count // 4)  # Упрощенное количество раундов
    current_time = start_time + timedelta(hours=1)
    
    for round_num in range(1, lower_rounds + 1):
        stage_name = f"Нижняя сетка - Раунд {round_num}"
        
        stage = BracketStage.objects.create(
            bracket=bracket,
            name=stage_name,
            format='BO3',
            stage_type='lower',
            order=100 + round_num,
            scheduled_time=current_time
        )
        
        # Создаем матчи без команд - они будут назначены позже
        for i in range(max(1, team_count // (2 ** (round_num + 1)))):
            BracketMatch.objects.create(
                stage=stage,
                order=i + 1,
                scheduled_time=current_time + timedelta(minutes=i * 30)
            )
        
        current_time += timedelta(hours=2)


def create_grand_final(bracket, start_time):
    """Создает гранд-финал для Double Elimination"""
    stage = BracketStage.objects.create(
        bracket=bracket,
        name="Гранд-финал",
        format='BO5',
        stage_type='final',
        order=200,
        scheduled_time=start_time
    )
    
    BracketMatch.objects.create(
        stage=stage,
        order=1,
        scheduled_time=start_time
    )


def create_third_place_match(bracket, start_time):
    """Создает матч за третье место"""
    stage = BracketStage.objects.create(
        bracket=bracket,
        name="Матч за 3 место",
        format='BO3',
        stage_type='third_place',
        order=999,
        scheduled_time=start_time
    )
    
    BracketMatch.objects.create(
        stage=stage,
        order=1,
        scheduled_time=start_time
    )


def create_matches_for_stage(stage, teams, matches_count, start_time):
    """Создает матчи для этапа"""
    for i in range(matches_count):
        team1 = teams[i * 2] if i * 2 < len(teams) else None
        team2 = teams[i * 2 + 1] if i * 2 + 1 < len(teams) else None
        
        # Если команда только одна, она проходит автоматически
        is_bye = team2 is None
        
        match_time = start_time + timedelta(minutes=i * 30)
        
        match = BracketMatch.objects.create(
            stage=stage,
            team1=team1,
            team2=team2,
            order=i + 1,
            scheduled_time=match_time,
            is_bye=is_bye
        )
        
        # Если это проход, автоматически определяем победителя
        if is_bye and team1:
            match.winner = team1
            match.is_completed = True
            match.save()


def get_stage_name(team_count):
    """Получает название этапа по количеству команд"""
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


def promote_winner_to_next_stage(match):
    """Продвигает победителя в следующий этап и назначает матч за 3 место"""
    if not match.winner:
        print(f"Нет победителя для матча {match.id}")
        return

    bracket = match.stage.bracket
    loser = match.team1 if match.winner == match.team2 else match.team2

    # Для Single Elimination
    if bracket.tournament.tournament_format == 'single_elimination':
        # --- Назначение победителя в финал или следующий этап ---
        next_stage = BracketStage.objects.filter(
            bracket=bracket,
            stage_type__in=['normal', 'final'],
            order=match.stage.order + 1
        ).first()
        print(f"Текущий этап: {match.stage.name} (order={match.stage.order}), следующий этап: {getattr(next_stage, 'name', None)} (order={getattr(next_stage, 'order', None)})")
        if not next_stage:
            next_stage = BracketStage.objects.filter(bracket=bracket, stage_type='final').first()
        if next_stage:
            print(f"Следующий этап: {next_stage.name}, матчей: {next_stage.matches.count()}, stage_type: {next_stage.stage_type}")
            # Если это финал (stage_type == 'final')
            if next_stage.stage_type == 'final':
                next_match = next_stage.matches.first()
                print(f"Финал: назначаем победителя {match.winner} из полуфинала order={match.order}")
                if match.order == 1:
                    next_match.team1 = match.winner
                else:
                    next_match.team2 = match.winner
                next_match.save()
            else:
                # Обычная логика для других этапов
                match_position = math.ceil(match.order / 2)
                next_match = BracketMatch.objects.filter(stage=next_stage, order=match_position).first()
                print(f"Назначаем победителя {match.winner} в матч: {getattr(next_match, 'id', None)} (order={match_position})")
                if next_match:
                    # Проверяем, есть ли уже команда в слоте
                    if next_match.team1 is None:
                        next_match.team1 = match.winner
                    elif next_match.team2 is None:
                        next_match.team2 = match.winner
                    else:
                        # Если оба слота заняты, ищем следующий свободный матч
                        next_match = BracketMatch.objects.filter(
                            stage=next_stage,
                            team1__isnull=True
                        ).first()
                        if next_match:
                            next_match.team1 = match.winner
                        else:
                            next_match = BracketMatch.objects.filter(
                                stage=next_stage,
                                team2__isnull=True
                            ).first()
                            if next_match:
                                next_match.team2 = match.winner
                    next_match.save()

        # --- Назначение матча за 3 место ---
        final_stage = BracketStage.objects.filter(bracket=bracket, stage_type='final').first()
        if final_stage and bracket.third_place_match:
            third_place_stage = BracketStage.objects.filter(
                bracket=bracket,
                stage_type='third_place'
            ).first()
            if not third_place_stage:
                third_place_stage = BracketStage.objects.create(
                    bracket=bracket,
                    name="Матч за 3 место",
                    format='BO3',
                    stage_type='third_place',
                    order=final_stage.order + 1,
                    scheduled_time=final_stage.scheduled_time + timedelta(hours=2)
                )
            third_place_match = BracketMatch.objects.filter(stage=third_place_stage).first()
            if not third_place_match:
                third_place_match = BracketMatch.objects.create(
                    stage=third_place_stage,
                    order=1,
                    scheduled_time=third_place_stage.scheduled_time
                )
            if third_place_match.team1 is None:
                third_place_match.team1 = loser
            else:
                third_place_match.team2 = loser
            third_place_match.save()


def get_upcoming_matches(tournament):
    """Получает предстоящие матчи турнира"""
    upcoming_matches = []
    
    if tournament.tournament_format == 'round_robin':
        if hasattr(tournament, 'round_robin_table'):
            matches = tournament.round_robin_table.matches.filter(
                is_completed=False,
                scheduled_time__isnull=False
            ).order_by('scheduled_time')[:10]
            upcoming_matches.extend(matches)
    else:
        if hasattr(tournament, 'bracket'):
            matches = BracketMatch.objects.filter(
                stage__bracket=tournament.bracket,
                is_completed=False,
                scheduled_time__isnull=False,
                team1__isnull=False,
                team2__isnull=False
            ).order_by('scheduled_time')[:10]
            upcoming_matches.extend(matches)
    
    return upcoming_matches


def get_stage_name_by_round(round_number, total_rounds, matches_count):
    """Получает название этапа по номеру раунда и общему количеству раундов"""
    if round_number == total_rounds:
        return "Финал"
    elif round_number == total_rounds - 1:
        return "Полуфиналы" if matches_count > 1 else "Полуфинал"
    elif round_number == total_rounds - 2:
        return "Четвертьфиналы" if matches_count > 1 else "Четвертьфинал"
    else:
        return f"Раунд {round_number}"


def create_empty_matches_for_stage(stage, matches_count, start_time):
    """Создает пустые матчи для этапа (команды будут назначены позже)"""
    for i in range(matches_count):
        match_time = start_time + timedelta(minutes=i * 30)
        
        BracketMatch.objects.create(
            stage=stage,
            order=i + 1,
            scheduled_time=match_time
        )


def create_simple_double_elimination(bracket, teams, start_time, stage_formats=None):
    """Создает упрощенную Double Elimination сетку для 2-3 команд"""
    team_count = len(teams)
    current_time = start_time
    
    if team_count == 2:
        # Для 2 команд: 1 матч верхней сетки, возможный реванш в гранд-финале
        
        # Верхняя сетка - финал
        upper_final = BracketStage.objects.create(
            bracket=bracket,
            name="Верхний финал",
            format='BO3',
            stage_type='upper',
            order=1,
            scheduled_time=current_time
        )
        
        BracketMatch.objects.create(
            stage=upper_final,
            team1=teams[0],
            team2=teams[1],
            order=1,
            scheduled_time=current_time
        )
        
        current_time += timedelta(hours=2)
        
        # Гранд-финал
        grand_final = BracketStage.objects.create(
            bracket=bracket,
            name="Гранд-финал",
            format='BO5',
            stage_type='final',
            order=100,
            scheduled_time=current_time
        )
        
        BracketMatch.objects.create(
            stage=grand_final,
            order=1,
            scheduled_time=current_time
        )
        
    elif team_count == 3:
        # Для 3 команд: полуфинал верхней сетки, матч нижней сетки, гранд-финал
        
        # Верхняя сетка - полуфинал
        upper_semi = BracketStage.objects.create(
            bracket=bracket,
            name="Верхний полуфинал",
            format='BO3',
            stage_type='upper',
            order=1,
            scheduled_time=current_time
        )
        
        BracketMatch.objects.create(
            stage=upper_semi,
            team1=teams[0],
            team2=teams[1],
            order=1,
            scheduled_time=current_time
        )
        
        current_time += timedelta(hours=1)
        
        # Нижняя сетка - матч на выживание
        lower_match = BracketStage.objects.create(
            bracket=bracket,
            name="Матч на выживание",
            format='BO3',
            stage_type='lower',
            order=50,
            scheduled_time=current_time
        )
        
        # Матч между проигравшим верхнего полуфинала и третьей командой
        BracketMatch.objects.create(
            stage=lower_match,
            team2=teams[2],  # Третья команда сразу попадает в нижнюю сетку
            order=1,
            scheduled_time=current_time
        )
        
        current_time += timedelta(hours=2)
        
        # Гранд-финал
        grand_final = BracketStage.objects.create(
            bracket=bracket,
            name="Гранд-финал",
            format='BO5',
            stage_type='final',
            order=100,
            scheduled_time=current_time
        )
        
        BracketMatch.objects.create(
            stage=grand_final,
            order=1,
            scheduled_time=current_time
        )
