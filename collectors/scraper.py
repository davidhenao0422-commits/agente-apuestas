import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# Mapeo de códigos de liga a ESPN
ESPN_LEAGUES = {
    140: {"espn_id": "esp.1", "name": "La Liga"},
    39: {"espn_id": "eng.1", "name": "Premier League"},
    135: {"espn_id": "ita.1", "name": "Serie A"},
    78: {"espn_id": "ger.1", "name": "Bundesliga"},
    61: {"espn_id": "fra.1", "name": "Ligue 1"},
    2: {"espn_id": "uefa.champions", "name": "Champions League"},
}


class WebScraper:
    """Web scraping para estadísticas y fixtures."""

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get(self, url: str) -> Optional[dict]:
        time.sleep(self.delay)
        try:
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None

    def get_upcoming_fixtures_espn(self, league_api_id: int, limit: int = 10) -> list:
        """Obtiene próximos partidos desde ESPN (gratis, sin API key)."""
        league_info = ESPN_LEAGUES.get(league_api_id)
        if not league_info:
            return []

        espn_id = league_info["espn_id"]
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{espn_id}/scoreboard?dates=future&limit={limit}"

        data = self._get(url)
        if not data:
            return []

        events = data.get("events", [])
        fixtures = []
        for event in events[:limit]:
            competitions = event.get("competitions", [])
            if not competitions:
                continue
            comp = competitions[0]
            teams = comp.get("competitors", [])
            if len(teams) < 2:
                continue

            home = teams[0] if teams[0].get("homeAway") == "home" else teams[1]
            away = teams[1] if teams[0].get("homeAway") == "home" else teams[0]

            fixtures.append({
                "date": event.get("date", ""),
                "home_team": home.get("team", {}).get("displayName", ""),
                "away_team": away.get("team", {}).get("displayName", ""),
                "home_logo": home.get("team", {}).get("logo", ""),
                "away_logo": away.get("team", {}).get("logo", ""),
            })
        return fixtures
