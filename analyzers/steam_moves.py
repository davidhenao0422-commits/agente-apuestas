"""Steam Move Detection para identificar movimientos bruscos de líneas en bookmakers sharp.

Un "steam move" es un movimiento rápido y significativo de la línea de apuestas
causado por apuestas grandes de apostadores profesionales (sharps/syndicates).

Bookmakers sharp de referencia: Pinnacle, Betfair, Bet365, Circa, Bookmaker.eu
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from storage.database import Database

logger = logging.getLogger(__name__)

# Bookmakers considerados "sharp" (líderes de mercado)
SHARP_BOOKMAKERS = {
    "pinnacle",
    "betfair",
    "betfair_ex_uk",
    "bet365",
    "circa",
    "bookmaker",
    "thegreek",
    "5dimes",
    "sbo",
    "maxbet",
}

# Umbrales por defecto
DEFAULT_THRESHOLDS = {
    "h2h": 0.03,       # 3% movimiento en 1X2
    "totals": 0.025,   # 2.5% en over/under
    "btts": 0.03,      # 3% en BTTS
    "spreads": 0.02,   # 2% en handicaps
}

# Ventana de tiempo para detectar steam (minutos)
STEAM_WINDOW_MINUTES = 15
MIN_SNAPSHOTS_FOR_COMPARISON = 2


@dataclass
class SteamMove:
    """Representa un steam move detectado."""
    match_id: str
    home_team: str
    away_team: str
    league: str
    kickoff: str
    bookmaker: str
    market: str
    direction: str  # "home", "draw", "away", "over", "under", "btts_yes", "btts_no"
    old_odds: float
    new_odds: float
    pct_change: float
    time_elapsed_min: float
    severity: str  # "low", "medium", "high", "extreme"
    timestamp: str
    implied_prob_change: float


class SteamMoveDetector:
    """Detecta steam moves comparando snapshots de odds en bookmakers sharp."""

    def __init__(self, db: Database = None, thresholds: Dict[str, float] = None):
        self.db = db or Database()
        self.thresholds = thresholds or DEFAULT_THRESHOLDS
        self.sharp_books = SHARP_BOOKMAKERS

    def detect_steam_moves(
        self, 
        match_id: str = None, 
        hours_back: int = 2,
        min_severity: str = "medium"
    ) -> List[SteamMove]:
        """Detecta steam moves en partidos recientes.
        
        Args:
            match_id: Si se proporciona, solo analiza ese partido
            hours_back: Ventana temporal hacia atrás
            min_severity: Severidad mínima ("low", "medium", "high", "extreme")
            
        Returns:
            Lista de SteamMove detectados
        """
        if match_id:
            matches_to_check = [{"match_id": match_id}]
        else:
            matches_to_check = self._get_recent_matches_with_odds(hours_back)
        
        all_moves = []
        
        for match in matches_to_check:
            moves = self._analyze_match(match["match_id"], hours_back)
            all_moves.extend(moves)
        
        # Filtrar por severidad mínima
        severity_order = {"low": 0, "medium": 1, "high": 2, "extreme": 3}
        min_level = severity_order.get(min_severity, 1)
        filtered = [m for m in all_moves if severity_order.get(m.severity, 0) >= min_level]
        
        # Ordenar: más recientes y severos primero
        filtered.sort(key=lambda x: (severity_order.get(x.severity, 0), x.timestamp), reverse=True)
        
        return filtered

    def _get_recent_matches_with_odds(self, hours_back: int) -> List[dict]:
        """Obtiene partidos que tienen snapshots de odds recientes."""
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(hours=hours_back)).isoformat()
        
        return self.db.query(
            """SELECT DISTINCT match_id, home_team, away_team, league, kickoff
               FROM odds_snapshots 
               WHERE snapshot_at >= ? AND is_sharp = 1
               ORDER BY snapshot_at DESC LIMIT 100""",
            (cutoff,),
        )

    def _analyze_match(self, match_id: str, hours_back: int) -> List[SteamMove]:
        """Analiza un partido específico buscando steam moves."""
        moves = []
        
        # Obtener snapshots de bookmakers sharp
        for market in ["h2h", "totals", "btts"]:
            threshold = self.thresholds.get(market, 0.03)
            snapshots = self.db.get_sharp_bookmakers_odds(match_id, market, hours_back)
            
            if len(snapshots) < MIN_SNAPSHOTS_FOR_COMPARISON:
                continue
            
            # Agrupar por bookmaker
            by_bookmaker = {}
            for snap in snapshots:
                bm = snap["bookmaker"]
                if bm not in by_bookmaker:
                    by_bookmaker[bm] = []
                by_bookmaker[bm].append(snap)
            
            # Analizar cada bookmaker sharp
            for bookmaker, snaps in by_bookmaker.items():
                if len(snaps) < 2:
                    continue
                
                # Comparar snapshots consecutivos
                for i in range(1, len(snaps)):
                    prev = snaps[i-1]
                    curr = snaps[i]
                    
                    move = self._compare_snapshots(prev, curr, threshold, market)
                    if move:
                        moves.append(move)
        
        return moves

    def _compare_snapshots(
        self, 
        prev: dict, 
        curr: dict, 
        threshold: float,
        market: str
    ) -> Optional[SteamMove]:
        """Compara dos snapshots y detecta si hay steam move."""
        prev_time = datetime.fromisoformat(prev["snapshot_at"])
        curr_time = datetime.fromisoformat(curr["snapshot_at"])
        time_elapsed = (curr_time - prev_time).total_seconds() / 60
        
        # Solo considerar si el movimiento fue rápido (ventana steam)
        if time_elapsed > STEAM_WINDOW_MINUTES:
            return None
        
        # Extraer odds según mercado
        odds_pairs = self._extract_odds_pairs(prev, curr, market)
        
        for direction, old_odds, new_odds in odds_pairs:
            if old_odds <= 0 or new_odds <= 0:
                continue
                
            pct_change = abs(new_odds - old_odds) / old_odds
            
            if pct_change >= threshold:
                # Calcular cambio en probabilidad implícita
                old_prob = 1 / old_odds
                new_prob = 1 / new_odds
                prob_change = abs(new_prob - old_prob)
                
                severity = self._classify_severity(pct_change, time_elapsed)
                
                return SteamMove(
                    match_id=prev["match_id"],
                    home_team=prev["home_team"],
                    away_team=prev["away_team"],
                    league=prev["league"],
                    kickoff=prev["kickoff"],
                    bookmaker=curr["bookmaker"],
                    market=market,
                    direction=direction,
                    old_odds=round(old_odds, 3),
                    new_odds=round(new_odds, 3),
                    pct_change=round(pct_change * 100, 2),
                    time_elapsed_min=round(time_elapsed, 1),
                    severity=severity,
                    timestamp=curr["snapshot_at"],
                    implied_prob_change=round(prob_change * 100, 2),
                )
        
        return None

    def _extract_odds_pairs(self, prev: dict, curr: dict, market: str) -> List[Tuple[str, float, float]]:
        """Extrae pares de odds comparables según el mercado."""
        pairs = []
        
        if market == "h2h":
            # 1X2: home, draw, away
            if prev["odds_home"] and curr["odds_home"]:
                pairs.append(("home", prev["odds_home"], curr["odds_home"]))
            if prev["odds_draw"] and curr["odds_draw"]:
                pairs.append(("draw", prev["odds_draw"], curr["odds_draw"]))
            if prev["odds_away"] and curr["odds_away"]:
                pairs.append(("away", prev["odds_away"], curr["odds_away"]))
                
        elif market == "totals":
            # Over/Under (usualmente 2.5)
            if prev["odds_over"] and curr["odds_over"]:
                pairs.append(("over", prev["odds_over"], curr["odds_over"]))
            if prev["odds_under"] and curr["odds_under"]:
                pairs.append(("under", prev["odds_under"], curr["odds_under"]))
                
        elif market == "btts":
            # Both Teams To Score
            if prev["odds_btts_yes"] and curr["odds_btts_yes"]:
                pairs.append(("btts_yes", prev["odds_btts_yes"], curr["odds_btts_yes"]))
            if prev["odds_btts_no"] and curr["odds_btts_no"]:
                pairs.append(("btts_no", prev["odds_btts_no"], curr["odds_btts_no"]))
        
        return pairs

    def _classify_severity(self, pct_change: float, time_elapsed: float) -> str:
        """Clasifica la severidad del steam move."""
        # Combinar magnitud y velocidad
        speed_factor = max(1, STEAM_WINDOW_MINUTES / max(time_elapsed, 0.5))
        intensity = pct_change * speed_factor
        
        if intensity >= 0.15:  # 15%+ ajustado por velocidad
            return "extreme"
        elif intensity >= 0.08:
            return "high"
        elif intensity >= 0.04:
            return "medium"
        else:
            return "low"

    def get_steam_summary(self, hours_back: int = 24) -> Dict:
        """Resumen de steam moves para dashboard."""
        moves = self.detect_steam_moves(hours_back=hours_back, min_severity="low")
        
        by_severity = {"low": 0, "medium": 0, "high": 0, "extreme": 0}
        by_market = {"h2h": 0, "totals": 0, "btts": 0}
        by_bookmaker = {}
        
        for move in moves:
            by_severity[move.severity] += 1
            by_market[move.market] += 1
            by_bookmaker[move.bookmaker] = by_bookmaker.get(move.bookmaker, 0) + 1
        
        return {
            "total_moves": len(moves),
            "by_severity": by_severity,
            "by_market": by_market,
            "by_bookmaker": by_bookmaker,
            "top_moves": [
                {
                    "match": f"{m.home_team} vs {m.away_team}",
                    "league": m.league,
                    "bookmaker": m.bookmaker,
                    "market": m.market,
                    "direction": m.direction,
                    "pct_change": m.pct_change,
                    "time_min": m.time_elapsed_min,
                    "severity": m.severity,
                    "timestamp": m.timestamp,
                }
                for m in moves[:20]
            ],
        }

    def format_telegram_alert(self, move: SteamMove) -> str:
        """Formatea alerta para Telegram."""
        direction_emoji = {
            "home": "🏠", "draw": "⚖️", "away": "✈️",
            "over": "📈", "under": "📉",
            "btts_yes": "⚽", "btts_no": "🚫",
        }
        emoji = direction_emoji.get(move.direction, "📊")
        
        severity_emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "extreme": "🔴"}
        sev_emoji = severity_emoji.get(move.severity, "⚪")
        
        market_name = {"h2h": "1X2", "totals": "O/U", "btts": "BTTS"}.get(move.market, move.market)
        
        return (
            f"{sev_emoji} <b>STEAM MOVE DETECTADO</b> {emoji}\n\n"
            f"⚽ <b>{move.home_team} vs {move.away_team}</b>\n"
            f"🏆 {move.league} | ⏰ {move.kickoff[:16].replace('T', ' ')}\n"
            f"📊 <b>Mercado:</b> {market_name} ({move.direction})\n"
            f"🏪 <b>Bookmaker:</b> {move.bookmaker} (sharp)\n\n"
            f"📈 <b>Cambio:</b> {move.old_odds:.2f} → {move.new_odds:.2f} "
            f"({move.pct_change:.1f}% en {move.time_elapsed_min:.0f} min)\n"
            f"🎯 <b>Prob. implícita:</b> {move.implied_prob_change:.1f}%\n"
            f"⚡ <b>Severidad:</b> {move.severity.upper()}"
        )


def create_steam_detector(db: Database = None) -> SteamMoveDetector:
    """Factory para crear detector con configuración por defecto."""
    return SteamMoveDetector(db)


# Función auxiliar para polling programado
def poll_and_store_odds(db: Database, odds_client) -> int:
    """Obtiene odds actuales y guarda snapshots para partidos próximos.
    
    Returns:
        Número de snapshots guardados
    """
    from collectors.odds_api import OddsAPIClient
    from catalog import get_regions, get_leagues_by_region, get_league_info
    from datetime import date, timedelta
    
    if not isinstance(odds_client, OddsAPIClient):
        odds_client = OddsAPIClient(db)
    
    saved = 0
    today = date.today()
    tomorrow = today + timedelta(days=1)
    
    # Obtener todas las ligas del catálogo
    all_leagues = {}
    for region in get_regions():
        for liga in get_leagues_by_region(region["key"]):
            info = get_league_info(liga["code"])
            if info:
                all_leagues[liga["code"]] = info
    
    for league_code, league_info in all_leagues.items():
        try:
            odds_matches = odds_client.get_odds(league_code)
            if not odds_matches:
                continue
                
            for match in odds_matches:
                # Filtrar solo partidos de hoy/mañana
                match_date = match.get("date", "")[:10]
                if match_date not in [today.isoformat(), tomorrow.isoformat()]:
                    continue
                
                home = match["home_team"]
                away = match["away_team"]
                match_id = f"{home}_vs_{away}_{league_code}_{match_date}"
                kickoff = match["date"]
                
                # Guardar snapshot por cada mercado
                now = datetime.now().isoformat()
                odds_avg = match.get("odds_avg", {})
                
                # h2h
                if "1" in odds_avg and "X" in odds_avg and "2" in odds_avg:
                    db.save_odds_snapshot({
                        "match_id": match_id,
                        "home_team": home,
                        "away_team": away,
                        "league": league_info["name"],
                        "kickoff": kickoff,
                        "bookmaker": "avg",
                        "market": "h2h",
                        "odds_home": odds_avg["1"],
                        "odds_draw": odds_avg["X"],
                        "odds_away": odds_avg["2"],
                        "snapshot_at": now,
                        "is_sharp": 0,
                    })
                    saved += 1
                
                # totals (over/under 2.5)
                over_key = "over_2.5"
                under_key = "under_2.5"
                if over_key in odds_avg and under_key in odds_avg:
                    db.save_odds_snapshot({
                        "match_id": match_id,
                        "home_team": home,
                        "away_team": away,
                        "league": league_info["name"],
                        "kickoff": kickoff,
                        "bookmaker": "avg",
                        "market": "totals",
                        "odds_over": odds_avg[over_key],
                        "odds_under": odds_avg[under_key],
                        "snapshot_at": now,
                        "is_sharp": 0,
                    })
                    saved += 1
                
                # BTTS
                if "btts_yes" in odds_avg and "btts_no" in odds_avg:
                    db.save_odds_snapshot({
                        "match_id": match_id,
                        "home_team": home,
                        "away_team": away,
                        "league": league_info["name"],
                        "kickoff": kickoff,
                        "bookmaker": "avg",
                        "market": "btts",
                        "odds_btts_yes": odds_avg["btts_yes"],
                        "odds_btts_no": odds_avg["btts_no"],
                        "snapshot_at": now,
                        "is_sharp": 0,
                    })
                    saved += 1
                
                # Guardar también por bookmaker individual (sharp)
                for bm_key, bm_data in match.get("odds_best", {}).items():
                    bm_name = bm_data.get("bookmaker", "").lower().replace(" ", "_")
                    is_sharp = 1 if any(sb in bm_name for sb in SHARP_BOOKMAKERS) else 0
                    
                    if bm_key == "1" and "X" in match["odds_best"] and "2" in match["odds_best"]:
                        db.save_odds_snapshot({
                            "match_id": match_id,
                            "home_team": home,
                            "away_team": away,
                            "league": league_info["name"],
                            "kickoff": kickoff,
                            "bookmaker": bm_data["bookmaker"],
                            "market": "h2h",
                            "odds_home": match["odds_best"]["1"]["odds"],
                            "odds_draw": match["odds_best"]["X"]["odds"],
                            "odds_away": match["odds_best"]["2"]["odds"],
                            "snapshot_at": now,
                            "is_sharp": is_sharp,
                        })
                        saved += 1
                        
        except Exception as e:
            logger.warning(f"Error polling odds for {league_code}: {e}")
    
    return saved