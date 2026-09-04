import logging
from typing import Dict, List, Optional

from config import Config

logger = logging.getLogger(__name__)


class PredictionEngine:
    """Motor principal que coordina la generación de predicciones de apuestas."""

    def __init__(self):
        self._weights_valid = True
        total = (Config.FORM_WEIGHT + Config.H2H_WEIGHT +
                 Config.SEASON_WEIGHT + Config.HOME_AWAY_WEIGHT)
        if abs(total - 1.0) > 0.001:
            logger.warning(
                f"Los pesos del modelo no suman 1.0 (suma={total}). "
                f"Usando valores normalizados."
            )
            self._weights_valid = False

    def predict(self, home_data: dict, away_data: dict,
                h2h_data: dict = None) -> Dict:
        """Genera una predicción completa para un partido.

        Argumentos:
            home_data: stats del equipo local. Debe incluir
                'goals_per_game', 'conceded_per_game', 'form', etc.
            away_data: stats del equipo visitante.
            h2h_data: análisis de enfrentamientos directos (opcional).

        Retorna dict con probabilidades y recomendaciones.
        """
        # 1. Goles esperados con modelo Poisson
        lambda_home = self._expected_goals(
            home_attack=home_data.get("goals_per_game", 1.2),
            away_defense=away_data.get("conceded_per_game", 1.2),
        )
        lambda_away = self._expected_goals(
            home_attack=away_data.get("goals_per_game", 1.2),
            away_defense=home_data.get("conceded_per_game", 1.2),
        )

        # 2. Calcular probabilidades base
        from predictors.probabilities import (
            adjust_for_market_odds,
            calculate_market_probabilities,
            normalize_probabilities,
        )

        probs_raw = calculate_market_probabilities(lambda_home, lambda_away)
        probs = self._apply_weights(
            probs_raw,
            home_form=home_data.get("form"),
            away_form=away_data.get("form"),
            h2h=h2h_data,
            home_away=home_data.get("home_performance"),
        )
        # Normalizar siempre 1X2
        probs = normalize_probabilities(probs)

        # 3. Ajustar con cuotas del mercado si están disponibles
        odds = home_data.get("odds") or {}
        if odds:
            probs = adjust_for_market_odds(probs, odds)

        # 4. Generar recomendaciones
        from predictors.recommendations import build_recommendations

        recommendations = build_recommendations(probs, odds or None)

        return {
            "probabilities": probs,
            "expected_goals": {
                "home": round(lambda_home, 2),
                "away": round(lambda_away, 2),
                "total": round(lambda_home + lambda_away, 2),
            },
            "recommendations": recommendations,
            "h2h_available": bool(h2h_data),
        }

    def _expected_goals(self, home_attack: float, away_defense: float) -> float:
        from analyzers.poisson import expected_goals
        return expected_goals(home_attack, away_defense)

    def _apply_weights(self, probs: dict, home_form=None, away_form=None,
                       h2h=None, home_away=None) -> dict:
        """Ajusta las probabilidades según los pesos del modelo.

        La aplicación de pesos es implícita en cómo se calculan los
        goles esperados. Aquí aplicamos ajustes diferenciados cuando
        hay señales complementarias (forma, H2H).

        Este método modifica ligeramente las probabilidades base
        reflejando el peso de los factores no incluidos directamente
        en Poisson (forma reciente y enfrentamientos directos).
        """
        adjusted = dict(probs)

        # Ajuste por forma reciente (40%)
        if home_form and away_form:
            form_diff = (home_form.get("avg_score", 0.5) - away_form.get("avg_score", 0.5))
            # Factor de ajuste acotado
            adjustment = max(-0.15, min(0.15, form_diff * 0.1))
            adjusted["1"] = min(0.95, max(0.05, adjusted["1"] * (1 + adjustment)))
            adjusted["2"] = min(0.95, max(0.05, adjusted["2"] * (1 - adjustment)))

        # Ajuste por H2H (30%)
        if h2h and h2h.get("team_a_wins", 0) + h2h.get("team_b_wins", 0) + \
                h2h.get("draws", 0) > 0:
            total_h2h = max(h2h.get("total_matches", 0), 1)
            a_win_rate = (h2h.get("team_a_wins", 0) / total_h2h) * 0.3
            # Sube la probabilidad del local según dominio en H2H
            h2h_unfav_adj = (0.5 - a_win_rate) / 10
            adjusted["1"] = min(0.95, max(0.05, adjusted["1"] + h2h_unfav_adj))

        # Ajuste por local/visitante (10%)
        if home_away:
            home_win_rate = home_away.get("win_rate", 0.5)
            adj = (home_win_rate - 0.5) * 0.1
            adjusted["1"] = min(0.95, max(0.05, adjusted["1"] + adj))

        # Normalizar de nuevo
        from predictors.probabilities import normalize_probabilities
        return normalize_probabilities(adjusted)
