import pytest

from analyzers.poisson import (
    btts_probability,
    expected_goals,
    over_under_probabilities,
    poisson_probability,
    predict_match_scores,
)


class TestPoisson:
    def test_poisson_probability_basic(self):
        # λ=1, P(X=0) = e^-1 ≈ 0.3679
        assert poisson_probability(1.0, 0) == pytest.approx(0.367879, abs=0.001)

    def test_poisson_negative_lambda(self):
        with pytest.raises(ValueError):
            poisson_probability(-1.0, 0)

    def test_expected_goals(self):
        # Ataque fuerte local, defensa débil visitante => muchos goles esperados
        eg = expected_goals(2.5, 1.5)
        assert eg > 2.5
        # Ataque débil, defensa fuerte => pocos goles
        eg2 = expected_goals(0.8, 0.9)
        assert eg2 < 1.5

    def test_predict_match_scores_probabilities_sum(self):
        result = predict_match_scores(1.5, 1.2)
        total = result["home_win"] + result["draw"] + result["away_win"]
        assert total == pytest.approx(1.0, abs=0.01)

    def test_predict_match_scores_basics(self):
        result = predict_match_scores(1.5, 1.2)
        assert result["home_win"] > result["away_win"]
        assert 0 <= result["draw"] <= 0.5

    def test_over_under(self):
        result = over_under_probabilities(1.5, 1.5)
        assert result["over"] + result["under"] == pytest.approx(1.0, abs=0.01)
        # Con muchos goles esperados, over debe ser probable
        high = over_under_probabilities(3.0, 3.0)
        assert high["over"] > result["over"]

    def test_btts(self):
        prob = btts_probability(1.5, 1.5)
        assert 0 < prob < 1
        assert btts_probability(0.1, 0.1) < btts_probability(3.0, 3.0)