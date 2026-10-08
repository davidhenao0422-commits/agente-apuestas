"""Advanced Analytics Engine para Paper Trading.

Incluye:
- Performance Attribution: descomposición de ROI por factor (modelo, liga, mercado, timing, suerte)
- Regime Detection: detección de regímenes de mercado (bull/bear/volatile/calm)
- Stress Testing: escenarios extremos (crash, alta volatilidad, correlaciones)
- Monte Carlo Portfolio: simulación de paths de bankroll
- Factor Analysis: PCA/regresión para identificar drivers de rendimiento
"""

import logging
import json
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.decomposition import PCA
from sklearn.linear_model import LinearRegression

from storage.database import Database
from analyzers.paper_trading import create_paper_trading_engine

logger = logging.getLogger(__name__)


@dataclass
class AttributionResult:
    """Resultado de atribución de rendimiento."""
    total_roi: float
    total_pnl: float
    by_model: Dict[str, Dict]
    by_league: Dict[str, Dict]
    by_market: Dict[str, Dict]
    by_timing: Dict[str, Dict]  # early/late placement
    by_luck: Dict[str, float]   # residual = luck
    selection_effect: float
    allocation_effect: float
    interaction_effect: float


@dataclass
class RegimeInfo:
    """Información de régimen de mercado."""
    regime_type: str  # bull, bear, volatile, calm, trending, mean_reverting
    start_date: str
    end_date: Optional[str]
    metrics: Dict
    confidence: float
    description: str


@dataclass
class StressTestResult:
    """Resultado de stress test."""
    scenario_name: str
    max_drawdown: float
    var_95: float
    expected_shortfall: float
    survival_probability: float
    median_final_bankroll: float
    worst_case_bankroll: float
    recovery_time_days: float


