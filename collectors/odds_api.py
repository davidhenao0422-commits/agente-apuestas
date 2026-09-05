"""Cliente para The Odds API (https://the-odds-api.com/).

Plan gratuito:
- 1000 requests/mes
- Sin tarjeta de crédito
- Soporta: soccer, basketball, nfl, etc.
- Mercados: h2h (1X2), totals (over/under), btts, spreads
- Regiones: eu, us, uk
- Bookmakers: bet365, pinnacle, betfair, etc.

Rate limit: 500 requests/min (no problem).
"""

import logging
from typing import Dict, List, Optional

import requests

from config import Config
from storage.database import Database

logger = logging.getLogger(__name__)

# Mapeo de nuestro league_code a sport_key de The Odds API
# soccer_epl = Premier League, soccer_spain_la_liga = La Liga, etc.
LEAGUE_TO_SPORT_KEY = {
    "PL": "soccer_epl",
    "PD": "soccer_spain_la_liga",
    "SA": "soccer_italy_serie_a",
    "BL1": "soccer_germany_bundesliga",
    "FL1": "soccer_france_ligue_one",
    "CL": "soccer_uefa_champs_league",
    "PPL": "soccer_portugal_primeira_liga",
    "ERE": "soccer_netherlands_eredivisie",
    "ARG": "soccer_argentina_primera_division",
    "BRA": "soccer_brazil_campeonato",
    "MEX": "soccer_mexico_liga_mx",
    "COL": "soccer_colombia_liga_aguila",
    "PER": "soccer_peru_primera_division",
    "HON": "soccer_honduras_liga_nacional",
    "GUA": "soccer_guatemala_liga_nacional",
    "CRC": "soccer_costa_rica_primera_division",
    "PAN": "soccer_panama_liga_pk",
}

# Deporte por defecto si no hay mapeo
DEFAULT_SPORT = "soccer_epl"


