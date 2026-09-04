import pytest

from analyzers.value_betting import (
    detect_value,
    implied_probability,
    value_edge,
)


class TestValueBetting:
    def test_implied_probability(self):
        assert implied_probability(2.0) == pytest.approx(0.5)
        assert implied_probability(3.0) == pytest.approx(1/3)
        assert implied_probability(1.0) == 0.0
        assert implied_probability(0.5) == 0.0

    def test_value_edge(self):
        # Prob 0.6 a cuota 2.0 => edge = 0.2 (positivo, valor)
        assert value_edge(0.6, 2.0) == pytest.approx(0.2)
        # Prob 0.4 a cuota 2.0 => edge = -0.2 (negativo, sin valor)
        assert value_edge(0.4, 2.0) == pytest.approx(-0.2)

    def test_detect_value_recommends_only_positive(self):
        probs = {"1": 0.55, "draw": 0.25, "2": 0.20}
        odds = {"1": 2.0, "X": 4.0, "2": 5.0}
        result = detect_value(probs, odds, min_edge=0.01)

        # "1" tiene edge = 0.55*2-1 = +0.10 -> recomendado
        rec_1 = [r for r in result if r["market"] == "1"][0]
        assert rec_1["recommended"] is True

        # "2" tiene edge = 0.20*5-1 = 0.0 < 0.01 -> NO recomendado
        rec_2 = [r for r in result if r["market"] == "2"][0]
        assert rec_2["recommended"] is False

    def test_detect_value_no_odds(self):
        result = detect_value({"1": 0.5}, {})
        assert result == []

    def test_detect_value_orders_by_edge(self):
        probs = {"1": 0.6, "2": 0.55}
        odds = {"1": 2.0, "2": 2.5}
        result = detect_value(probs, odds, min_edge=0.0)
        # "2" edge = 0.55*2.5-1 = +0.375; "1" edge = +0.20
        assert result[0]["market"] == "2"