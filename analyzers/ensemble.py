import logging
from typing import Dict, List, Optional
from collections import defaultdict
from datetime import date, timedelta
import math

logger = logging.getLogger(__name__)


class ModelPrediction:
    """Contenedor para predicción de un modelo individual."""
    
    def __init__(self, model_name: str, probs: Dict[str, float],
                 lambda_home: float, lambda_away: float,
                 metadata: Dict = None):
        self.model_name = model_name
        # Extraer solo las probabilidades de mercado (sin matrix)
        self.probs = {k: v for k, v in probs.items() if k != "matrix"}
        self.lambda_home = lambda_home
        self.lambda_away = lambda_away
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict:
        return {
            "model": self.model_name,
            "probs": self.probs,
            "lambda_home": self.lambda_home,
            "lambda_away": self.lambda_away,
            "metadata": self.metadata,
        }


class BrierWeightedEnsemble:
    """
    Ensemble ponderado por Brier Score histórico.
    
    Cada modelo tiene peso = 1 / (brier_score + epsilon)
    Se re-calibran semanalmente con ventana rodante de 200 partidos.
    """
    
    MODEL_NAMES = [
        "poisson_basic",
        "dixon_coles",
        "bivariate_poisson",
        "elo_model",
        "pi_ratings",
        "skellam_handicap",
        "market_consensus",
        "xg_model",
    ]
    
    def __init__(self, window_size: int = 200, min_weight: float = 0.01):
        self.window_size = window_size
        self.min_weight = min_weight
        self.model_predictions: Dict[str, List[Dict]] = defaultdict(list)
        self.brier_scores: Dict[str, float] = {name: 0.25 for name in self.MODEL_NAMES}
        self.weights: Dict[str, float] = {name: 1.0 / len(self.MODEL_NAMES) 
                                          for name in self.MODEL_NAMES}
        self.calibration_data: List[Dict] = []
    
    def add_prediction(self, model_name: str, prediction: ModelPrediction,
                       actual_result: Dict = None):
        """Registra predicción y resultado real para calibración."""
        record = {
            "model": model_name,
            "timestamp": date.today().isoformat(),
            "prediction": prediction.to_dict(),
            "actual": actual_result,
        }
        self.model_predictions[model_name].append(record)
        self.calibration_data.append(record)
        
        if len(self.calibration_data) > self.window_size * 2:
            self.calibration_data = self.calibration_data[-self.window_size:]
        
        if actual_result:
            self._update_brier_score(model_name, prediction, actual_result)
            self._recalculate_weights()
    
    def _update_brier_score(self, model_name: str, 
                            prediction: ModelPrediction,
                            actual: Dict):
        """Actualiza Brier score para un modelo (solo 1X2)."""
        probs = prediction.probs
        actual_outcome = actual.get("result")
        
        if actual_outcome not in ["1", "draw", "2"]:
            return
        
        outcome_vec = {"1": 0, "draw": 0, "2": 0}
        outcome_vec[actual_outcome] = 1
        
        brier = 0.0
        for key in ["1", "draw", "2"]:
            pred_prob = probs.get(key, 0)
            brier += (pred_prob - outcome_vec[key]) ** 2
        
        alpha = 0.1
        self.brier_scores[model_name] = (
            (1 - alpha) * self.brier_scores[model_name] + alpha * brier
        )
    
    def _recalculate_weights(self):
        """Recalcula pesos inversamente proporcionales a Brier score."""
        eps = 1e-6
        inv_brier = {name: 1.0 / (score + eps) 
                     for name, score in self.brier_scores.items()}
        total = sum(inv_brier.values())
        
        for name in self.MODEL_NAMES:
            self.weights[name] = max(self.min_weight, inv_brier[name] / total)
        
        logger.info(f"Ensemble weights updated: {self.weights}")
    
    def get_weights(self) -> Dict[str, float]:
        return dict(self.weights)
    
    def get_brier_scores(self) -> Dict[str, float]:
        return dict(self.brier_scores)
    
    def combine_predictions(self, predictions: Dict[str, ModelPrediction]) -> Dict:
        """
        Combina predicciones usando pesos Brier.
        
        predictions: dict {model_name: ModelPrediction}
        """
        combined_probs = defaultdict(float)
        combined_lambda_home = 0.0
        combined_lambda_away = 0.0
        total_weight = 0.0
        
        for model_name, pred in predictions.items():
            weight = self.weights.get(model_name, 0)
            if weight <= 0:
                continue
            
            for key, prob in pred.probs.items():
                combined_probs[key] += weight * prob
            
            combined_lambda_home += weight * pred.lambda_home
            combined_lambda_away += weight * pred.lambda_away
            total_weight += weight
        
        if total_weight > 0:
            for key in combined_probs:
                combined_probs[key] /= total_weight
            combined_lambda_home /= total_weight
            combined_lambda_away /= total_weight
        
        combined_probs = self._normalize_1x2(combined_probs)
        
        return {
            "probs": dict(combined_probs),
            "lambda_home": combined_lambda_home,
            "lambda_away": combined_lambda_away,
            "weights_used": {k: v for k, v in self.weights.items() 
                           if k in predictions},
            "brier_scores": self.brier_scores,
        }
    
    def _normalize_1x2(self, probs: Dict) -> Dict:
        total = probs.get("1", 0) + probs.get("draw", 0) + probs.get("2", 0)
        if total <= 0:
            return probs
        return {
            **probs,
            "1": probs.get("1", 0) / total,
            "draw": probs.get("draw", 0) / total,
            "2": probs.get("2", 0) / total,
        }
    
    def calibration_curve(self, model_name: str = None, 
                          n_bins: int = 10) -> Dict:
        """Genera curva de calibración (reliability diagram)."""
        if model_name:
            data = [d for d in self.calibration_data if d["model"] == model_name]
        else:
            data = self.calibration_data
        
        if not data:
            return {"bins": [], "ece": None}
        
        bins = [[] for _ in range(n_bins)]
        
        for d in data:
            if not d.get("actual"):
                continue
            pred = d["prediction"]["probs"]
            actual = d["actual"].get("result")
            if actual not in ["1", "draw", "2"]:
                continue
            
            max_prob = max(pred.get("1", 0), pred.get("draw", 0), pred.get("2", 0))
            bin_idx = min(int(max_prob * n_bins), n_bins - 1)
            bins[bin_idx].append((max_prob, 1 if actual == "1" else 0))
        
        result = {"bins": [], "ece": 0.0}
        total_samples = 0
        
        for i, bin_data in enumerate(bins):
            if not bin_data:
                continue
            avg_conf = sum(x[0] for x in bin_data) / len(bin_data)
            avg_acc = sum(x[1] for x in bin_data) / len(bin_data)
            result["bins"].append({
                "bin": i,
                "confidence": avg_conf,
                "accuracy": avg_acc,
                "count": len(bin_data),
            })
            result["ece"] += len(bin_data) * abs(avg_conf - avg_acc)
            total_samples += len(bin_data)
        
        if total_samples > 0:
            result["ece"] /= total_samples
        
        return result


