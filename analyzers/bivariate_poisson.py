import math
from typing import Dict, Tuple


def bivariate_poisson_prob(h: int, a: int,
                            lambda1: float, lambda2: float, lambda3: float) -> float:
    """
    Probabilidad conjunta Bivariate Poisson.
    
    H ~ Poisson(lambda1 + lambda3)
    A ~ Poisson(lambda2 + lambda3)
    Cov(H,A) = lambda3
    
    Para BTTS y Clean Sheet, lambda3 captura la correlación de goles.
    """
    if h < 0 or a < 0:
        return 0.0
    
    total = 0.0
    max_k = min(h, a)
    
    for k in range(max_k + 1):
        term = (math.exp(-lambda1 - lambda2 - lambda3) *
                (lambda1 ** (h - k)) / math.factorial(h - k) *
                (lambda2 ** (a - k)) / math.factorial(a - k) *
                (lambda3 ** k) / math.factorial(k))
        total += term
    
    return total


def estimate_lambda3(historical_matches: list,
                      lambda1: float, lambda2: float) -> float:
    """
    Estima lambda3 (correlación) por máxima verosimilitud.
    
    lambda3 > 0: goles correlacionados (partidos abiertos)
    lambda3 < 0: goles anti-correlacionados (partidos cerrados)
    """
    if not historical_matches:
        return 0.0
    
    def log_likelihood(l3: float) -> float:
        ll = 0.0
        for m in historical_matches:
            hg = m.get('home_goals', 0)
            ag = m.get('away_goals', 0)
            prob = bivariate_poisson_prob(hg, ag, lambda1, lambda2, l3)
            if prob > 0:
                ll += math.log(prob)
        return ll
    
    best_l3 = 0.0
    best_ll = -float('inf')
    
    for l3_test in [i * 0.05 for i in range(-10, 21)]:
        ll = log_likelihood(l3_test)
        if ll > best_ll:
            best_ll = ll
            best_l3 = l3_test
    
    return max(0.0, best_l3)


def btts_probability_biv(lambda_home: float, lambda_away: float,
                          lambda3: float = 0.0) -> float:
    """
    P(BTTS=Yes) = 1 - P(H=0) - P(A=0) + P(H=0, A=0)
    
    Con Bivariate Poisson, P(H=0, A=0) = exp(-lambda1 - lambda2 - lambda3)
    """
    p_home_zero = math.exp(-lambda_home)
    p_away_zero = math.exp(-lambda_away)
    p_both_zero = math.exp(-lambda_home - lambda_away - lambda3)
    
    return 1.0 - p_home_zero - p_away_zero + p_both_zero


def clean_sheet_probability_biv(lambda_team: float, lambda_opp: float,
                                 lambda3: float = 0.0,
                                 team_is_home: bool = True) -> float:
    """
    Probabilidad de portería a cero para un equipo.
    
    P(opp scores 0) = exp(-lambda_opp) marginal,
    pero con bivariate: sum_h P(H=h, A=0)
    """
    if team_is_home:
        lambda1, lambda2 = lambda_team, lambda_opp
    else:
        lambda1, lambda2 = lambda_opp, lambda_team
    
    prob = 0.0
    for h in range(15):
        prob += bivariate_poisson_prob(h, 0, lambda1, lambda2, lambda3)
    
    return prob


def predict_match_scores_biv(lambda_home: float, lambda_away: float,
                              lambda3: float = 0.0,
                              max_goals: int = 8) -> Dict:
    """Matriz completa con Bivariate Poisson."""
    matrix = {}
    home_win = 0.0
    draw = 0.0
    away_win = 0.0

    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            prob = bivariate_poisson_prob(h, a, lambda_home, lambda_away, lambda3)
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


def over_under_biv(lambda_home: float, lambda_away: float,
                   lambda3: float, line: float = 2.5) -> Dict:
    """Over/Under con Bivariate Poisson."""
    over = 0.0
    max_goals = 12
    
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            if h + a > line:
                over += bivariate_poisson_prob(h, a, lambda_home, lambda_away, lambda3)
    
    return {"over": over, "under": 1.0 - over}


def correct_score_top5_biv(lambda_home: float, lambda_away: float,
                            lambda3: float = 0.0) -> list:
    """Top 5 marcadores más probables."""
    from analyzers.bivariate_poisson import bivariate_poisson_prob
    
    scores = []
    for h in range(6):
        for a in range(6):
            prob = bivariate_poisson_prob(h, a, lambda_home, lambda_away, lambda3)
            scores.append(((h, a), prob))
    
    scores.sort(key=lambda x: x[1], reverse=True)
    return [{"score": f"{s[0]}-{s[1]}", "probability": round(s[2], 4)} 
            for s in scores[:5]]


class BivariatePoissonModel:
    """Wrapper class for Bivariate Poisson model functions (for ML pipeline)."""
    
    @staticmethod
    def probability(h: int, a: int,
                    lambda1: float, lambda2: float, lambda3: float) -> float:
        return bivariate_poisson_prob(h, a, lambda1, lambda2, lambda3)
    
    @staticmethod
    def estimate_lambda3(historical_matches: list,
                         lambda1: float, lambda2: float) -> float:
        return estimate_lambda3(historical_matches, lambda1, lambda2)
    
    @staticmethod
    def btts_probability(lambda_home: float, lambda_away: float,
                         lambda3: float = 0.0) -> float:
        return btts_probability_biv(lambda_home, lambda_away, lambda3)
    
    @staticmethod
    def clean_sheet_probability(lambda_team: float, lambda_opp: float,
                                 lambda3: float = 0.0,
                                 team_is_home: bool = True) -> float:
        return clean_sheet_probability_biv(lambda_team, lambda_opp, lambda3, team_is_home)
    
    @staticmethod
    def predict_match_scores(lambda_home: float, lambda_away: float,
                             lambda3: float = 0.0,
                             max_goals: int = 8) -> Dict:
        return predict_match_scores_biv(lambda_home, lambda_away, lambda3, max_goals)
    
    @staticmethod
    def over_under(lambda_home: float, lambda_away: float,
                   lambda3: float, line: float = 2.5) -> Dict:
        return over_under_biv(lambda_home, lambda_away, lambda3, line)