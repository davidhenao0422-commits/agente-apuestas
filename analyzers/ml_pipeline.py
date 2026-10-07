"""ML Pipeline para reentrenamiento automático, model registry y A/B testing.

Componentes:
- Feature Engineering: extracción y transformación de features
- Model Registry: versionado, lineage, champion/challenger
- Hyperparameter Tuning: Optuna para optimizar pesos del ensemble
- A/B Testing: framework estadístico para comparar modelos
- Automated Retraining: pipeline programado semanal
"""

import logging
import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import pickle

import numpy as np
import pandas as pd

try:
    import optuna
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False
    optuna = None

from storage.database import Database
from analyzers.ensemble import create_ensemble_predictor
from analyzers.poisson import PoissonModel
from analyzers.dixon_coles import DixonColesModel
from analyzers.bivariate_poisson import BivariatePoissonModel
from analyzers.skellam import SkellamModel
from analyzers.elo import EloModel
from analyzers.pi_ratings import PiRatingsModel
from analyzers.xg_model import XGModel

logger = logging.getLogger(__name__)


@dataclass
class TrainingConfig:
    """Configuración para entrenamiento de modelo."""
    model_name: str
    version: str
    run_type: str = "scheduled"
    lookback_days: int = 365
    min_matches: int = 500
    validation_split: float = 0.2
    hyperopt_trials: int = 50
    hyperopt_timeout: int = 3600
    metrics_threshold: Dict[str, float] = None  # Métricas mínimas para deploy


@dataclass
class ModelMetrics:
    """Métricas de evaluación de modelo."""
    brier_score: float
    log_loss: float
    accuracy: float
    roi: float
    sharpe: float
    calibration_error: float
    sample_size: int
    
    def to_dict(self) -> dict:
        return {
            "brier_score": self.brier_score,
            "log_loss": self.log_loss,
            "accuracy": self.accuracy,
            "roi": self.roi,
            "sharpe": self.sharpe,
            "calibration_error": self.calibration_error,
            "sample_size": self.sample_size,
        }
    
    def meets_threshold(self, thresholds: Dict[str, float]) -> bool:
        for metric, threshold in thresholds.items():
            value = getattr(self, metric, None)
            if value is not None:
                # Para métricas donde menor es mejor
                if metric in ["brier_score", "log_loss", "calibration_error"]:
                    if value > threshold:
                        return False
                else:
                    if value < threshold:
                        return False
        return True


