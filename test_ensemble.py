from analyzers.ensemble import create_ensemble_predictor

predictor = create_ensemble_predictor()

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

result = predictor.predict(home_data, away_data, market_odds=market_odds)

import json
print(json.dumps({
    "probs": {k: round(v, 4) for k, v in result["probs"].items()},
    "lambda_home": result["lambda_home"],
    "lambda_away": result["lambda_away"],
    "weights_used": result.get("weights_used"),
    "brier_scores": {k: round(v, 4) for k, v in result.get("brier_scores", {}).items()},
}, indent=2, ensure_ascii=False))