class EnsemblePredictor:
    """
    Orquestador que ejecuta todos los modelos y combina con ensemble.
    """
    
    def __init__(self):
        self.ensemble = BrierWeightedEnsemble()
        self.models = {}
        self._init_models()
    
    def _init_models(self):
        try:
            from analyzers.poisson import predict_match_scores
            self.models["poisson_basic"] = predict_match_scores
        except ImportError:
            pass
        
        try:
            from analyzers.dixon_coles import predict_match_scores_dc
            self.models["dixon_coles"] = predict_match_scores_dc
        except ImportError:
            pass
        
        try:
            from analyzers.bivariate_poisson import predict_match_scores_biv
            self.models["bivariate_poisson"] = predict_match_scores_biv
        except ImportError:
            pass
        
        try:
            from analyzers.elo import EloModel, elo_to_poisson_lambda
            self.elo_model = EloModel()
            self.models["elo_model"] = True
        except ImportError:
            self.elo_model = None
        
        try:
            from analyzers.pi_ratings import PiRatings
            self.pi_model = PiRatings()
            self.models["pi_ratings"] = True
        except ImportError:
            self.pi_model = None
    
    def predict(self, home_data: Dict, away_data: Dict,
                h2h_data: Dict = None,
                market_odds: Dict = None,
                historical_matches: List[Dict] = None) -> Dict:
        """
        Genera predicción completa del ensemble.
        
        Returns:
            Dict con probs combinadas, lambdas, weights, brier_scores, 
            individual_predictions, calibration
        """
        lambda_home_base = home_data.get("goals_per_game", 1.2)
        lambda_away_base = away_data.get("goals_per_game", 1.2)
        conceded_home = away_data.get("conceded_per_game", 1.2)
        conceded_away = home_data.get("conceded_per_game", 1.2)
        
        lambda_home = (lambda_home_base * conceded_home * 2.5) / 2.5
        lambda_away = (lambda_away_base * conceded_away * 2.5) / 2.5
        
        individual = {}
        
        if "poisson_basic" in self.models:
            from analyzers.poisson import predict_match_scores
            res = predict_match_scores(lambda_home, lambda_away)
            individual["poisson_basic"] = ModelPrediction(
                "poisson_basic", res, lambda_home, lambda_away
            )
        
        if "dixon_coles" in self.models:
            from analyzers.dixon_coles import predict_match_scores_dc
            res = predict_match_scores_dc(lambda_home, lambda_away)
            individual["dixon_coles"] = ModelPrediction(
                "dixon_coles", res, lambda_home, lambda_away
            )
        
        if "bivariate_poisson" in self.models:
            from analyzers.bivariate_poisson import predict_match_scores_biv, estimate_lambda3
            lambda3 = 0.0
            if historical_matches:
                lambda3 = estimate_lambda3(historical_matches, lambda_home, lambda_away)
            res = predict_match_scores_biv(lambda_home, lambda_away, lambda3)
            individual["bivariate_poisson"] = ModelPrediction(
                "bivariate_poisson", res, lambda_home, lambda_away,
                {"lambda3": lambda3}
            )
        
        if self.elo_model and historical_matches:
            self.elo_model = self._update_elo_from_history(historical_matches)
            pred = self.elo_model.predict_match(
                home_data.get("team_name", "Home"), 
                away_data.get("team_name", "Away")
            )
            lh, la = pred["lambda_home"] if "lambda_home" in pred else elo_to_poisson_lambda(
                self.elo_model.get_rating(home_data.get("team_name", "Home")),
                self.elo_model.get_rating(away_data.get("team_name", "Away"))
            )
            individual["elo_model"] = ModelPrediction(
                "elo_model", 
                {"1": pred["home_win"], "draw": pred["draw"], "2": pred["away_win"]},
                lh, la,
                {"home_rating": pred.get("home_rating"), "away_rating": pred.get("away_rating")}
            )
        
        if self.pi_model and historical_matches:
            self.pi_model = self._update_pi_from_history(historical_matches)
            pred = self.pi_model.predict_match(
                home_data.get("team_name", "Home"),
                away_data.get("team_name", "Away")
            )
            individual["pi_ratings"] = ModelPrediction(
                "pi_ratings",
                {"1": pred["home_win"], "draw": pred["draw"], "2": pred["away_win"]},
                pred["lambda_home"], pred["lambda_away"],
                {"home_ratings": pred.get("home_ratings"), "away_ratings": pred.get("away_ratings")}
            )
        
        if market_odds:
            from analyzers.value_betting import implied_probability
            market_probs = {k: implied_probability(v) for k, v in market_odds.items()}
            total = sum(market_probs.values())
            market_probs = {k: v/total for k, v in market_probs.items()}
            individual["market_consensus"] = ModelPrediction(
                "market_consensus",
                {"1": market_probs.get("1", 0.33), "draw": market_probs.get("draw", 0.33), 
                 "2": market_probs.get("2", 0.33)},
                lambda_home, lambda_away,
                {"odds": market_odds}
            )
        
        combined = self.ensemble.combine_predictions(individual)
        
        for model_name, pred in individual.items():
            actual = None
            if "actual_result" in home_data:
                actual = home_data["actual_result"]
            self.ensemble.add_prediction(model_name, pred, actual)
        
        return {
            **combined,
            "individual_predictions": {k: v.to_dict() for k, v in individual.items()},
            "calibration": self.ensemble.calibration_curve(),
        }
    
    def _update_elo_from_history(self, matches: List[Dict]) -> 'EloModel':
        from analyzers.elo import EloModel
        model = EloModel()
        for m in matches:
            model.update(m['home_team'], m['away_team'], 
                        m['home_goals'], m['away_goals'],
                        date_str=m.get('date'))
        return model
    
    def _update_pi_from_history(self, matches: List[Dict]) -> 'PiRatings':
        from analyzers.pi_ratings import PiRatings
        model = PiRatings()
        for m in matches:
            model.update(m['home_team'], m['away_team'],
                        m['home_goals'], m['away_goals'],
                        date_str=m.get('date'))
        return model


def create_ensemble_predictor() -> EnsemblePredictor:
    return EnsemblePredictor()