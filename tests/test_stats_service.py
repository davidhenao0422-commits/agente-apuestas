"""Tests de integración para el servicio de stats y la recolección real.

Verifica que:
1) _fetch_and_store_team guarda stats reales en la DB.
2) StatsService prioriza datos reales sobre preseleccionados.
3) Sin datos reales, se cae a preseleccionados.
"""
import os
import tempfile
import pytest


@pytest.fixture
def tmp_db():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    os.environ["DB_PATH"] = db_path
    from storage.database import Database
    db = Database()
    yield db
    db._get_conn().close()


class FakeAPIClient:
    """Simula APIFootballClient con fetch_and_store_season_stats."""
    def __init__(self, stats_result, db=None):
        self.stats_result = stats_result
        self.db = db
        self.request_count = 0
        self.DAILY_LIMIT = 100

    def resolve_team_id(self, name, league=""):
        return 999

    def fetch_and_store_season_stats(self, team_local_id, league_id, season,
                                     api_id, league_name):
        self.request_count += 1
        if self.stats_result is None:
            return None
        built = {
            **self.stats_result,
            "season": season,
            "league": league_name,
        }
        self.db.upsert_team_stats(team_local_id, built)
        return built


def _team_row(db, name, league="La Liga"):
    return db.query_one(
        "SELECT id, api_id FROM teams WHERE name = ? AND league = ?",
        (name, league),
    )


def test_fetch_and_store_guarda_stats_reales(tmp_db):
    from web.app import _fetch_and_store_team

    api = FakeAPIClient({
        "position": 1, "played": 34, "won": 27, "drawn": 4, "lost": 3,
        "goals_for": 78, "goals_against": 26,
        "shots_on_target": 210, "corners": 320, "possession_avg": 58.0,
        "home_won": 15, "home_drawn": 1, "home_lost": 1,
        "home_goals_for": 48, "home_goals_against": 9,
        "away_won": 12, "away_drawn": 3, "away_lost": 2,
        "away_goals_for": 30, "away_goals_against": 17,
    }, db=tmp_db)

    ok = _fetch_and_store_team(api, tmp_db, "Real Madrid", "La Liga", 140, "2024")
    assert ok is True
    assert api.request_count == 1

    row = _team_row(tmp_db, "Real Madrid")
    assert row is not None
    assert row["api_id"] == 999

    stats = tmp_db.get_team_stats(row["id"], "2024")
    assert stats is not None
    assert stats["goals_for"] == 78


def test_stats_service_prioriza_datos_reales(tmp_db):
    from web.stats_service import StatsService

    # Insertar un equipo con stats reales "floja" (jugó poco)
    team_id = tmp_db.upsert_team("Saprissa", "CRC")
    tmp_db.upsert_team_stats(team_id, {
        "season": "2024", "league": "CRC", "position": 1,
        "played": 10, "won": 7, "drawn": 2, "lost": 1,
        "goals_for": 20, "goals_against": 6,
        "shots_on_target": 60, "corners": 55, "possession_avg": 55.0,
        "home_won": 5, "home_drawn": 0, "home_lost": 0,
        "home_goals_for": 12, "home_goals_against": 2,
        "away_won": 2, "away_drawn": 2, "away_lost": 1,
        "away_goals_for": 8, "away_goals_against": 4,
    })

    svc = StatsService(tmp_db)
    # Debe devolver datos REALES (source=real), no preseleccionados
    stats = svc.get_team_stats("Saprissa", "CRC")
    assert stats["_source"] == "real"
    assert stats["goals_per_game"] == pytest.approx(2.0)
    assert stats["conceded_per_game"] == pytest.approx(0.6)


def test_stats_service_cae_a_preseleccionado(tmp_db):
    from web.stats_service import StatsService

    svc = StatsService(tmp_db)
    # Equipo sin datos reales en DB → preseleccionado
    stats = svc.get_team_stats("Real Madrid", "PD")
    assert stats["_source"] == "preseleccionado"
    assert stats["goals_per_game"] > 0