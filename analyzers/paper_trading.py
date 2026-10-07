"""Paper Trading Engine - Simulador de apuestas sin dinero real.

Permite:
- Gestión de portfolios (bankroll, Kelly, límites)
- Colocación de picks manuales o desde recomendaciones
- Seguimiento de P&L en tiempo real
- Métricas de rendimiento (ROI, Sharpe, Max DD, Win Rate)
- Auto-settlement post-partido
"""

import logging
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
import json

from storage.database import Database
from predictors.engine import PredictionEngine

logger = logging.getLogger(__name__)


@dataclass
class PaperPick:
    """Representa una apuesta en paper trading."""
    id: Optional[int]
    portfolio_id: int
    match_id: str
    home_team: str
    away_team: str
    league: str
    kickoff: str
    market: str
    choice: str
    odds: float
    probability: float
    edge: Optional[float]
    kelly_stake_pct: Optional[float]
    stake_units: float
    status: str  # pending, won, lost, void, settled
    result: Optional[str]
    pnl: Optional[float]
    source: str
    confidence_score: Optional[int]
    placed_at: str


@dataclass
class PortfolioPerformance:
    """Métricas de rendimiento del portfolio."""
    total_picks: int
    wins: int
    losses: int
    pushes: int
    total_staked: float
    total_pnl: float
    roi_pct: float
    win_rate: float
    avg_odds: float
    sharpe: float
    max_drawdown: float
    current_bankroll: float
    by_market: Dict
    by_league: Dict