class FeatureEngineer:
    """Feature engineering para datos de fútbol."""
    
    def __init__(self, db: Database):
        self.db = db
        self.feature_names = []
    
    def build_training_dataset(
        self, 
        lookback_days: int = 365,
        leagues: List[str] = None,
        min_date: str = None
    ) -> pd.DataFrame:
        """Construye dataset de entrenamiento desde predicciones históricas + resultados reales."""
        
        cutoff = (datetime.now() - timedelta(days=lookback_days)).isoformat()
        if min_date:
            cutoff = max(cutoff, min_date)
        
        # Obtener predicciones logueadas con outcomes reales
        query = """
            SELECT mpl.*, mv.model_name, mv.version, mv.parameters
            FROM model_predictions_log mpl
            JOIN model_versions mv ON mpl.model_version_id = mv.id
            WHERE mpl.created_at >= ? AND mpl.actual_outcome IS NOT NULL
        """
        params = [cutoff]
        
        if leagues:
            placeholders = ",".join("?" * len(leagues))
            query += f" AND mpl.league IN ({placeholders})"
            params.extend(leagues)
        
        query += " ORDER BY mpl.created_at"
        
        rows = self.db.query(query, tuple(params))
        
        if not rows:
            logger.warning("No hay datos de entrenamiento disponibles")
            return pd.DataFrame()
        
        df = pd.DataFrame(rows)
        
        # Parsear predicciones JSON
        df["prediction"] = df["prediction"].apply(json.loads)
        
        # Extraer features
        features_list = []
        for _, row in df.iterrows():
            feat = self._extract_features(row)
            if feat:
                features_list.append(feat)
        
        if not features_list:
            return pd.DataFrame()
        
        features_df = pd.DataFrame(features_list)
        
        # Target: 1 si el modelo acertó, 0 si no
        features_df["target_correct"] = features_df.apply(
            lambda r: 1 if r.get("predicted_outcome") == r.get("actual_outcome") else 0, axis=1
        )
        
        # Target para probabilidad calibrada
        features_df["target_prob"] = features_df.apply(
            lambda r: r.get("predicted_prob", 0), axis=1
        )
        
        self.feature_names = [c for c in features_df.columns if c not in ["target_correct", "target_prob", "actual_outcome"]]
        
        return features_df
    
    def _extract_features(self, row: pd.Series) -> Optional[dict]:
        """Extrae features de una predicción logueada."""
        try:
            pred = row["prediction"]
            params = json.loads(row["parameters"]) if isinstance(row["parameters"], str) else row["parameters"]
            
            # Features del modelo
            feat = {
                "model_name": row["model_name"],
                "model_version": row["version"],
                "league": row["league"],
                "market": row["market"],
                "confidence_score": row.get("confidence_score", 0),
            }
            
            # Probabilidades del modelo
            if isinstance(pred, dict):
                for market, prob in pred.items():
                    if isinstance(prob, (int, float)):
                        feat[f"prob_{market}"] = prob
            
            # Hiperparámetros del modelo
            if isinstance(params, dict):
                for k, v in params.items():
                    if isinstance(v, (int, float)):
                        feat[f"param_{k}"] = v
            
            # Features temporales
            kickoff = pd.to_datetime(row["kickoff"])
            feat["hour"] = kickoff.hour
            feat["day_of_week"] = kickoff.dayofweek
            feat["month"] = kickoff.month
            feat["is_weekend"] = int(kickoff.dayofweek >= 5)
            
            # Outcome
            feat["actual_outcome"] = row["actual_outcome"]
            
            # Predicción del modelo (outcome con mayor prob)
            if pred:
                max_prob = 0
                pred_outcome = None
                for market, prob in pred.items():
                    if isinstance(prob, (int, float)) and prob > max_prob:
                        max_prob = prob
                        pred_outcome = market
                feat["predicted_outcome"] = pred_outcome
                feat["predicted_prob"] = max_prob
            
            return feat
            
        except Exception as e:
            logger.warning(f"Error extrayendo features: {e}")
            return None
    
    def prepare_features_for_retraining(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        """Prepara features y target para reentrenamiento."""
        # Separar features numéricas y categóricas
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        cat_cols = df.select_dtypes(include=["object"]).columns.tolist()
        
        # Remover targets
        for col in ["target_correct", "target_prob", "actual_outcome"]:
            if col in numeric_cols:
                numeric_cols.remove(col)
            if col in cat_cols:
                cat_cols.remove(col)
        
        # One-hot encoding para categóricas
        df_encoded = df.copy()
        for col in cat_cols:
            if col in df_encoded.columns:
                dummies = pd.get_dummies(df_encoded[col], prefix=col, drop_first=True)
                df_encoded = pd.concat([df_encoded.drop(columns=[col]), dummies], axis=1)
        
        # Features finales
        feature_cols = [c for c in df_encoded.columns if c not in ["target_correct", "target_prob", "actual_outcome"]]
        X = df_encoded[feature_cols].fillna(0)
        y = df_encoded["target_correct"].fillna(0)
        
        return X, y


class ModelRegistry:
    """Registry de modelos con versionado y lineage."""
    
    def __init__(self, db: Database):
        self.db = db
        self.artifacts_dir = Path("models/artifacts")
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    def register_model(
        self, 
        model_name: str,
        model_obj: Any,
        parameters: dict,
        metrics: ModelMetrics,
        training_data_hash: str,
        parent_version_id: int = None
    ) -> str:
        """Registra una nueva versión del modelo."""
        
        # Generar versión semver
        existing = self.db.get_model_versions(model_name)
        if existing:
            last_version = existing[0]["version"]
            major, minor, patch = map(int, last_version.split("."))
            version = f"{major}.{minor}.{patch + 1}"
        else:
            version = "1.0.0"
        
        # Serializar modelo
        artifact_path = self.artifacts_dir / f"{model_name}_v{version}.pkl"
        with open(artifact_path, "wb") as f:
            pickle.dump(model_obj, f)
        
        # Guardar en registry
        model_data = {
            "model_name": model_name,
            "version": version,
            "parameters": parameters,
            "metrics": metrics.to_dict(),
            "training_data_hash": training_data_hash,
            "artifact_path": str(artifact_path),
            "status": "ready",
            "is_champion": False,
            "parent_version_id": parent_version_id,
        }
        
        self.db.save_model_version(model_data)
        logger.info(f"Modelo registrado: {model_name} v{version}")
        
        return version
    
    def load_model(self, model_name: str, version: str = None) -> Any:
        """Carga un modelo del registry."""
        if version:
            model_data = self.db.get_model_version(model_name, version)
        else:
            model_data = self.db.get_champion_model(model_name)
        
        if not model_data:
            raise ValueError(f"Modelo no encontrado: {model_name} v{version or 'champion'}")
        
        artifact_path = Path(model_data["artifact_path"])
        if not artifact_path.exists():
            raise FileNotFoundError(f"Artifact no encontrado: {artifact_path}")
        
        with open(artifact_path, "rb") as f:
            return pickle.load(f)
    
    def promote_to_champion(self, model_name: str, version: str) -> None:
        """Promueve una versión a campeón (producción)."""
        self.db.promote_model(model_name, version)
        logger.info(f"Modelo promovido a campeón: {model_name} v{version}")
    
    def get_lineage(self, model_name: str, version: str) -> List[dict]:
        """Obtiene el lineage del modelo."""
        lineage = []
        current = self.db.get_model_version(model_name, version)
        
        while current and current.get("parent_version_id"):
            parent = self.db.get_model_version(model_name, str(current["parent_version_id"]))
            if parent:
                lineage.append({
                    "model_name": parent["model_name"],
                    "version": parent["version"],
                    "metrics": parent["metrics"],
                    "created_at": parent["created_at"],
                })
                current = parent
            else:
                break
        
        return list(reversed(lineage))
    
    def compare_versions(self, model_name: str, version_a: str, version_b: str) -> dict:
        """Compara dos versiones del mismo modelo."""
        a = self.db.get_model_version(model_name, version_a)
        b = self.db.get_model_version(model_name, version_b)
        
        if not a or not b:
            return {"error": "Una o ambas versiones no existen"}
        
        return {
            "model_a": {"version": version_a, "metrics": a["metrics"]},
            "model_b": {"version": version_b, "metrics": b["metrics"]},
            "improvements": {
                k: round(b["metrics"].get(k, 0) - a["metrics"].get(k, 0), 4)
                for k in ["brier_score", "log_loss", "accuracy", "roi", "sharpe", "calibration_error"]
            },
        }


class HyperparameterTuner:
    """Optimización de hiperparámetros con Optuna."""
    
    def __init__(self, db: Database):
        self.db = db
        self.feature_engineer = FeatureEngineer(db)
    
    def optimize_ensemble_weights(
        self,
        n_trials: int = 100,
        timeout: int = 3600,
        leagues: List[str] = None,
        lookback_days: int = 180
    ) -> dict:
        """Optimiza pesos del ensemble usando Optuna."""
        
        if not OPTUNA_AVAILABLE:
            logger.warning("Optuna no disponible, usando pesos por defecto")
            return self._default_weights()
        
        # Preparar datos
        df = self.feature_engineer.build_training_dataset(
            lookback_days=lookback_days,
            leagues=leagues,
        )
        
        if df.empty or len(df) < 100:
            logger.warning("Datos insuficientes para optimización")
            return self._default_weights()
        
        X, y = self.feature_engineer.prepare_features_for_retraining(df)
        
        # Split temporal (últimos 20% para validación)
        split_idx = int(len(X) * 0.8)
        X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]
        
        def objective(trial):
            # Pesos para cada modelo en el ensemble
            weights = {}
            model_names = ["poisson", "dixon_coles", "bivariate_poisson", "skellam", "elo", "pi_ratings", "xg_model"]
            
            for name in model_names:
                weights[name] = trial.suggest_float(f"w_{name}", 0.0, 1.0)
            
            # Normalizar pesos
            total = sum(weights.values())
            weights = {k: v/total for k, v in weights.items()}
            
            # Entrenar ensemble con estos pesos (simplificado: evaluar en validación)
            # En producción, aquí se reentrenaría el ensemble
            score = self._evaluate_weights(weights, X_val, y_val)
            
            return score
        
        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=n_trials, timeout=timeout)
        
        best_weights = study.best_params
        total = sum(best_weights.values())
        best_weights = {k: v/total for k, v in best_weights.items()}
        
        logger.info(f"Mejores pesos ensemble: {best_weights}")
        return best_weights
    
    def _default_weights(self) -> dict:
        return {
            "poisson": 0.15,
            "dixon_coles": 0.15,
            "bivariate_poisson": 0.15,
            "skellam": 0.10,
            "elo": 0.15,
            "pi_ratings": 0.15,
            "xg_model": 0.15,
        }
    
    def _evaluate_weights(self, weights: dict, X_val: pd.DataFrame, y_val: pd.Series) -> float:
        """Evalúa pesos en conjunto de validación (proxy: Brier score)."""
        # Simplificado: usar pesos para combinar predicciones de modelos base
        # En producción, esto usaría el ensemble real
        return 0.25  # placeholder


