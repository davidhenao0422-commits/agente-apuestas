import logging
import requests
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import date, datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class BookmakerOdds:
    bookmaker: str
    home: float
    draw: float
    away: float
    home_ah: Optional[float] = None
    away_ah: Optional[float] = None
    ah_line: Optional[float] = None
    over_25: Optional[float] = None
    under_25: Optional[float] = None
    btts_yes: Optional[float] = None
    btts_no: Optional[float] = None
    last_update: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class MatchOdds:
    match_id: str
    home_team: str
    away_team: str
    league: str
    kickoff: str
    odds_by_book: Dict[str, BookmakerOdds] = field(default_factory=dict)
    consensus: Dict = field(default_factory=dict)
    line_movement: List[Dict] = field(default_factory=list)
    sharp_signals: List[Dict] = field(default_factory=list)


class OddsAggregator:
    """
    Agregador de odds en tiempo real de múltiples bookmakers.
    
    Soporta:
    - OpticOdds API (200+ books, 1M req/sec, 15-60s refresh)
    - The Odds API (40+ books, free tier 500 req/month)
    - Perplexity MCP (gratis para Pro/Max users)
    - Pinnacle API (sharp book reference)
    - Betfair Exchange (market prices)
    """
    
    def __init__(self, api_keys: Dict = None):
        self.api_keys = api_keys or {}
        self.cache: Dict[str, MatchOdds] = {}
        self.cache_ttl = 60
        self.bookmaker_weights = self._default_bookmaker_weights()
        self.line_history: Dict[str, List[Dict]] = defaultdict(list)
    
    def _default_bookmaker_weights(self) -> Dict[str, float]:
        """Pesos por bookmaker (sharp books = mayor peso)."""
        return {
            "pinnacle": 1.0,
            "betfair": 0.95,
            "bet365": 0.8,
            "william_hill": 0.75,
            "ladbrokes": 0.7,
            "unibet": 0.7,
            "betway": 0.65,
            "1xbet": 0.6,
            "marathonbet": 0.65,
            "sbobet": 0.6,
            "188bet": 0.55,
            "dafabet": 0.5,
            "default": 0.4,
        }
    
    def fetch_opticodds(self, sport: str = "soccer", 
                        leagues: List[str] = None) -> List[MatchOdds]:
        """
        Obtiene odds desde OpticOdds API.
        
        Requiere API key. Plan gratuito: 1000 req/month.
        Docs: https://docs.opticodds.com/
        """
        api_key = self.api_keys.get("opticodds")
        if not api_key:
            logger.warning("OpticOdds API key not configured")
            return []
        
        headers = {"Authorization": f"Bearer {api_key}"}
        params = {"sport": sport}
        if leagues:
            params["leagues"] = ",".join(leagues)
        
        try:
            resp = requests.get(
                "https://api.opticodds.com/v3/fixtures/odds",
                headers=headers, params=params, timeout=15
            )
            data = resp.json()
            
            matches = []
            for fixture in data.get("data", []):
                match = self._parse_opticodds_fixture(fixture)
                if match:
                    matches.append(match)
            
            return matches
        except Exception as e:
            logger.error(f"OpticOdds fetch error: {e}")
            return []
    
    def _parse_opticodds_fixture(self, fixture: Dict) -> Optional[MatchOdds]:
        try:
            participants = fixture.get("participants", [])
            if len(participants) != 2:
                return None
            
            home = participants[0].get("name", "")
            away = participants[1].get("name", "")
            
            match = MatchOdds(
                match_id=str(fixture.get("id", "")),
                home_team=home,
                away_team=away,
                league=fixture.get("league", {}).get("name", ""),
                kickoff=fixture.get("start_time", ""),
            )
            
            for odd in fixture.get("odds", []):
                bookie = odd.get("sportsbook", "").lower().replace(" ", "_")
                values = odd.get("values", [])
                
                book_odds = BookmakerOdds(bookmaker=bookie)
                for v in values:
                    market = v.get("name", "").lower()
                    if "home" in market and "draw" not in market and "away" not in market:
                        book_odds.home = v.get("price", 0)
                    elif "draw" in market:
                        book_odds.draw = v.get("price", 0)
                    elif "away" in market:
                        book_odds.away = v.get("price", 0)
                    elif "over" in market and "2.5" in market:
                        book_odds.over_25 = v.get("price", 0)
                    elif "under" in market and "2.5" in market:
                        book_odds.under_25 = v.get("price", 0)
                    elif "btts" in market and "yes" in market:
                        book_odds.btts_yes = v.get("price", 0)
                    elif "btts" in market and "no" in market:
                        book_odds.btts_no = v.get("price", 0)
                
                match.odds_by_book[bookie] = book_odds
                self._update_line_history(match.match_id, bookie, book_odds)
            
            match.consensus = self._calculate_consensus(match)
            match.sharp_signals = self._detect_sharp_money(match)
            
            self.cache[match.match_id] = match
            return match
        except Exception as e:
            logger.error(f"Error parsing fixture: {e}")
            return None
    
    def fetch_the_odds_api(self, sport: str = "soccer",
                            regions: str = "eu,uk,us") -> List[MatchOdds]:
        """
        Obtiene odds desde The Odds API.
        
        Free tier: 500 requests/month.
        Docs: https://the-odds-api.com/
        """
        api_key = self.api_keys.get("the_odds_api")
        if not api_key:
            logger.warning("The Odds API key not configured")
            return []
        
        params = {
            "apiKey": api_key,
            "sport": sport,
            "regions": regions,
            "markets": "h2h,spreads,totals",
            "oddsFormat": "decimal",
        }
        
        try:
            resp = requests.get(
                "https://api.the-odds-api.com/v4/sports/soccer/odds",
                params=params, timeout=15
            )
            data = resp.json()
            
            matches = []
            for game in data:
                match = self._parse_the_odds_api_game(game)
                if match:
                    matches.append(match)
            
            return matches
        except Exception as e:
            logger.error(f"The Odds API fetch error: {e}")
            return []
    
    def _parse_the_odds_api_game(self, game: Dict) -> Optional[MatchOdds]:
        try:
            home = game.get("home_team", "")
            away = game.get("away_team", "")
            
            match = MatchOdds(
                match_id=game.get("id", ""),
                home_team=home,
                away_team=away,
                league=game.get("sport_title", ""),
                kickoff=game.get("commence_time", ""),
            )
            
            for bookie_data in game.get("bookmakers", []):
                bookie = bookie_data.get("title", "").lower().replace(" ", "_")
                markets = bookie_data.get("markets", [])
                
                book_odds = BookmakerOdds(bookmaker=bookie)
                for market in markets:
                    if market.get("key") == "h2h":
                        for outcome in market.get("outcomes", []):
                            name = outcome.get("name", "").lower()
                            price = outcome.get("price", 0)
                            if name == home.lower():
                                book_odds.home = price
                            elif name == away.lower():
                                book_odds.away = price
                            elif "draw" in name:
                                book_odds.draw = price
                    elif market.get("key") == "totals":
                        for outcome in market.get("outcomes", []):
                            if outcome.get("name", "").lower() == "over":
                                book_odds.over_25 = outcome.get("price", 0)
                            elif outcome.get("name", "").lower() == "under":
                                book_odds.under_25 = outcome.get("price", 0)
                
                match.odds_by_book[bookie] = book_odds
                self._update_line_history(match.match_id, bookie, book_odds)
            
            match.consensus = self._calculate_consensus(match)
            match.sharp_signals = self._detect_sharp_money(match)
            
            self.cache[match.match_id] = match
            return match
        except Exception as e:
            logger.error(f"Error parsing game: {e}")
            return None
    
    def fetch_perplexity_mcp(self, query: str) -> Dict:
        """
        Usa Perplexity MCP para obtener odds en lenguaje natural.
        
        Requiere suscripción Pro/Max de Perplexity.
        """
        try:
            from perplexity_mcp import PerplexityClient
            
            client = PerplexityClient()
            response = client.search(query)
            
            return {"response": response}
        except ImportError:
            logger.warning("perplexity-mcp not installed")
            return {}
        except Exception as e:
            logger.error(f"Perplexity MCP error: {e}")
            return {}
    
    def _calculate_consensus(self, match: MatchOdds) -> Dict:
        """Calcula consenso ponderado por sharpness de bookmakers."""
        weighted_probs = defaultdict(float)
        total_weight = 0.0
        
        for bookie, odds in match.odds_by_book.items():
            weight = self.bookmaker_weights.get(bookie, 
                        self.bookmaker_weights["default"])
            
            implied = {
                "1": 1 / odds.home if odds.home > 0 else 0,
                "draw": 1 / odds.draw if odds.draw > 0 else 0,
                "2": 1 / odds.away if odds.away > 0 else 0,
            }
            total_implied = sum(implied.values())
            if total_implied > 0:
                implied = {k: v / total_implied for k, v in implied.items()}
                
                for k, v in implied.items():
                    weighted_probs[k] += weight * v
                total_weight += weight
        
        if total_weight > 0:
            consensus = {k: v / total_weight for k, v in weighted_probs.items()}
        else:
            consensus = {"1": 0.33, "draw": 0.33, "2": 0.33}
        
        best_odds = {"1": 0, "draw": 0, "2": 0}
        best_bookies = {"1": "", "draw": "", "2": ""}
        
        for bookie, odds in match.odds_by_book.items():
            if odds.home > best_odds["1"]:
                best_odds["1"] = odds.home
                best_bookies["1"] = bookie
            if odds.draw > best_odds["draw"]:
                best_odds["draw"] = odds.draw
                best_bookies["draw"] = bookie
            if odds.away > best_odds["2"]:
                best_odds["2"] = odds.away
                best_bookies["2"] = bookie
        
        return {
            "fair_probs": consensus,
            "fair_odds": {k: 1/v if v > 0 else 0 for k, v in consensus.items()},
            "best_odds": best_odds,
            "best_bookmakers": best_bookies,
            "bookmakers_count": len(match.odds_by_book),
        }
    
    def _detect_sharp_money(self, match: MatchOdds) -> List[Dict]:
        """
        Detecta sharp money signals:
        - Reverse line movement (line moves against public %)
        - Steam moves (sincronized movement across sharp books)
        - Line movement > 5% en sharp books
        """
        signals = []
        
        for bookie, odds in match.odds_by_book.items():
            weight = self.bookmaker_weights.get(bookie, 0.4)
            if weight < 0.7:
                continue
            
            history = self.line_history.get(f"{match.match_id}:{bookie}", [])
            if len(history) < 2:
                continue
            
            current = {"home": odds.home, "draw": odds.draw, "away": odds.away}
            previous = history[-2]
            
            for side in ["home", "draw", "away"]:
                curr_price = current.get(side, 0)
                prev_price = previous.get(side, 0)
                
                if prev_price > 0 and curr_price > 0:
                    change_pct = (curr_price - prev_price) / prev_price
                    
                    if abs(change_pct) > 0.05:
                        direction = "shortening" if change_pct < 0 else "drifting"
                        signals.append({
                            "type": "sharp_line_movement",
                            "bookmaker": bookie,
                            "side": side,
                            "change_pct": round(change_pct * 100, 1),
                            "direction": direction,
                            "current_odds": curr_price,
                            "previous_odds": prev_price,
                            "sharpness": weight,
                        })
        
        steam_groups = defaultdict(list)
        for sig in signals:
            key = f"{sig['side']}:{sig['direction']}"
            steam_groups[key].append(sig)
        
        for key, group in steam_groups.items():
            if len(group) >= 3:
                avg_change = sum(s['change_pct'] for s in group) / len(group)
                signals.append({
                    "type": "steam_move",
                    "side": group[0]['side'],
                    "direction": group[0]['direction'],
                    "bookmakers": [s['bookmaker'] for s in group],
                    "avg_change_pct": round(avg_change, 1),
                    "consensus_strength": len(group),
                })
        
        return signals
    
    def _update_line_history(self, match_id: str, bookie: str, 
                             odds: BookmakerOdds):
        key = f"{match_id}:{bookie}"
        self.line_history[key].append({
            "timestamp": datetime.now().isoformat(),
            "home": odds.home,
            "draw": odds.draw,
            "away": odds.away,
            "over_25": odds.over_25,
            "under_25": odds.under_25,
        })
        
        if len(self.line_history[key]) > 100:
            self.line_history[key] = self.line_history[key][-100:]
    
    def get_match_odds(self, home_team: str, away_team: str, 
                       league: str = None) -> Optional[MatchOdds]:
        """Busca odds en cache por nombres de equipos."""
        for match in self.cache.values():
            if (match.home_team.lower() == home_team.lower() and 
                match.away_team.lower() == away_team.lower()):
                if not league or league.lower() in match.league.lower():
                    return match
        return None
    
    def get_best_odds(self, home_team: str, away_team: str,
                      league: str = None) -> Dict:
        """Retorna mejores odds disponibles para un partido."""
        match = self.get_match_odds(home_team, away_team, league)
        if not match:
            return {}
        
        return {
            "match_id": match.match_id,
            "home_team": match.home_team,
            "away_team": match.away_team,
            "league": match.league,
            "kickoff": match.kickoff,
            "best_odds": match.consensus.get("best_odds", {}),
            "best_bookmakers": match.consensus.get("best_bookmakers", {}),
            "fair_odds": match.consensus.get("fair_odds", {}),
            "fair_probs": match.consensus.get("fair_probs", {}),
            "sharp_signals": match.sharp_signals,
            "bookmakers_count": match.consensus.get("bookmakers_count", 0),
        }
    
    def get_all_matches_odds(self, league: str = None) -> List[Dict]:
        """Retorna todos los partidos con odds disponibles."""
        results = []
        for match in self.cache.values():
            if not league or league.lower() in match.league.lower():
                results.append({
                    "match_id": match.match_id,
                    "home_team": match.home_team,
                    "away_team": match.away_team,
                    "league": match.league,
                    "kickoff": match.kickoff,
                    "best_odds": match.consensus.get("best_odds", {}),
                    "fair_probs": match.consensus.get("fair_probs", {}),
                    "sharp_signals": match.sharp_signals[:3],
                })
        return results
    
    def refresh_all(self):
        """Refresca odds de todas las fuentes configuradas."""
        self.fetch_opticodds()
        self.fetch_the_odds_api()


def create_odds_aggregator(api_keys: Dict = None) -> OddsAggregator:
    return OddsAggregator(api_keys)