from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import date, timedelta
from collections import defaultdict


@dataclass
class PlayerInjury:
    player_id: str
    player_name: str
    team: str
    injury_type: str
    severity: str
    expected_return: Optional[date] = None
    status: str = "out"
    position: str = "unknown"
    market_value: float = 0.0
    minutes_played_pct: float = 0.0
    xg_per90: float = 0.0
    xa_per90: float = 0.0


@dataclass
class TeamInjuryImpact:
    team: str
    total_players_out: int
    key_players_out: int
    xg_loss_pct: float
    xa_loss_pct: float
    defense_loss_pct: float
    adjusted_xg_multiplier: float
    adjusted_xga_multiplier: float
    positions_affected: Dict[str, int]


POSITION_WEIGHTS = {
    "striker": {"xg": 0.7, "xa": 0.2, "defense": 0.05},
    "winger": {"xg": 0.4, "xa": 0.5, "defense": 0.1},
    "attacking_mid": {"xg": 0.3, "xa": 0.6, "defense": 0.1},
    "central_mid": {"xg": 0.15, "xa": 0.3, "defense": 0.3},
    "defensive_mid": {"xg": 0.05, "xa": 0.1, "defense": 0.6},
    "center_back": {"xg": 0.02, "xa": 0.05, "defense": 0.8},
    "fullback": {"xg": 0.1, "xa": 0.2, "defense": 0.5},
    "goalkeeper": {"xg": 0.0, "xa": 0.0, "defense": 1.0},
}


SEVERITY_MULTIPLIERS = {
    "minor": 0.3,
    "moderate": 0.6,
    "major": 0.9,
    "season_ending": 1.0,
    "doubtful": 0.2,
    "suspended": 1.0,
}


def calculate_injury_impact(team: str, injuries: List[PlayerInjury],
                            team_xg: float, team_xga: float,
                            squad_depth: Dict = None) -> TeamInjuryImpact:
    """
    Calcula impacto de lesiones en xG/xGA del equipo.
    
    Usa with/without splits concept: mide contribución del jugador
    y ajusta según profundidad de plantilla.
    """
    if not injuries:
        return TeamInjuryImpact(
            team=team,
            total_players_out=0,
            key_players_out=0,
            xg_loss_pct=0.0,
            xa_loss_pct=0.0,
            defense_loss_pct=0.0,
            adjusted_xg_multiplier=1.0,
            adjusted_xga_multiplier=1.0,
            positions_affected={},
        )
    
    total_xg_loss = 0.0
    total_xa_loss = 0.0
    total_def_loss = 0.0
    positions_affected = defaultdict(int)
    key_players = 0
    
    for inj in injuries:
        if inj.status not in ["out", "injured", "suspended"]:
            continue
        
        severity_mult = SEVERITY_MULTIPLIERS.get(inj.severity.lower(), 0.5)
        position = inj.position.lower()
        
        weights = POSITION_WEIGHTS.get(position, 
            {"xg": 0.2, "xa": 0.2, "defense": 0.2})
        
        player_xg_contrib = inj.xg_per90 * weights["xg"]
        player_xa_contrib = inj.xa_per90 * weights["xa"]
        player_def_contrib = weights["defense"]
        
        minutes_factor = inj.minutes_played_pct / 100
        value_factor = min(1.0, inj.market_value / 50_000_000)
        
        impact = severity_mult * minutes_factor * value_factor
        
        total_xg_loss += player_xg_contrib * impact
        total_xa_loss += player_xa_contrib * impact
        total_def_loss += player_def_contrib * impact
        
        positions_affected[position] += 1
        
        if inj.market_value > 20_000_000 or inj.minutes_played_pct > 70:
            key_players += 1
    
    xg_loss_pct = min(0.5, total_xg_loss / max(team_xg, 0.01))
    xa_loss_pct = min(0.5, total_xa_loss / max(team_xg * 0.5, 0.01))
    defense_loss_pct = min(0.4, total_def_loss / 11)
    
    depth_factor = 1.0
    if squad_depth:
        depth_factor = squad_depth.get(team, {}).get("depth_score", 1.0)
        depth_factor = max(0.7, min(1.2, depth_factor))
    
    xg_mult = 1.0 - xg_loss_pct * depth_factor
    xga_mult = 1.0 + defense_loss_pct * depth_factor
    
    return TeamInjuryImpact(
        team=team,
        total_players_out=len([i for i in injuries if i.status in ["out", "injured"]]),
        key_players_out=key_players,
        xg_loss_pct=round(xg_loss_pct * 100, 1),
        xa_loss_pct=round(xa_loss_pct * 100, 1),
        defense_loss_pct=round(defense_loss_pct * 100, 1),
        adjusted_xg_multiplier=round(xg_mult, 3),
        adjusted_xga_multiplier=round(xga_mult, 3),
        positions_affected=dict(positions_affected),
    )


