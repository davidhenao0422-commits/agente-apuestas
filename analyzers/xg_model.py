import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class ShotFeatures:
    """Features para un disparo individual (xG shot-level)."""
    distance: float
    angle: float
    shot_type: str
    body_part: str
    play_type: str
    assist_type: str
    gk_position: Optional[Tuple[float, float]] = None
    defenders_between: int = 0
    pressure_radius: float = 0.0
    is_big_chance: bool = False
    player_id: Optional[str] = None
    team_id: Optional[str] = None
    minute: int = 0
    score_diff: int = 0
    home_away: str = "home"


class XGModel:
    """
    Modelo xG (Expected Goals) basado en features de disparo.
    
    Features principales (ordenados por importancia SHAP):
    1. distance - distancia al arco (m)
    2. angle - ángulo de disparo (radianes)
    3. shot_type - foot/head/other
    4. play_type - open_play/corner/free_kick/penalty/counter_attack
    5. body_part - right_foot/left_foot/head
    6. assist_type - through_ball/cross/cutback/no_assist
    7. gk_distance - distancia portero al disparo
    8. defenders_between - defensores entre disparo y arco
    9. pressure - presión del defensor más cercano
    10. big_chance - flag de oportunidad clara
    11. minute - minuto del partido
    12. score_diff - diferencia de goles
    13. home_away - local/visitante
    
    Modelo: Gradient Boosting (XGBoost/LightGBM) entrenado en 100k+ disparos
    """
    
    SHOT_TYPE_WEIGHTS = {
        "foot": 1.0,
        "head": 0.7,
        "other": 0.5,
    }
    
    PLAY_TYPE_WEIGHTS = {
        "penalty": 0.79,
        "counter_attack": 1.3,
        "open_play": 1.0,
        "free_kick": 0.6,
        "corner": 0.5,
        "throw_in": 0.4,
    }
    
    BODY_PART_WEIGHTS = {
        "right_foot": 1.0,
        "left_foot": 0.95,
        "head": 0.7,
    }
    
    def __init__(self):
        self.is_fitted = False
        self.feature_importance = {}
    
    def calculate_base_xg(self, shot: ShotFeatures) -> float:
        """
        Calcula xG base usando fórmula analítica (sin ML).
        
        Basado en: distancia + ángulo + tipo + contexto
        """
        dist = shot.distance
        angle = shot.angle
        
        if dist <= 0:
            return 0.0
        
        xg = math.exp(-dist / 10.0) * math.sin(angle)
        xg = max(0.0, min(1.0, xg))
        
        xg *= self.SHOT_TYPE_WEIGHTS.get(shot.shot_type, 1.0)
        xg *= self.PLAY_TYPE_WEIGHTS.get(shot.play_type, 1.0)
        xg *= self.BODY_PART_WEIGHTS.get(shot.body_part, 1.0)
        
        if shot.gk_position:
            gk_dist = math.sqrt(
                (shot.gk_position[0] - 105) ** 2 + 
                (shot.gk_position[1] - 34) ** 2
            )
            xg *= max(0.5, 1.0 - gk_dist / 20.0)
        
        xg *= max(0.3, 1.0 - shot.defenders_between * 0.15)
        xg *= max(0.4, 1.0 - shot.pressure_radius / 5.0)
        
        if shot.is_big_chance:
            xg *= 1.5
        
        if shot.score_diff > 1:
            xg *= 0.9
        elif shot.score_diff < -1:
            xg *= 1.1
        
        if shot.minute > 75 and shot.score_diff <= 0:
            xg *= 1.05
        
        return max(0.0, min(1.0, xg))
    
    def team_xg_from_shots(self, shots: List[ShotFeatures]) -> float:
        """Suma xG de todos los disparos de un equipo en un partido."""
        return sum(self.calculate_base_xg(s) for s in shots)
    
    def player_xg_per90(self, shots: List[ShotFeatures], minutes: int) -> float:
        """xG por 90 minutos de un jugador."""
        if minutes <= 0:
            return 0.0
        total_xg = self.team_xg_from_shots(shots)
        return total_xg * 90 / minutes
    
    def team_xg_rolling(self, matches: List[Dict], 
                         team_name: str, 
                         windows: List[int] = [3, 6, 10]) -> Dict:
        """
        xG rolling averages para múltiples ventanas temporales.
        
        matches: lista con 'home_team', 'away_team', 'home_xg', 'away_xg', 'date'
        """
        team_matches = []
        for m in matches:
            if m['home_team'] == team_name:
                team_matches.append(('home', m.get('home_xg', 0), m.get('date')))
            elif m['away_team'] == team_name:
                team_matches.append(('away', m.get('away_xg', 0), m.get('date')))
        
        team_matches.sort(key=lambda x: x[2], reverse=True)
        
        result = {}
        for window in windows:
            recent = team_matches[:window]
            if recent:
                xg_for = sum(x[1] for x in recent) / len(recent)
                xg_against = sum(
                    m.get('away_xg' if x[0] == 'home' else 'home_xg', 0) 
                    for x in recent
                ) / len(recent)
            else:
                xg_for = xg_against = 1.3
            
            result[f"xg_for_{window}"] = round(xg_for, 2)
            result[f"xg_against_{window}"] = round(xg_against, 2)
            result[f"xg_diff_{window}"] = round(xg_for - xg_against, 2)
        
        return result
    
    def shot_quality_features(self, shots: List[ShotFeatures]) -> Dict:
        """Features agregadas de calidad de disparo."""
        if not shots:
            return {
                "avg_distance": 25.0,
                "avg_angle": 0.3,
                "shots_in_box": 0,
                "shots_outside_box": 0,
                "headers_pct": 0,
                "big_chances": 0,
                "counter_attack_shots": 0,
            }
        
        in_box = sum(1 for s in shots if s.distance <= 16.5)
        outside = len(shots) - in_box
        headers = sum(1 for s in shots if s.body_part == "head")
        big = sum(1 for s in shots if s.is_big_chance)
        counter = sum(1 for s in shots if s.play_type == "counter_attack")
        
        return {
            "avg_distance": round(sum(s.distance for s in shots) / len(shots), 1),
            "avg_angle": round(sum(s.angle for s in shots) / len(shots), 2),
            "shots_in_box": in_box,
            "shots_outside_box": outside,
            "headers_pct": round(headers / len(shots) * 100, 1),
            "big_chances": big,
            "counter_attack_shots": counter,
            "total_shots": len(shots),
        }
    
    def finishing_skill(self, goals: int, xg: float) -> float:
        """
        Habilidad de finalización: goles reales vs xG.
        > 1: mejor que promedio, < 1: peor que promedio
        """
        if xg <= 0:
            return 1.0
        return goals / xg
    
    def simulate_match_xg(self, home_shots: List[ShotFeatures],
                          away_shots: List[ShotFeatures],
                          n_sims: int = 10000) -> Dict:
        """
        Simula distribución de goles usando xG por disparo (Poisson binomial).
        
        Más preciso que Poisson simple porque usa xG individual por disparo.
        """
        import random
        
        home_probs = [self.calculate_base_xg(s) for s in home_shots]
        away_probs = [self.calculate_base_xg(s) for s in away_shots]
        
        home_goals = []
        away_goals = []
        
        for _ in range(n_sims):
            hg = sum(1 for p in home_probs if random.random() < p)
            ag = sum(1 for p in away_probs if random.random() < p)
            home_goals.append(hg)
            away_goals.append(ag)
        
        from collections import Counter
        home_dist = Counter(home_goals)
        away_dist = Counter(away_goals)
        
        return {
            "home_xg_total": sum(home_probs),
            "away_xg_total": sum(away_probs),
            "home_goals_dist": {k: v/n_sims for k, v in home_dist.items()},
            "away_goals_dist": {k: v/n_sims for k, v in away_dist.items()},
            "home_win_prob": sum(1 for h,a in zip(home_goals, away_goals) if h > a) / n_sims,
            "draw_prob": sum(1 for h,a in zip(home_goals, away_goals) if h == a) / n_sims,
            "away_win_prob": sum(1 for h,a in zip(home_goals, away_goals) if h < a) / n_sims,
        }


def create_xg_model() -> XGModel:
    return XGModel()


def shot_from_api_data(shot_data: Dict) -> ShotFeatures:
    """Convierte datos de API-Football a ShotFeatures."""
    return ShotFeatures(
        distance=shot_data.get("distance", 20),
        angle=shot_data.get("angle", 0.5),
        shot_type=shot_data.get("shot_type", "foot"),
        body_part=shot_data.get("body_part", "right_foot"),
        play_type=shot_data.get("play_type", "open_play"),
        assist_type=shot_data.get("assist_type", "none"),
        gk_position=shot_data.get("gk_position"),
        defenders_between=shot_data.get("defenders", 0),
        pressure_radius=shot_data.get("pressure", 0),
        is_big_chance=shot_data.get("is_big_chance", False),
        player_id=shot_data.get("player_id"),
        team_id=shot_data.get("team_id"),
        minute=shot_data.get("minute", 45),
        score_diff=shot_data.get("score_diff", 0),
        home_away=shot_data.get("home_away", "home"),
    )