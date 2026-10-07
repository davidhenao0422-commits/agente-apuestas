"""Bookmaker Quality Scoring & Ranking.

Evalúa bookmakers por:
- CLV Score: capacidad de ofrecer líneas que baten el cierre
- Accuracy: precisión de sus líneas vs resultado real
- Consistency: estabilidad de sus odds (menos volatilidad = más sharp)
- Volume: liquidez / número de mercados ofrecidos
- Sharp Factor: combinación ponderada para ranking global
"""

import logging
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np

from storage.database import Database

logger = logging.getLogger(__name__)


@dataclass
class BookmakerScore:
    bookmaker: str
    league: str
    period_days: int
    
    # Métricas base
    total_markets: int
    total_matches: int
    
    # CLV (Closing Line Value)
    clv_score: float          # % de mercados que baten línea de cierre
    avg_clv_pct: float        # CLV promedio en pp
    beat_rate: float          # % mercados beating closing line
    
    # Accuracy
    accuracy_score: float     # Brier score inverso (0-1, mayor mejor)
    log_loss: float
    brier_score: float
    
    # Consistency
    consistency_score: float  # Inverso de volatilidad odds (0-1)
    odds_volatility: float    # Std dev de cambios de odds
    
    # Sharp Factor (ponderado)
    sharp_factor: float       # Score combinado 0-100
    
    # Ranking
    rank: int = 0
    
    last_updated: str = ""


