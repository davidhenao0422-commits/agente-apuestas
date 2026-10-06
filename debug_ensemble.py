from analyzers.ensemble import create_ensemble_predictor
from analyzers.poisson import predict_match_scores
from analyzers.dixon_coles import predict_match_scores_dc
from analyzers.bivariate_poisson import predict_match_scores_biv, estimate_lambda3
from analyzers.value_betting import implied_probability

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

lambda_home = home_data.get("goals_per_game", 1.2)
lambda_away = away_data.get("goals_per_game", 1.2)

print("lambda_home:", lambda_home)
print("lambda_away:", lambda_away)

res = predict_match_scores(lambda_home, lambda_away)
print("poisson_basic probs:", res)

res = predict_match_scores_dc(lambda_home, lambda_away)
print("dixon_coles probs:", res)

res = predict_match_scores_biv(lambda_home, lambda_away, 0.0)
print("bivariate_poisson probs:", res)

market_probs = {k: implied_probability(v) for k, v in market_odds.items()}
total = sum(market_probs.values())
market_probs = {k: v/total for k, v in market_probs.items()}
print("market_consensus probs:", market_probs)

# Now test ModelPrediction
from analyzers.ensemble import ModelPrediction

mp1 = ModelPrediction("poisson_basic", res, lambda_home, lambda_away)
print("ModelPrediction probs type:", type(mp1.probs))
print("ModelPrediction probs:", mp1.probs)
print("Items:", list(mp1.probs.items()))

for k, v in mp1.probs.items():
    print(f"  {k}: {v} (type: {type(v)})")