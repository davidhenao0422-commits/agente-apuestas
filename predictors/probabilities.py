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
    btts = btts_probability(lambda_home, lambda_away)

    # Calcular Over/Under para múltiples líneas
    def calc_ou(line):
        over = 0.0
        for h in range(13):
            for a in range(13):
                if h + a > line:
                    over += poisson_probability(lambda_home, h) * poisson_probability(lambda_away, a)
        return {"over": over, "under": 1.0 - over}

    ou_1_5 = calc_ou(1.5)
    ou_2_5 = calc_ou(2.5)
    ou_3_5 = calc_ou(3.5)

    home_clean_sheet = sum(
        poisson_probability(lambda_home, h) * poisson_probability(lambda_away, 0)
        for h in range(8)
    )
    away_clean_sheet = sum(
        poisson_probability(lambda_away, a) * poisson_probability(lambda_home, 0)
        for a in range(8)
    )

    # Doble Oportunidad
    double_chance_1x = scores["home_win"] + scores["draw"]
    double_chance_x2 = scores["draw"] + scores["away_win"]
    double_chance_12 = scores["home_win"] + scores["away_win"]

    # Over/Under adicionales
    over_1_5 = ou_1_5.get("over", 0)
    under_1_5 = ou_1_5.get("under", 0)
    over_2_5 = ou_2_5.get("over", 0)
    under_2_5 = ou_2_5.get("under", 0)
    over_3_5 = ou_3_5.get("over", 0)
    under_3_5 = ou_3_5.get("under", 0)

    return {
        "1": scores["home_win"],
        "draw": scores["draw"],
        "2": scores["away_win"],
        "over_1_5": over_1_5,
        "under_1_5": under_1_5,
        "over_2.5": over_2_5,
        "under_2.5": under_2_5,
        "over_3_5": over_3_5,
        "under_3_5": under_3_5,
        "btts_yes": btts,
        "double_chance_1x": double_chance_1x,
        "double_chance_x2": double_chance_x2,
        "double_chance_12": double_chance_12,
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
