from typing import Dict, List


def calculate_market_probabilities(lambda_home: float, lambda_away: float) -> Dict:
    """Calcula probabilidades para todos los mercados usando Poisson.

    Retorna dict con:
        '1', 'draw', '2'       -> resultado final
        'over_2.5', 'under_2.5'-> goles
        'btts_yes'             -> ambos equipos anotan
        'home_clean_sheet', 'away_clean_sheet'
    """
    from analyzers.poisson import (
        btts_probability,
        over_under_probabilities,
        poisson_probability,
        predict_match_scores,
    )

    scores = predict_match_scores(lambda_home, lambda_away)
    ou = over_under_probabilities(lambda_home, lambda_away)
    btts = btts_probability(lambda_home, lambda_away)

    home_clean_sheet = sum(
        poisson_probability(lambda_home, h) * poisson_probability(lambda_away, 0)
        for h in range(8)
    )
    away_clean_sheet = sum(
        poisson_probability(lambda_away, a) * poisson_probability(lambda_home, 0)
        for a in range(8)
    )

    return {
        "1": scores["home_win"],
        "draw": scores["draw"],
        "2": scores["away_win"],
        "over_2.5": ou["over"],
        "under_2.5": ou["under"],
        "btts_yes": btts,
        "home_clean_sheet": home_clean_sheet,
        "away_clean_sheet": away_clean_sheet,
    }


def normalize_probabilities(probs: Dict[str, float]) -> Dict[str, float]:
    """Normaliza las probabilidades del mercado 1X2 para que sumen 1."""
    total = probs.get("1", 0) + probs.get("draw", 0) + probs.get("2", 0)
    if total <= 0:
        return probs
    return {
        **probs,
        "1": probs.get("1", 0) / total,
        "draw": probs.get("draw", 0) / total,
        "2": probs.get("2", 0) / total,
    }


def adjust_for_market_odds(probs: Dict[str, float],
                           odds: Dict[str, float],
                           margin_weight: float = 0.05) -> Dict[str, float]:
    """Ajusta ligeramente las probabilidades hacia las implícitas si hay cuotas."""

    if not odds:
        return probs

    from analyzers.value_betting import implied_probability

    adjusted = dict(probs)
    mapping = {"1": "1", "draw": "X", "2": "2"}

    for calc_key, odds_key in mapping.items():
        if odds_key in odds and calc_key in adjusted:
            imp = implied_probability(odds[odds_key])
            adjusted[calc_key] = (1 - margin_weight) * adjusted[calc_key] \
                + margin_weight * imp

    return normalize_probabilities(adjusted)
