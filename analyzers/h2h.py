from collections import defaultdict
from typing import Dict, List

from storage.models import H2H


def analyze_h2h(matches: List[dict], team_name: str, opponent_name: str) -> H2H:
    """Analiza los enfrentamientos directos entre dos equipos.

    Args:
        matches: Lista de diccionarios con 'home_team', 'away_team',
                 'home_goals', 'away_goals', opcional 'home_corners', 'away_corners'.
        team_name: nombre del equipo de interes.
        opponent_name: nombre del rival.
    """
    result = H2H(team_a=team_name, team_b=opponent_name)

    total_goals = 0
    total_corners = 0
    matches_with_corners = 0

    for m in matches:
        home = m.get("home_team", "")
        away = m.get("away_team", "")
        hg = m.get("home_goals")
        ag = m.get("away_goals")

        if hg is None or ag is None:
            continue

        result.total_matches += 1

        # Determinar si team_name jugó de local o visitante
        team_is_home = home == team_name
        team_goals = hg if team_is_home else ag
        opp_goals = ag if team_is_home else hg
        wins = 1 if team_goals > opp_goals else 0
        draws = 1 if team_goals == opp_goals else 0

        if team_goals > opp_goals:
            result.team_a_wins += 1
        elif opp_goals > team_goals:
            result.team_b_wins += 1
        else:
            result.draws += 1

        total_goals += hg + ag

        hc = m.get("home_corners")
        ac = m.get("away_corners")
        if hc is not None and ac is not None:
            total_corners += hc + ac
            matches_with_corners += 1

        result.recent.append({
            "date": m.get("match_date"),
            "team_is_home": team_is_home,
            "team_goals": team_goals,
            "opp_goals": opp_goals,
            "result": "W" if wins else ("D" if draws else "L"),
        })

    result.avg_goals_per_match = round(
        total_goals / max(result.total_matches, 1), 2
    )
    if matches_with_corners:
        result.avg_corners_per_match = round(
            total_corners / matches_with_corners, 1
        )

    return result


def h2h_recent_form(h2h: H2H, last_n: int = 5) -> List[str]:
    """Devuelve la forma reciente del equipo A en el H2H (últimos n partidos)."""
    recent = h2h.recent[:last_n]
    return [r["result"] for r in recent]
