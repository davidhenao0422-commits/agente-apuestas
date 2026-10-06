from predictors.engine import PredictionEngine

engine = PredictionEngine()

home_data = {
    "team_name": "Real Madrid",
    "league": "PD",
    "goals_per_game": 2.3,
    "conceded_per_game": 0.8,
    "form": "VVVEV",
    "home_performance": {"win_rate": 0.85},
}

away_data = {
    "team_name": "Barcelona",
    "league": "PD",
    "goals_per_game": 2.1,
    "conceded_per_game": 0.9,
    "form": "VVVED",
    "home_performance": {"win_rate": 0.78},
}

market_odds = {"1": 1.85, "X": 3.50, "2": 4.20}

result = engine.predict(home_data, away_data, market_odds=market_odds, bankroll=1000, kelly_frac=0.25)

import json
def safe_round(v, n=4):
    return round(v, n) if v is not None else None

print(json.dumps({
    "probabilities": {k: safe_round(v) for k, v in result["probabilities"].items()},
    "expected_goals": result["expected_goals"],
    "recommendations": [
        {
            "market": r["market"],
            "pick": r["pick_text"],
            "probability": safe_round(r["probability"]),
            "odds": r.get("odds"),
            "edge": safe_round(r.get("edge")),
            "confidence": r["confidence"],
        } for r in result["recommendations"]
    ],
    "confidence_score": result.get("confidence_score"),
    "confidence_breakdown": result.get("confidence_breakdown"),
    "ensemble_weights": result.get("ensemble_weights"),
    "brier_scores": {k: safe_round(v) for k, v in result.get("brier_scores", {}).items()},
    "kelly_stakes": {k: {sk: safe_round(sv) for sk, sv in v.items()} for k, v in result.get("kelly_stakes", {}).items()},
}, indent=2, ensure_ascii=False))