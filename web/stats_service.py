"""Capa de servicios de stats para la app web.

Origen de datos con prioridad:
1. Datos REALES guardados en la DB (por recolector API-Football).
2. Datos preseleccionados (fallback cuando no hay API o datos reales).

Permite que la app funcione siempre, y que cuando el usuario actualice
desde la API obtenga estadísticas reales.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class StatsService:
    """Suministra stats de un equipo consultando DB real primero."""

    def __init__(self, db):
        self.db = db

    def get_team_stats(self, team_name: str, league_code: str,
                       league_id: Optional[int] = None) -> dict:
        """Devuelve stats: reales de DB si existen, si no preseleccionadas."""
        from web.preselected_data import get_team_stats as get_preselected

        real = self._from_db(team_name, league_code)
        if real:
            return real

        preselected = get_preselected(team_name, league_code)
        preselected["_source"] = "preseleccionado"
        return preselected

    def _from_db(self, team_name: str, league_code: str) -> Optional[dict]:
        """Busca stats reales agregados del equipo en la DB."""
        team = self.db.query_one(
            "SELECT id FROM teams WHERE name = ? AND league = ?",
            (team_name, league_code),
        )
        if not team:
            return None

        rows = self.db.query(
            """SELECT season, position, played, won, drawn, lost,
                      goals_for, goals_against, shots_on_target, corners,
                      possession_avg, home_won, home_drawn, home_lost,
                      home_goals_for, home_goals_against, away_won, away_drawn,
                      away_lost, away_goals_for, away_goals_against
               FROM team_stats WHERE team_id = ?
               ORDER BY season DESC LIMIT 3""",
            (team["id"],),
        )
        if not rows:
            return None

        played_total = sum(r["played"] for r in rows)
        if played_total <= 0:
            return None

        def per_game(total):
            return round(total / played_total, 2)

        pos = None
        for r in rows:
            if r["position"] is not None:
                pos = r["position"]
                break

        gf = sum(r["goals_for"] for r in rows)
        ga = sum(r["goals_against"] for r in rows)
        shots = sum(r["shots_on_target"] for r in rows)
        corners = sum(r["corners"] for r in rows)
        pos_avg = sum(r["possession_avg"] * r["played"] for r in rows) / played_total
        home_wr = sum(r["home_won"] for r in rows) / max(sum(r["home_won"] + r["home_drawn"] + r["home_lost"] for r in rows), 1)

        return {
            "position": pos,
            "goals_per_game": per_game(gf),
            "conceded_per_game": per_game(ga),
            "home_wr": round(home_wr, 2),
            "shots": per_game(shots),
            "corners": per_game(corners),
            "possession": round(pos_avg, 1),
            "played": played_total,
            "_source": "real",
            "_seasons": [r["season"] for r in rows],
        }

    def mark_stale_real_data(self, league_code: str) -> None:
        """(No op) - la DB guarda por equipo; aquí no hay limpieza global."""


def build_service(db) -> StatsService:
    return StatsService(db)