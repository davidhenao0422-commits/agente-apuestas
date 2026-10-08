import math
from typing import Dict, List


def skellam_probability(k: int, lambda1: float, lambda2: float) -> float:
    """
    Distribución Skellam: diferencia de dos Poisson independientes.
    
    P(X - Y = k) donde X ~ Pois(lambda1), Y ~ Pois(lambda2)
    
    Usa la función de Bessel modificada de primera especie I_k(2*sqrt(λ1*λ2))
    """
    if lambda1 <= 0 or lambda2 <= 0:
        return 0.0
    
    sqrt_prod = math.sqrt(lambda1 * lambda2)
    ratio = math.sqrt(lambda1 / lambda2)
    
    try:
        from scipy.special import iv
        bessel = iv(abs(k), 2 * sqrt_prod)
    except ImportError:
        bessel = _bessel_i_approx(abs(k), 2 * sqrt_prod)
    
    prob = math.exp(-lambda1 - lambda2) * (ratio ** k) * bessel
    return prob


def _bessel_i_approx(nu: int, x: float) -> float:
    """Aproximación de Bessel I para cuando no está scipy."""
    if x == 0:
        return 1.0 if nu == 0 else 0.0
    
    # Series expansion
    sum_val = 0.0
    term = 1.0
    for k in range(0, 50):
        if k > 0:
            term *= (x * x) / (4 * k * (k + nu))
        sum_val += term / math.factorial(k + nu)
    
    return (x / 2) ** nu * sum_val


def skellam_cdf(k: int, lambda1: float, lambda2: float) -> float:
    """CDF: P(X - Y <= k)"""
    total = 0.0
    for i in range(-20, k + 1):
        total += skellam_probability(i, lambda1, lambda2)
    return total


def asian_handicap_probabilities(lambda_home: float, lambda_away: float,
                                  handicap: float) -> Dict:
    """
    Probabilidades para Asian Handicap.
    
    handicap: línea en goles (ej: -0.5, -1.0, -1.5, 0.0, +0.5, etc.)
    Positive = home team starts with advantage
    """
    if handicap == 0:
        home_win = 1 - skellam_cdf(0, lambda_home, lambda_away)
        draw = skellam_probability(0, lambda_home, lambda_away)
        away_win = skellam_cdf(-1, lambda_home, lambda_away)
        return {"home": home_win, "draw": draw, "away": away_win}
    
    if handicap > 0:
        # Home team receives goals
        adj_line = int(handicap) if handicap == int(handicap) else handicap
        if handicap == int(handicap):
            # Integer handicap: push possible
            home_win = 1 - skellam_cdf(-int(handicap) - 1, lambda_home, lambda_away)
            push = skellam_probability(-int(handicap), lambda_home, lambda_away)
            away_win = skellam_cdf(-int(handicap) - 1, lambda_home, lambda_away)
            return {"home": home_win, "push": push, "away": away_win}
        else:
            # Half handicap: no push
            line_int = int(handicap - 0.5)
            home_win = 1 - skellam_cdf(line_int, lambda_home, lambda_away)
            away_win = skellam_cdf(line_int, lambda_home, lambda_away)
            return {"home": home_win, "away": away_win}
    else:
        # Away team receives goals (handicap negative)
        handicap = abs(handicap)
        if handicap == int(handicap):
            away_win = 1 - skellam_cdf(-int(handicap) - 1, lambda_away, lambda_home)
            push = skellam_probability(-int(handicap), lambda_away, lambda_home)
            home_win = skellam_cdf(-int(handicap) - 1, lambda_away, lambda_home)
            return {"home": home_win, "push": push, "away": away_win}
        else:
            line_int = int(handicap - 0.5)
            away_win = 1 - skellam_cdf(line_int, lambda_away, lambda_home)
            home_win = skellam_cdf(line_int, lambda_away, lambda_home)
            return {"home": home_win, "away": away_win}


def goal_difference_distribution(lambda_home: float, lambda_away: float,
                                  max_diff: int = 6) -> Dict:
    """Distribución completa de diferencia de goles."""
    dist = {}
    for k in range(-max_diff, max_diff + 1):
        dist[k] = skellam_probability(k, lambda_home, lambda_away)
    return dist


def exact_handicap_lines(lambda_home: float, lambda_away: float) -> List[Dict]:
    """Todas las líneas de handicap estándar con probabilidades."""
    lines = [-2.5, -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
    results = []
    
    for line in lines:
        probs = asian_handicap_probabilities(lambda_home, lambda_away, line)
        results.append({
            "line": line,
            "home_win_prob": probs.get("home", 0),
            "away_win_prob": probs.get("away", 0),
            "push_prob": probs.get("push", 0),
            "fair_odds_home": 1 / probs.get("home", 1) if probs.get("home", 0) > 0 else None,
            "fair_odds_away": 1 / probs.get("away", 1) if probs.get("away", 0) > 0 else None,
        })
    
    return results


class SkellamModel:
    """Wrapper class for Skellam model functions (for ML pipeline)."""
    
    @staticmethod
    def probability(k: int, lambda1: float, lambda2: float) -> float:
        return skellam_probability(k, lambda1, lambda2)
    
    @staticmethod
    def cdf(k: int, lambda1: float, lambda2: float) -> float:
        return skellam_cdf(k, lambda1, lambda2)
    
    @staticmethod
    def asian_handicap(lambda_home: float, lambda_away: float,
                       handicap: float) -> Dict:
        return asian_handicap_probabilities(lambda_home, lambda_away, handicap)
    
    @staticmethod
    def goal_difference_distribution(lambda_home: float, lambda_away: float,
                                      max_diff: int = 6) -> Dict:
        return goal_difference_distribution(lambda_home, lambda_away, max_diff)
    
    @staticmethod
    def exact_handicap_lines(lambda_home: float, lambda_away: float) -> List[Dict]:
        return exact_handicap_lines(lambda_home, lambda_away)