class BookmakerRanker:
    """Calcula y actualiza scores de calidad para bookmakers."""

    def __init__(self, db: Database = None):
        self.db = db or Database()
        
        # Pesos para Sharp Factor
        self.weights = {
            "clv": 0.40,        # 40% - más importante para value bettors
            "accuracy": 0.25,   # 25% - precisión predictiva
            "consistency": 0.20, # 20% - estabilidad líneas
            "volume": 0.15,     # 15% - liquidez/cobertura
        }

    def calculate_all_scores(self, period_days: int = 30, min_markets: int = 50) -> List[BookmakerScore]:
        """Calcula scores para todos los bookmakers con datos suficientes."""
        from datetime import datetime, timedelta
        
        cutoff = (datetime.now() - timedelta(days=period_days)).isoformat()
        
        # Obtener snapshots de odds con bookmakers sharp
        snapshots = self.db.query(
            """SELECT * FROM odds_snapshots 
               WHERE snapshot_at >= ? AND is_sharp = 1
               ORDER BY bookmaker, match_id, market, snapshot_at""",
            (cutoff,),
        )
        
        if not snapshots:
            logger.warning("No hay snapshots de odds para calcular scores")
            return []
        
        # Agrupar por bookmaker + liga
        by_bookmaker_league = {}
        for snap in snapshots:
            key = (snap["bookmaker"], snap["league"])
            if key not in by_bookmaker_league:
                by_bookmaker_league[key] = []
            by_bookmaker_league[key].append(snap)
        
        scores = []
        for (bookmaker, league), snaps in by_bookmaker_league.items():
            score = self._calculate_bookmaker_score(
                bookmaker, league, snaps, period_days, min_markets
            )
            if score:
                scores.append(score)
        
        # Calcular ranking global por sharp_factor
        scores.sort(key=lambda x: x.sharp_factor, reverse=True)
        for i, s in enumerate(scores):
            s.rank = i + 1
        
        return scores

    def _calculate_bookmaker_score(
        self, 
        bookmaker: str, 
        league: str, 
        snapshots: List[dict],
        period_days: int,
        min_markets: int
    ) -> Optional[BookmakerScore]:
        """Calcula score para un bookmaker+liga específico."""
        
        # Agrupar por partido+mercado para ver evolución temporal
        by_match_market = {}
        for snap in snapshots:
            key = (snap["match_id"], snap["market"])
            if key not in by_match_market:
                by_match_market[key] = []
            by_match_market[key].append(snap)
        
        # Filtrar solo los que tienen al menos 2 snapshots (apertura + cierre)
        valid_series = {k: v for k, v in by_match_market.items() if len(v) >= 2}
        
        if len(valid_series) < min_markets:
            return None
        
        # Calcular métricas
        clv_metrics = self._calculate_clv_metrics(valid_series)
        accuracy_metrics = self._calculate_accuracy_metrics(valid_series)
        consistency_metrics = self._calculate_consistency_metrics(valid_series)
        volume = len(valid_series)
        
        # Sharp Factor combinado
        sharp_factor = self._calculate_sharp_factor(
            clv_metrics, accuracy_metrics, consistency_metrics, volume
        )
        
        return BookmakerScore(
            bookmaker=bookmaker,
            league=league,
            period_days=period_days,
            total_markets=volume,
            total_matches=len(set(k[0] for k in valid_series.keys())),
            clv_score=clv_metrics["clv_score"],
            avg_clv_pct=clv_metrics["avg_clv_pct"],
            beat_rate=clv_metrics["beat_rate"],
            accuracy_score=accuracy_metrics["accuracy_score"],
            log_loss=accuracy_metrics["log_loss"],
            brier_score=accuracy_metrics["brier_score"],
            consistency_score=consistency_metrics["consistency_score"],
            odds_volatility=consistency_metrics["odds_volatility"],
            sharp_factor=sharp_factor,
            last_updated=datetime.now().isoformat(),
        )

    def _calculate_clv_metrics(self, series: Dict) -> Dict:
        """CLV: ¿las odds de apertura baten a las de cierre?"""
        beats = 0
        clv_values = []
        
        for (match_id, market), snaps in series.items():
            # Ordenar por tiempo
            snaps_sorted = sorted(snaps, key=lambda x: x["snapshot_at"])
            opening = snaps_sorted[0]
            closing = snaps_sorted[-1]
            
            # Comparar odds de apertura vs cierre para el mercado ganador
            # Para simplificar: asumimos que el mercado "favorito" en apertura
            # debería mantenerse o mejorar en cierre si el bookmaker es sharp
            clv = self._compute_market_clv(opening, closing, market)
            if clv is not None:
                clv_values.append(clv)
                if clv > 0:
                    beats += 1
        
        if not clv_values:
            return {"clv_score": 0, "avg_clv_pct": 0, "beat_rate": 0}
        
        avg_clv = np.mean(clv_values)
        beat_rate = beats / len(clv_values)
        
        # Score 0-1: combinar beat_rate y magnitud promedio
        clv_score = (beat_rate * 0.7) + (min(avg_clv * 10, 0.3))  # cap magnitude contribution
        
        return {
            "clv_score": round(clv_score, 4),
            "avg_clv_pct": round(avg_clv * 100, 2),
            "beat_rate": round(beat_rate * 100, 1),
        }

    def _compute_market_clv(self, opening: dict, closing: dict, market: str) -> Optional[float]:
        """Calcula CLV para un mercado específico."""
        try:
            if market == "h2h":
                # Para 1X2: comparar odds del favorito en apertura vs cierre
                open_odds = [opening.get("odds_home"), opening.get("odds_draw"), opening.get("odds_away")]
                close_odds = [closing.get("odds_home"), closing.get("odds_draw"), closing.get("odds_away")]
                
                # Filtrar None
                open_odds = [o for o in open_odds if o]
                close_odds = [c for c in close_odds if c]
                
                if not open_odds or not close_odds:
                    return None
                
                # Favorito = menor odd en apertura
                fav_idx = np.argmin(open_odds)
                open_fav = open_odds[fav_idx]
                close_fav = close_odds[fav_idx] if fav_idx < len(close_odds) else open_fav
                
                # CLV = (1/open - 1/close) / (1/open) = 1 - open/close
                # Positivo = odd de cierre MEJOR (mayor) que apertura = beat closing line
                return 1 - (open_fav / close_fav) if close_fav > 0 else 0
                
            elif market == "totals":
                open_over = opening.get("odds_over")
                close_over = closing.get("odds_over")
                if open_over and close_over:
                    return 1 - (open_over / close_over)
                    
            elif market == "btts":
                open_yes = opening.get("odds_btts_yes")
                close_yes = closing.get("odds_btts_yes")
                if open_yes and close_yes:
                    return 1 - (open_yes / close_yes)
                    
        except Exception:
            pass
        return None

    def _calculate_accuracy_metrics(self, series: Dict) -> Dict:
        """Accuracy: Brier score de las probabilidades implícitas vs resultado real.
        
        Nota: Requiere resultados reales. Por ahora usa proxy: 
        - Consistencia interna de las odds (suma probabilidades ~ 1)
        - Dispersión entre bookmakers (consenso = más preciso)
        """
        brier_scores = []
        log_losses = []
        
        for (match_id, market), snaps in series.items():
            # Usar odds de cierre (más precisas)
            closing = sorted(snaps, key=lambda x: x["snapshot_at"])[-1]
            
            probs = self._odds_to_probs(closing, market)
            if not probs:
                continue
            
            # Proxy accuracy: overround (debe ser bajo para sharp books)
            overround = sum(probs.values()) - 1
            # Brier proxy: penalizar overround alto
            brier_proxy = overround ** 2
            brier_scores.append(brier_proxy)
            
            # Log loss proxy
            log_losses.append(-np.log(max(1 - overround, 0.01)))
        
        if not brier_scores:
            return {"accuracy_score": 0, "log_loss": 1, "brier_score": 1}
        
        avg_brier = np.mean(brier_scores)
        avg_log_loss = np.mean(log_losses)
        
        # Invertir: menor brier = mayor accuracy
        accuracy_score = max(0, 1 - avg_brier * 10)
        
        return {
            "accuracy_score": round(accuracy_score, 4),
            "log_loss": round(avg_log_loss, 4),
            "brier_score": round(avg_brier, 4),
        }

    def _odds_to_probs(self, snap: dict, market: str) -> Dict[str, float]:
        """Convierte odds a probabilidades implícitas."""
        probs = {}
        
        if market == "h2h":
            for k, key in [("home", "odds_home"), ("draw", "odds_draw"), ("away", "odds_away")]:
                if snap.get(key):
                    probs[k] = 1 / snap[key]
                    
        elif market == "totals":
            for k, key in [("over", "odds_over"), ("under", "odds_under")]:
                if snap.get(key):
                    probs[k] = 1 / snap[key]
                    
        elif market == "btts":
            for k, key in [("yes", "odds_btts_yes"), ("no", "odds_btts_no")]:
                if snap.get(key):
                    probs[k] = 1 / snap[key]
        
        return probs

    def _calculate_consistency_metrics(self, series: Dict) -> Dict:
        """Consistency: volatilidad de odds a lo largo del tiempo.
        
        Bookmakers sharp = líneas estables (menos movimiento aleatorio).
        """
        volatilities = []
        
        for (match_id, market), snaps in series.items():
            if len(snaps) < 3:
                continue
                
            snaps_sorted = sorted(snaps, key=lambda x: x["snapshot_at"])
            
            # Calcular volatilidad para cada outcome
            market_vols = []
            
            if market == "h2h":
                for key in ["odds_home", "odds_draw", "odds_away"]:
                    vals = [s[key] for s in snaps_sorted if s.get(key)]
                    if len(vals) >= 3:
                        cv = np.std(vals) / np.mean(vals) if np.mean(vals) > 0 else 0
                        market_vols.append(cv)
                        
            elif market == "totals":
                for key in ["odds_over", "odds_under"]:
                    vals = [s[key] for s in snaps_sorted if s.get(key)]
                    if len(vals) >= 3:
                        cv = np.std(vals) / np.mean(vals) if np.mean(vals) > 0 else 0
                        market_vols.append(cv)
                        
            elif market == "btts":
                for key in ["odds_btts_yes", "odds_btts_no"]:
                    vals = [s[key] for s in snaps_sorted if s.get(key)]
                    if len(vals) >= 3:
                        cv = np.std(vals) / np.mean(vals) if np.mean(vals) > 0 else 0
                        market_vols.append(cv)
            
            if market_vols:
                volatilities.append(np.mean(market_vols))
        
        if not volatilities:
            return {"consistency_score": 0.5, "odds_volatility": 0.05}
        
        avg_vol = np.mean(volatilities)
        # Invertir: menor volatilidad = mayor consistency
        consistency_score = max(0, 1 - avg_vol * 20)
        
        return {
            "consistency_score": round(consistency_score, 4),
            "odds_volatility": round(avg_vol, 4),
        }

    def _calculate_sharp_factor(self, clv: Dict, acc: Dict, cons: Dict, volume: int) -> float:
        """Sharp Factor combinado 0-100."""
        # Normalizar volume (log scale, cap at 1000 markets)
        vol_score = min(np.log10(max(volume, 1)) / 3, 1.0)
        
        factor = (
            self.weights["clv"] * clv["clv_score"] +
            self.weights["accuracy"] * acc["accuracy_score"] +
            self.weights["consistency"] * cons["consistency_score"] +
            self.weights["volume"] * vol_score
        )
        
        return round(factor * 100, 1)

    def save_scores(self, scores: List[BookmakerScore]) -> int:
        """Guarda scores en BD."""
        saved = 0
        for score in scores:
            try:
                self.db.save_bookmaker_score({
                    "bookmaker": score.bookmaker,
                    "league": score.league,
                    "period_days": score.period_days,
                    "accuracy": score.accuracy_score,
                    "consistency": score.consistency_score,
                    "clv_score": score.clv_score,
                    "volume": score.total_markets,
                    "last_updated": score.last_updated,
                })
                saved += 1
            except Exception as e:
                logger.warning(f"Error guardando score {score.bookmaker}/{score.league}: {e}")
        return saved

    def get_ranking(self, league: str = None, period_days: int = 30, top: int = 20) -> List[Dict]:
        """Obtiene ranking formateado para API."""
        scores = self.calculate_all_scores(period_days)
        
        if league:
            scores = [s for s in scores if s.league == league]
        
        return [
            {
                "rank": s.rank,
                "bookmaker": s.bookmaker,
                "league": s.league,
                "sharp_factor": s.sharp_factor,
                "clv_score": s.clv_score,
                "clv_beat_rate": s.beat_rate,
                "avg_clv_pct": s.avg_clv_pct,
                "accuracy_score": s.accuracy_score,
                "brier_score": s.brier_score,
                "consistency_score": s.consistency_score,
                "odds_volatility": s.odds_volatility,
                "total_markets": s.total_markets,
                "total_matches": s.total_matches,
                "last_updated": s.last_updated,
            }
            for s in scores[:top]
        ]

    def get_bookmaker_detail(self, bookmaker: str, league: str = None, period_days: int = 30) -> Optional[Dict]:
        """Detalle completo de un bookmaker."""
        scores = self.calculate_all_scores(period_days)
        
        if league:
            scores = [s for s in scores if s.league == league]
        
        target = [s for s in scores if s.bookmaker.lower() == bookmaker.lower()]
        if not target:
            return None
        
        s = target[0]
        return {
            "bookmaker": s.bookmaker,
            "league": s.league,
            "period_days": s.period_days,
            "rank": s.rank,
            "sharp_factor": s.sharp_factor,
            "metrics": {
                "clv": {
                    "score": s.clv_score,
                    "beat_rate_pct": s.beat_rate,
                    "avg_clv_pct": s.avg_clv_pct,
                },
                "accuracy": {
                    "score": s.accuracy_score,
                    "brier_score": s.brier_score,
                    "log_loss": s.log_loss,
                },
                "consistency": {
                    "score": s.consistency_score,
                    "odds_volatility": s.odds_volatility,
                },
                "volume": {
                    "markets": s.total_markets,
                    "matches": s.total_matches,
                },
            },
            "weights_used": self.weights,
            "last_updated": s.last_updated,
        }


def create_bookmaker_ranker(db: Database = None) -> BookmakerRanker:
    return BookmakerRanker(db)