class PaperTradingEngine:
    """Motor principal de paper trading."""

    def __init__(self, db: Database = None):
        self.db = db or Database()
        self.prediction_engine = PredictionEngine()

    # ===================== PORTFOLIO MANAGEMENT =====================

    def create_portfolio(self, name: str = "Default", initial_bankroll: float = 1000,
                         kelly_fraction: float = 0.25, max_bet_pct: float = 0.05,
                         currency: str = "EUR") -> int:
        """Crea un nuevo portfolio de paper trading."""
        portfolio_id = self.db.create_portfolio(
            name=name, initial_bankroll=initial_bankroll,
            kelly_fraction=kelly_fraction, max_bet_pct=max_bet_pct,
            currency=currency
        )
        logger.info(f"Portfolio creado: {name} (ID: {portfolio_id}, Bankroll: {initial_bankroll} {currency})")
        return portfolio_id

    def get_portfolio(self, portfolio_id: int = None) -> Optional[dict]:
        """Obtiene portfolio por ID o el activo."""
        if portfolio_id:
            return self.db.get_portfolio(portfolio_id)
        return self.db.get_active_portfolio()

    def get_all_portfolios(self) -> List[dict]:
        return self.db.get_all_portfolios()

    def update_portfolio_settings(self, portfolio_id: int, kelly_fraction: float = None,
                                  max_bet_pct: float = None) -> None:
        portfolio = self.db.get_portfolio(portfolio_id)
        if not portfolio:
            raise ValueError("Portfolio no encontrado")
        
        kf = kelly_fraction if kelly_fraction is not None else portfolio["kelly_fraction"]
        mb = max_bet_pct if max_bet_pct is not None else portfolio["max_bet_pct"]
        
        # Update via raw SQL since we don't have a dedicated method
        self.db.execute(
            "UPDATE paper_portfolio SET kelly_fraction = ?, max_bet_pct = ?, updated_at = datetime('now') WHERE id = ?",
            (kf, mb, portfolio_id),
        )

    # ===================== PICK PLACEMENT =====================

    def calculate_kelly_stake(self, probability: float, odds: float, 
                              bankroll: float, kelly_fraction: float = 0.25,
                              max_bet_pct: float = 0.05) -> Tuple[float, float]:
        """Calcula stake usando Kelly Criterion fraccionado.
        
        Returns:
            (stake_pct, stake_units)
        """
        if probability <= 0 or odds <= 1:
            return 0.0, 0.0
        
        # Kelly: f = (p * b - q) / b donde b = odds - 1, q = 1 - p
        b = odds - 1
        p = probability
        q = 1 - p
        
        kelly_full = (p * b - q) / b if b > 0 else 0
        kelly_frac = max(0, kelly_full * kelly_fraction)
        kelly_capped = min(kelly_frac, max_bet_pct)
        
        stake_units = bankroll * kelly_capped
        return round(kelly_capped * 100, 4), round(stake_units, 2)

    def place_pick_from_recommendation(self, portfolio_id: int, 
                                        league_code: str, home_team: str, away_team: str,
                                        market: str, choice: str, odds: float,
                                        probability: float, edge: float = None,
                                        confidence_score: int = None,
                                        ensemble_weights: dict = None,
                                        expected_goals: dict = None,
                                        kelly_fraction: float = None,
                                        max_bet_pct: float = None) -> dict:
        """Coloca un pick basado en una recomendación del ensemble."""
        portfolio = self.db.get_portfolio(portfolio_id)
        if not portfolio:
            raise ValueError("Portfolio no encontrado")
        
        bankroll = portfolio["current_bankroll"]
        kf = kelly_fraction or portfolio["kelly_fraction"]
        mb = max_bet_pct or portfolio["max_bet_pct"]
        
        # Calcular stake Kelly
        kelly_stake_pct, stake_units = self.calculate_kelly_stake(
            probability, odds, bankroll, kf, mb
        )
        
        if stake_units <= 0:
            return {"success": False, "error": "Stake calculado es 0 (probabilidad/odds inválidas)"}
        
        if stake_units > bankroll:
            return {"success": False, "error": "Stake excede bankroll actual"}
        
        match_id = f"{home_team}_vs_{away_team}_{league_code}_{date.today().isoformat()}"
        
        pick_data = {
            "portfolio_id": portfolio_id,
            "match_id": match_id,
            "home_team": home_team,
            "away_team": away_team,
            "league": league_code,
            "kickoff": datetime.now().isoformat(),  # Se actualizará con datos reales
            "market": market,
            "choice": choice,
            "odds": odds,
            "probability": probability,
            "edge": edge,
            "kelly_stake_pct": kelly_stake_pct,
            "stake_units": stake_units,
            "status": "pending",
            "source": "recommendation",
            "confidence_score": confidence_score,
            "ensemble_weights": json.dumps(ensemble_weights) if ensemble_weights else None,
            "expected_goals": json.dumps(expected_goals) if expected_goals else None,
        }
        
        pick_id = self.db.place_pick(pick_data)
        
        # Actualizar bankroll (reservar stake)
        self.db.update_portfolio_bankroll(portfolio_id, bankroll - stake_units)
        
        logger.info(f"Pick colocado: {home_team} vs {away_team} | {market} {choice} @ {odds} | Stake: {stake_units:.2f}")
        
        return {
            "success": True,
            "pick_id": pick_id,
            "stake_units": stake_units,
            "kelly_stake_pct": kelly_stake_pct,
            "remaining_bankroll": bankroll - stake_units,
        }

    def place_manual_pick(self, portfolio_id: int, match_id: str,
                          home_team: str, away_team: str, league: str,
                          kickoff: str, market: str, choice: str,
                          odds: float, probability: float, stake_units: float,
                          source: str = "manual") -> dict:
        """Coloca un pick manual con stake fijo."""
        portfolio = self.db.get_portfolio(portfolio_id)
        if not portfolio:
            raise ValueError("Portfolio no encontrado")
        
        if stake_units > portfolio["current_bankroll"]:
            return {"success": False, "error": "Stake excede bankroll disponible"}
        
        pick_data = {
            "portfolio_id": portfolio_id,
            "match_id": match_id,
            "home_team": home_team,
            "away_team": away_team,
            "league": league,
            "kickoff": kickoff,
            "market": market,
            "choice": choice,
            "odds": odds,
            "probability": probability,
            "edge": probability - (1/odds) if odds > 0 else None,
            "kelly_stake_pct": (stake_units / portfolio["current_bankroll"] * 100) if portfolio["current_bankroll"] > 0 else 0,
            "stake_units": stake_units,
            "status": "pending",
            "source": source,
            "confidence_score": None,
            "ensemble_weights": None,
            "expected_goals": None,
        }
        
        pick_id = self.db.place_pick(pick_data)
        self.db.update_portfolio_bankroll(portfolio_id, portfolio["current_bankroll"] - stake_units)
        
        return {
            "success": True,
            "pick_id": pick_id,
            "stake_units": stake_units,
            "remaining_bankroll": portfolio["current_bankroll"] - stake_units,
        }

    # ===================== PICK MANAGEMENT =====================

    def get_picks(self, portfolio_id: int, status: str = None, limit: int = 100) -> List[dict]:
        return self.db.get_picks(portfolio_id, status, limit)

    def get_pending_picks(self, portfolio_id: int = None) -> List[dict]:
        return self.db.get_pending_picks(portfolio_id)

    def cancel_pick(self, pick_id: int) -> dict:
        """Cancela un pick pendiente y devuelve el stake al bankroll."""
        pick = self.db.get_pick(pick_id)
        if not pick:
            return {"success": False, "error": "Pick no encontrado"}
        
        if pick["status"] != "pending":
            return {"success": False, "error": f"Pick no está pendiente (status: {pick['status']})"}
        
        portfolio = self.db.get_portfolio(pick["portfolio_id"])
        self.db.update_pick_status(pick_id, "cancelled")
        self.db.update_portfolio_bankroll(pick["portfolio_id"], 
                                          portfolio["current_bankroll"] + pick["stake_units"])
        
        return {"success": True, "refunded": pick["stake_units"]}

    # ===================== SETTLEMENT =====================

    def determine_result(self, market: str, choice: str, actual_score: str) -> str:
        """Determina si un pick ganó, perdió o push basado en resultado real."""
        try:
            home_goals, away_goals = map(int, actual_score.split("-"))
        except:
            return "void"
        
        total_goals = home_goals + away_goals
        home_win = home_goals > away_goals
        draw = home_goals == away_goals
        away_win = home_goals < away_goals
        btts = home_goals > 0 and away_goals > 0
        
        if market == "h2h" or market == "1x2":
            if choice in ["1", "home", "home_win"] and home_win:
                return "win"
            elif choice in ["X", "draw"] and draw:
                return "win"
            elif choice in ["2", "away", "away_win"] and away_win:
                return "win"
            return "loss"
            
        elif market == "totals" or market == "over_under":
            # choice format: "over_2.5" or "under_2.5"
            if "_" in choice:
                side, line = choice.split("_")
                line = float(line)
            else:
                return "void"
            
            if side == "over" and total_goals > line:
                return "win"
            elif side == "under" and total_goals < line:
                return "win"
            elif total_goals == line:
                return "push"  # Exact line = push
            return "loss"
            
        elif market == "btts":
            if choice in ["yes", "btts_yes"] and btts:
                return "win"
            elif choice in ["no", "btts_no"] and not btts:
                return "win"
            return "loss"
            
        elif market in ["handicap", "asian_handicap", "spreads"]:
            # Simplificado: choice = "home_-1.5" o "away_+1.5"
            return "void"  # TODO: implementar handicap
            
        return "void"

    def settle_pick(self, pick_id: int, actual_score: str) -> dict:
        """Liquida un pick con el resultado real del partido."""
        pick = self.db.get_pick(pick_id)
        if not pick:
            return {"success": False, "error": "Pick no encontrado"}
        
        if pick["status"] != "pending":
            return {"success": False, "error": f"Pick ya liquidado (status: {pick['status']})"}
        
        # Determinar resultado
        result = self.determine_result(pick["market"], pick["choice"], actual_score)
        
        if result == "win":
            pnl = pick["stake_units"] * (pick["odds"] - 1)
        elif result == "loss":
            pnl = -pick["stake_units"]
        else:  # push or void
            pnl = 0
        
        roi_pct = (pnl / pick["stake_units"] * 100) if pick["stake_units"] > 0 else 0
        
        # Registrar liquidación
        self.db.settle_pick(pick_id, result, actual_score, pnl, roi_pct)
        
        # Actualizar bankroll (stake + pnl)
        portfolio = self.db.get_portfolio(pick["portfolio_id"])
        new_bankroll = portfolio["current_bankroll"] + pick["stake_units"] + pnl
        self.db.update_portfolio_bankroll(pick["portfolio_id"], new_bankroll)
        
        logger.info(f"Pick liquidado: {pick['home_team']} vs {pick['away_team']} | {result.upper()} | P&L: {pnl:.2f}")
        
        return {
            "success": True,
            "result": result,
            "pnl": round(pnl, 2),
            "roi_pct": round(roi_pct, 2),
            "new_bankroll": round(new_bankroll, 2),
        }

    def auto_settle_pending(self, portfolio_id: int = None) -> dict:
        """Liquida automáticamente picks pendientes cuyos partidos ya terminaron.
        
        Nota: Requiere integración con API de resultados reales.
        Por ahora marca como 'void' los picks de partidos pasados sin resultado.
        """
        pending = self.db.get_pending_picks(portfolio_id)
        settled = 0
        voided = 0
        
        for pick in pending:
            try:
                kickoff = datetime.fromisoformat(pick["kickoff"].replace("Z", "+00:00"))
                if kickoff < datetime.now() - timedelta(hours=3):  # Partido debería haber terminado
                    # TODO: Obtener resultado real de API-Football
                    # Por ahora: void si no tenemos resultado
                    self.db.update_pick_status(pick["id"], "void", "void", 0, datetime.now().isoformat())
                    
                    # Devolver stake
                    portfolio = self.db.get_portfolio(pick["portfolio_id"])
                    self.db.update_portfolio_bankroll(pick["portfolio_id"], 
                                                      portfolio["current_bankroll"] + pick["stake_units"])
                    voided += 1
            except Exception as e:
                logger.warning(f"Error auto-settling pick {pick['id']}: {e}")
        
        return {"settled": settled, "voided": voided, "checked": len(pending)}

    # ===================== PERFORMANCE =====================

    def get_performance(self, portfolio_id: int, days: int = 30) -> PortfolioPerformance:
        perf = self.db.get_portfolio_performance(portfolio_id, days)
        return PortfolioPerformance(**perf)

    def get_performance_summary(self, portfolio_id: int) -> dict:
        """Resumen para dashboard: 7d, 30d, 90d, all-time."""
        periods = [7, 30, 90, 365]
        summary = {}
        
        for days in periods:
            perf = self.db.get_portfolio_performance(portfolio_id, days)
            label = f"{days}d" if days < 365 else "1y"
            summary[label] = {
                "picks": perf["total_picks"],
                "roi": perf["roi_pct"],
                "win_rate": perf["win_rate"],
                "pnl": perf["total_pnl"],
                "sharpe": perf["sharpe"],
                "max_dd": perf["max_drawdown"],
            }
        
        # All-time
        all_time = self.db.get_portfolio_performance(portfolio_id, 3650)  # 10 años
        summary["all"] = {
            "picks": all_time["total_picks"],
            "roi": all_time["roi_pct"],
            "win_rate": all_time["win_rate"],
            "pnl": all_time["total_pnl"],
            "sharpe": all_time["sharpe"],
            "max_dd": all_time["max_drawdown"],
        }
        
        portfolio = self.db.get_portfolio(portfolio_id)
        summary["current_bankroll"] = portfolio["current_bankroll"] if portfolio else 0
        summary["initial_bankroll"] = portfolio["initial_bankroll"] if portfolio else 0
        summary["total_return_pct"] = round(
            (summary["current_bankroll"] - summary["initial_bankroll"]) / summary["initial_bankroll"] * 100, 2
        ) if summary["initial_bankroll"] > 0 else 0
        
        return summary

    def get_recent_activity(self, portfolio_id: int, limit: int = 20) -> List[dict]:
        return self.db.get_recent_picks(portfolio_id, limit)


def create_paper_trading_engine(db: Database = None) -> PaperTradingEngine:
    return PaperTradingEngine(db)