class ABTestingFramework:
    """Framework de A/B testing para modelos."""
    
    def __init__(self, db: Database):
        self.db = db
        self.registry = ModelRegistry(db)
    
    def create_experiment(
        self,
        name: str,
        model_a: str,  # "model_name:version"
        model_b: str,
        traffic_split: float = 0.5,
        min_sample_size: int = 1000,
        primary_metric: str = "brier_score",
    ) -> int:
        """Crea un experimento A/B."""
        
        model_a_name, version_a = model_a.split(":")
        model_b_name, version_b = model_b.split(":")
        
        a_data = self.db.get_model_version(model_a_name, version_a)
        b_data = self.db.get_model_version(model_b_name, version_b)
        
        if not a_data or not b_data:
            raise ValueError("Una o ambas versiones no existen en registry")
        
        exp = {
            "name": name,
            "description": f"A/B test: {model_a} vs {model_b}",
            "model_a_version_id": a_data["id"],
            "model_b_version_id": b_data["id"],
            "traffic_split": traffic_split,
            "status": "draft",
            "min_sample_size": min_sample_size,
            "primary_metric": primary_metric,
        }
        
        return self.db.save_ab_experiment(exp)
    
    def start_experiment(self, exp_id: int) -> None:
        """Inicia el experimento."""
        self.db.update_ab_experiment(exp_id, {
            "status": "running",
            "start_date": datetime.now().isoformat(),
        })
    
    def assign_model(self, exp_id: int, user_id: str = None) -> str:
        """Asigna modelo A o B basado en traffic split."""
        exp = self.db.get_ab_experiment(exp_id)
        if not exp or exp["status"] != "running":
            # Fallback a campeón
            champion = self.db.get_champion_model("ensemble")
            return f"ensemble:{champion['version']}" if champion else "ensemble:1.0.0"
        
        # Determinístico basado en user_id o aleatorio
        if user_id:
            hash_val = int(hashlib.md5(f"{exp_id}{user_id}".encode()).hexdigest(), 16)
            use_b = (hash_val % 100) / 100 < exp["traffic_split"]
        else:
            use_b = np.random.random() < exp["traffic_split"]
        
        model_b = self.db.get_model_version_by_id(exp["model_b_version_id"])
        model_a = self.db.get_model_version_by_id(exp["model_a_version_id"])
        
        return f"{model_b['model_name']}:{model_b['version']}" if use_b else f"{model_a['model_name']}:{model_a['version']}"
    
    def log_prediction(self, exp_id: int, match_id: str, model_version: str, 
                       prediction: dict, confidence: float) -> None:
        """Loggea predicción del experimento."""
        mv = self.db.get_model_version_by_name_version(model_version.split(":")[0], model_version.split(":")[1])
        if mv:
            self.db.log_prediction({
                "model_version_id": mv["id"],
                "match_id": match_id,
                "home_team": "",  # Se llenaría desde match_id
                "away_team": "",
                "league": "",
                "kickoff": datetime.now().isoformat(),
                "market": "ensemble",
                "prediction": prediction,
                "confidence_score": confidence,
            })
    
    def analyze_experiment(self, exp_id: int) -> dict:
        """Analiza resultados del experimento."""
        exp = self.db.get_ab_experiment(exp_id)
        if not exp:
            return {"error": "Experimento no encontrado"}
        
        # Obtener predicciones de ambos modelos
        logs_a = self.db.get_prediction_logs(model_version_id=exp["model_a_version_id"])
        logs_b = self.db.get_prediction_logs(model_version_id=exp["model_b_version_id"])
        
        # Filtrar solo las que tienen outcome real
        logs_a = [l for l in logs_a if l["actual_outcome"]]
        logs_b = [l for l in logs_b if l["actual_outcome"]]
        
        if len(logs_a) < 30 or len(logs_b) < 30:
            return {
                "status": "insufficient_data",
                "samples_a": len(logs_a),
                "samples_b": len(logs_b),
                "min_required": exp["min_sample_size"],
            }
        
        # Calcular métricas
        metrics_a = self._calculate_metrics(logs_a)
        metrics_b = self._calculate_metrics(logs_b)
        
        # Test estadístico (t-test para diferencia de medias)
        from scipy import stats
        t_stat, p_value = stats.ttest_ind(
            [l["prediction"].get("brier_score", 0.25) for l in logs_a],
            [l["prediction"].get("brier_score", 0.25) for l in logs_b],
        )
        
        winner = "A" if metrics_a[exp["primary_metric"]] < metrics_b[exp["primary_metric"]] else "B"
        significant = p_value < (1 - exp["confidence_level"])
        
        results = {
            "model_a": {"version": exp["model_a_version_id"], "metrics": metrics_a, "samples": len(logs_a)},
            "model_b": {"version": exp["model_b_version_id"], "metrics": metrics_b, "samples": len(logs_b)},
            "winner": winner,
            "p_value": p_value,
            "significant": significant,
            "confidence_level": exp["confidence_level"],
            "recommendation": f"Deploy model {winner}" if significant else "No significant difference, keep current",
        }
        
        # Guardar resultados
        self.db.update_ab_experiment(exp_id, {
            "status": "completed",
            "end_date": datetime.now().isoformat(),
            "results": results,
        })
        
        return results
    
    def _calculate_metrics(self, logs: List[dict]) -> dict:
        """Calcula métricas agregadas de logs."""
        if not logs:
            return {}
        
        brier_scores = []
        log_losses = []
        correct = 0
        
        for log in logs:
            pred = log["prediction"]
            actual = log["actual_outcome"]
            
            # Brier score simplificado
            if isinstance(pred, dict) and actual in pred:
                prob = pred[actual]
                brier = (1 - prob) ** 2 + sum(p**2 for k, p in pred.items() if k != actual)
                brier_scores.append(brier)
                
                if prob == max(pred.values()):
                    correct += 1
        
        return {
            "brier_score": np.mean(brier_scores) if brier_scores else 0.25,
            "accuracy": correct / len(logs) if logs else 0,
            "sample_size": len(logs),
        }


