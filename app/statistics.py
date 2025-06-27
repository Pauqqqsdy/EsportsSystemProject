from .models import RoundRobinResult, RoundRobinMatch

def update_round_robin_results(match):
    """Обновляет результаты турнирной таблицы после изменения результата матча"""
    print(f"Обновляем результаты для матча {match.team1.name} vs {match.team2.name} ({match.team1_score}-{match.team2_score})")
    
    # Получаем все результаты команд в таблице
    all_results = RoundRobinResult.objects.filter(table=match.table)
    print(f"Найдено {all_results.count()} результатов команд в таблице")
    
    # Создаем словарь для хранения статистики каждой команды
    team_stats = {}
    for result in all_results:
        team_stats[result.team.id] = {
            'matches_played': 0,
            'wins': 0,
            'losses': 0,
            'draws': 0,
            'points': 0,
            'map_difference': 0
        }
    
    # Пересчитываем статистику для всех матчей
    completed_matches = RoundRobinMatch.objects.filter(
        table=match.table,
        is_completed=True
    )
    print(f"Найдено {completed_matches.count()} завершенных матчей")
    
    for m in completed_matches:
        print(f"Обрабатываем матч: {m.team1.name} vs {m.team2.name} ({m.team1_score}-{m.team2_score})")
        
        # Обновляем статистику для первой команды
        team1_stats = team_stats[m.team1.id]
        team1_stats['matches_played'] += 1
        team1_stats['map_difference'] += (m.team1_score - m.team2_score)
        
        if m.team1_score > m.team2_score:
            team1_stats['wins'] += 1
            team1_stats['points'] += 3
            print(f"  {m.team1.name} побеждает")
        elif m.team1_score < m.team2_score:
            team1_stats['losses'] += 1
            print(f"  {m.team1.name} проигрывает")
        else:
            team1_stats['draws'] += 1
            team1_stats['points'] += 1
            print(f"  {m.team1.name} ничья")
        
        # Обновляем статистику для второй команды
        team2_stats = team_stats[m.team2.id]
        team2_stats['matches_played'] += 1
        team2_stats['map_difference'] += (m.team2_score - m.team1_score)
        
        if m.team2_score > m.team1_score:
            team2_stats['wins'] += 1
            team2_stats['points'] += 3
            print(f"  {m.team2.name} побеждает")
        elif m.team2_score < m.team1_score:
            team2_stats['losses'] += 1
            print(f"  {m.team2.name} проигрывает")
        else:
            team2_stats['draws'] += 1
            team2_stats['points'] += 1
            print(f"  {m.team2.name} ничья")
    
    # Обновляем и сохраняем результаты в базе данных
    for result in all_results:
        stats = team_stats[result.team.id]
        result.matches_played = stats['matches_played']
        result.wins = stats['wins']
        result.losses = stats['losses']
        result.draws = stats['draws']
        result.points = stats['points']
        result.map_difference = stats['map_difference']
        result.save()
        print(f"Сохранен результат для {result.team.name}: И={result.matches_played}, П={result.wins}, Пр={result.losses}, О={result.points}") 