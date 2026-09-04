from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Team:
    name: str
    league: str
    api_id: Optional[int] = None
    id: Optional[int] = None
    created_at: Optional[str] = None

    def __str__(self):
        return f"{self.name} ({self.league})"


@dataclass
class Match:
    home_team_id: int
    away_team_id: int
    match_date: str
    league: str = ""
    season: str = ""
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None
    home_shots: Optional[int] = None
    away_shots: Optional[int] = None
    home_corners: Optional[int] = None
    away_corners: Optional[int] = None
    home_possession: Optional[float] = None
    away_possession: Optional[float] = None
    id: Optional[int] = None


@dataclass
class TeamStats:
    """Estadisticas agregadas de un equipo para una temporada."""
    team: str
    league: str
    season: str
    position: Optional[int] = None
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    shots_on_target: int = 0
    corners: int = 0
    possession_avg: float = 0.0
    home_won: int = 0
    home_drawn: int = 0
    home_lost: int = 0
    home_goals_for: int = 0
    home_goals_against: int = 0
    away_won: int = 0
    away_drawn: int = 0
    away_lost: int = 0
    away_goals_for: int = 0
    away_goals_against: int = 0

    @property
    def goals_per_game(self) -> float:
        return round(self.goals_for / max(self.played, 1), 2)

    @property
    def conceded_per_game(self) -> float:
        return round(self.goals_against / max(self.played, 1), 2)

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against

    @property
    def shots_on_target_per_game(self) -> float:
        return round(self.shots_on_target / max(self.played, 1), 2)

    @property
    def corners_per_game(self) -> float:
        return round(self.corners / max(self.played, 1), 2)


@dataclass
class H2H:
    """Enfrentamientos directos entre dos equipos."""
    team_a: str
    team_b: str
    total_matches: int = 0
    team_a_wins: int = 0
    team_b_wins: int = 0
    draws: int = 0
    total_goals: int = 0
    avg_goals_per_match: float = 0.0
    avg_corners_per_match: float = 0.0
    recent: list = field(default_factory=list)


@dataclass
class Prediction:
    match_description: str
    recommendations: list = field(default_factory=list)
    confidence: str = ""
    probabilities: dict = field(default_factory=dict)
    expected_goals: float = 0.0
    reasoning: str = ""
    created_at: Optional[str] = None
    id: Optional[int] = None
