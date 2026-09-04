from typing import List, Optional

from storage.models import TeamStats


def compute_summary_stats(stats_list: List[TeamStats]) -> dict:
    """Calcula promedios de múltiples temporadas para un equipo."""
    if not stats_list:
        return {}

    n = len(stats_list)
    recent = stats_list[-1] if stats_list[-1].played > 0 else stats_list[-1]

    total_played = sum(s.played for s in stats_list)
    total_goals_for = sum(s.goals_for for s in stats_list)
    total_goals_against = sum(s.goals_against for s in stats_list)
    total_shots = sum(s.shots_on_target for s in stats_list)
    total_corners = sum(s.corners for s in stats_list)
    avg_possession = sum(
        s.possession_avg * s.played for s in stats_list
    ) / max(total_played, 1)

    average_positions = [s.position for s in stats_list if s.position]
    avg_position = sum(average_positions) / max(len(average_positions), 1)

    return {
        "league": recent.league,
        "season": recent.season,
        "position": recent.position,
        "avg_position_last_5": round(avg_position, 1) if average_positions else None,
        "goals_per_game": round(total_goals_for / max(total_played, 1), 2),
        "conceded_per_game": round(total_goals_against / max(total_played, 1), 2),
        "goal_difference_avg": round(
            (total_goals_for - total_goals_against) / max(total_played, 1), 2
        ),
        "shots_on_target_per_game": round(total_shots / max(total_played, 1), 2),
        "corners_per_game": round(total_corners / max(total_played, 1), 2),
        "possession_avg": round(avg_possession, 1),
        "played_total": total_played,
        "win_rate": round(sum(s.won for s in stats_list) / max(total_played, 1), 3),
    }


def get_home_away_split(stats_list: List[TeamStats]) -> dict:
    """Extrae recortes local/visitante de las estadísticas."""
    if not stats_list:
        return {"home": {}, "away": {}}

    home = {"won": 0, "drawn": 0, "lost": 0, "gf": 0, "ga": 0, "played": 0}
    away = {"won": 0, "drawn": 0, "lost": 0, "gf": 0, "ga": 0, "played": 0}

    for s in stats_list:
        home["won"] += s.home_won
        home["drawn"] += s.home_drawn
        home["lost"] += s.home_lost
        home["gf"] += s.home_goals_for
        home["ga"] += s.home_goals_against
        home["played"] += s.home_won + s.home_drawn + s.home_lost

        away["won"] += s.away_won
        away["drawn"] += s.away_drawn
        away["lost"] += s.away_lost
        away["gf"] += s.away_goals_for
        away["ga"] += s.away_goals_against
        away["played"] += s.away_won + s.away_drawn + s.away_lost

    return {"home": home, "away": away}
