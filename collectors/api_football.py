import logging
from typing import Optional

import requests

from config import Config
from storage.database import Database

logger = logging.getLogger(__name__)


class APIFootballClient:
    """Cliente para la API v3 de API-Football (https://www.api-football.com/).

    Diseñado para minimizar el consumo del plan gratuito (100 requests/día):
    - Cachea agresivamente todas las respuestas.
    - Reutiliza api_id guardado en la DB en vez de re-buscar equipos.
    - Contador de requests para avisar cuándo queda poco margen.
    """

    DAILY_LIMIT = 100

    def __init__(self, db: Optional[Database] = None):
        self.api_key = Config.API_FOOTBALL_KEY
        self.base_url = Config.API_FOOTBALL_BASE_URL
        self.db = db or Database()
        self.session = requests.Session()
        self.session.headers.update({"x-apisports-key": self.api_key})
        self._request_count = 0

    @property
    def request_count(self) -> int:
        return self._request_count

    def _request(self, endpoint: str, params: dict = None, use_cache: bool = True):
        cache_key = f"api_football:{endpoint}:{params if params else ''}"
        if use_cache:
            cached = self.db.cache_get(cache_key)
            if cached:
                import json
                return json.loads(cached)

        # Antes de gastar un request real, verificar límite diario
        if self._request_count >= self.DAILY_LIMIT:
            logger.error(
                "Se alcanzó el límite diario de API-Football (%d requests). "
                "Responde desde datos cacheados si es posible.",
                self.DAILY_LIMIT,
            )
            return None

        url = f"{self.base_url}/{endpoint}"
        try:
            resp = self.session.get(url, params=params, timeout=15)
            self._request_count += 1
            resp.raise_for_status()
            data = resp.json()

            if data.get("results", 0) == 0 and "errors" in data and data["errors"]:
                logger.warning(f"API-Football sin resultados para {endpoint}: {data['errors']}")

            if use_cache:
                import json
                self.db.cache_set(cache_key, data, ttl_hours=Config.CACHE_TTL_HOURS)
            return data
        except requests.RequestException as e:
            logger.error(f"Error en API-Football ({endpoint}): {e}")
            return None

    def search_team(self, team_name: str) -> Optional[int]:
        """Busca el ID del equipo por nombre (con cacheo)."""
        data = self._request("teams", {"search": team_name})
        if not data or data.get("results", 0) == 0:
            return None
        return data["response"][0]["team"]["id"]

    def resolve_team_id(self, team_name: str, league: str = "") -> Optional[int]:
        """Devuelve el api_id del equipo reutilizando el guardado en la DB.

        Es el método recomendado para minimizar requests, ya que evita
        re-buscar un equipo que ya se resolvió antes.
        """
        row = self.db.query_one(
            "SELECT api_id FROM teams WHERE name = ? AND (? = '' OR league = ?)",
            (team_name, league, league),
        )
        if row and row["api_id"]:
            return row["api_id"]

        api_id = self.search_team(team_name)
        if api_id:
            self.db.upsert_team(team_name, league, api_id)
        return api_id

    def get_team_info(self, team_id: int) -> Optional[dict]:
        data = self._request("teams", {"id": team_id})
        if not data or data.get("results", 0) == 0:
            return None
        return data["response"][0]

    def fetch_and_store_season_stats(self, team_id: int, league_id: int,
                                     season: str, api_team_id: int,
                                     league_name: str) -> Optional[dict]:
        """Obtiene y guarda stats de temporada en la DB.

        Endpoint: /teams?season=2024&team=33&league=140
        Devuelve el dict de stats y lo persiste en 'team_stats'.
        """
        # Reutilizar lo ya guardado en DB si existe para esa temporada
        existing = self.db.get_team_stats(team_id, season)
        if existing:
            return existing

        data = self._request(
            "teams", {"season": season, "team": api_team_id, "league": league_id}
        )
        if not data or data.get("results", 0) == 0:
            return None

        team_entry = data["response"][0]
        stats = team_entry.get("statistics", [{}])
        stat_map = {s.get("type"): s.get("value") for s in stats}

        built = self._build_team_stats(team_entry, stat_map)
        built["season"] = season
        built["league"] = league_name
        self.db.upsert_team_stats(team_id, built)
        return built

    def get_season_stats(self, team_id: int, league_id: int, season: str) -> Optional[dict]:
        """Obtiene estadísticas de temporada para un equipo.

        Endpoint: /teams?season=2024&team=33&league=140
        Requiere conocer league_id y season para el filtro.
        """
        data = self._request("teams", {"season": season, "team": team_id, "league": league_id})
        if not data or data.get("results", 0) == 0:
            return None

        team_entry = data["response"][0]
        stats = team_entry.get("statistics", [{}])
        stat_map = {s.get("type"): s.get("value") for s in stats}

        return self._build_team_stats(team_entry, stat_map)

    def _build_team_stats(self, team_entry, stat_map) -> dict:
        def num(key):
            v = stat_map.get(key, 0)
            if v is None:
                return 0
            try:
                return int(v)
            except (TypeError, ValueError):
                return 0

        def repr_stats(key):
            """Devuelve stats de local/visitante en formato dict."""
            v = stat_map.get(key, {})
            if not isinstance(v, dict):
                return {}
            return v

        home = repr_stats("Fixtures: home")
        away = repr_stats("Fixtures: away")
        home_goals = repr_stats("Goals for: home")
        away_goals = repr_stats("Goals for: away")

        return {
            "position": num("rank") if "rank" in stat_map else None,
            "played": num("Fixtures: played"),
            "won": num("Fixtures: wins"),
            "drawn": num("Fixtures: draws"),
            "lost": num("Fixtures: loses"),
            "goals_for": num("Goals for: total"),
            "goals_against": num("Goals against: total"),
            "shots_on_target": num("Shots on target: total"),
            "corners": num("Corners: total"),
            "possession_avg": float(stat_map.get("Possession", 0) or 0),
            "home_won": home.get("wins", 0),
            "home_drawn": home.get("draws", 0),
            "home_lost": home.get("loses", 0),
            "home_goals_for": home_goals.get("total", 0),
            "home_goals_against": (stat_map.get("Goals against: home") or {}).get("total", 0),
            "away_won": away.get("wins", 0),
            "away_drawn": away.get("draws", 0),
            "away_lost": away.get("loses", 0),
            "away_goals_for": away_goals.get("total", 0),
            "away_goals_against": (stat_map.get("Goals against: away") or {}).get("total", 0),
        }

    def fetch_and_store_h2h(self, team_id_a: int, team_id_b: int,
                            api_team_id_a: int, api_team_id_b: int,
                            team_name_a: str, team_name_b: str,
                            limit: int = 10) -> list:
        """Obtiene y almacena los enfrentamientos directos en la DB."""
        data = self._request(
            "fixtures/headtohead", {"h2h": f"{api_team_id_a}-{api_team_id_b}"}
        )
        if not data or data.get("results", 0) == 0:
            return []

        stored = []
        for fixture in data["response"][:limit]:
            teams = fixture.get("teams", {})
            goals = fixture.get("goals", {})
            h = goals.get("home")
            a = goals.get("away")
            if h is None or a is None:
                continue

            date = fixture.get("fixture", {}).get("date")
            home_name = teams.get("home", {}).get("name")
            away_name = teams.get("away", {}).get("name")
            h_id = teams.get("home", {}).get("id")
            a_id = teams.get("away", {}).get("id")

            # Resolver IDs locales
            home_local = db_team_id_for(team_name_a, team_name_b, home_name,
                                        self.db)
            away_local = db_team_id_for(team_name_a, team_name_b, away_name,
                                        self.db)
            if home_local is None or away_local is None:
                continue

            self.db.insert_h2h({
                "team_id_a": team_id_a,
                "team_id_b": team_id_b,
                "match_date": date,
                "home_team": home_name,
                "away_team": away_name,
                "home_goals": h,
                "away_goals": a,
                "home_corners": teams.get("home", {}).get("corner", None),
                "away_corners": teams.get("away", {}).get("corner", None),
            })
            stored.append({
                "match_date": date,
                "home_team": home_name,
                "away_team": away_name,
                "home_goals": h,
                "away_goals": a,
                "home_team_id": h_id,
                "away_team_id": a_id,
            })
        return stored

    def get_league_by_name(self, league_name: str) -> Optional[int]:
        """Busca el ID de la liga por nombre (o nombre aproximado)."""
        data = self._request("leagues", {"search": league_name})
        if not data or data.get("results", 0) == 0:
            return None
        for league in data["response"]:
            if league_name.lower() in league["league"]["name"].lower():
                return league["league"]["id"]
        return data["response"][0]["league"]["id"]


def db_team_id_for(name_a: str, name_b: str, candidate: str,
                   db: Database) -> Optional[int]:
    """Resuelve el id local de un equipo a partir de su nombre API.

    El nombre en la API suele coincidir con el que el usuario dio, pero
    a veces trae sufijos. Se compara contra los dos equipos que se analizan.
    """
    norm = lambda s: s.lower().strip()
    target = norm(candidate)

    for name, id_key in ((name_a, "a"), (name_b, "b")):
        if norm(name) == target:
            row = db.query_one("SELECT id FROM teams WHERE name = ?", (name,))
            if row:
                return row["id"]
    return None
