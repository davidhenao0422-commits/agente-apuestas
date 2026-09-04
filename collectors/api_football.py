import logging
import time
from typing import Optional

import requests

from config import Config
from storage.database import Database

logger = logging.getLogger(__name__)


class APIFootballClient:
    """Cliente para la API v3 de API-Football (https://www.api-football.com/).

    Diseñado para respetar los límites del plan gratuito:
    - 100 requests/día (límite global).
    - ~10 requests/minuto (límite de tasa).

    Estrategia:
    - Cachea agresivamente todas las respuestas.
    - Reutiliza api_id guardado en la DB en vez de re-buscar equipos.
    - Cuenta requests diarios y añade un retardo entre peticiones para no
      exceder el límite por minuto.
    """

    DAILY_LIMIT = 100
    MINUTE_LIMIT = 10
    MIN_INTERVAL = 6.0  # segundos entre requests para no pasar 10/min

    def __init__(self, db: Optional[Database] = None):
        self.api_key = Config.API_FOOTBALL_KEY
        self.base_url = Config.API_FOOTBALL_BASE_URL
        self.db = db or Database()
        self.session = requests.Session()
        self.session.headers.update({"x-apisports-key": self.api_key})
        self._request_count = 0
        self._last_request_time = 0.0

    @property
    def request_count(self) -> int:
        return self._request_count

    def _request(self, endpoint: str, params: dict = None, use_cache: bool = True,
                 retries: int = 2):
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

        for attempt in range(retries + 1):
            # Throttle: respetar el intervalo mínimo entre requests
            elapsed = time.time() - self._last_request_time
            if elapsed < self.MIN_INTERVAL:
                time.sleep(self.MIN_INTERVAL - elapsed)

            url = f"{self.base_url}/{endpoint}"
            try:
                resp = self.session.get(url, params=params, timeout=20)
                self._request_count += 1
                self._last_request_time = time.time()
                resp.raise_for_status()
                data = resp.json()

                # Detectar límite de tasa alcanzado
                errors = data.get("errors", {}) or {}
                if "rateLimit" in errors:
                    logger.warning(
                        f"Rate limit en {endpoint} (intento {attempt+1}). Esperando..."
                    )
                    time.sleep(10)  # esperar a que se libere la tasa
                    continue

                if data.get("results", 0) == 0:
                    logger.warning(
                        f"API-Football sin resultados para {endpoint}: {data['errors']}"
                    )

                if use_cache:
                    import json
                    self.db.cache_set(cache_key, data, ttl_hours=Config.CACHE_TTL_HOURS)
                return data
            except requests.RequestException as e:
                logger.error(f"Error en API-Football ({endpoint}): {e}")
                if attempt < retries:
                    time.sleep(3)
                    continue
                return None

        return None

    def search_team(self, team_name: str, league_id: Optional[int] = None) -> Optional[int]:
        """Busca el ID del equipo por nombre (con cacheo).

        Si se proporciona league_id, filtra por esa liga (más preciso).
        """
        params = {"search": team_name}
        if league_id is not None:
            params["league"] = league_id
        data = self._request("teams", params)
        if not data or data.get("results", 0) == 0:
            return None
        return data["response"][0]["team"]["id"]

    def resolve_team_id(self, team_name: str, league: str = "",
                        league_api_id: Optional[int] = None) -> Optional[int]:
        """Devuelve el api_id del equipo reutilizando el guardado en la DB.

        Es el método recomendado para minimizar requests, ya que evita
        re-buscar un equipo que ya se resolvió antes.
        Si league_api_id se proporciona, filtra por liga para mayor precisión.
        """
        row = self.db.query_one(
            "SELECT api_id FROM teams WHERE name = ? AND (? = '' OR league = ?)",
            (team_name, league, league),
        )
        if row and row["api_id"]:
            return row["api_id"]

        api_id = self.search_team(team_name, league_id=league_api_id)
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

    def fetch_and_store_standings(self, league_api_id: int, season: str) -> dict:
        """Obtiene la tabla de posiciones de una liga y guarda stats en la DB.

        Retorna dict con team_id → stats básicas. Solo hace 1 request.
        """
        data = self._request("standings", {"league": league_api_id, "season": season})
        if not data or data.get("results", 0) == 0:
            return {}

        result = {}
        for league_entry in data.get("response", []):
            for standings in league_entry.get("league", {}).get("standings", []):
                for row in standings:
                    team_info = row.get("team", {})
                    team_name = team_info.get("name", "")
                    team_api_id = team_info.get("id")
                    all_stats = row.get("all", {})
                    all_goals = all_stats.get("goals", {})

                    result[team_name] = {
                        "team_api_id": team_api_id,
                        "position": row.get("rank"),
                        "played": all_stats.get("played", 0),
                        "won": all_stats.get("win", 0),
                        "drawn": all_stats.get("draw", 0),
                        "lost": all_stats.get("lose", 0),
                        "goals_for": all_goals.get("for", 0),
                        "goals_against": all_goals.get("against", 0),
                        "goals_diff": row.get("goalsDiff", 0),
                        "points": row.get("points", 0),
                    }
        return result

    def get_upcoming_fixtures(self, league_api_id: int, limit: int = 10) -> list:
        """Obtiene los próximos partidos de una liga.

        Retorna lista de dicts con:
            'date', 'home_team', 'away_team', 'home_logo', 'away_logo'
        """
        data = self._request(
            "fixtures",
            {"league": league_api_id, "season": "2024", "next": limit, "status": "NS"}
        )
        if not data or data.get("results", 0) == 0:
            return []

        fixtures = []
        for fix in data.get("response", []):
            teams = fix.get("teams", {})
            fixture_info = fix.get("fixture", {})
            fixtures.append({
                "date": fixture_info.get("date", ""),
                "home_team": teams.get("home", {}).get("name", ""),
                "away_team": teams.get("away", {}).get("name", ""),
                "home_logo": teams.get("home", {}).get("logo", ""),
                "away_logo": teams.get("away", {}).get("logo", ""),
            })
        return fixtures


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
