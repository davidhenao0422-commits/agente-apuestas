import logging
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

BASE_FBREF = "https://fbref.com"
BASE_TRANSFERMARKT = "https://www.transfermarkt.com"


class WebScraper:
    """Web scraping de fallback para estadísticas avanzadas."""

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get(self, url: str) -> Optional[BeautifulSoup]:
        time.sleep(self.delay)  # Respetar rate limits
        try:
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as e:
            logger.error(f"Error scraping {url}: {e}")
            return None

    def get_team_stats_fbref(self, team_slug: str) -> Optional[dict]:
        """Extrae estadísticas de equipo desde FBref.

        Args:
            team_slug: URL slug tipo 'Real-Madrid/20062'.
        """
        url = f"{BASE_FBREF}/en/squads/{team_slug}"
        soup = self._get(url)
        if not soup:
            return None

        table = soup.find("table", {"id": "stats_squads_standard_for"})
        if not table:
            logger.warning(f"Tabla no encontrada para {team_slug}")
            return None

        stats = {}
        for row in table.find("tbody").find_all("tr"):
            cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) >= 10:
                stats["matches"] = cells[4]  # Jugados
                stats["goals"] = cells[5]
                stats["xg"] = cells[6]
                stats["shots_on_target"] = cells[10]
                stats["possession"] = cells[14]
                break
        return stats

    def get_team_value_transfermarkt(self, team_name: str) -> Optional[dict]:
        """Obtiene valores de mercado desde Transfermarkt."""
        url = f"{BASE_TRANSFERMARKT}/schnellsuche/ergebnis/schnellsuche"
        soup = self._get(url)
        # Nota: Transfermarkt requiere cookies/locale y cambia frecuentemente.
        # Este método es un placeholder para indicar dónde integrar.
        logger.info("Transfermarkt scraping dispone de anti-bot; revisar libs dedicadas.")
        return None
