import math
from typing import Dict, Tuple


def dixon_coles_tau(home_goals: int, away_goals: int,
                     lambda_home: float, lambda_away: float,
                     rho: float = 0.13) -> float:
    """
    Factor de corrección tau de Dixon-Coles para marcadores bajos.
    
    Corrige la independencia de Poisson para 0-0, 1-0, 0-1, 1-1.
    rho ~ 0.13 para fútbol (paper original).
    """
    if home_goals == 0 and away_goals == 0:
        return 1 - lambda_home * lambda_away * rho
    elif home_goals == 1 and away_goals == 0:
        return 1 + lambda_away * rho
    elif home_goals == 0 and away_goals == 1:
        return 1 + lambda_home * rho
    elif home_goals == 1 and away_goals == 1:
        return 1 - rho
    return 1.0


def dixon_coles_probability(lambda_home: float, lambda_away: float,
                             home_goals: int, away_goals: int,
                             rho: float = 0.13) -> float:
    """
    Probabilidad conjunta con corrección Dixon-Coles.
    
    P(H=h, A=a) = Poisson(h|λh) * Poisson(a|λa) * tau(h,a,λh,λa,ρ)
    """
    from analyzers.poisson import poisson_probability
    
    base_prob = poisson_probability(lambda_home, home_goals) * \
                poisson_probability(lambda_away, away_goals)
    tau = dixon_coles_tau(home_goals, away_goals, lambda_home, lambda_away, rho)
    return base_prob * tau


def predict_match_scores_dc(lambda_home: float, lambda_away: float,
                            max_goals: int = 8, rho: float = 0.13) -> Dict:
    """
    Matriz de probabilidades con Dixon-Coles.
    
    Devuelve dict con 'matrix', 'home_win', 'draw', 'away_win'.
    """
    matrix = {}
    home_win = 0.0
    draw = 0.0
    away_win = 0.0

    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            prob = dixon_coles_probability(lambda_home, lambda_away, h, a, rho)
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


def estimate_rho(historical_matches: list, lambda_home_avg: float,
                 lambda_away_avg: float) -> float:
    """
    Estima rho usando máxima verosimilitud en datos históricos.
    
    historical_matches: lista de dicts con 'home_goals', 'away_goals'
    """
    if not historical_matches:
        return 0.13
    
    def log_likelihood(rho_val: float) -> float:
        ll = 0.0
        for m in historical_matches:
            hg = m.get('home_goals', 0)
            ag = m.get('away_goals', 0)
            tau = dixon_coles_tau(hg, ag, lambda_home_avg, lambda_away_avg, rho_val)
            if tau > 0:
                ll += math.log(tau)
        return ll
    
    best_rho = 0.13
    best_ll = -float('inf')
    for rho_test in [i * 0.01 for i in range(0, 30)]:
        ll = log_likelihood(rho_test)
        if ll > best_ll:
            best_ll = ll
            best_rho = rho_test
    
    return best_rho


def time_decay_weight(match_date: str, xi: float = 0.0019) -> float:
    """
    Peso de decaimiento temporal (ξ = 0.0019 del paper original).
    
    match_date: formato ISO 'YYYY-MM-DD'
    """
    from datetime import date, datetime
    
    try:
        if isinstance(match_date, str):
            m_date = datetime.fromisoformat(match_date).date()
        else:
            m_date = match_date
        days_ago = (date.today() - m_date).days
        return math.exp(-xi * days_ago)
    except Exception:
        return 1.0


class DixonColesModel:
    """Wrapper class for Dixon-Coles model functions (for ML pipeline)."""
    
    @staticmethod
    def tau(home_goals: int, away_goals: int,
            lambda_home: float, lambda_away: float,
            rho: float = 0.13) -> float:
        return dixon_coles_tau(home_goals, away_goals, lambda_home, lambda_away, rho)
    
    @staticmethod
    def probability(lambda_home: float, lambda_away: float,
                    home_goals: int, away_goals: int,
                    rho: float = 0.13) -> float:
        return dixon_coles_probability(lambda_home, lambda_away, home_goals, away_goals, rho)
    
    @staticmethod
    def predict_match_scores(lambda_home: float, lambda_away: float,
                             max_goals: int = 8, rho: float = 0.13) -> Dict:
        return predict_match_scores_dc(lambda_home, lambda_away, max_goals, rho)
    
    @staticmethod
    def estimate_rho(historical_matches: list, lambda_home_avg: float,
                     lambda_away_avg: float) -> float:
        return estimate_rho(historical_matches, lambda_home_avg, lambda_away_avg)