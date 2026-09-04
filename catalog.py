"""Catálogo precargado de ligas y equipos.

Organizado por región: Europa, Latinoamérica y Centroamérica.
Cada liga tiene un código, nombre, región y la lista de equipos (con su
nombre usado en la API para resolver api_id al actualizar datos).
"""

CATALOGO = {
    "region_europa": {
        "label": "Europa",
        "leagues": {
            "PD": {
                "name": "La Liga (España)",
                "api_league_id": 140,
                "teams": [
                    "Real Madrid", "Barcelona", "Atlético Madrid", "Athletic Bilbao",
                    "Girona", "Real Betis", "Real Sociedad", "Villarreal",
                    "Sevilla", "Valencia", "Osasuna", "Celta Vigo", "Espanyol",
                    "Rayo Vallecano", "Getafe", "Mallorca", "Valladolid", "Alavés",
                    "Las Palmas", "Leganés",
                ],
            },
            "PL": {
                "name": "Premier League (Inglaterra)",
                "api_league_id": 39,
                "teams": [
                    "Manchester City", "Arsenal", "Liverpool", "Chelsea",
                    "Tottenham", "Manchester United", "Newcastle", "Aston Villa",
                    "Brighton", "West Ham", "Wolverhampton", "Crystal Palace",
                    "Brentford", "Bournemouth", "Fulham", "Everton", "Nottingham Forest",
                    "Burnley", "Luton", "Sheffield United",
                ],
            },
            "SA": {
                "name": "Serie A (Italia)",
                "api_league_id": 135,
                "teams": [
                    "Inter", "Milan", "Juventus", "Napoli", "Roma", "Atalanta",
                    "Lazio", "Fiorentina", "Bologna", "Torino", "Monza", "Udinese",
                    "Cagliari", "Genoa", "Lecce", "Empoli", "Sassuolo", "Verona",
                    "Salernitana", "Frosinone",
                ],
            },
            "BL1": {
                "name": "Bundesliga (Alemania)",
                "api_league_id": 78,
                "teams": [
                    "Bayern Munich", "Borussia Dortmund", "RB Leipzig",
                    "Bayer Leverkusen", "VfL Wolfsburg", "Eintracht Frankfurt",
                    "SC Freiburg", "TSG Hoffenheim", "FC Augsburg", "Borussia Mönchengladbach",
                    "Mainz 05", "VfB Stuttgart", "Union Berlin", "Werder Bremen",
                    "Cologne", "Bochum", "Darmstadt", "Heidenheim",
                ],
            },
            "FL1": {
                "name": "Ligue 1 (Francia)",
                "api_league_id": 61,
                "teams": [
                    "Paris Saint Germain", "Marseille", "Lyon", "Monaco", "Lille",
                    "Rennes", "Nice", "Lens", "Toulouse", "Reims", "Strasbourg",
                    "Nantes", "Montpellier", "Le Havre", "Brest", "Metz", "Clermont",
                    "Lorient",
                ],
            },
            "PPL": {
                "name": "Primeira Liga (Portugal)",
                "api_league_id": 94,
                "teams": [
                    "Benfica", "Porto", "Sporting CP", "Braga", "Vitória SC",
                    "Famalicão", "Gil Vicente", "Rio Ave", "Boavista", "Farense",
                    "Arouca", "Casa Pia", "Estoril", "Portimonense", "Chaves",
                ],
            },
            "ERE": {
                "name": "Eredivisie (Países Bajos)",
                "api_league_id": 88,
                "teams": [
                    "Ajax", "PSV", "Feyenoord", "Twente", "AZ Alkmaar",
                    "Vitesse", "Utrecht", "Sparta Rotterdam", "NEC Nijmegen",
                    "Heerenveen", "Go Ahead Eagles", "Fortuna Sittard", "PEC Zwolle",
                    "Excelsior", "RKC Waalwijk", "Volendam", "Almere City",
                    "Heracles", "Emmen",
                ],
            },
            "CL": {
                "name": "Champions League (Europea)",
                "api_league_id": 2,
                "teams": [
                    "Real Madrid", "Manchester City", "Bayern Munich", "Paris Saint Germain",
                    "Barcelona", "Arsenal", "Inter", "Liverpool", "Borussia Dortmund",
                    "Atlético Madrid",
                ],
            },
        },
    },
    "region_latinoamerica": {
        "label": "Latinoamérica",
        "leagues": {
            "ARG": {
                "name": "Liga Profesional (Argentina)",
                "api_league_id": 128,
                "teams": [
                    "Boca Juniors", "River Plate", "Racing Club", "Independiente",
                    "San Lorenzo", "Vélez Sarsfield", "Estudiantes", "Talleres",
                    "Godoy Cruz", "Rosario Central", "Gimnasia", "Newell's Old Boys",
                    "Argentinos Juniors", "Lanús", "Banfield", "Huracán",
                ],
            },
            "BRA": {
                "name": "Brasileirão Série A (Brasil)",
                "api_league_id": 71,
                "teams": [
                    "Flamengo", "Palmeiras", "São Paulo", "Corinthians",
                    "Fluminense", "Atlético Mineiro", "Grêmio", "Internacional",
                    "Botafogo", "Santos", "Cruzeiro", "Vasco da Gama",
                    "Athletico Paranaense", "Fortaleza", "Bahia", "Red Bull Bragantino",
                ],
            },
            "MEX": {
                "name": "Liga MX (México)",
                "api_league_id": 262,
                "teams": [
                    "América", "Guadalajara", "Cruz Azul", "Tigres UANL",
                    "Monterrey", "Pumas UNAM", "León", "Santos Laguna",
                    "Toluca", "Pachuca", "Tijuana", "Atlas", "Necaxa",
                    "Mazatlán", "Puebla", "Querétaro",
                ],
            },
            "COL": {
                "name": "Liga BetPlay (Colombia)",
                "api_league_id": 239,
                "teams": [
                    "Atlético Nacional", "Millonarios", "América de Cali",
                    "Deportivo Cali", "Junior", "Independiente Santa Fe",
                    "Once Caldas", "Deportes Tolima", "La Equidad", "Águilas Doradas",
                    "Envigado", "Boyacá Chicó", "Alianza Petrolera", "Jaguares",
                ],
            },
            "PER": {
                "name": "Liga 1 (Perú)",
                "api_league_id": 301,
                "teams": [
                    "Universitario", "Alianza Lima", "Sporting Cristal",
                    "Cienciano", "Melgar", "Cusco FC", "Sport Boys", "UTC Cajamarca",
                    "Deportivo Municipal", "Ayacucho", "Alianza Atlético", "Los Chankas",
                ],
            },
        },
    },
    "region_centroamerica": {
        "label": "Centroamérica",
        "leagues": {
            "HON": {
                "name": "Liga Nacional (Honduras)",
                "api_league_id": 332,
                "teams": [
                    "Olimpia", "Motagua", "Real España", "Marathón", "Vida",
                    "Victoria", "Platense", "Olancho", "Juticalpa", "Genesis",
                ],
            },
            "GUA": {
                "name": "Liga Nacional (Guatemala)",
                "api_league_id": 333,
                "teams": [
                    "Comunicaciones", "Municipal", "Antigua GFC", "Xelajú MC",
                    "Cobán Imperial", "Guastatoya", "Malacateco", "Mixco",
                    "Achí de Quiché", "Aurora",
                ],
            },
            "CRC": {
                "name": "Primera División (Costa Rica)",
                "api_league_id": 329,
                "teams": [
                    "Saprissa", "Alajuelense", "Herediano", "Cartaginés",
                    "San Carlos", "Pérez Zeledón", "Guadalupe", "Sporting San José",
                    "Guanacasteca", "Puntarenas", "Liberia",
                ],
            },
            "PAN": {
                "name": "Liga Panameña de Fútbol",
                "api_league_id": 331,
                "teams": [
                    "Plaza Amador", "Alianza FC", "Tauro", "San Francisco",
                    "Árabe Unido", "Costa del Este", "Herrera FC", "Universitario",
                    "Veraguas", "UMECIT", "Sporting San Miguelito",
                ],
            },
        },
    },
}


def get_regions() -> list:
    return [
        {"key": key, "label": data["label"]}
        for key, data in CATALOGO.items()
    ]


def get_leagues_by_region(region_key: str) -> list:
    region = CATALOGO.get(region_key)
    if not region:
        return []
    return [
        {
            "code": code,
            "name": league["name"],
            "api_league_id": league["api_league_id"],
            "team_count": len(league["teams"]),
        }
        for code, league in region["leagues"].items()
    ]


def get_teams_by_league(league_code: str) -> list:
    for region in CATALOGO.values():
        league = region["leagues"].get(league_code)
        if league:
            return league["teams"]
    return []


def get_league_info(league_code: str) -> dict:
    for region in CATALOGO.values():
        league = region["leagues"].get(league_code)
        if league:
            return {
                "code": league_code,
                "name": league["name"],
                "api_league_id": league["api_league_id"],
                "region": region["label"],
                "teams": league["teams"],
            }
    return {}


def league_codes() -> list:
    codes = []
    for region in CATALOGO.values():
        codes.extend(region["leagues"].keys())
    return codes