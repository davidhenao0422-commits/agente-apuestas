import pytest

from predictors.probabilities import (
    calculate_market_probabilities,
    normalize_probabilities,
)
from predictors.recommendations import build_recommendations


class TestProbabilities:
    def test_calculate_1x2_sums_to_1(self):
        probs = calculate_market_probabilities(1.5, 1.2)
        total = probs["1"] + probs["draw"] + probs["2"]
        assert total == pytest.approx(1.0, abs=0.01)

    def test_normalize(self):
        probs = {"1": 0.4, "draw": 0.4, "2": 0.2}
        normalized = normalize_probabilities(probs)
        total = normalized["1"] + normalized["draw"] + normalized["2"]
        assert total == pytest.approx(1.0)

    def test_strong_home_is_favored(self):
        probs = calculate_market_probabilities(2.5, 0.8)
        assert probs["1"] > probs["2"]


class TestRecommendations:
    def test_builds_recs_without_odds(self):
        probs = calculate_market_probabilities(2.0, 1.0)
        recs = build_recommendations(probs)
        assert len(recs) >= 3
        assert all("market" in r for r in recs)
        assert all("choice" in r for r in recs)

    def test_recommendation_confidence(self):
        probs = {"1": 0.85, "draw": 0.10, "2": 0.05,
                 "over_2.5": 0.50, "under_2.5": 0.50, "btts_yes": 0.40}
        recs = build_recommendations(probs, min_confidence=0.60)
        # El 1 con 85% debería estar recomendado
        rec_1 = [r for r in recs if r["choice"] == "1"][0]
        assert rec_1["recommended"] is True
        assert rec_1["confidence"] == "ALTA"

    def test_with_odds_enriches_and_filters(self):
        probs = calculate_market_probabilities(2.0, 0.5)
        recs_with_odds = build_recommendations(
            probs,
            odds={"1": 2.5, "X": 3.5, "2": 4.0},
            min_confidence=0.50,
        )
        for r in recs_with_odds:
            if r.get("odds") is not None:
                assert r.get("edge") is not None