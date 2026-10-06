import math
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from datetime import date, datetime


DEFAULT_ELO = 1500
HOME_ADVANTAGE = 65
K_FACTOR = 20
K_FACTOR_NEW_TEAM = 40


class EloModel:
    """Modelo Elo dinámico para fútbol con home advantage."""
    
    def __init__(self, default_elo: int = DEFAULT_ELO,
                 home_advantage: int = HOME_ADVANTAGE,
                 k_factor: int = K_FACTOR):
        self.ratings: Dict[str, float] = defaultdict(lambda: default_elo)
        self.default_elo = default_elo
        self.home_advantage = home_advantage
        self.k_factor = k_factor
        self.history: List[Dict] = []
    
    def expected_score(self, rating_a: float, rating_b: float) -> float:
        """Probabilidad esperada de que A gane a B."""
        return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400))
    
    def update(self, team_a: str, team_b: str,
               score_a: int, score_b: int,
               is_neutral: bool = False,
               date_str: str = None) -> Dict:
        """
        Actualiza ratings tras un partido.
        
        Retorna dict con cambios de rating y probabilidades pre-partido.
        """
        rating_a = self.ratings[team_a]
        rating_b = self.ratings[team_b]
        
        home_adv = 0 if is_neutral else self.home_advantage
        
        exp_a = self.expected_score(rating_a + home_adv, rating_b)
        exp_b = 1.0 - exp_a
        
        if score_a > score_b:
            actual_a, actual_b = 1.0, 0.0
        elif score_a < score_b:
            actual_a, actual_b = 0.0, 1.0
        else:
            actual_a, actual_b = 0.5, 0.5
        
        k = self.k_factor
        if len([h for h in self.history if h['team'] == team_a]) < 10:
            k = K_FACTOR_NEW_TEAM
        if len([h for h in self.history if h['team'] == team_b]) < 10:
            k = K_FACTOR_NEW_TEAM
        
        change_a = k * (actual_a - exp_a)
        change_b = k * (actual_b - exp_b)
        
        self.ratings[team_a] += change_a
        self.ratings[team_b] += change_b
        
        record = {
            "date": date_str or date.today().isoformat(),
            "team_a": team_a,
            "team_b": team_b,
            "score_a": score_a,
            "score_b": score_b,
            "rating_a_before": rating_a,
            "rating_b_before": rating_b,
            "rating_a_after": self.ratings[team_a],
            "rating_b_after": self.ratings[team_b],
            "change_a": change_a,
            "change_b": change_b,
            "exp_a": exp_a,
            "exp_b": exp_b,
            "is_neutral": is_neutral,
        }
        self.history.append(record)
        
        return record
    
    def get_rating(self, team: str) -> float:
        return self.ratings.get(team, self.default_elo)
    
    def predict_match(self, home_team: str, away_team: str,
                      is_neutral: bool = False) -> Dict:
        """Predice probabilidades 1X2 para un partido."""
        home_rating = self.get_rating(home_team)
        away_rating = self.get_rating(away_team)
        
        home_adv = 0 if is_neutral else self.home_advantage
        home_exp = self.expected_score(home_rating + home_adv, away_rating)
        away_exp = self.expected_score(away_rating, home_rating + home_adv)
        draw_exp = 1.0 - home_exp - away_exp
        
        return {
            "home_team": home_team,
            "away_team": away_team,
            "home_rating": home_rating,
            "away_rating": away_rating,
            "home_win": home_exp,
            "draw": max(0.0, draw_exp),
            "away_win": away_exp,
        }
    
    def simulate_season(self, fixtures: List[Dict],
                        num_sims: int = 1000) -> Dict:
        """Simula temporada Monte Carlo."""
        from collections import Counter
        
        final_positions = defaultdict(Counter)
        
        for _ in range(num_sims):
            sim_ratings = dict(self.ratings)
            
            for fix in fixtures:
                home = fix['home_team']
                away = fix['away_team']
                
                home_rating = sim_ratings.get(home, self.default_elo)
                away_rating = sim_ratings.get(away, self.default_elo)
                
                home_exp = self.expected_score(home_rating + self.home_advantage, away_rating)
                away_exp = self.expected_score(away_rating, home_rating + self.home_advantage)
                draw_exp = 1.0 - home_exp - away_exp
                
                r = random.random()
                if r < home_exp:
                    score_a, score_b = 2, 1
                elif r < home_exp + draw_exp:
                    score_a, score_b = 1, 1
                else:
                    score_a, score_b = 1, 2
                
                self._update_ratings(sim_ratings, home, away, score_a, score_b)
            
            sorted_teams = sorted(sim_ratings.items(), key=lambda x: x[1], reverse=True)
            for pos, (team, _) in enumerate(sorted_teams, 1):
                final_positions[team][pos] += 1
        
        return {team: dict(positions) for team, positions in final_positions.items()}
    
    def _update_ratings(self, ratings: Dict[str, float],
                        team_a: str, team_b: str,
                        score_a: int, score_b: int):
        rating_a = ratings.get(team_a, self.default_elo)
        rating_b = ratings.get(team_b, self.default_elo)
        
        exp_a = self.expected_score(rating_a + self.home_advantage, rating_b)
        
        if score_a > score_b:
            actual_a = 1.0
        elif score_a < score_b:
            actual_a = 0.0
        else:
            actual_a = 0.5
        
        ratings[team_a] += self.k_factor * (actual_a - exp_a)
        ratings[team_b] += self.k_factor * ((1 - actual_a) - (1 - exp_a))


def elo_from_results(matches: List[Dict], initial_ratings: Dict[str, float] = None) -> EloModel:
    """Construye modelo Elo desde histórico de partidos."""
    model = EloModel()
    
    if initial_ratings:
        model.ratings.update(initial_ratings)
    
    for m in matches:
        model.update(
            team_a=m['home_team'],
            team_b=m['away_team'],
            score_a=m['home_goals'],
            score_b=m['away_goals'],
            is_neutral=m.get('is_neutral', False),
            date_str=m.get('date')
        )
    
    return model


def elo_to_poisson_lambda(home_rating: float, away_rating: float,
                           league_avg: float = 2.5,
                           home_advantage: int = 65) -> Tuple[float, float]:
    """
    Convierte ratings Elo a lambdas Poisson esperados.
    
    Basado en: expected_goals = league_avg * exp((elo_diff) / scale)
    scale ~ 400 * ln(10) / (goals_per_rating_point) ≈ 200-250
    """
    elo_diff = (home_rating + home_advantage) - away_rating
    
    scale = 220.0
    home_multiplier = math.exp(elo_diff / scale)
    away_multiplier = math.exp(-elo_diff / scale)
    
    lambda_home = league_avg * home_multiplier / 2
    lambda_away = league_avg * away_multiplier / 2
    
    return lambda_home, lambda_away


import random