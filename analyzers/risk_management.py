"""Advanced Risk Management para Paper Trading.

Incluye:
- Límites de exposición por liga/mercado/equipo
- Análisis de correlación entre picks activos
- Stop-loss dinámico y max drawdown alerts
- Portfolio optimization (Kelly fraccionado con constraints)
- Risk monitoring automatizado con alertas
"""

import logging
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Set
import json

from storage.database import Database

logger = logging.getLogger(__name__)


@dataclass
class RiskLimit:
    limit_type: str
    limit_value: float
    current_value: float
    utilization_pct: float
    status: str  # ok, warning, breach


@dataclass
class CorrelationPair:
    pick_id_a: int
    pick_id_b: int
    match_a: str
    match_b: str
    correlation: float
    shared_team: bool
    shared_league: bool
    shared_market: bool


@dataclass
class RiskMetrics:
    portfolio_id: int
    bankroll: float
    total_exposure: float
    exposure_pct: float
    max_drawdown: float
    current_drawdown: float
    sharpe_ratio: float
    var_95: float  # Value at Risk 95%
    limits: List[RiskLimit]
    correlations: List[CorrelationPair]
    alerts: List[dict]


class RiskManager:
    """Gestión avanzada de riesgo para portfolios de paper trading."""

    def __init__(self, db: Database = None):
        self.db = db or Database()
        
        # Límites por defecto
        self.default_limits = {
            "max_exposure_pct": 0.30,        # 30% bankroll máximo en picks simultáneos
            "max_exposure_league_pct": 0.15,  # 15% por liga
            "max_exposure_market_pct": 0.20,  # 20% por mercado
            "max_exposure_team_pct": 0.10,    # 10% por equipo
            "max_correlation": 0.70,          # Correlación máxima entre picks
            "max_drawdown_pct": 0.20,         # 20% max drawdown
            "stop_loss_pct": 0.10,            # 10% stop loss desde peak
            "max_concurrent_picks": 20,       # Máximo picks pendientes
            "min_kelly_fraction": 0.10,       # Kelly mínimo
            "max_kelly_fraction": 0.50,       # Kelly máximo
        }

    def analyze_portfolio_risk(self, portfolio_id: int) -> RiskMetrics:
        """Análisis completo de riesgo del portfolio."""
        portfolio = self.db.get_portfolio(portfolio_id)
        if not portfolio:
            raise ValueError("Portfolio no encontrado")
        
        bankroll = portfolio["current_bankroll"]
        initial = portfolio["initial_bankroll"]
        
        # Obtener picks pendientes
        pending_picks = self.db.get_pending_picks_for_risk(portfolio_id)
        
        # Calcular exposición total
        total_exposure = sum(p["stake_units"] for p in pending_picks)
        exposure_pct = (total_exposure / bankroll * 100) if bankroll > 0 else 0
        
        # Exposición por liga
        exposure_by_league = {}
        exposure_by_market = {}
        exposure_by_team = {}
        
        for pick in pending_picks:
            stake = pick["stake_units"]
            league = pick["league"]
            market = pick["market"]
            home = pick["home_team"]
            away = pick["away_team"]
            
            exposure_by_league[league] = exposure_by_league.get(league, 0) + stake
            exposure_by_market[market] = exposure_by_market.get(market, 0) + stake
            exposure_by_team[home] = exposure_by_team.get(home, 0) + stake
            exposure_by_team[away] = exposure_by_team.get(away, 0) + stake
        
        # Límites de riesgo
        limits = self._check_limits(portfolio_id, bankroll, total_exposure,
                                     exposure_by_league, exposure_by_market, exposure_by_team,
                                     len(pending_picks))
        
        # Correlaciones entre picks
        correlations = self._calculate_correlations(portfolio_id, pending_picks)
        
        # Métricas de performance para VaR y Sharpe
        perf = self.db.get_portfolio_performance(portfolio_id, days=30)
        sharpe = perf.get("sharpe", 0)
        max_dd = perf.get("max_drawdown", 0)
        
        # Current drawdown
        current_dd = 0
        if bankroll < initial:
            current_dd = (initial - bankroll) / initial * 100
        
        # VaR 95% (simplificado: peor caso histórico * exposición)
        var_95 = max_dd / 100 * total_exposure if max_dd > 0 else 0
        
        # Alertas activas
        alerts = self.db.get_risk_alerts(portfolio_id, acknowledged=0, limit=10)
        
        return RiskMetrics(
            portfolio_id=portfolio_id,
            bankroll=bankroll,
            total_exposure=round(total_exposure, 2),
            exposure_pct=round(exposure_pct, 2),
            max_drawdown=round(max_dd, 2),
            current_drawdown=round(current_dd, 2),
            sharpe_ratio=round(sharpe, 2),
            var_95=round(var_95, 2),
            limits=limits,
            correlations=correlations,
            alerts=alerts,
        )

    def _check_limits(self, portfolio_id: int, bankroll: float, total_exposure: float,
                       by_league: Dict, by_market: Dict, by_team: Dict,
                       num_picks: int) -> List[RiskLimit]:
        """Verifica todos los límites de riesgo configurados."""
        limits = []
        
        # Obtener límites personalizados del portfolio
        db_limits = {l["limit_type"]: l["limit_value"] for l in self.db.get_risk_limits(portfolio_id)}
        
        def get_limit(key: str, default: float) -> float:
            return db_limits.get(key, default)
        
        # 1. Exposición total
        max_exp_pct = get_limit("max_exposure_pct", self.default_limits["max_exposure_pct"])
        max_exp = bankroll * max_exp_pct
        util = (total_exposure / max_exp * 100) if max_exp > 0 else 0
        limits.append(RiskLimit(
            limit_type="max_exposure_pct",
            limit_value=round(max_exp, 2),
            current_value=round(total_exposure, 2),
            utilization_pct=round(util, 1),
            status="breach" if util >= 100 else "warning" if util >= 80 else "ok",
        ))
        
        # 2. Por liga
        max_league_pct = get_limit("max_exposure_league_pct", self.default_limits["max_exposure_league_pct"])
        max_league = bankroll * max_league_pct
        for league, exp in by_league.items():
            util = (exp / max_league * 100) if max_league > 0 else 0
            limits.append(RiskLimit(
                limit_type=f"league_{league}",
                limit_value=round(max_league, 2),
                current_value=round(exp, 2),
                utilization_pct=round(util, 1),
                status="breach" if util >= 100 else "warning" if util >= 80 else "ok",
            ))
        
        # 3. Por mercado
        max_market_pct = get_limit("max_exposure_market_pct", self.default_limits["max_exposure_market_pct"])
        max_market = bankroll * max_market_pct
        for market, exp in by_market.items():
            util = (exp / max_market * 100) if max_market > 0 else 0
            limits.append(RiskLimit(
                limit_type=f"market_{market}",
                limit_value=round(max_market, 2),
                current_value=round(exp, 2),
                utilization_pct=round(util, 1),
                status="breach" if util >= 100 else "warning" if util >= 80 else "ok",
            ))
        
        # 4. Por equipo
        max_team_pct = get_limit("max_exposure_team_pct", self.default_limits["max_exposure_team_pct"])
        max_team = bankroll * max_team_pct
        for team, exp in by_team.items():
            util = (exp / max_team * 100) if max_team > 0 else 0
            if util >= 50:  # Solo reportar si > 50%
                limits.append(RiskLimit(
                    limit_type=f"team_{team}",
                    limit_value=round(max_team, 2),
                    current_value=round(exp, 2),
                    utilization_pct=round(util, 1),
                    status="breach" if util >= 100 else "warning" if util >= 80 else "ok",
                ))
        
        # 5. Número de picks concurrentes
        max_picks = int(get_limit("max_concurrent_picks", self.default_limits["max_concurrent_picks"]))
        util = (num_picks / max_picks * 100) if max_picks > 0 else 0
        limits.append(RiskLimit(
            limit_type="max_concurrent_picks",
            limit_value=max_picks,
            current_value=num_picks,
            utilization_pct=round(util, 1),
            status="breach" if util >= 100 else "warning" if util >= 80 else "ok",
        ))
        
        # 6. Drawdown actual
        max_dd_pct = get_limit("max_drawdown_pct", self.default_limits["max_drawdown_pct"])
        # Se calcula en analyze_portfolio_risk
        
        # Actualizar valores actuales en BD
        for limit in limits:
            if limit.limit_type in ["max_exposure_pct", "max_concurrent_picks"] or \
               limit.limit_type.startswith("league_") or limit.limit_type.startswith("market_"):
                self.db.update_risk_limit_current(portfolio_id, limit.limit_type, limit.current_value)
        
        return limits

    def _calculate_correlations(self, portfolio_id: int, pending_picks: List[dict]) -> List[CorrelationPair]:
        """Calcula correlaciones entre picks pendientes."""
        correlations = []
        
        if len(pending_picks) < 2:
            return correlations
        
        for i, pick_a in enumerate(pending_picks):
            for pick_b in pending_picks[i+1:]:
                corr = self._estimate_correlation(pick_a, pick_b)
                
                if corr >= 0.3:  # Solo correlaciones significativas
                    shared_team = 1 if (pick_a["home_team"] in [pick_b["home_team"], pick_b["away_team"]] or
                                        pick_a["away_team"] in [pick_b["home_team"], pick_b["away_team"]]) else 0
                    shared_league = 1 if pick_a["league"] == pick_b["league"] else 0
                    shared_market = 1 if pick_a["market"] == pick_b["market"] else 0
                    
                    # Guardar en BD
                    self.db.save_correlation(
                        portfolio_id, pick_a["id"], pick_b["id"], corr,
                        shared_team, shared_league, shared_market
                    )
                    
                    correlations.append(CorrelationPair(
                        pick_id_a=pick_a["id"],
                        pick_id_b=pick_b["id"],
                        match_a=f"{pick_a['home_team']} vs {pick_a['away_team']}",
                        match_b=f"{pick_b['home_team']} vs {pick_b['away_team']}",
                        correlation=round(corr, 3),
                        shared_team=bool(shared_team),
                        shared_league=bool(shared_league),
                        shared_market=bool(shared_market),
                    ))
        
        return correlations

    def _estimate_correlation(self, pick_a: dict, pick_b: dict) -> float:
        """Estima correlación entre dos picks basado en factores compartidos."""
        corr = 0.0
        
        # Mismo equipo = correlación alta
        teams_a = {pick_a["home_team"], pick_a["away_team"]}
        teams_b = {pick_b["home_team"], pick_b["away_team"]}
        shared_teams = teams_a & teams_b
        
        if len(shared_teams) == 1:
            corr += 0.4  # Un equipo en común
        elif len(shared_teams) == 2:
            corr += 0.8  # Mismo partido (diferente mercado)
        
        # Misma liga
        if pick_a["league"] == pick_b["league"]:
            corr += 0.15
        
        # Mismo mercado
        if pick_a["market"] == pick_b["market"]:
            corr += 0.2
        
        # Mismo resultado esperado (ambos favoritos locales, etc.)
        if pick_a["choice"] == pick_b["choice"] and pick_a["market"] == pick_b["market"]:
            corr += 0.1
        
        # Partidos en fechas cercanas (mismo día = mayor correlación)
        try:
            kickoff_a = datetime.fromisoformat(pick_a["kickoff"].replace("Z", "+00:00"))
            kickoff_b = datetime.fromisoformat(pick_b["kickoff"].replace("Z", "+00:00"))
            days_diff = abs((kickoff_a - kickoff_b).days)
            if days_diff == 0:
                corr += 0.15
            elif days_diff <= 2:
                corr += 0.05
        except:
            pass
        
        return min(corr, 1.0)

    def check_and_alert(self, portfolio_id: int) -> List[dict]:
        """Verifica límites y genera alertas si es necesario."""
        metrics = self.analyze_portfolio_risk(portfolio_id)
        alerts_created = []
        
        # Verificar límites en breach
        for limit in metrics.limits:
            if limit.status == "breach":
                alert_type = self._limit_type_to_alert(limit.limit_type)
                severity = "critical" if limit.utilization_pct >= 120 else "warning"
                
                message = self._generate_alert_message(limit)
                
                alert_id = self.db.create_risk_alert(
                    portfolio_id, alert_type, severity, message,
                    metric_value=limit.current_value,
                    limit_value=limit.limit_value,
                )
                alerts_created.append({"id": alert_id, "type": alert_type, "severity": severity, "message": message})
            
            elif limit.status == "warning":
                # Solo alertar warning si es la primera vez o hace > 24h
                alert_type = self._limit_type_to_alert(limit.limit_type)
                recent = self.db.query(
                    """SELECT * FROM risk_alerts 
                       WHERE portfolio_id = ? AND alert_type = ? AND severity = 'warning'
                       AND created_at > datetime('now', '-24 hours')""",
                    (portfolio_id, alert_type),
                )
                if not recent:
                    message = self._generate_alert_message(limit)
                    alert_id = self.db.create_risk_alert(
                        portfolio_id, alert_type, "warning", message,
                        metric_value=limit.current_value,
                        limit_value=limit.limit_value,
                    )
                    alerts_created.append({"id": alert_id, "type": alert_type, "severity": "warning", "message": message})
        
        # Verificar correlaciones altas
        max_corr = self.default_limits["max_correlation"]
        for corr_pair in metrics.correlations:
            if corr_pair.correlation >= max_corr:
                recent = self.db.query(
                    """SELECT * FROM risk_alerts 
                       WHERE portfolio_id = ? AND alert_type = 'correlation_high'
                       AND created_at > datetime('now', '-6 hours')""",
                    (portfolio_id,),
                )
                if not recent:
                    message = (f"⚠️ Alta correlación ({corr_pair.correlation:.0%}) entre: "
                              f"{corr_pair.match_a} ↔ {corr_pair.match_b}")
                    if corr_pair.shared_team:
                        message += " (equipo compartido)"
                    if corr_pair.shared_league:
                        message += " (misma liga)"
                    if corr_pair.shared_market:
                        message += " (mismo mercado)"
                    
                    alert_id = self.db.create_risk_alert(
                        portfolio_id, "correlation_high", "warning", message,
                        metric_value=corr_pair.correlation,
                        limit_value=max_corr,
                    )
                    alerts_created.append({"id": alert_id, "type": "correlation_high", "severity": "warning", "message": message})
        
        # Verificar drawdown
        if metrics.current_drawdown >= self.default_limits["max_drawdown_pct"] * 100:
            recent = self.db.query(
                """SELECT * FROM risk_alerts 
                   WHERE portfolio_id = ? AND alert_type = 'drawdown_warning'
                   AND created_at > datetime('now', '-12 hours')""",
                (portfolio_id,),
            )
            if not recent:
                message = (f"📉 Drawdown actual: {metrics.current_drawdown:.1f}% "
                          f"(límite: {self.default_limits['max_drawdown_pct']*100:.0f}%)")
                alert_id = self.db.create_risk_alert(
                    portfolio_id, "drawdown_warning", "critical", message,
                    metric_value=metrics.current_drawdown,
                    limit_value=self.default_limits["max_drawdown_pct"] * 100,
                )
                alerts_created.append({"id": alert_id, "type": "drawdown_warning", "severity": "critical", "message": message})
        
        # Verificar stop loss
        if metrics.current_drawdown >= self.default_limits["stop_loss_pct"] * 100:
            recent = self.db.query(
                """SELECT * FROM risk_alerts 
                   WHERE portfolio_id = ? AND alert_type = 'stop_loss_triggered'
                   AND created_at > datetime('now', '-24 hours')""",
                (portfolio_id,),
            )
            if not recent:
                message = (f"🛑 STOP LOSS ACTIVADO: Drawdown {metrics.current_drawdown:.1f}% "
                          f"≥ {self.default_limits['stop_loss_pct']*100:.0f}%. "
                          f"Considerar reducir exposición o pausar nuevos picks.")
                alert_id = self.db.create_risk_alert(
                    portfolio_id, "stop_loss_triggered", "critical", message,
                    metric_value=metrics.current_drawdown,
                    limit_value=self.default_limits["stop_loss_pct"] * 100,
                )
                alerts_created.append({"id": alert_id, "type": "stop_loss_triggered", "severity": "critical", "message": message})
        
        return alerts_created

    def _limit_type_to_alert(self, limit_type: str) -> str:
        if limit_type == "max_exposure_pct":
            return "exposure_breach"
        elif limit_type.startswith("league_"):
            return "league_exposure_breach"
        elif limit_type.startswith("market_"):
            return "market_exposure_breach"
        elif limit_type.startswith("team_"):
            return "team_exposure_breach"
        elif limit_type == "max_concurrent_picks":
            return "concurrent_picks_breach"
        return "limit_breach"

    def _generate_alert_message(self, limit: RiskLimit) -> str:
        if limit.limit_type == "max_exposure_pct":
            return f"📊 Exposición total: {limit.current_value:.2f}€ / {limit.limit_value:.2f}€ ({limit.utilization_pct:.0f}%)"
        elif limit.limit_type.startswith("league_"):
            league = limit.limit_type.replace("league_", "")
            return f"🏆 Liga {league}: {limit.current_value:.2f}€ / {limit.limit_value:.2f}€ ({limit.utilization_pct:.0f}%)"
        elif limit.limit_type.startswith("market_"):
            market = limit.limit_type.replace("market_", "").upper()
            return f"📈 Mercado {market}: {limit.current_value:.2f}€ / {limit.limit_value:.2f}€ ({limit.utilization_pct:.0f}%)"
        elif limit.limit_type.startswith("team_"):
            team = limit.limit_type.replace("team_", "")
            return f"⚽ Equipo {team}: {limit.current_value:.2f}€ / {limit.limit_value:.2f}€ ({limit.utilization_pct:.0f}%)"
        elif limit.limit_type == "max_concurrent_picks":
            return f"📋 Picks concurrentes: {int(limit.current_value)} / {int(limit.limit_value)} ({limit.utilization_pct:.0f}%)"
        return f"Límite {limit.limit_type}: {limit.utilization_pct:.0f}%"

    def optimize_kelly_for_risk(self, portfolio_id: int, 
                                 probability: float, odds: float,
                                 base_kelly_fraction: float = 0.25) -> float:
        """Ajusta fracción Kelly basada en riesgo actual del portfolio."""
        metrics = self.analyze_portfolio_risk(portfolio_id)
        
        # Factor de reducción por exposición
        exposure_factor = 1.0
        if metrics.exposure_pct > 20:
            exposure_factor = max(0.3, 1 - (metrics.exposure_pct - 20) / 100)
        
        # Factor por drawdown
        dd_factor = 1.0
        if metrics.current_drawdown > 5:
            dd_factor = max(0.2, 1 - metrics.current_drawdown / 50)
        
        # Factor por correlación alta
        corr_factor = 1.0
        high_corr = [c for c in metrics.correlations if c.correlation > 0.6]
        if high_corr:
            corr_factor = max(0.5, 1 - len(high_corr) * 0.1)
        
        # Factor por número de picks
        picks_factor = 1.0
        if metrics.limits:
            picks_limit = next((l for l in metrics.limits if l.limit_type == "max_concurrent_picks"), None)
            if picks_limit and picks_limit.utilization_pct > 70:
                picks_factor = 0.7
        
        adjusted_kelly = base_kelly_fraction * exposure_factor * dd_factor * corr_factor * picks_factor
        
        # Aplicar límites configurados
        min_kelly = self.default_limits["min_kelly_fraction"]
        max_kelly = self.default_limits["max_kelly_fraction"]
        
        return round(max(min_kelly, min(max_kelly, adjusted_kelly)), 4)

    def get_risk_dashboard(self, portfolio_id: int) -> dict:
        """Dashboard completo de riesgo para frontend."""
        metrics = self.analyze_portfolio_risk(portfolio_id)
        portfolio = self.db.get_portfolio(portfolio_id)
        
        # Resumen de límites
        limits_summary = {
            "ok": sum(1 for l in metrics.limits if l.status == "ok"),
            "warning": sum(1 for l in metrics.limits if l.status == "warning"),
            "breach": sum(1 for l in metrics.limits if l.status == "breach"),
        }
        
        # Top correlaciones
        top_correlations = sorted(metrics.correlations, key=lambda x: x.correlation, reverse=True)[:10]
        
        # Alertas por severidad
        alerts_by_severity = {"critical": 0, "warning": 0, "info": 0}
        for alert in metrics.alerts:
            alerts_by_severity[alert["severity"]] = alerts_by_severity.get(alert["severity"], 0) + 1
        
        return {
            "portfolio": {
                "id": portfolio_id,
                "name": portfolio["name"],
                "bankroll": metrics.bankroll,
                "initial_bankroll": portfolio["initial_bankroll"],
            },
            "exposure": {
                "total": metrics.total_exposure,
                "pct": metrics.exposure_pct,
                "available": metrics.bankroll - metrics.total_exposure,
            },
            "risk_metrics": {
                "current_drawdown": metrics.current_drawdown,
                "max_drawdown": metrics.max_drawdown,
                "sharpe_ratio": metrics.sharpe_ratio,
                "var_95": metrics.var_95,
            },
            "limits_summary": limits_summary,
            "limits_detail": [
                {
                    "type": l.limit_type,
                    "limit": l.limit_value,
                    "current": l.current_value,
                    "utilization": l.utilization_pct,
                    "status": l.status,
                }
                for l in metrics.limits
            ],
            "correlations": [
                {
                    "match_a": c.match_a,
                    "match_b": c.match_b,
                    "correlation": c.correlation,
                    "shared_team": c.shared_team,
                    "shared_league": c.shared_league,
                    "shared_market": c.shared_market,
                }
                for c in metrics.correlations
            ],
            "top_correlations": [
                {
                    "match_a": c.match_a,
                    "match_b": c.match_b,
                    "correlation": c.correlation,
                    "factors": [
                        f for f, v in [
                            ("Equipo compartido", c.shared_team),
                            ("Misma liga", c.shared_league),
                            ("Mismo mercado", c.shared_market),
                        ] if v
                    ],
                }
                for c in top_correlations
            ],
            "alerts": metrics.alerts,
            "alerts_summary": alerts_by_severity,
        }

    def set_default_limits(self, portfolio_id: int) -> int:
        """Configura límites por defecto para un portfolio."""
        count = 0
        for limit_type, limit_value in self.default_limits.items():
            if limit_type in ["max_exposure_pct", "max_exposure_league_pct", 
                             "max_exposure_market_pct", "max_exposure_team_pct",
                             "max_drawdown_pct", "stop_loss_pct"]:
                self.db.set_risk_limit(portfolio_id, limit_type, limit_value)
                count += 1
        return count


def create_risk_manager(db: Database = None) -> RiskManager:
    return RiskManager(db)