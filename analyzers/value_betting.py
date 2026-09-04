from typing import Dict, List, Optional


def implied_probability(decimal_odds: float) -> float:
    """Convierte cuota decimal a probabilidad implícita."""
    if decimal_odds <= 1:
        return 0.0
    return 1.0 / decimal_odds


def value_edge(probability: float, decimal_odds: float) -> float:
    """Calcula el valor esperado de una apuesta.

    Valor = (probabilidad_calculada * cuota) - 1
    Si > 0, hay valor positivo.
    """
    expected_return = probability * decimal_odds
    return expected_return - 1.0


def detect_value(probabilities: Dict[str, float],
                 odds: Dict[str, float],
                 min_edge: float = 0.05) -> List[Dict]:
    """Detecta apuestas de valor comparando probabilidades calculadas vs cuotas.

    Args:
        probabilities: {'1', 'X', '2', 'over_2.5', 'btts_yes', ...}
        odds: {'1': 2.10, 'X': 3.40, '2': 3.20, 'over_2.5': 1.90, ...}
        min_edge: valor mínimo para considerar apuesta.

    Retorna lista de:
        {'market', 'probability', 'odds', 'edge', 'recommended'}
    """
    if not odds:
        return []

    results = []
    for market, prob in probabilities.items():
        market_key = _find_odds_key(market, odds)
        if market_key is None:
            continue

        curr_odds = odds[market_key]
        edge = value_edge(prob, curr_odds)
        imp = implied_probability(curr_odds)

        results.append({
            "market": market,
            "probability": prob,
            "odds": curr_odds,
            "implied": imp,
            "edge": edge,
            "recommended": edge >= min_edge,
        })

    results.sort(key=lambda r: r["edge"], reverse=True)
    return results


def _find_odds_key(market: str, odds: Dict[str, float]) -> Optional[str]:
    """Busca la clave de cuota que corresponde a un mercado calculado."""
    market_lower = market.lower()

    if market_lower == "1":
        return "1"
    if market_lower == "draw":
        return "X"
    if market_lower == "2":
        return "2"

    if market_lower.startswith("over"):
        line = market_lower.replace("over", "").strip()
        if f"over{line}" in odds:
            return f"over{line}"
        if f"o{line}" in odds:
            return f"o{line}"
        for key in odds:
            if key.lower().startswith("over") and line in key.lower():
                return key

    if market_lower.startswith("under"):
        line = market_lower.replace("under", "").strip()
        for key in odds:
            if key.lower().startswith("under") and line in key.lower():
                return key

    if market_lower == "btts_yes":
        for key in odds:
            if key.lower() in ("btts", "btts_yes", "btts si", "yes") or "btts" in key.lower():
                return key

    return None
