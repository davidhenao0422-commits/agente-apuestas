from collections import defaultdict
from typing import Dict, List


def analyze_form(matches: List[dict], team_name: str, last_n: int = 10) -> Dict:
    """Analiza la forma reciente de un equipo.

    Devuelve:
        - 'results': lista de W/D/L
        - 'points_per_game'
        - 'goals_for_per_game'
        - 'goals_against_per_game'
        - 'clean_sheets'
        - 'form_string'
    """
    results = []
    gf_total = 0
    ga_total = 0
    clean_sheets = 0
    played = 0

    for m in matches[:last_n]:
        home = m.get("home_team", "")
        away = m.get("away_team", "")
        hg = m.get("home_goals")
        ag = m.get("away_goals")

        if hg is None or ag is None:
            continue

        team_is_home = home == team_name
        team_goals = hg if team_is_home else ag
        opp_goals = ag if team_is_home else hg

        played += 1
        gf_total += team_goals
        ga_total += opp_goals
        if opp_goals == 0:
            clean_sheets += 1

        if team_goals > opp_goals:
            results.append("W")
        elif team_goals == opp_goals:
            results.append("D")
        else:
            results.append("L")

    if not results:
        return {
            "results": [], "form_string": "",
            "points_per_game": 0.0, "goals_for_per_game": 0.0,
            "goals_against_per_game": 0.0, "clean_sheets": 0,
            "win_rate": 0.0,
        }

    pts = results.count("W") * 3 + results.count("D")
    form_scores = {"W": 1, "D": 0.5, "L": 0}

    return {
        "results": results,
        "form_string": "".join(results),
        "points_per_game": round(pts / len(results), 2),
        "goals_for_per_game": round(gf_total / len(results), 2),
        "goals_against_per_game": round(ga_total / len(results), 2),
        "clean_sheets": clean_sheets,
        "win_rate": round(results.count("W") / len(results), 3),
        "avg_score": sum(form_scores[r] for r in results) / len(results),
    }


def strength_differential(home_ppg: float, away_ppg: float) -> float:
    """Calcula diferencia de fortaleza entre local y visitante."""
    return home_ppg - away_ppg
