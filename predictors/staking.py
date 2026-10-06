import math
import random
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class KellyResult:
    fraction: float
    stake_units: float
    stake_currency: float
    edge: float
    prob: float
    odds: float


@dataclass
class MonteCarloResult:
    paths: List[List[float]]
    median_growth: float
    mean_growth: float
    pct_profitable: float
    max_drawdown_median: float
    max_drawdown_p95: float
    risk_of_ruin: float
    final_bankroll_p10: float
    final_bankroll_p50: float
    final_bankroll_p90: float


def kelly_fraction(prob: float, odds: float) -> float:
    """
    Fracción de Kelly: f* = (bp - q) / b
    b = odds - 1 (net odds)
    p = prob (true probability)
    q = 1 - p
    """
    if prob <= 0 or odds <= 1:
        return 0.0
    
    b = odds - 1
    p = prob
    q = 1 - p
    
    f = (b * p - q) / b
    return max(0.0, f)


def half_kelly_fraction(prob: float, odds: float) -> float:
    return kelly_fraction(prob, odds) * 0.5


def quarter_kelly_fraction(prob: float, odds: float) -> float:
    return kelly_fraction(prob, odds) * 0.25


def kelly_stake(prob: float, odds: float, bankroll: float, 
                kelly_mult: float = 0.5, max_bet_pct: float = 0.05) -> KellyResult:
    """
    Calcula stake recomendado con Kelly fraccionado.
    
    Args:
        prob: Probabilidad estimada (0-1)
        odds: Cuota decimal
        bankroll: Bankroll total
        kelly_mult: Multiplicador (0.5 = Half-Kelly, 0.25 = Quarter)
        max_bet_pct: Cap máximo como % del bankroll
    """
    f = kelly_fraction(prob, odds) * kelly_mult
    f = min(f, max_bet_pct)
    
    stake_units = f * bankroll
    edge = prob * odds - 1
    
    return KellyResult(
        fraction=f,
        stake_units=stake_units,
        stake_currency=stake_units,
        edge=edge,
        prob=prob,
        odds=odds,
    )


def clv(opening_odds: float, closing_odds: float) -> float:
    """
    Closing Line Value: (closing / opening) - 1
    Positivo = beat the closing line (edge)
    """
    if opening_odds <= 0:
        return 0.0
    return (closing_odds / opening_odds) - 1


