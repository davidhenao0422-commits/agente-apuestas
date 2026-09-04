"""Datos base preseleccionados para los equipos del catálogo.

Estos valores son estadísticas aggregated de referencia (editable por el
usuario o actualizables desde API-Football). Se usan para generar
recomendaciones inmediatas sin consumir requests de la API.

Cada equipo puede sobreescribirse con datos reales al "actualizar" desde la API.
"""
import random
from typing import Optional

# Stats por defecto (ponderadas por liga). Se generan de forma determinista
# por equipo usando un seed derivado del nombre, para que sean estables.

_TEAM_OVERRIDES = {
    # La Liga
    ("Real Madrid", "PD"): {
        "position": 1, "goals_per_game": 2.4, "conceded_per_game": 0.9,
        "home_wr": 0.85, "form": "VVVVV", "shots": 7.2, "corners": 6.8,
        "possession": 57.0,
    },
    ("Barcelona", "PD"): {
        "position": 2, "goals_per_game": 2.2, "conceded_per_game": 1.1,
        "home_wr": 0.78, "form": "VVVVE", "shots": 6.9, "corners": 6.4,
        "possession": 60.0,
    },
    ("Atlético Madrid", "PD"): {
        "position": 3, "goals_per_game": 1.9, "conceded_per_game": 0.8,
        "home_wr": 0.80, "form": "VVEVV", "shots": 6.0, "corners": 5.4,
        "possession": 51.0,
    },
    # Premier League
    ("Manchester City", "PL"): {
        "position": 1, "goals_per_game": 2.5, "conceded_per_game": 0.9,
        "home_wr": 0.85, "form": "VVVEV", "shots": 7.5, "corners": 7.0,
        "possession": 61.0,
    },
    ("Arsenal", "PL"): {
        "position": 2, "goals_per_game": 2.1, "conceded_per_game": 0.9,
        "home_wr": 0.80, "form": "VVVDD", "shots": 7.0, "corners": 6.5,
        "possession": 58.0,
    },
    ("Liverpool", "PL"): {
        "position": 3, "goals_per_game": 2.3, "conceded_per_game": 1.0,
        "home_wr": 0.82, "form": "VVVVD", "shots": 6.8, "corners": 6.2,
        "possession": 59.0,
    },
    # Serie A
    ("Inter", "SA"): {
        "position": 1, "goals_per_game": 2.2, "conceded_per_game": 0.7,
        "home_wr": 0.85, "form": "VVVVV", "shots": 6.5, "corners": 5.8,
        "possession": 55.0,
    },
    ("Milan", "SA"): {
        "position": 2, "goals_per_game": 2.0, "conceded_per_game": 1.0,
        "home_wr": 0.75, "form": "VEVVV", "shots": 6.2, "corners": 5.2,
        "possession": 53.0,
    },
    # Bundesliga
    ("Bayern Munich", "BL1"): {
        "position": 1, "goals_per_game": 2.7, "conceded_per_game": 0.8,
        "home_wr": 0.90, "form": "VVVVV", "shots": 8.0, "corners": 7.2,
        "possession": 62.0,
    },
    # Ligue 1
    ("Paris Saint Germain", "FL1"): {
        "position": 1, "goals_per_game": 2.6, "conceded_per_game": 0.9,
        "home_wr": 0.88, "form": "VVVVV", "shots": 7.8, "corners": 6.9,
        "possession": 63.0,
    },
    # Sudamérica destacados
    ("Boca Juniors", "ARG"): {
        "position": 1, "goals_per_game": 1.8, "conceded_per_game": 0.7,
        "home_wr": 0.80, "form": "VVVDV", "shots": 6.0, "corners": 5.2,
        "possession": 54.0,
    },
    ("River Plate", "ARG"): {
        "position": 2, "goals_per_game": 2.0, "conceded_per_game": 0.8,
        "home_wr": 0.82, "form": "VVVVE", "shots": 6.4, "corners": 5.6,
        "possession": 56.0,
    },
    ("Flamengo", "BRA"): {
        "position": 1, "goals_per_game": 2.1, "conceded_per_game": 0.8,
        "home_wr": 0.85, "form": "VVVEV", "shots": 6.7, "corners": 5.8,
        "possession": 57.0,
    },
    ("Palmeiras", "BRA"): {
        "position": 2, "goals_per_game": 1.9, "conceded_per_game": 0.7,
        "home_wr": 0.82, "form": "VVVVD", "shots": 6.3, "corners": 5.4,
        "possession": 55.0,
    },
    ("América", "MEX"): {
        "position": 1, "goals_per_game": 1.9, "conceded_per_game": 0.9,
        "home_wr": 0.75, "form": "VVVDV", "shots": 6.1, "corners": 5.0,
        "possession": 54.0,
    },
    ("Tigres UANL", "MEX"): {
        "position": 2, "goals_per_game": 1.8, "conceded_per_game": 0.8,
        "home_wr": 0.78, "form": "VVEVV", "shots": 5.9, "corners": 4.8,
        "possession": 53.0,
    },
    ("Atlético Nacional", "COL"): {
        "position": 1, "goals_per_game": 1.7, "conceded_per_game": 0.8,
        "home_wr": 0.75, "form": "VVVED", "shots": 5.8, "corners": 4.9,
        "possession": 53.0,
    },
    ("Millonarios", "COL"): {
        "position": 2, "goals_per_game": 1.6, "conceded_per_game": 0.9,
        "home_wr": 0.70, "form": "VEVVD", "shots": 5.6, "corners": 4.6,
        "possession": 52.0,
    },
    ("Universitario", "PER"): {
        "position": 1, "goals_per_game": 1.7, "conceded_per_game": 0.8,
        "home_wr": 0.74, "form": "VVVVE", "shots": 5.7, "corners": 4.7,
        "possession": 52.0,
    },
    ("Alianza Lima", "PER"): {
        "position": 2, "goals_per_game": 1.6, "conceded_per_game": 0.9,
        "home_wr": 0.72, "form": "VVVDV", "shots": 5.5, "corners": 4.5,
        "possession": 51.0,
    },
    # Centroamérica
    ("Olimpia", "HON"): {
        "position": 1, "goals_per_game": 1.8, "conceded_per_game": 0.6,
        "home_wr": 0.85, "form": "VVVVV", "shots": 6.0, "corners": 5.4,
        "possession": 56.0,
    },
    ("Motagua", "HON"): {
        "position": 2, "goals_per_game": 1.6, "conceded_per_game": 0.8,
        "home_wr": 0.78, "form": "VVVEV", "shots": 5.6, "corners": 4.9,
        "possession": 54.0,
    },
    ("Comunicaciones", "GUA"): {
        "position": 1, "goals_per_game": 1.7, "conceded_per_game": 0.7,
        "home_wr": 0.80, "form": "VVVVD", "shots": 5.8, "corners": 5.0,
        "possession": 55.0,
    },
    ("Saprissa", "CRC"): {
        "position": 1, "goals_per_game": 1.8, "conceded_per_game": 0.7,
        "home_wr": 0.82, "form": "VVVVV", "shots": 6.1, "corners": 5.3,
        "possession": 55.0,
    },
    ("Alajuelense", "CRC"): {
        "position": 2, "goals_per_game": 1.6, "conceded_per_game": 0.8,
        "home_wr": 0.76, "form": "VVEVV", "shots": 5.7, "corners": 4.8,
        "possession": 53.0,
    },
    ("Plaza Amador", "PAN"): {
        "position": 1, "goals_per_game": 1.6, "conceded_per_game": 0.8,
        "home_wr": 0.75, "form": "VVVED", "shots": 5.5, "corners": 4.6,
        "possession": 52.0,
    },
}


