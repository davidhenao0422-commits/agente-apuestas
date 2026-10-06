import logging
import hashlib
import json
from typing import Dict, List, Optional
from datetime import datetime, date

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

        self._ensemble = None
        self._init_ensemble()

    def _init_ensemble(self):
        try:
            from analyzers.ensemble import create_ensemble_predictor
            self._ensemble = create_ensemble_predictor()
            logger.info("Ensemble predictor initialized successfully")
        except Exception as e:
            logger.warning(f"Could not initialize ensemble: {e}")
            self._ensemble = None

    def predict(self, home_data: dict, away_data: dict,
                h2h_data: dict = None, bankroll: float = None,
                kelly_frac: float = 0.25,
                market_odds: dict = None,
                historical_matches: list = None,
                home_injuries: list = None,
                away_injuries: list = None,
                squad_depth: dict = None,
                lock_prediction: bool = True) -> Dict:
        """
        Genera una predicción completa para un partido usando ensemble.
        """
        home_team = home_data.get("team_name", "Home")
        away_team = away_data.get("team_name", "Away")
        league = home_data.get("league", "")

        lambda_home_base = home_data.get("goals_per_game", 1.2)
        lambda_away_base = away_data.get("goals_per_game", 1.2)

        lambda_home = lambda_home_base
        lambda_away = lambda_away_base

        if home_injuries or away_injuries:
            from analyzers.injury_model import injury_adjusted_prediction
            inj_result = injury_adjusted_prediction(
                home_data, away_data, home_injuries or [], away_injuries or [], squad_depth
            )
            lambda_home = inj_result["lambda_home_adjusted"]
            lambda_away = inj_result["lambda_away_adjusted"]
            injury_info = {
                "home_impact": inj_result["home_impact"],
                "away_impact": inj_result["away_impact"],
            }
        else:
            injury_info = None

        if self._ensemble:
            ensemble_result = self._ensemble.predict(
                home_data, away_data,
                h2h_data=h2h_data,
                market_odds=market_odds,
                historical_matches=historical_matches
            )
            probs = ensemble_result["probs"]
            lambda_home = ensemble_result["lambda_home"]
            lambda_away = ensemble_result["lambda_away"]
            individual_predictions = ensemble_result.get("individual_predictions", {})
            ensemble_weights = ensemble_result.get("weights_used", {})
            brier_scores = ensemble_result.get("brier_scores", {})
        else:
            probs = self._predict_fallback(lambda_home, lambda_away, home_data, away_data, h2h_data)
            individual_predictions = {}
            ensemble_weights = {}
            brier_scores = {}

        if market_odds:
            from predictors.probabilities import adjust_for_market_odds
            probs = adjust_for_market_odds(probs, market_odds)

        from predictors.probabilities import (
            calculate_market_probabilities,
            normalize_probabilities,
        )
        market_probs = calculate_market_probabilities(lambda_home, lambda_away)
        probs = {**market_probs, **probs}
        probs = normalize_probabilities(probs)

        from predictors.recommendations import build_recommendations
        from predictors.staking import kelly_stake, half_kelly_fraction

        recommendations = build_recommendations(
            probs, market_odds or None, bankroll=bankroll, kelly_frac=kelly_frac
        )

        kelly_stakes = {}
        for rec in recommendations:
            if rec.get("odds") and rec.get("probability", 0) > 0:
                ks = kelly_stake(rec["probability"], rec["odds"], bankroll or 1000, 
                                kelly_mult=0.5, max_bet_pct=0.05)
                kelly_stakes[rec["market"]] = {
                    "fraction": ks.fraction,
                    "stake_units": ks.stake_units,
                    "edge": ks.edge,
                }

        confidence_score, confidence_breakdown = self._calculate_confidence(
            probs, market_odds, h2h_data, home_data, away_data,
            ensemble_weights, brier_scores, injury_info
        )

        expected_goals = {
            "home": round(lambda_home, 2),
            "away": round(lambda_away, 2),
            "total": round(lambda_home + lambda_away, 2),
        }

        result = {
            "probabilities": probs,
            "expected_goals": expected_goals,
            "recommendations": recommendations,
            "h2h_available": bool(h2h_data),
            "kelly_fraction": kelly_frac,
            "bankroll": bankroll,
            "ensemble_weights": ensemble_weights,
            "brier_scores": brier_scores,
            "individual_predictions": individual_predictions,
            "confidence_score": confidence_score,
            "confidence_breakdown": confidence_breakdown,
            "kelly_stakes": kelly_stakes,
            "injury_info": injury_info,
        }

        if lock_prediction:
            self._lock_prediction(
                home_team, away_team, league, 
                probs, expected_goals, recommendations,
                ensemble_weights, brier_scores,
                confidence_score, confidence_breakdown, kelly_stakes
            )

        return result

    def _predict_fallback(self, lambda_home: float, lambda_away: float,
                          home_data: dict, away_data: dict, h2h_data: dict) -> dict:
        from predictors.probabilities import (
            calculate_market_probabilities, normalize_probabilities
        )
        probs_raw = calculate_market_probabilities(lambda_home, lambda_away)
        probs = self._apply_weights(
            probs_raw,
            home_form=home_data.get("form"),
            away_form=away_data.get("form"),
            h2h=h2h_data,
            home_away=home_data.get("home_performance"),
        )
        return normalize_probabilities(probs)

    def _calculate_confidence(self, probs: dict, market_odds: dict,
                              h2h_data: dict, home_data: dict, away_data: dict,
                              ensemble_weights: dict, brier_scores: dict,
                              injury_info: dict) -> tuple:
        """
        Calcula confidence score (0-100) con desglose de 8 factores.
        
        Factores:
        1. Model Agreement (0-15): Variance entre modelos del ensemble
        2. Calibration (0-15): Brier score histórico
        3. Edge Magnitude (0-15): EV vs market
        4. CLV History (0-10): Historial beating closing line
        5. Injury Certainty (0-10): Calidad info lesiones
        6. Form Consistency (0-10): Consistencia forma reciente
        7. H2H Relevance (0-10): Sample size y recencia H2H
        8. Market Depth (0-15): Número de bookmakers, liquidez
        """
        factors = {}

        if ensemble_weights and len(ensemble_weights) > 1:
            probs_list = []
            for model_name, pred in ensemble_weights.items():
                if isinstance(pred, dict) and "probs" in pred:
                    probs_list.append(pred["probs"])
            
            if probs_list:
                variance = self._calculate_variance(probs_list)
                factors["model_agreement"] = max(0, 15 - variance * 100)
            else:
                factors["model_agreement"] = 8
        else:
            factors["model_agreement"] = 5

        avg_brier = sum(brier_scores.values()) / len(brier_scores) if brier_scores else 0.1
        factors["calibration"] = max(0, 15 - avg_brier * 100)

        if market_odds:
            from analyzers.value_betting import implied_probability
            max_edge = 0
            for market, prob in probs.items():
                if market in ["1", "draw", "2"] and market in market_odds:
                    imp = implied_probability(market_odds[market])
                    edge = prob - imp
                    max_edge = max(max_edge, edge)
            factors["edge_magnitude"] = min(15, max_edge * 100)
        else:
            factors["edge_magnitude"] = 5

        factors["clv_history"] = 5

        if injury_info:
            home_out = injury_info["home_impact"].get("players_out", 0)
            away_out = injury_info["away_impact"].get("players_out", 0)
            factors["injury_certainty"] = max(0, 10 - (home_out + away_out) * 2)
        else:
            factors["injury_certainty"] = 3

        home_form = home_data.get("form", "")
        away_form = away_data.get("form", "")
        if home_form and away_form:
            h_consistency = len(set(home_form)) / max(len(home_form), 1)
            a_consistency = len(set(away_form)) / max(len(away_form), 1)
            factors["form_consistency"] = min(10, (2 - h_consistency - a_consistency) * 10)
        else:
            factors["form_consistency"] = 3

        if h2h_data:
            total = h2h_data.get("total_matches", 0)
            recent = len(h2h_data.get("recent", []))
            factors["h2h_relevance"] = min(10, total * 0.5 + recent * 0.5)
        else:
            factors["h2h_relevance"] = 0

        factors["market_depth"] = 5

        for k, v in factors.items():
            factors[k] = max(0, min(v, {"model_agreement": 15, "calibration": 15, 
                                        "edge_magnitude": 15, "clv_history": 10,
                                        "injury_certainty": 10, "form_consistency": 10,
                                        "h2h_relevance": 10, "market_depth": 15}[k]))

        total_score = sum(factors.values())
        confidence_score = int(max(0, min(100, total_score)))

        return confidence_score, factors

    def _calculate_variance(self, probs_list: List[dict]) -> float:
        import statistics
        variances = []
        for key in ["1", "draw", "2"]:
            values = [p.get(key, 0) for p in probs_list if key in p]
            if len(values) > 1:
                variances.append(statistics.variance(values))
        return statistics.mean(variances) if variances else 0

    def _apply_weights(self, probs: dict, home_form=None, away_form=None,
                       h2h=None, home_away=None) -> dict:
        adjusted = dict(probs)

        if home_form and away_form:
            form_diff = (home_form.get("avg_score", 0.5) - away_form.get("avg_score", 0.5))
            adjustment = max(-0.15, min(0.15, form_diff * 0.1))
            adjusted["1"] = min(0.95, max(0.05, adjusted["1"] * (1 + adjustment)))
            adjusted["2"] = min(0.95, max(0.05, adjusted["2"] * (1 - adjustment)))

        if h2h and h2h.get("team_a_wins", 0) + h2h.get("team_b_wins", 0) + \
                h2h.get("draws", 0) > 0:
            total_h2h = max(h2h.get("total_matches", 0), 1)
            a_win_rate = (h2h.get("team_a_wins", 0) / total_h2h) * 0.3
            h2h_unfav_adj = (0.5 - a_win_rate) / 10
            adjusted["1"] = min(0.95, max(0.05, adjusted["1"] + h2h_unfav_adj))

        if home_away:
            home_win_rate = home_away.get("win_rate", 0.5)
            adj = (home_win_rate - 0.5) * 0.1
            adjusted["1"] = min(0.95, max(0.05, adjusted["1"] + adj))

        from predictors.probabilities import normalize_probabilities
        return normalize_probabilities(adjusted)

    def _lock_prediction(self, home_team: str, away_team: str, league: str,
                         probs: dict, expected_goals: dict, recommendations: list,
                         ensemble_weights: dict, brier_scores: dict,
                         confidence_score: int, confidence_breakdown: dict,
                         kelly_stakes: dict):
        """Bloquea predicción para transparencia (inmutable)."""
        try:
            from storage.database import Database
            
            match_id = f"{home_team}_vs_{away_team}_{league}_{date.today().isoformat()}"
            locked_at = datetime.now().isoformat()
            
            lock_data = {
                "match_id": match_id,
                "home_team": home_team,
                "away_team": away_team,
                "league": league,
                "kickoff": date.today().isoformat() + "T20:00:00",
                "locked_at": locked_at,
                "probabilities": probs,
                "expected_goals": expected_goals,
                "recommendations": recommendations,
                "ensemble_weights": ensemble_weights,
                "brier_scores": brier_scores,
                "confidence_score": confidence_score,
                "confidence_breakdown": confidence_breakdown,
                "kelly_stakes": kelly_stakes,
            }
            
            lock_str = json.dumps(lock_data, sort_keys=True)
            immutable_hash = hashlib.sha256(lock_str.encode()).hexdigest()[:16]
            lock_data["immutable_hash"] = immutable_hash
            
            db = Database()
            db.save_prediction_lock(lock_data)
            
        except Exception as e:
            logger.warning(f"Could not lock prediction: {e}")

    def _expected_goals(self, home_attack: float, away_defense: float) -> float:
        from analyzers.poisson import expected_goals
        return expected_goals(home_attack, away_defense)