class OddsAPIClient:
    """Cliente para The Odds API."""

    def __init__(self, db: Optional[Database] = None):
        self.api_key = Config.ODDS_API_KEY
        self.base_url = Config.ODDS_API_BASE_URL
        self.regions = Config.ODDS_API_REGIONS
        self.bookmakers = Config.ODDS_API_BOOKMAKERS
        self.db = db or Database()
        self.session = requests.Session()
        self._request_count = 0

    @property
    def request_count(self) -> int:
        return self._request_count

    def _request(self, endpoint: str, params: dict = None,
                 use_cache: bool = True, cache_ttl: int = 6) -> Optional[dict]:
        """Realiza request a The Odds API con cache."""
        cache_key = f"odds_api:{endpoint}:{params}"

        if use_cache:
            cached = self.db.cache_get(cache_key)
            if cached:
                import json
                return json.loads(cached)

        if not self.api_key:
            logger.warning("ODDS_API_KEY no configurada")
            return None

        url = f"{self.base_url}/{endpoint}"
        try:
            resp = self.session.get(url, params=params, timeout=15)
            self._request_count += 1
            resp.raise_for_status()
            data = resp.json()

            if use_cache:
                import json
                self.db.cache_set(cache_key, data, ttl_hours=cache_ttl)

            return data
        except requests.RequestException as e:
            logger.error(f"Error en Odds API ({endpoint}): {e}")
            return None

    def get_available_sports(self) -> List[dict]:
        """Obtiene deportes/ligas disponibles."""
        data = self._request("sports", use_cache=True, cache_ttl=24)
        if not data:
            return []
        return [
            {
                "key": s.get("key"),
                "title": s.get("title"),
                "active": s.get("active"),
                "group": s.get("group"),
            }
            for s in data
            if s.get("active")
        ]

    def get_odds(self, league_code: str, region: str = None,
                 bookmakers: str = None) -> List[dict]:
        """Obtiene odds para una liga específica.

        Retorna lista de partidos con odds de todos los bookmakers.
        """
        sport_key = LEAGUE_TO_SPORT_KEY.get(league_code, DEFAULT_SPORT)
        region = region or self.regions
        bk = bookmakers or self.bookmakers

        params = {
            "apiKey": self.api_key,
            "regions": region,
            "markets": "h2h,totals,btts",
            "bookmakers": bk,
        }

        data = self._request(f"sports/{sport_key}/odds/", params=params,
                             use_cache=True, cache_ttl=6)
        if not data:
            return []

        return self._parse_odds_response(data)

    def get_odds_multiple_leagues(self, league_codes: List[str],
                                   region: str = None,
                                   bookmakers: str = None) -> Dict[str, List[dict]]:
        """Obtiene odds para múltiples ligas (un request por liga)."""
        result = {}
        for code in league_codes:
            odds = self.get_odds(code, region, bookmakers)
            if odds:
                result[code] = odds
        return result

    def _parse_odds_response(self, data: list) -> List[dict]:
        """Parsea la respuesta de The Odds API a formato interno."""
        parsed = []

        for match in data:
            home_name = match.get("home_team", "")
            away_name = match.get("away_team", "")
            match_time = match.get("time", "")
            sport_key = match.get("sport_key", "")

            # Mapear sport_key de vuelta a nuestro league_code
            league_code = self._sport_key_to_league(sport_key)

            # Recoger odds promedio por mercado de todos los bookmakers
            odds_by_bookmaker = {}
            for bm in match.get("bookmakers", []):
                bm_name = bm.get("title", "")
                for market in bm.get("markets", []):
                    market_key = market.get("key", "")  # h2h, totals, btts
                    for outcome in market.get("outcomes", []):
                        outcome_name = outcome.get("name", "")
                        outcome_odds = outcome.get("price", 0)

                        if market_key == "h2h":
                            if outcome_name == home_name:
                                key = "1"
                            elif outcome_name == away_name:
                                key = "2"
                            else:
                                key = "X"
                        elif market_key == "totals":
                            point = market.get("point", 2.5)
                            if outcome_name == "Over":
                                key = f"over_{point}"
                            else:
                                key = f"under_{point}"
                        elif market_key == "btts":
                            if outcome_name == "Yes":
                                key = "btts_yes"
                            else:
                                key = "btts_no"
                        else:
                            continue

                        if key not in odds_by_bookmaker:
                            odds_by_bookmaker[key] = []

                        odds_by_bookmaker[key].append({
                            "bookmaker": bm_name,
                            "odds": outcome_odds,
                        })

            # Calcular odds promedio por mercado
            avg_odds = {}
            best_odds = {}
            for key, bm_list in odds_by_bookmaker.items():
                if not bm_list:
                    continue
                prices = [b["odds"] for b in bm_list if b["odds"] > 1]
                if prices:
                    avg_odds[key] = round(sum(prices) / len(prices), 3)
                    best = max(bm_list, key=lambda x: x["odds"])
                    best_odds[key] = {
                        "odds": best["odds"],
                        "bookmaker": best["bookmaker"],
                    }

            if avg_odds:
                parsed.append({
                    "match": f"{home_name} vs {away_name}",
                    "home_team": home_name,
                    "away_team": away_name,
                    "league_code": league_code,
                    "date": match_time,
                    "odds_avg": avg_odds,
                    "odds_best": best_odds,
                    "bookmakers_count": len(match.get("bookmakers", [])),
                })

        return parsed

    def _sport_key_to_league(self, sport_key: str) -> str:
        """Convierte sport_key de The Odds API a nuestro league_code."""
        for code, key in LEAGUE_TO_SPORT_KEY.items():
            if key == sport_key:
                return code
        return "UNKNOWN"

    def get_remaining_requests(self) -> Optional[int]:
        """Obtiene el número de requests restantes del mes.

        The Odds API devuelve el header x-requests-remaining.
        """
        if not self.api_key:
            return None

        try:
            resp = self.session.get(
                f"{self.base_url}/sports",
                params={"apiKey": self.api_key},
                timeout=10,
            )
            remaining = resp.headers.get("x-requests-remaining")
            used = resp.headers.get("x-requests-used")
            return {
                "remaining": int(remaining) if remaining else None,
                "used": int(used) if used else None,
            }
        except Exception:
            return None


def odds_to_internal_format(odds_data: dict) -> dict:
    """Convierte odds de The Odds API a formato interno del predictor.

    Input: odds_avg del parser (ej: {'1': 2.10, 'X': 3.40, '2': 3.20})
    Output: formato que el engine puede usar (ej: {'1': 2.10, 'X': 3.40, '2': 3.20})
    """
    return odds_data.get("odds_avg", {})
