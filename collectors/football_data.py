import logging
from typing import Optional

import requests

from config import Config
from storage.database import Database

logger = logging.getLogger(__name__)


class FootballDataClient:
    """Cliente para la API v4 de football-data.org."""

    def __init__(self, db: Optional[Database] = None):
        self.api_key = Config.FOOTBALL_DATA_KEY
        self.base_url = Config.FOOTBALL_DATA_BASE_URL
        self.db = db or Database()
        self.session = requests.Session()
        self.session.headers.update({"X-Auth-Token": self.api_key})

    def _request(self, endpoint: str, params: dict = None, use_cache: bool = True):
        cache_key = f"football_data:{endpoint}:{params if params else ''}"
        if use_cache:
            cached = self.db.cache_get(cache_key)
            if cached:
                import json
                return json.loads(cached)

        url = f"{self.base_url}/{endpoint}"
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if use_cache:
                import json
                self.db.cache_set(cache_key, data, ttl_hours=Config.CACHE_TTL_HOURS)
            return data
        except requests.RequestException as e:
            logger.error(f"Error en Football-data ({endpoint}): {e}")
            return None

    def get_team(self, team_name: str) -> Optional[dict]:
        data = self._request("teams", {"limit": 30})
        if not data:
            return None
        for team in data.get("teams", []):
            if team_name.lower() in team["name"].lower():
                return team
        return None

    def get_standings(self, competition_code: str, season: Optional[str] = None) -> Optional[list]:
        """Obtiene la tabla de posiciones de una competición."""
        params = {}
        if season:
            params["season"] = season
        data = self._request(f"competitions/{competition_code}/standings", params)
        if not data:
            return None
        standings = data.get("standings", [])
        if not standings:
            return None
        return standings[0].get("table", [])

    def get_team_stats_from_standings(self, competition_code: str) -> Optional[dict]:
        """Extrae stats de todos los equipos desde la tabla de posiciones."""
        table = self.get_standings(competition_code)
        if not table:
            return None

        result = {}
        for row in table:
            team_name = row["team"]["name"]
            result[team_name] = {
                "position": row.get("position"),
                "played": row.get("playedGames", 0),
                "won": row.get("won", 0),
                "drawn": row.get("draw", 0),
                "lost": row.get("lost", 0),
                "goals_for": row.get("goalsFor", 0),
                "goals_against": row.get("goalsAgainst", 0),
                "goal_difference": row.get("goalDifference", 0),
                "points": row.get("points", 0),
            }
        return result

    def get_recent_matches(self, team_id: int, limit: int = 10) -> Optional[list]:
        data = self._request(
            f"teams/{team_id}/matches",
            {"status": "FINISHED", "limit": limit},
        )
        if not data:
            return None
        return data.get("matches", [])

    def get_head_to_head(self, competition_code: str, home_team: str, away_team: str) -> list:
        """Nota: football-data.org no ofrece H2H directamente.
        Recolecta partidos y filtra manualmente."""
        data = self._request(
            f"competitions/{competition_code}/matches",
            {"status": "FINISHED", "limit": 100},
        )
        if not data:
            return []

        matches = []
        for match in data.get("matches", []):
            home = match.get("homeTeam", {}).get("name", "")
            away = match.get("awayTeam", {}).get("name", "")
            if (home == home_team and away == away_team) or \
               (home == away_team and away == home_team):
                score = match.get("score", {})
                ft = score.get("fullTime", {})
                matches.append({
                    "match_date": match.get("utcDate"),
                    "home_team": home,
                    "away_team": away,
                    "home_goals": ft.get("home"),
                    "away_goals": ft.get("away"),
                })
        return matches

    @staticmethod
    def league_code_map() -> dict:
        """Mapea nombre de liga a código en football-data.org."""
        return {
            "La Liga": "PD",
            "Premier League": "PL",
            "Serie A": "SA",
            "Bundesliga": "BL1",
            "Ligue 1": "FL1",
            "Champions League": "CL",
            "Europa League": "EL",
        }