def fetch_injuries_from_espn(league: str = "soccer") -> List[PlayerInjury]:
    """
    Obtiene lesiones desde ESPN API (gratis, sin auth, 15-min refresh).
    
    Endpoint: https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/injuries
    """
    import requests
    
    league_map = {
        "PD": "esp.1", "PL": "eng.1", "SA": "ita.1", 
        "BL1": "ger.1", "FL1": "fra.1", "CL": "uefa.champions"
    }
    
    espn_league = league_map.get(league, "eng.1")
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{espn_league}/injuries"
    
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        
        injuries = []
        for team_data in data.get("teams", []):
            team_name = team_data.get("team", {}).get("displayName", "")
            for player_data in team_data.get("injuries", []):
                athlete = player_data.get("athlete", {})
                injuries.append(PlayerInjury(
                    player_id=str(athlete.get("id", "")),
                    player_name=athlete.get("displayName", ""),
                    team=team_name,
                    injury_type=player_data.get("description", ""),
                    severity=player_data.get("status", "unknown"),
                    status=player_data.get("status", "unknown").lower(),
                    position=athlete.get("position", {}).get("abbreviation", "unknown").lower(),
                    market_value=0.0,
                    minutes_played_pct=0.0,
                    xg_per90=0.0,
                    xa_per90=0.0,
                ))
        return injuries
    except Exception as e:
        print(f"Error fetching ESPN injuries: {e}")
        return []


def apply_injury_adjustment(lambda_home: float, lambda_away: float,
                            home_impact: TeamInjuryImpact,
                            away_impact: TeamInjuryImpact) -> Tuple[float, float]:
    """Ajusta lambdas Poisson por impacto de lesiones."""
    adj_home = lambda_home * home_impact.adjusted_xg_multiplier
    adj_away = lambda_away * away_impact.adjusted_xg_multiplier
    
    adj_home *= (1 + (1 - home_impact.adjusted_xga_multiplier) * 0.5)
    adj_away *= (1 + (1 - away_impact.adjusted_xga_multiplier) * 0.5)
    
    return max(0.1, adj_home), max(0.1, adj_away)


def get_squad_depth_scores(teams_data: List[Dict]) -> Dict:
    """
    Calcula score de profundidad de plantilla por equipo.
    
    Basado en: valor de mercado total, minutos distribuidos, 
    calidad de suplentes (valor mercado > 5M).
    """
    depth = {}
    for team_data in teams_data:
        team = team_data.get("name", "")
        players = team_data.get("players", [])
        
        total_value = sum(p.get("market_value", 0) for p in players)
        starter_value = sum(p.get("market_value", 0) 
                          for p in players if p.get("minutes_pct", 0) > 60)
        bench_value = total_value - starter_value
        bench_quality = sum(1 for p in players 
                          if p.get("market_value", 0) > 5_000_000 
                          and p.get("minutes_pct", 0) < 30)
        
        depth_score = 1.0
        if starter_value > 0:
            depth_score = min(1.5, 0.8 + bench_value / starter_value + bench_quality * 0.05)
        
        depth[team] = {
            "total_value": total_value,
            "starter_value": starter_value,
            "bench_value": bench_value,
            "bench_quality_players": bench_quality,
            "depth_score": round(depth_score, 2),
        }
    
    return depth


def injury_adjusted_prediction(home_data: Dict, away_data: Dict,
                               home_injuries: List[PlayerInjury],
                               away_injuries: List[PlayerInjury],
                               squad_depth: Dict = None) -> Dict:
    """
    Aplica ajustes de lesiones a predicción.
    
    Retorna lambdas ajustados + detalles de impacto.
    """
    from analyzers.xg_model import XGModel
    
    xg_model = XGModel()
    home_xg = home_data.get("goals_per_game", 1.3)
    away_xg = away_data.get("goals_per_game", 1.3)
    home_xga = away_data.get("conceded_per_game", 1.3)
    away_xga = home_data.get("conceded_per_game", 1.3)
    
    home_impact = calculate_injury_impact(
        home_data.get("team_name", "Home"), home_injuries,
        home_xg, home_xga, squad_depth
    )
    away_impact = calculate_injury_impact(
        away_data.get("team_name", "Away"), away_injuries,
        away_xg, away_xga, squad_depth
    )
    
    adj_home, adj_away = apply_injury_adjustment(
        home_xg, away_xg, home_impact, away_impact
    )
    
    return {
        "lambda_home_adjusted": adj_home,
        "lambda_away_adjusted": adj_away,
        "home_impact": {
            "players_out": home_impact.total_players_out,
            "key_players_out": home_impact.key_players_out,
            "xg_loss_pct": home_impact.xg_loss_pct,
            "defense_loss_pct": home_impact.defense_loss_pct,
            "adjusted_multiplier": home_impact.adjusted_xg_multiplier,
            "positions": home_impact.positions_affected,
        },
        "away_impact": {
            "players_out": away_impact.total_players_out,
            "key_players_out": away_impact.key_players_out,
            "xg_loss_pct": away_impact.xg_loss_pct,
            "defense_loss_pct": away_impact.defense_loss_pct,
            "adjusted_multiplier": away_impact.adjusted_xg_multiplier,
            "positions": away_impact.positions_affected,
        },
    }