class AnalyticsEngine:
    """Motor de analytics avanzado para paper trading."""

    def __init__(self, db: Database = None):
        self.db = db or Database()
        self.paper_engine = create_paper_trading_engine(db)

    # ===================== PERFORMANCE ATTRIBUTION =====================

    def run_performance_attribution(self, portfolio_id: int, 
                                     period_days: int = 30) -> AttributionResult:
        """Descompone el ROI en factores contribuyentes."""
        
        perf = self.paper_engine.get_performance(portfolio_id, period_days)
        picks = self.paper_engine.get_picks(portfolio_id, status="settled", limit=1000)
        
        # Filtrar por período
        cutoff = (datetime.now() - timedelta(days=period_days)).isoformat()
        picks = [p for p in picks if p.get("settled_at", "") >= cutoff]
        
        if not picks:
            return AttributionResult(
                total_roi=0, total_pnl=0,
                by_model={}, by_league={}, by_market={}, by_timing={}, by_luck={},
                selection_effect=0, allocation_effect=0, interaction_effect=0
            )
        
        total_pnl = sum(p.get("pnl", 0) for p in picks)
        total_staked = sum(p.get("stake_units", 0) for p in picks)
        total_roi = (total_pnl / total_staked * 100) if total_staked > 0 else 0
        
        # Atribución por modelo
        by_model = self._attribute_by_field(picks, "source", total_staked, total_pnl)
        
        # Atribución por liga
        by_league = self._attribute_by_field(picks, "league", total_staked, total_pnl)
        
        # Atribución por mercado
        by_market = self._attribute_by_field(picks, "market", total_staked, total_pnl)
        
        # Atribución por timing (días antes del partido)
        by_timing = self._attribute_by_timing(picks, total_staked, total_pnl)
        
        # Efectos Brinson
        selection, allocation, interaction = self._brinson_attribution(picks, total_staked)
        
        # Luck = residual
        explained_pnl = sum(v["pnl"] for v in by_model.values())
        luck_pnl = total_pnl - explained_pnl
        
        return AttributionResult(
            total_roi=round(total_roi, 2),
            total_pnl=round(total_pnl, 2),
            by_model=by_model,
            by_league=by_league,
            by_market=by_market,
            by_timing=by_timing,
            by_luck={"luck_pnl": round(luck_pnl, 2), "luck_pct": round(luck_pnl/total_pnl*100, 1) if total_pnl != 0 else 0},
            selection_effect=round(selection, 2),
            allocation_effect=round(allocation, 2),
            interaction_effect=round(interaction, 2),
        )

    def _attribute_by_field(self, picks: List[dict], field: str, 
                            total_staked: float, total_pnl: float) -> Dict:
        """Atribución genérica por un campo."""
        groups = defaultdict(lambda: {"picks": 0, "staked": 0, "pnl": 0, "wins": 0})
        
        for p in picks:
            key = p.get(field, "unknown")
            groups[key]["picks"] += 1
            groups[key]["staked"] += p.get("stake_units", 0)
            groups[key]["pnl"] += p.get("pnl", 0)
            if p.get("result") == "win":
                groups[key]["wins"] += 1
        
        result = {}
        for key, vals in groups.items():
            roi = (vals["pnl"] / vals["staked"] * 100) if vals["staked"] > 0 else 0
            win_rate = (vals["wins"] / vals["picks"] * 100) if vals["picks"] > 0 else 0
            contrib_pct = (vals["pnl"] / total_pnl * 100) if total_pnl != 0 else 0
            
            result[key] = {
                "picks": vals["picks"],
                "staked": round(vals["staked"], 2),
                "pnl": round(vals["pnl"], 2),
                "roi": round(roi, 2),
                "win_rate": round(win_rate, 1),
                "contribution_pct": round(contrib_pct, 1),
            }
        
        return dict(sorted(result.items(), key=lambda x: x[1]["pnl"], reverse=True))

    def _attribute_by_timing(self, picks: List[dict], 
                             total_staked: float, total_pnl: float) -> Dict:
        """Atribución por timing de colocación (días antes del kickoff)."""
        groups = defaultdict(lambda: {"picks": 0, "staked": 0, "pnl": 0, "wins": 0})
        
        for p in picks:
            try:
                placed = datetime.fromisoformat(p.get("placed_at", "").replace("Z", "+00:00"))
                kickoff = datetime.fromisoformat(p.get("kickoff", "").replace("Z", "+00:00"))
                days_before = (kickoff - placed).days
                
                if days_before <= 1:
                    bucket = "same_day"
                elif days_before <= 3:
                    bucket = "1-3_days"
                elif days_before <= 7:
                    bucket = "4-7_days"
                else:
                    bucket = "7+_days"
            except:
                bucket = "unknown"
            
            groups[bucket]["picks"] += 1
            groups[bucket]["staked"] += p.get("stake_units", 0)
            groups[bucket]["pnl"] += p.get("pnl", 0)
            if p.get("result") == "win":
                groups[bucket]["wins"] += 1
        
        result = {}
        for key, vals in groups.items():
            roi = (vals["pnl"] / vals["staked"] * 100) if vals["staked"] > 0 else 0
            win_rate = (vals["wins"] / vals["picks"] * 100) if vals["picks"] > 0 else 0
            contrib_pct = (vals["pnl"] / total_pnl * 100) if total_pnl != 0 else 0
            
            result[key] = {
                "picks": vals["picks"],
                "staked": round(vals["staked"], 2),
                "pnl": round(vals["pnl"], 2),
                "roi": round(roi, 2),
                "win_rate": round(win_rate, 1),
                "contribution_pct": round(contrib_pct, 1),
            }
        
        return result

    def _brinson_attribution(self, picks: List[dict], total_staked: float) -> Tuple[float, float, float]:
        """Atribución estilo Brinson: Selection + Allocation + Interaction."""
        # Simplificado: por liga
        league_data = defaultdict(lambda: {"staked": 0, "pnl": 0, "picks": 0})
        total_portfolio_roi = sum(p.get("pnl", 0) for p in picks) / total_staked if total_staked > 0 else 0
        
        for p in picks:
            league = p.get("league", "unknown")
            stake = p.get("stake_units", 0)
            pnl = p.get("pnl", 0)
            league_data[league]["staked"] += stake
            league_data[league]["pnl"] += pnl
            league_data[league]["picks"] += 1
        
        selection = 0
        allocation = 0
        interaction = 0
        
        for league, data in league_data.items():
            weight = data["staked"] / total_staked if total_staked > 0 else 0
            league_roi = data["pnl"] / data["staked"] if data["staked"] > 0 else 0
            excess_roi = league_roi - total_portfolio_roi
            
            # Selection: peso del portfolio * (ROI liga - ROI total)
            selection += weight * excess_roi
            # Allocation: (peso liga - peso benchmark) * ROI total
            # Simplificado: asumimos benchmark = equal weight
            bench_weight = 1 / len(league_data)
            allocation += (weight - bench_weight) * total_portfolio_roi
            # Interaction: (peso liga - peso bench) * (ROI liga - ROI total)
            interaction += (weight - bench_weight) * excess_roi
        
        return selection * 100, allocation * 100, interaction * 100

    # ===================== REGIME DETECTION =====================

    def detect_market_regime(self, portfolio_id: int = None, 
                              lookback_days: int = 60) -> RegimeInfo:
        """Detecta el régimen actual del mercado basado en métricas de portfolio."""
        
        if portfolio_id:
            perf = self.paper_engine.get_performance(portfolio_id, lookback_days)
            picks = self.paper_engine.get_picks(portfolio_id, status="settled", limit=500)
        else:
            # Usar primer portfolio activo
            portfolios = self.db.get_all_portfolios()
            active = [p for p in portfolios if p.get("is_active")]
            if not active:
                return RegimeInfo("unknown", "", None, {}, 0, "No portfolio")
            portfolio_id = active[0]["id"]
            perf = self.paper_engine.get_performance(portfolio_id, lookback_days)
            picks = self.paper_engine.get_picks(portfolio_id, status="settled", limit=500)
        
        if not picks or len(picks) < 20:
            return RegimeInfo("insufficient_data", "", None, {}, 0, "Not enough data")
        
        # Calcular métricas de régimen
        returns = []
        daily_pnl = defaultdict(float)
        
        for p in picks:
            if p.get("settled_at"):
                day = p["settled_at"][:10]
                daily_pnl[day] += p.get("pnl", 0)
        
        for day in sorted(daily_pnl.keys()):
            returns.append(daily_pnl[day])
        
        if len(returns) < 10:
            return RegimeInfo("insufficient_data", "", None, {}, 0, "Not enough daily data")
        
        returns = np.array(returns)
        volatility = np.std(returns)
        mean_return = np.mean(returns)
        sharpe = mean_return / volatility if volatility > 0 else 0
        
        # Trend strength (correlación serial)
        if len(returns) > 1:
            trend_strength = np.corrcoef(returns[:-1], returns[1:])[0, 1]
        else:
            trend_strength = 0
        
        # Win rate reciente
        recent_picks = picks[-20:]
        win_rate = sum(1 for p in recent_picks if p.get("result") == "win") / len(recent_picks)
        
        # Avg correlation entre picks concurrentes
        avg_corr = self._calculate_avg_correlation(picks)
        
        metrics = {
            "volatility": round(volatility, 4),
            "mean_daily_return": round(mean_return, 4),
            "sharpe": round(sharpe, 2),
            "trend_strength": round(trend_strength, 3),
            "win_rate": round(win_rate, 3),
            "avg_correlation": round(avg_corr, 3),
            "daily_returns_count": len(returns),
        }
        
        # Clasificar régimen
        regime_type, confidence, description = self._classify_regime(
            volatility, sharpe, trend_strength, win_rate, avg_corr
        )
        
        # Verificar si ya existe régimen activo del mismo tipo
        current = self.db.get_current_regime()
        if current and current["regime_type"] == regime_type:
            return RegimeInfo(
                regime_type=regime_type,
                start_date=current["start_date"],
                end_date=None,
                metrics=metrics,
                confidence=confidence,
                description=description,
            )
        
        # Cerrar régimen anterior si existe
        if current:
            self.db.execute(
                "UPDATE regime_history SET end_date = ? WHERE id = ?",
                (datetime.now().isoformat(), current["id"]),
            )
        
        # Crear nuevo régimen
        regime_id = self.db.save_regime({
            "regime_type": regime_type,
            "start_date": datetime.now().isoformat(),
            "metrics": metrics,
            "description": description,
            "confidence": confidence,
        })
        
        return RegimeInfo(
            regime_type=regime_type,
            start_date=datetime.now().isoformat(),
            end_date=None,
            metrics=metrics,
            confidence=confidence,
            description=description,
        )

    def _calculate_avg_correlation(self, picks: List[dict]) -> float:
        """Calcula correlación promedio entre picks concurrentes."""
        # Agrupar por día
        by_day = defaultdict(list)
        for p in picks:
            if p.get("settled_at"):
                day = p["settled_at"][:10]
                by_day[day].append(p)
        
        correlations = []
        for day, day_picks in by_day.items():
            if len(day_picks) >= 2:
                # Simplificado: correlación basada en resultados compartidos
                results = [1 if p.get("result") == "win" else 0 for p in day_picks]
                if len(set(results)) > 1:
                    corr_matrix = np.corrcoef([results, results])[0, 1]
                    correlations.append(corr_matrix)
        
        return np.mean(correlations) if correlations else 0

    def _classify_regime(self, volatility: float, sharpe: float, 
                         trend_strength: float, win_rate: float, 
                         avg_corr: float) -> Tuple[str, float, str]:
        """Clasifica el régimen de mercado."""
        
        # Thresholds
        high_vol = volatility > 50  # € diario
        low_sharpe = sharpe < 0.5
        high_corr = avg_corr > 0.3
        strong_trend = abs(trend_strength) > 0.3
        good_wr = win_rate > 0.55
        
        if high_vol and low_sharpe:
            return "volatile", 0.8, "Alta volatilidad, Sharpe bajo - mercado inestable"
        elif high_vol and good_wr:
            return "trending", 0.7, "Alta volatilidad pero buen win rate - tendencias explotables"
        elif not high_vol and good_wr and sharpe > 1:
            return "bull", 0.75, "Baja volatilidad, buen win rate, Sharpe alto - entorno favorable"
        elif not high_vol and low_sharpe and win_rate < 0.45:
            return "bear", 0.7, "Baja volatilidad pero mal win rate - entorno adverso"
        elif high_corr and not high_vol:
            return "mean_reverting", 0.65, "Alta correlación, baja volatilidad - mean reversion"
        elif not high_vol and not low_sharpe:
            return "calm", 0.6, "Baja volatilidad, Sharpe decente - mercado tranquilo"
        else:
            return "uncertain", 0.5, "Régimen mixto/incierto"

    # ===================== STRESS TESTING =====================

    def run_stress_test(self, portfolio_id: int, 
                         scenario: str = "market_crash",
                         runs: int = 2000) -> StressTestResult:
        """Ejecuta stress test Monte Carlo para un escenario."""
        
        perf = self.paper_engine.get_performance(portfolio_id, days=90)
        bankroll = perf.current_bankroll
        
        # Parámetros base del portfolio
        daily_returns = self._get_daily_returns(portfolio_id, days=90)
        
        if len(daily_returns) < 10:
            daily_returns = np.random.normal(0, 10, 100)  # Fallback
        
        base_mean = np.mean(daily_returns)
        base_std = np.std(daily_returns)
        
        # Configurar escenario
        scenarios = {
            "market_crash": {"mean_mult": 0.1, "std_mult": 3.0, "correlation_boost": 0.5},
            "high_volatility": {"mean_mult": 0.5, "std_mult": 2.5, "correlation_boost": 0.3},
            "correlated_losses": {"mean_mult": 0.3, "std_mult": 2.0, "correlation_boost": 0.7},
            "liquidity_crisis": {"mean_mult": 0.2, "std_mult": 2.5, "correlation_boost": 0.6},
            "normal": {"mean_mult": 1.0, "std_mult": 1.0, "correlation_boost": 0.0},
        }
        
        params = scenarios.get(scenario, scenarios["normal"])
        
        scenario_mean = base_mean * params["mean_mult"]
        scenario_std = base_std * params["std_mult"]
        
        # Simulación Monte Carlo
        final_bankrolls = []
        max_drawdowns = []
        ruin_count = 0
        
        for _ in range(runs):
            br = bankroll
            peak = br
            max_dd = 0
            
            for _ in range(30):  # 30 días
                daily_ret = np.random.normal(scenario_mean, scenario_std)
                br += daily_ret
                
                if br > peak:
                    peak = br
                dd = (peak - br) / peak if peak > 0 else 0
                if dd > max_dd:
                    max_dd = dd
                
                if br <= bankroll * 0.1:  # Ruin = 90% loss
                    ruin_count += 1
                    break
            
            final_bankrolls.append(br)
            max_drawdowns.append(max_dd)
        
        final_bankrolls = np.array(final_bankrolls)
        max_drawdowns = np.array(max_drawdowns)
        
        # Guardar resultado
        self.db.save_stress_test({
            "portfolio_id": portfolio_id,
            "scenario_name": scenario,
            "parameters": params,
            "results": {
                "max_drawdown": float(np.percentile(max_drawdowns, 95)),
                "var_95": float(np.percentile((bankroll - final_bankrolls) / bankroll * 100, 95)),
                "expected_shortfall": float(np.mean((bankroll - final_bankrolls[final_bankrolls < np.percentile(final_bankrolls, 5)]) / bankroll * 100)),
                "survival_probability": float(1 - ruin_count / runs),
                "median_final_bankroll": float(np.median(final_bankrolls)),
                "worst_case_bankroll": float(np.min(final_bankrolls)),
                "recovery_time_days": self._estimate_recovery_time(final_bankrolls, bankroll),
            },
            "runs": runs,
        })
        
        return StressTestResult(
            scenario_name=scenario,
            max_drawdown=float(np.percentile(max_drawdowns, 95)),
            var_95=float(np.percentile((bankroll - final_bankrolls) / bankroll * 100, 95)),
            expected_shortfall=float(np.mean((bankroll - final_bankrolls[final_bankrolls < np.percentile(final_bankrolls, 5)]) / bankroll * 100)),
            survival_probability=float(1 - ruin_count / runs),
            median_final_bankroll=float(np.median(final_bankrolls)),
            worst_case_bankroll=float(np.min(final_bankrolls)),
            recovery_time_days=self._estimate_recovery_time(final_bankrolls, bankroll),
        )

    def _get_daily_returns(self, portfolio_id: int, days: int) -> np.ndarray:
        """Obtiene returns diarios del portfolio."""
        picks = self.paper_engine.get_picks(portfolio_id, status="settled", limit=1000)
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        daily = defaultdict(float)
        for p in picks:
            if p.get("settled_at", "") >= cutoff:
                day = p["settled_at"][:10]
                daily[day] += p.get("pnl", 0)
        
        return np.array([daily[d] for d in sorted(daily.keys())])

    def _estimate_recovery_time(self, final_bankrolls: np.ndarray, initial: float) -> float:
        """Estima días para recuperar drawdown."""
        below = final_bankrolls[final_bankrolls < initial]
        if len(below) == 0:
            return 0
        avg_loss = np.mean(initial - below)
        # Asumiendo retorno diario promedio
        daily_return = max(1, np.mean(final_bankrolls) - initial) / 30
        return avg_loss / daily_return if daily_return > 0 else 999

    # ===================== MONTE CARLO PORTFOLIO =====================

    def run_monte_carlo_portfolio(self, portfolio_id: int,
                                   num_sims: int = 2000,
                                   horizon_days: int = 90) -> Dict:
        """Simulación Monte Carlo completa del portfolio."""
        
        perf = self.paper_engine.get_performance(portfolio_id, days=90)
        bankroll = perf.current_bankroll
        daily_returns = self._get_daily_returns(portfolio_id, days=90)
        
        if len(daily_returns) < 10:
            daily_returns = np.random.normal(2, 15, 100)
        
        mean_ret = np.mean(daily_returns)
        std_ret = np.std(daily_returns)
        
        paths = []
        for _ in range(num_sims):
            path = [bankroll]
            br = bankroll
            for _ in range(horizon_days):
                br += np.random.normal(mean_ret, std_ret)
                path.append(max(br, 0))
            paths.append(path)
        
        paths = np.array(paths)
        
        # Métricas agregadas
        final_values = paths[:, -1]
        median_growth = (np.median(final_values) - bankroll) / bankroll
        pct_profitable = np.mean(final_values > bankroll)
        max_dd_paths = []
        
        for path in paths:
            peak = path[0]
            max_dd = 0
            for v in path:
                if v > peak:
                    peak = v
                dd = (peak - v) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)
            max_dd_paths.append(max_dd)
        
        return {
            "paths": paths[:50].tolist(),  # Primeros 50 para visualización
            "median_growth": round(median_growth * 100, 2),
            "mean_growth": round((np.mean(final_values) - bankroll) / bankroll * 100, 2),
            "pct_profitable": round(pct_profitable * 100, 1),
            "max_drawdown_median": round(np.median(max_dd_paths) * 100, 1),
            "max_drawdown_p95": round(np.percentile(max_dd_paths, 95) * 100, 1),
            "risk_of_ruin": round(np.mean(final_values < bankroll * 0.1) * 100, 1),
            "final_bankroll_p10": round(np.percentile(final_values, 10), 2),
            "final_bankroll_p50": round(np.percentile(final_values, 50), 2),
            "final_bankroll_p90": round(np.percentile(final_values, 90), 2),
            "var_95": round(np.percentile((bankroll - final_values) / bankroll * 100, 95), 2),
            "expected_shortfall": round(np.mean((bankroll - final_values[final_values < np.percentile(final_values, 5)]) / bankroll * 100), 2),
        }

    # ===================== FACTOR ANALYSIS =====================

    def run_factor_analysis(self, portfolio_id: int, 
                             period_days: int = 90,
                             method: str = "pca") -> Dict:
        """Análisis de factores (PCA/Regresión) para drivers de rendimiento."""
        
        perf = self.paper_engine.get_performance(portfolio_id, days=period_days)
        picks = self.paper_engine.get_picks(portfolio_id, status="settled", limit=1000)
        
        cutoff = (datetime.now() - timedelta(days=period_days)).isoformat()
        picks = [p for p in picks if p.get("settled_at", "") >= cutoff]
        
        if len(picks) < 30:
            return {"error": "Insuficientes datos para factor analysis"}
        
        # Construir matriz de features
        df = pd.DataFrame(picks)
        
        # Features numéricas
        feature_cols = []
        for col in ["odds", "probability", "edge", "kelly_stake_pct", "stake_units"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                if df[col].notna().sum() > len(df) * 0.5:
                    feature_cols.append(col)
        
        # Features categóricas (one-hot)
        for col in ["market", "league", "source"]:
            if col in df.columns:
                dummies = pd.get_dummies(df[col], prefix=col, drop_first=True)
                df = pd.concat([df, dummies], axis=1)
                feature_cols.extend(dummies.columns.tolist())
        
        # Target: P&L
        df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce")
        
        # Limpiar
        clean_cols = ["pnl"] + feature_cols
        df_clean = df[clean_cols].dropna()
        
        if len(df_clean) < 20:
            return {"error": "Datos insuficientes tras limpieza"}
        
        X = df_clean[feature_cols].values
        y = df_clean["pnl"].values
        
        if method == "pca":
            return self._pca_analysis(X, y, feature_cols)
        else:
            return self._regression_analysis(X, y, feature_cols, portfolio_id, period_days)

    def _pca_analysis(self, X: np.ndarray, y: np.ndarray, feature_names: List[str]) -> Dict:
        """PCA para identificar factores principales."""
        # Normalizar
        X_std = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-8)
        
        # PCA
        n_components = min(5, X.shape[1], X.shape[0] - 1)
        pca = PCA(n_components=n_components)
        X_pca = pca.fit_transform(X_std)
        
        # Regresar y sobre componentes principales
        reg = LinearRegression().fit(X_pca, y)
        r2 = reg.score(X_pca, y)
        
        # Contribución de cada feature original a cada componente
        loadings = pca.components_.T  # (n_features, n_components)
        
        factors = {}
        for i in range(n_components):
            factor_name = f"PC{i+1}"
            top_features = sorted(
                zip(feature_names, loadings[:, i]),
                key=lambda x: abs(x[1]),
                reverse=True
            )[:5]
            
            factors[factor_name] = {
                "explained_variance": round(pca.explained_variance_ratio_[i] * 100, 1),
                "coefficient": round(reg.coef_[i], 4),
                "top_features": [
                    {"name": f, "loading": round(l, 3)} for f, l in top_features
                ],
            }
        
        return {
            "method": "pca",
            "r_squared": round(r2, 3),
            "n_components": n_components,
            "factors": factors,
            "total_explained_variance": round(sum(pca.explained_variance_ratio_) * 100, 1),
        }

    def _regression_analysis(self, X: np.ndarray, y: np.ndarray, 
                              feature_names: List[str],
                              portfolio_id: int, period_days: int) -> Dict:
        """Regresión lineal con selección de features."""
        # Normalizar
        X_std = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-8)
        
        # Ridge regression para estabilidad
        from sklearn.linear_model import RidgeCV
        reg = RidgeCV(alphas=[0.01, 0.1, 1.0, 10.0, 100.0]).fit(X_std, y)
        r2 = reg.score(X_std, y)
        
        # Coeficientes
        coef_dict = dict(zip(feature_names, reg.coef_))
        sorted_coef = sorted(coef_dict.items(), key=lambda x: abs(x[1]), reverse=True)
        
        factors = {}
        for name, coef in sorted_coef[:10]:
            # t-stat aproximado
            t_stat = abs(coef) / (np.std(X_std[:, feature_names.index(name)]) + 1e-8) * np.sqrt(len(y))
            p_val = 2 * (1 - stats.t.cdf(t_stat, len(y) - len(feature_names) - 1))
            
            factors[name] = {
                "exposure": round(coef, 4),
                "contribution_pct": round(abs(coef) / sum(abs(reg.coef_)) * 100, 1) if sum(abs(reg.coef_)) > 0 else 0,
                "t_stat": round(t_stat, 2),
                "p_value": round(p_val, 4),
                "significant": p_val < 0.05,
            }
        
        # Guardar en DB
        self.db.save_factor_analysis({
            "portfolio_id": portfolio_id,
            "period_start": (datetime.now() - timedelta(days=period_days)).isoformat(),
            "period_end": datetime.now().isoformat(),
            "factors": factors,
            "r_squared": r2,
            "method": "ridge_regression",
        })
        
        return {
            "method": "ridge_regression",
            "r_squared": round(r2, 3),
            "alpha": reg.alpha_,
            "factors": factors,
            "n_features": len(feature_names),
        }

    # ===================== REPORT GENERATION =====================

    def generate_full_report(self, portfolio_id: int, period_days: int = 30) -> Dict:
        """Genera reporte completo de analytics."""
        
        logger.info(f"Generando reporte completo para portfolio {portfolio_id}")
        
        attribution = self.run_performance_attribution(portfolio_id, period_days)
        regime = self.detect_market_regime(portfolio_id, lookback_days=60)
        stress_normal = self.run_stress_test(portfolio_id, "normal", runs=1000)
        stress_crash = self.run_stress_test(portfolio_id, "market_crash", runs=1000)
        mc = self.run_monte_carlo_portfolio(portfolio_id, num_sims=1000, horizon_days=90)
        factors = self.run_factor_analysis(portfolio_id, period_days=90, method="regression")
        
        report = {
            "portfolio_id": portfolio_id,
            "period_days": period_days,
            "generated_at": datetime.now().isoformat(),
            "attribution": {
                "total_roi": attribution.total_roi,
                "total_pnl": attribution.total_pnl,
                "by_model": attribution.by_model,
                "by_league": attribution.by_league,
                "by_market": attribution.by_market,
                "by_timing": attribution.by_timing,
                "by_luck": attribution.by_luck,
                "selection_effect": attribution.selection_effect,
                "allocation_effect": attribution.allocation_effect,
                "interaction_effect": attribution.interaction_effect,
            },
            "regime": {
                "type": regime.regime_type,
                "confidence": regime.confidence,
                "metrics": regime.metrics,
                "description": regime.description,
            },
            "stress_tests": {
                "normal": {
                    "max_drawdown": stress_normal.max_drawdown,
                    "var_95": stress_normal.var_95,
                    "survival_probability": stress_normal.survival_probability,
                },
                "market_crash": {
                    "max_drawdown": stress_crash.max_drawdown,
                    "var_95": stress_crash.var_95,
                    "survival_probability": stress_crash.survival_probability,
                },
            },
            "monte_carlo": {
                "median_growth": mc["median_growth"],
                "pct_profitable": mc["pct_profitable"],
                "max_drawdown_median": mc["max_drawdown_median"],
                "max_drawdown_p95": mc["max_drawdown_p95"],
                "risk_of_ruin": mc["risk_of_ruin"],
                "var_95": mc["var_95"],
                "expected_shortfall": mc["expected_shortfall"],
            },
            "factor_analysis": factors,
        }
        
        # Resumen ejecutivo
        summary = {
            "key_metrics": {
                "roi": attribution.total_roi,
                "current_regime": regime.regime_type,
                "regime_confidence": regime.confidence,
                "survival_normal": stress_normal.survival_probability,
                "survival_crash": stress_crash.survival_probability,
                "prob_profitable_90d": mc["pct_profitable"],
                "risk_of_ruin": mc["risk_of_ruin"],
            },
            "top_contributors": [
                {"factor": k, "roi": v["roi"], "contrib": v["contribution_pct"]}
                for k, v in list(attribution.by_model.items())[:3]
            ],
            "risk_alerts": self._generate_risk_alerts(regime, stress_crash, mc),
        }
        
        # Guardar reporte
        self.db.save_analytics_report({
            "report_type": "full",
            "portfolio_id": portfolio_id,
            "period_start": (datetime.now() - timedelta(days=period_days)).isoformat(),
            "period_end": datetime.now().isoformat(),
            "data": report,
            "summary": summary,
        })
        
        return {"report": report, "summary": summary}

    def _generate_risk_alerts(self, regime: RegimeInfo, 
                               stress_crash: StressTestResult, mc: Dict) -> List[str]:
        alerts = []
        
        if regime.regime_type in ["bear", "volatile"]:
            alerts.append(f"⚠️ Régimen adverso detectado: {regime.regime_type} ({regime.confidence:.0%} confianza)")
        
        if stress_crash.survival_probability < 0.9:
            alerts.append(f"🔴 Stress test crash: supervivencia {stress_crash.survival_probability:.0%}")
        
        if mc["risk_of_ruin"] > 5:
            alerts.append(f"📉 Risk of ruin en 90d: {mc['risk_of_ruin']:.1f}%")
        
        if mc["max_drawdown_p95"] > 30:
            alerts.append(f"📉 Max DD P95 en 90d: {mc['max_drawdown_p95']:.1f}%")
        
        return alerts


def create_analytics_engine(db: Database = None) -> AnalyticsEngine:
    return AnalyticsEngine(db)