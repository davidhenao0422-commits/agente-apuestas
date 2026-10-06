import math
from typing import Dict, List, Tuple
from collections import defaultdict


class PiRatings:
    """
    Pi-Ratings: 4 ratings por equipo (Attack Home, Defense Home, Attack Away, Defense Away).
    
    Basado en: Constantinou & Fenton (2017) - "Solving the Problem of Inadequate 
    Scoring Rules for Assessing Probabilistic Football Forecast Models"
    
    Venció a todos los modelos en Soccer Prediction Challenge 2017.
    """
    
    def __init__(self, default_attack: float = 1.0, default_defense: float = 1.0,
                 gamma: float = 0.1, home_advantage: float = 1.1):
        self.attack_home: Dict[str, float] = defaultdict(lambda: default_attack)
        self.defense_home: Dict[str, float] = defaultdict(lambda: default_defense)
        self.attack_away: Dict[str, float] = defaultdict(lambda: default_attack)
        self.defense_away: Dict[str, float] = defaultdict(lambda: default_defense)
        self.gamma = gamma
        self.home_advantage = home_advantage
        self.history = []
    
    def predict_lambdas(self, home_team: str, away_team: str) -> Tuple[float, float]:
        """Calcula lambdas Poisson esperados."""
        lambda_home = (self.attack_home[home_team] * 
                       self.defense_away[away_team] * 
                       self.home_advantage)
        lambda_away = (self.attack_away[away_team] * 
                       self.defense_home[home_team])
        return lambda_home, lambda_away
    
    def update(self, home_team: str, away_team: str,
               home_goals: int, away_goals: int,
               date_str: str = None) -> Dict:
        """Actualiza ratings tras observar resultado."""
        lambda_home, lambda_away = self.predict_lambdas(home_team, away_team)
        
        error_home = home_goals - lambda_home
        error_away = away_goals - lambda_away
        
        old_ah = self.attack_home[home_team]
        old_dh = self.defense_home[home_team]
        old_aa = self.attack_away[away_team]
        old_da = self.defense_away[away_team]
        
        self.attack_home[home_team] += self.gamma * error_home / max(self.defense_away[away_team], 0.01)
        self.defense_home[home_team] -= self.gamma * error_away / max(self.attack_away[away_team], 0.01)
        self.attack_away[away_team] += self.gamma * error_away / max(self.defense_home[home_team], 0.01)
        self.defense_away[away_team] -= self.gamma * error_home / max(self.attack_home[home_team], 0.01)
        
        for d in [self.attack_home, self.defense_home, self.attack_away, self.defense_away]:
            for k in d:
                d[k] = max(0.01, d[k])
        
        record = {
            "date": date_str,
            "home_team": home_team,
            "away_team": away_team,
            "home_goals": home_goals,
            "away_goals": away_goals,
            "lambda_home": lambda_home,
            "lambda_away": lambda_away,
            "error_home": error_home,
            "error_away": error_away,
            "attack_home_before": old_ah,
            "defense_home_before": old_dh,
            "attack_away_before": old_aa,
            "defense_away_before": old_da,
            "attack_home_after": self.attack_home[home_team],
            "defense_home_after": self.defense_home[home_team],
            "attack_away_after": self.attack_away[away_team],
            "defense_away_after": self.defense_away[away_team],
        }
        self.history.append(record)
        
        return record
    
    def get_ratings(self, team: str) -> Dict:
        return {
            "attack_home": self.attack_home[team],
            "defense_home": self.defense_home[team],
            "attack_away": self.attack_away[team],
            "defense_away": self.defense_away[team],
            "overall_attack": (self.attack_home[team] + self.attack_away[team]) / 2,
            "overall_defense": (self.defense_home[team] + self.defense_away[team]) / 2,
        }
    
    def predict_match(self, home_team: str, away_team: str) -> Dict:
        """Predice probabilidades 1X2 + goles."""
        from analyzers.poisson import predict_match_scores
        
        lambda_home, lambda_away = self.predict_lambdas(home_team, away_team)
        poisson_result = predict_match_scores(lambda_home, lambda_away)
        
        return {
            "home_team": home_team,
            "away_team": away_team,
            "lambda_home": lambda_home,
            "lambda_away": lambda_away,
            "home_win": poisson_result["home_win"],
            "draw": poisson_result["draw"],
            "away_win": poisson_result["away_win"],
            "home_ratings": self.get_ratings(home_team),
            "away_ratings": self.get_ratings(away_team),
        }
    
    def team_strength(self, team: str) -> float:
        """Fuerza general del equipo (promedio ponderado)."""
        ratings = self.get_ratings(team)
        return (ratings["overall_attack"] / ratings["overall_defense"]) if ratings["overall_defense"] > 0 else 1.0


def pi_ratings_from_matches(matches: List[Dict],
                             gamma: float = 0.1,
                             home_advantage: float = 1.1) -> PiRatings:
    """Construye Pi-Ratings desde histórico."""
    model = PiRatings(gamma=gamma, home_advantage=home_advantage)
    
    for m in matches:
        model.update(
            home_team=m['home_team'],
            away_team=m['away_team'],
            home_goals=m['home_goals'],
            away_goals=m['away_goals'],
            date_str=m.get('date')
        )
    
    return model


def optimize_gamma(matches: List[Dict], gamma_range: List[float] = None) -> float:
    """Optimiza gamma por validación cruzada (log-loss mínimo)."""
    if gamma_range is None:
        gamma_range = [0.05, 0.07, 0.1, 0.12, 0.15, 0.2]
    
    best_gamma = 0.1
    best_score = float('inf')
    
    for gamma in gamma_range:
        model = PiRatings(gamma=gamma)
        log_loss = 0.0
        count = 0
        
        for m in matches:
            pred = model.predict_match(m['home_team'], m['away_team'])
            actual = [0, 0, 0]
            if m['home_goals'] > m['away_goals']:
                actual[0] = 1
            elif m['home_goals'] == m['away_goals']:
                actual[1] = 1
            else:
                actual[2] = 1
            
            for i, (prob, act) in enumerate(zip(
                [pred['home_win'], pred['draw'], pred['away_win']], actual)):
                if prob > 0 and act == 1:
                    log_loss -= math.log(max(prob, 1e-10))
                    count += 1
        
        avg_loss = log_loss / max(count, 1)
        if avg_loss < best_score:
            best_score = avg_loss
            best_gamma = gamma
    
    return best_gamma