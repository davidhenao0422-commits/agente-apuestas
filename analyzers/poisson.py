import math
from typing import Dict, Tuple


def poisson_probability(lambda_val: float, k: int) -> float:
    """Probabilidad de que ocurran exactamente k eventos dado lambda."""
    if lambda_val < 0:
        raise ValueError("lambda debe ser >= 0")
    if k < 0:
        return 0.0
    return (lambda_val ** k) * math.exp(-lambda_val) / math.factorial(k)


def expected_goals(home_attack: float, away_defense: float,
                   league_avg_goals: float = 2.5) -> float:
    """Goles esperados.

    Args:
        home_attack: goles anotados por el local por partido.
        away_defense: goles concedidos por el visitante por partido.
        league_avg_goals: promedio de la liga (hasta 2024 suele ser ~2.5).
    """
    return (home_attack * away_defense * league_avg_goals) / max(league_avg_goals, 0.01)


def predict_match_scores(lambda_home: float, lambda_away: float,
                         max_goals: int = 8) -> Dict:
    """Crea la matriz de probabilidades de marcadores.

    Devuelve dict con:
        'matrix': {(h,a): prob}
        'home_win', 'draw', 'away_win': probabilidades de resultado.
    """
    matrix = {}
    home_win = 0.0
    draw = 0.0
    away_win = 0.0

    for h in range(max_goals + 1):
        ph = poisson_probability(lambda_home, h)
        for a in range(max_goals + 1):
            pa = poisson_probability(lambda_away, a)
            prob = ph * pa
            matrix[(h, a)] = prob
            if h > a:
                home_win += prob
            elif h == a:
                draw += prob
            else:
                away_win += prob

    return {
        "matrix": matrix,
        "home_win": home_win,
        "draw": draw,
        "away_win": away_win,
    }


def over_under_probabilities(lambda_home: float, lambda_away: float,
                             line: float = 2.5) -> Dict:
    """Probabilidad de over/under para una línea de goles."""
    total_lambda = lambda_home + lambda_away
    over = 0.0

    # Sumar todos los marcadores donde total > line
    max_goals = 12
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            if h + a > line:
                over += poisson_probability(lambda_home, h) * poisson_probability(lambda_away, a)

    return {"over": over, "under": 1.0 - over}


def btts_probability(lambda_home: float, lambda_away: float) -> float:
    """Probabilidad de que ambos equipos anoten (BTTS)."""
    p_home_scores = 1 - poisson_probability(lambda_home, 0)
    p_away_scores = 1 - poisson_probability(lambda_away, 0)
    return p_home_scores * p_away_scores


def corner_probabilities(avg_corners_home: float, avg_corners_away: float,
                         line: float = 9.5) -> Dict:
    """Probabilidad de over/under en tiros de esquina."""
    return over_under_probabilities(avg_corners_home, avg_corners_away, line)