def simulate_growth(win_prob: float, odds: float, 
                    num_bets: int = 500,
                    kelly_mult: float = 0.5,
                    num_paths: int = 2000,
                    starting_bankroll: float = 100.0) -> MonteCarloResult:
    """
    Simulación Monte Carlo de crecimiento de bankroll bajo Kelly.
    
    Retorna distribución completa de resultados.
    """
    f = kelly_fraction(win_prob, odds) * kelly_mult
    f = max(0.0, min(f, 0.1))
    
    paths = []
    
    for _ in range(num_paths):
        bankroll = starting_bankroll
        path = [bankroll]
        peak = bankroll
        max_dd = 0.0
        
        for _ in range(num_bets):
            if random.random() < win_prob:
                bankroll *= (1 + f * (odds - 1))
            else:
                bankroll *= (1 - f)
            
            path.append(bankroll)
            peak = max(peak, bankroll)
            dd = (peak - bankroll) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        paths.append(path)
    
    final_bankrolls = [p[-1] for p in paths]
    final_bankrolls.sort()
    
    profitable = sum(1 for b in final_bankrolls if b > starting_bankroll)
    ruin = sum(1 for b in final_bankrolls if b < starting_bankroll * 0.5)
    
    all_drawdowns = []
    for path in paths:
        peak = path[0]
        for val in path:
            peak = max(peak, val)
            dd = (peak - val) / peak if peak > 0 else 0
            all_drawdowns.append(dd)
    
    all_drawdowns.sort()
    
    return MonteCarloResult(
        paths=paths[:100],
        median_growth=final_bankrolls[len(final_bankrolls)//2] / starting_bankroll,
        mean_growth=sum(final_bankrolls) / len(final_bankrolls) / starting_bankroll,
        pct_profitable=profitable / num_paths,
        max_drawdown_median=all_drawdowns[len(all_drawdowns)//2],
        max_drawdown_p95=all_drawdowns[int(len(all_drawdowns)*0.95)],
        risk_of_ruin=ruin / num_paths,
        final_bankroll_p10=final_bankrolls[int(len(final_bankrolls)*0.1)],
        final_bankroll_p50=final_bankrolls[len(final_bankrolls)//2],
        final_bankroll_p90=final_bankrolls[int(len(final_bankrolls)*0.9)],
    )


def optimal_kelly_mult(win_prob: float, odds: float,
                       risk_tolerance: str = "moderate") -> float:
    """
    Recomienda multiplicador de Kelly según tolerancia al riesgo.
    
    Conservative: Quarter Kelly (0.25)
    Moderate: Half Kelly (0.5)
    Aggressive: 0.75 Kelly
    """
    edge = win_prob * odds - 1
    if edge <= 0:
        return 0.0
    
    variance = win_prob * (1 - win_prob)
    
    if risk_tolerance == "conservative":
        return 0.25
    elif risk_tolerance == "moderate":
        return 0.5
    elif risk_tolerance == "aggressive":
        return 0.75
    return 0.5


def portfolio_kelly(bets: List[Dict], bankroll: float,
                    correlation_matrix: List[List[float]] = None,
                    kelly_mult: float = 0.5) -> Dict:
    """
    Kelly para portafolio de apuestas simultáneas.
    
    bets: [{'prob': p, 'odds': o, 'max_stake_pct': 0.05}, ...]
    correlation_matrix: matriz de correlación entre apuestas (opcional)
    
    Usa optimización numérica para maximizar log growth con constraints.
    """
    from scipy.optimize import minimize
    import numpy as np
    
    n = len(bets)
    if n == 0:
        return {"stakes": [], "total_stake_pct": 0}
    
    probs = np.array([b['prob'] for b in bets])
    odds = np.array([b['odds'] for b in bets])
    max_stakes = np.array([b.get('max_stake_pct', 0.05) for b in bets])
    
    def neg_log_growth(fractions):
        if np.any(fractions < 0) or np.any(fractions > max_stakes):
            return 1e10
        
        growth = 0
        for i in range(n):
            f = fractions[i]
            p = probs[i]
            o = odds[i]
            growth += p * math.log(1 + f * (o - 1)) + (1 - p) * math.log(1 - f)
        
        if correlation_matrix is not None:
            corr = np.array(correlation_matrix)
            portfolio_var = fractions @ corr @ fractions
            growth -= 0.5 * portfolio_var
        
        return -growth
    
    x0 = np.full(n, 0.01)
    bounds = [(0, max_stakes[i]) for i in range(n)]
    
    result = minimize(neg_log_growth, x0, bounds=bounds, method='L-BFGS-B')
    
    optimal_fractions = result.x * kelly_mult
    stakes = [f * bankroll for f in optimal_fractions]
    
    return {
        "fractions": optimal_fractions.tolist(),
        "stakes": stakes,
        "total_stake_pct": sum(optimal_fractions),
        "expected_log_growth": -result.fun,
        "success": result.success,
    }


def kelly_criterion_bankroll(history: List[Dict], 
                              kelly_mult: float = 0.5) -> Dict:
    """
    Analiza historial de apuestas y sugiere Kelly óptimo retrospectivamente.
    
    history: [{'prob': p, 'odds': o, 'result': 1/0, 'stake': s}, ...]
    """
    if not history:
        return {"recommended_kelly_mult": 0.5}
    
    profits = []
    for bet in history:
        p = bet['prob']
        o = bet['odds']
        r = bet['result']
        s = bet.get('stake', 1)
        
        if r == 1:
            profits.append(s * (o - 1))
        else:
            profits.append(-s)
    
    total_profit = sum(profits)
    total_staked = sum(bet.get('stake', 1) for bet in history)
    roi = total_profit / total_staked if total_staked > 0 else 0
    
    win_rate = sum(bet['result'] for bet in history) / len(history)
    avg_odds = sum(bet['odds'] for bet in history) / len(history)
    avg_prob = sum(bet['prob'] for bet in history) / len(history)
    
    edge = avg_prob * avg_odds - 1
    
    return {
        "total_bets": len(history),
        "win_rate": win_rate,
        "avg_odds": avg_odds,
        "avg_model_prob": avg_prob,
        "edge": edge,
        "roi": roi,
        "total_profit": total_profit,
        "recommended_kelly_mult": min(0.5, max(0.1, edge * 2)) if edge > 0 else 0.1,
    }


def bankroll_management_rules(bankroll: float) -> Dict:
    """Reglas de gestión de bankroll."""
    return {
        "bankroll": bankroll,
        "unit_size": round(bankroll * 0.01, 2),
        "max_bet_per_game": round(bankroll * 0.05, 2),
        "max_daily_exposure": round(bankroll * 0.15, 2),
        "max_weekly_exposure": round(bankroll * 0.30, 2),
        "max_sport_exposure": round(bankroll * 0.20, 2),
        "stop_loss_daily": round(bankroll * 0.05, 2),
        "stop_loss_weekly": round(bankroll * 0.10, 2),
        "recommended_kelly": "half_kelly (0.5)",
        "rebalancing": "weekly",
    }


def expected_value(prob: float, odds: float) -> float:
    """EV = prob * odds - 1"""
    return prob * odds - 1


def probability_from_odds(odds: float) -> float:
    """Probabilidad implícita sin vig: 1 / odds"""
    if odds <= 0:
        return 0
    return 1 / odds


def remove_vig(odds_home: float, odds_draw: float, odds_away: float) -> Dict:
    """Elimina overround usando método proporcional (Shin's method aproximado)."""
    implied = {
        "1": 1 / odds_home,
        "draw": 1 / odds_draw,
        "2": 1 / odds_away,
    }
    total = sum(implied.values())
    fair = {k: v / total for k, v in implied.items()}
    return fair


def odds_with_margin(fair_probs: Dict, margin: float = 0.05) -> Dict:
    """Aplica margen de bookmaker a probabilidades justas."""
    return {k: 1 / (v * (1 + margin)) for k, v in fair_probs.items()}