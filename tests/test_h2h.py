import pytest

from analyzers.h2h import analyze_h2h, h2h_recent_form


def _make_matches(data):
    matches = []
    for entry in data:
        m = {
            "home_team": entry[0],
            "away_team": entry[1],
            "home_goals": entry[2],
            "away_goals": entry[3],
            "match_date": f"2024-{len(matches)+1:02d}-01",
        }
        matches.append(m)
    return matches


class TestH2H:
    def test_basic_analysis(self):
        matches = _make_matches([
            ("Real Madrid", "Barcelona", 2, 1),
            ("Barcelona", "Real Madrid", 1, 1),
            ("Real Madrid", "Barcelona", 0, 3),
        ])
        result = analyze_h2h(matches, "Real Madrid", "Barcelona")
        assert result.total_matches == 3
        assert result.team_a_wins == 1  # RM ganó 1
        assert result.team_b_wins == 1  # BARCELONA ganó 1
        assert result.draws == 1
        assert result.avg_goals_per_match == pytest.approx(8/3, abs=0.01)

    def test_empty(self):
        result = analyze_h2h([], "A", "B")
        assert result.total_matches == 0
        assert result.avg_goals_per_match == 0.0

    def test_recent_form(self):
        matches = _make_matches([
            ("A", "B", 1, 0),
            ("A", "B", 0, 0),
            ("A", "B", 0, 2),
            ("A", "B", 2, 0),
            ("A", "B", 1, 0),
        ])
        result = analyze_h2h(matches, "A", "B")
        assert h2h_recent_form(result, 5) == ["W", "D", "L", "W", "W"]

    def test_team_is_home_flag(self):
        matches = _make_matches([
            ("A", "B", 3, 0),
        ])
        result = analyze_h2h(matches, "A", "B")
        assert result.recent[0]["team_is_home"] is True
        assert result.recent[0]["team_goals"] == 3
        assert result.recent[0]["opp_goals"] == 0