def _default_stats(team: str, league_code: str) -> dict:
    """Genera stats base deterministas para equipos sin override."""
    seed = abs(hash(f"{team}:{league_code}")) % 1000
    rng = random.Random(seed)
    strength = 0.35 + (seed % 50) / 100.0  # 0.35 - 0.85
    return {
        "position": None,
        "goals_per_game": round(0.9 + strength * 1.3, 2),
        "conceded_per_game": round(1.6 - strength * 0.8, 2),
        "home_wr": round(range_home(seed), 2),
        "form": gen_form(seed),
        "shots": round(4.0 + strength * 3.0, 1),
        "corners": round(3.5 + strength * 3.0, 1),
        "possession": round(45 + strength * 15, 1),
    }


def range_home(seed: int) -> float:
    if seed % 3 == 0:
        return 0.80
    if seed % 3 == 1:
        return 0.65
    return 0.90


def gen_form(seed: int) -> str:
    letters = ["V", "E", "D"]
    rng = random.Random(seed)
    return "".join(rng.choice(letters) for _ in range(5))


def get_team_stats(team: str, league_code: str) -> dict:
    """Devuelve stats para un equipo, preferentemente el override."""
    override = _TEAM_OVERRIDES.get((team, league_code))
    if override:
        return dict(override)
    return _default_stats(team, league_code)


def all_teams_with_stats(league_code: str, teams: list) -> list:
    result = []
    for team in teams:
        stats = get_team_stats(team, league_code)
        result.append({"name": team, **stats})
    return result