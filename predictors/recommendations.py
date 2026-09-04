from typing import Dict, List, Optional

from config import Config


def build_recommendations(probabilities: Dict[str, float],
                          odds: Optional[Dict[str, float]] = None,
                          min_confidence: Optional[float] = None) -> List[Dict]:
    """Genera recomendaciones basadas en probabilidades y cuotas.

    Argumentos:
        probabilities: Probabilidades calculadas por mercado.
        odds: Cuotas del mercado (opcional).
        min_confidence: Umbral mínimo de confianza (sobreescribe Config).

    Retorna lista de dicts:
        {'market', 'choice', 'probability', 'confidence', 'recommended', 'odds', 'edge'}
    """
    mins = min_confidence or Config.MIN_CONFIDENCE
    min_edge = Config.MIN_VALUE_EDGE

    recommendations = []

    # Mapeo de mercados principales
    market_rules = [
        {
            "name": "1X2 - Local (1)",
            "key": "1",
            "choice": "1",
            "pick_text": "Gana Local (1)",
        },
        {
            "name": "1X2 - Empate (X)",
            "key": "draw",
            "choice": "X",
            "pick_text": "Empate (X)",
        },
        {
            "name": "1X2 - Visitante (2)",
            "key": "2",
            "choice": "2",
            "pick_text": "Gana Visitante (2)",
        },
        {
            "name": "Doble Oportunidad 1X",
            "key": "double_chance_1x",
            "choice": "1X",
            "pick_text": "Gana Local o Empate (1X)",
        },
        {
            "name": "Doble Oportunidad X2",
            "key": "double_chance_x2",
            "choice": "X2",
            "pick_text": "Empate o Gana Visitante (X2)",
        },
        {
            "name": "Doble Oportunidad 12",
            "key": "double_chance_12",
            "choice": "12",
            "pick_text": "Gana Local o Visitante (12)",
        },
        {
            "name": "Over 1.5",
            "key": "over_1_5",
            "choice": "Over 1.5",
            "pick_text": "Más de 1.5 goles",
        },
        {
            "name": "Over 2.5",
            "key": "over_2.5",
            "choice": "Over 2.5",
            "pick_text": "Más de 2.5 goles",
        },
        {
            "name": "Over 3.5",
            "key": "over_3_5",
            "choice": "Over 3.5",
            "pick_text": "Más de 3.5 goles",
        },
        {
            "name": "Under 1.5",
            "key": "under_1_5",
            "choice": "Under 1.5",
            "pick_text": "Menos de 1.5 goles",
        },
        {
            "name": "Under 2.5",
            "key": "under_2.5",
            "choice": "Under 2.5",
            "pick_text": "Menos de 2.5 goles",
        },
        {
            "name": "Under 3.5",
            "key": "under_3_5",
            "choice": "Under 3.5",
            "pick_text": "Menos de 3.5 goles",
        },
        {
            "name": "BTTS Sí",
            "key": "btts_yes",
            "choice": "BTTS Sí",
            "pick_text": "Ambos equipos anotan",
        },
        {
            "name": "Portería a cero Local",
            "key": "home_clean_sheet",
            "choice": "CS Local",
            "pick_text": "Local no recibe goles",
        },
        {
            "name": "Portería a cero Visitante",
            "key": "away_clean_sheet",
            "choice": "CS Visitante",
            "pick_text": "Visitante no recibe goles",
        },
    ]

    for rule in market_rules:
        prob = probabilities.get(rule["key"])
        if prob is None:
            continue

        item = {
            "market": rule["name"],
            "choice": rule["choice"],
            "pick_text": rule["pick_text"],
            "probability": round(prob, 3),
            "confidence": _confidence_label(prob),
            "recommended": prob >= mins,
            "odds": None,
            "edge": None,
        }

        # If user provided odds, enrich with value detection
        if odds:
            from analyzers.value_betting import value_edge

            odds_key = _find_odds_key_for_rule(rule["key"], odds)
            if odds_key:
                item["odds"] = odds[odds_key]
                item["edge"] = round(value_edge(prob, odds[odds_key]), 3)
                # Sólo recomendar si además hay valor positivo
                if item["edge"] is not None:
                    item["recommended"] = item["recommended"] and \
                        item["edge"] >= min_edge

        recommendations.append(item)

    # Ordenar por probabilidad descendente
    recommendations.sort(key=lambda r: r["probability"], reverse=True)
    return recommendations


def _confidence_label(prob: float) -> str:
    if prob >= 0.70:
        return "ALTA"
    if prob >= 0.60:
        return "MEDIA"
    return "BAJA"


def _find_odds_key_for_rule(rule_key: str, odds: Dict[str, float]) -> Optional[str]:
    mapping = {"1": "1", "draw": "X", "2": "2"}
    if rule_key in mapping:
        return mapping[rule_key] if mapping[rule_key] in odds else None

    if rule_key.startswith("over"):
        line = rule_key.replace("over_", "").replace(".", "")
        for key in odds:
            if key.lower().startswith("over") or key.lower() == f"o{line}":
                return key

    if rule_key.startswith("under"):
        line = rule_key.replace("under_", "").replace(".", "")
        for key in odds:
            if key.lower().startswith("under") or key.lower() == f"u{line}":
                return key

    if rule_key == "btts_yes":
        for key in odds:
            if "btts" in key.lower() or key.lower() in ("yes", "btts_si"):
                return key

    return None