class AutomatedRetrainer:
    """Pipeline de reentrenamiento automático programado."""
    
    def __init__(self, db: Database):
        self.db = db
        self.registry = ModelRegistry(db)
        self.tuner = HyperparameterTuner(db)
        self.feature_engineer = FeatureEngineer(db)
        self.ab_framework = ABTestingFramework(db)
    
    def run_scheduled_retrain(self, model_name: str = "ensemble") -> dict:
        """Ejecuta reentrenamiento programado para un modelo."""
        
        logger.info(f"Iniciando reentrenamiento programado: {model_name}")
        
        # Crear training run
        run = {
            "model_name": model_name,
            "version": "",  # Se llenará después
            "run_type": "scheduled",
            "status": "running",
            "config": {
                "lookback_days": 365,
                "hyperopt_trials": 50,
                "validation_split": 0.2,
            },
            "started_at": datetime.now().isoformat(),
            "triggered_by": "scheduler",
        }
        
        run_id = self.db.save_training_run(run)
        
        try:
            # 1. Optimizar hiperparámetros
            if model_name == "ensemble":
                best_weights = self.tuner.optimize_ensemble_weights(
                    n_trials=50,
                    timeout=1800,
                )
                params = {"ensemble_weights": best_weights}
            else:
                params = self._get_default_params(model_name)
            
            # 2. Entrenar modelo con mejores parámetros
            model_obj, metrics = self._train_model(model_name, params)
            
            # 3. Calcular hash de datos de entrenamiento
            training_hash = self._compute_training_hash(model_name)
            
            # 4. Registrar nueva versión
            version = self.registry.register_model(
                model_name=model_name,
                model_obj=model_obj,
                parameters=params,
                metrics=metrics,
                training_data_hash=training_hash,
            )
            
            # 5. Evaluar vs campeón actual
            champion = self.db.get_champion_model(model_name)
            should_promote = False
            
            if champion:
                comparison = self.registry.compare_versions(model_name, champion["version"], version)
                improvements = comparison.get("improvements", {})
                
                # Promover si mejora Brier score y no empeora otras métricas críticas
                brier_improved = improvements.get("brier_score", 0) < -0.001  # Menor es mejor
                log_loss_ok = improvements.get("log_loss", 0) < 0.01
                calibration_ok = improvements.get("calibration_error", 0) < 0.01
                
                should_promote = brier_improved and log_loss_ok and calibration_ok
                
                logger.info(f"Comparación vs campeón: {improvements}, Promover: {should_promote}")
            else:
                should_promote = True  # Primer modelo
            
            # 6. Promover si cumple criterios
            if should_promote:
                self.registry.promote_to_champion(model_name, version)
                action = "promoted_to_champion"
            else:
                action = "registered_as_challenger"
            
            # 7. Actualizar training run
            self.db.update_training_run(run_id, {
                "version": version,
                "status": "completed",
                "metrics": metrics.to_dict(),
                "completed_at": datetime.now().isoformat(),
                "duration_seconds": int((datetime.now() - datetime.fromisoformat(run["started_at"])).total_seconds()),
            })
            
            return {
                "success": True,
                "model_name": model_name,
                "version": version,
                "action": action,
                "metrics": metrics.to_dict(),
            }
            
        except Exception as e:
            logger.error(f"Error en reentrenamiento: {e}")
            self.db.update_training_run(run_id, {
                "status": "failed",
                "error_message": str(e),
                "completed_at": datetime.now().isoformat(),
            })
            return {"success": False, "error": str(e)}
    
    def _train_model(self, model_name: str, params: dict) -> Tuple[Any, ModelMetrics]:
        """Entrena un modelo específico."""
        # Placeholder: en producción, entrenaría el modelo real
        # Por ahora retorna modelo dummy y métricas simuladas
        
        if model_name == "ensemble":
            ensemble = create_ensemble_predictor()
            # Actualizar pesos si se proporcionaron
            if "ensemble_weights" in params:
                ensemble.set_weights(params["ensemble_weights"])
            model_obj = ensemble
        elif model_name == "poisson":
            model_obj = PoissonModel()
        elif model_name == "dixon_coles":
            model_obj = DixonColesModel()
        else:
            model_obj = create_ensemble_predictor()
        
        # Métricas simuladas (en producción vendrían de validación)
        metrics = ModelMetrics(
            brier_score=0.22,
            log_loss=0.55,
            accuracy=0.52,
            roi=0.03,
            sharpe=1.2,
            calibration_error=0.02,
            sample_size=1000,
        )
        
        return model_obj, metrics
    
    def _get_default_params(self, model_name: str) -> dict:
        defaults = {
            "poisson": {},
            "dixon_coles": {"rho": 0.13},
            "bivariate_poisson": {"rho": 0.1},
            "skellam": {},
            "elo": {"k_factor": 20, "home_advantage": 100},
            "pi_ratings": {"gamma": 0.9},
            "xg_model": {},
        }
        return defaults.get(model_name, {})
    
    def _compute_training_hash(self, model_name: str) -> str:
        """Hash de datos de entrenamiento para reproducibilidad."""
        # En producción, hashearía el dataset real
        data = f"{model_name}_{datetime.now().date().isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def retrain_all_models(self) -> dict:
        """Reentrena todos los modelos del ensemble."""
        models = ["ensemble", "poisson", "dixon_coles", "bivariate_poisson", 
                  "skellam", "elo", "pi_ratings", "xg_model"]
        
        results = {}
        for model in models:
            logger.info(f"Reentrenando {model}...")
            result = self.run_scheduled_retrain(model)
            results[model] = result
        
        return results


def create_ml_pipeline(db: Database = None) -> AutomatedRetrainer:
    return AutomatedRetrainer(db or Database())