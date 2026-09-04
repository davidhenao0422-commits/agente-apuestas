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
        home_played = sum(r["home_won"] + r["home_drawn"] + r["home_lost"] for r in rows)
        home_wr = sum(r["home_won"] for r in rows) / max(home_played, 1) if home_played > 0 else None

        # Forma reciente: derivar de won/drawn/lost de la última temporada
        last = rows[0]
        form_str = _build_form_string(last)

        # Si home_wr no está disponible (standings no trae stats por local),
        # estimarlo de la tasa general
        if home_wr is None or home_wr == 0:
            home_wr = sum(r["won"] for r in rows) / played_total if played_total > 0 else 0.5

        return {
            "position": pos,
            "goals_per_game": per_game(gf),
            "conceded_per_game": per_game(ga),
            "home_wr": round(home_wr, 2),
            "form": form_str,
            "shots": per_game(shots) if shots > 0 else None,
            "corners": per_game(corners) if corners > 0 else None,
            "possession": round(pos_avg, 1) if pos_avg > 0 else 50.0,
            "played": played_total,
            "_source": "real",
            "_seasons": [r["season"] for r in rows],
        }


def _build_form_string(row: dict) -> str:
    """Deriva una forma reciente (V/E/D) de los stats de una temporada."""
    won = row.get("won", 0)
    drawn = row.get("drawn", 0)
    lost = row.get("lost", 0)
    total = won + drawn + lost
    if total == 0:
        return "EEE"

    import random
    letters = list("V" * won + "E" * drawn + "D" * lost)
    rng = random.Random(abs(hash(str(row.get("season", "")))))
    rng.shuffle(letters)
    return "".join(letters[:5])

    def mark_stale_real_data(self, league_code: str) -> None:
        """(No op) - la DB guarda por equipo; aquí no hay limpieza global."""


def build_service(db) -> StatsService:
    return StatsService(db)