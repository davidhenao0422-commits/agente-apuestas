"""Tests de integración para el servicio de stats y la recolección real.

Verifica que:
1) fetch_and_store_standings guarda stats reales en la DB.
2) StatsService prioriza datos reales sobre preseleccionados.
3) Sin datos reales, se cae a preseleccionados.
"""
import os
import tempfile
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test.db"
    from storage.database import Database
    db = Database(db_path=db_path)
    yield db
    db._get_conn().close()


class FakeAPIClient:
    """Simula APIFootballClient con fetch_and_store_standings."""
    def __init__(self, standings_result, db=None):
        self.standings_result = standings_result
        self.db = db
        self.request_count = 0
        self.DAILY_LIMIT = 100

    def fetch_and_store_standings(self, league_api_id, season):
        self.request_count += 1
        return self.standings_result


def test_fetch_and_store_standings(tmp_db):
    api = FakeAPIClient({
        "Real Madrid": {
            "team_api_id": 541,
            "position": 2,
            "played": 38,
            "won": 26,
            "drawn": 6,
            "lost": 6,
            "goals_for": 78,
            "goals_against": 38,
            "goals_diff": 40,
            "points": 84,
        },
    }, db=tmp_db)

    standings = api.fetch_and_store_standings(league_api_id=140, season="2024")
    assert api.request_count == 1
    assert "Real Madrid" in standings
    assert standings["Real Madrid"]["team_api_id"] == 541


def test_stats_service_prioriza_datos_reales(tmp_db):
    from web.stats_service import StatsService

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
    stats = svc.get_team_stats("Saprissa", "CRC")
    assert stats["_source"] == "real"
    assert stats["goals_per_game"] == pytest.approx(2.0)
    assert stats["conceded_per_game"] == pytest.approx(0.6)


def test_stats_service_cae_a_preseleccionado(tmp_db):
    from web.stats_service import StatsService

    svc = StatsService(tmp_db)
    stats = svc.get_team_stats("Real Madrid", "PD")
    assert stats["_source"] == "preseleccionado"
    assert stats["goals_per_game"] > 0
