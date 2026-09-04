"""Backend FastAPI para la aplicación web de recomendaciones de apuestas.

Reutiliza la lógica de análisis probada de los módulos existentes
(analyzers/poisson, predictors/engine). Los datos consultan primero los
REALES guardados en la DB (recolectados desde API-Football) y, si no
existen, usan los preseleccionados.
"""
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from catalog import get_league_info, get_leagues_by_region, get_regions
from predictors.engine import PredictionEngine
from web.preselected_data import all_teams_with_stats, get_team_stats
from web.stats_service import StatsService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agente de Apuestas Deportivas API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = PredictionEngine()

# DB y servicio de stats (lazy para no abrir conexión en import)
_db = None
_stats_service = None


def _get_db():
    global _db
    if _db is None:
        from storage.database import Database
        _db = Database()
    return _db


def _get_stats_service() -> StatsService:
    global _stats_service
    if _stats_service is None:
        _stats_service = StatsService(_get_db())
    return _stats_service


# Sirve el frontend estático
app.mount("/static", StaticFiles(directory="web/static"), name="static")


@app.get("/")
def index():
    return FileResponse("web/static/index.html")


@app.get("/api/regiones")
def regiones():
    return get_regions()


@app.get("/api/ligas/{region}")
def ligas(region: str):
    data = get_leagues_by_region(region)
    if not data:
        raise HTTPException(404, detail="Región no encontrada")
    return data


@app.get("/api/equipos/{league_code}")
def equipos(league_code: str):
    """Equipos de una liga. Usa stats reales si están en DB, si no preseleccionadas."""
    info = get_league_info(league_code)
    if not info:
        raise HTTPException(404, detail="Liga no encontrada")

    svc = _get_stats_service()
    result = []
    for name in info["teams"]:
        stats = svc.get_team_stats(
            name, league_code, info.get("api_league_id")
        )
        result.append({
            "name": name,
            "position": stats.get("position"),
            "goals_per_game": stats.get("goals_per_game"),
            "conceded_per_game": stats.get("conceded_per_game"),
            "home_wr": stats.get("home_wr"),
            "form": stats.get("form"),
            "shots": stats.get("shots"),
            "corners": stats.get("corners"),
            "possession": stats.get("possession"),
            "_data_source": stats.get("_source", "preseleccionado"),
        })
    return result


@app.get("/api/recomendaciones/{league_code}/{team_name}")
def recomendaciones(league_code: str, team_name: str, rival: str = None, is_home: bool = True, 
                    bankroll: float = None, kelly_frac: float = 0.25):
    """Genera recomendaciones de apuesta para un equipo contra un rival específico.
    
    Si se proporciona 'rival', usa datos H2H reales entre ambos equipos.
    Si no, usa un rival promedio de la liga.
    
    Args:
        league_code: Código de la liga
        team_name: Nombre del equipo local
        rival: (opcional) Nombre del rival visitante
        is_home: (opcional) Si el equipo juega en casa (default: true)
        bankroll: (opcional) Bankroll total para calcular stake Kelly
        kelly_frac: (opcional) Fracción de Kelly (default 0.25 = 1/4 Kelly)
    """
    info = get_league_info(league_code)
    if not info:
        raise HTTPException(404, detail="Liga no encontrada")

    if team_name not in info["teams"]:
        raise HTTPException(404, detail="Equipo no encontrado en la liga")

    svc = _get_stats_service()
    team_stats = svc.get_team_stats(team_name, league_code)
    team_is_home = is_home

    # Determinar rival
    rival_name = rival
    h2h_data = None
    h2h_stats = None
    
    if rival_name and rival_name in info["teams"] and rival_name != team_name:
        # Rival específico: buscar H2H
        db = _get_db()
        team_a_row = db.query_one("SELECT id FROM teams WHERE name = ? AND league = ?", (team_name, league_code))
        team_b_row = db.query_one("SELECT id FROM teams WHERE name = ? AND league = ?", (rival_name, league_code))
        if team_a_row and team_b_row:
            h2h_matches = db.get_h2h(team_a_row["id"], team_b_row["id"], limit=20)
            if h2h_matches:
                h2h_stats = _calculate_h2h_stats(h2h_matches, team_name, rival_name)
                h2h_data = _format_h2h_for_engine(h2h_stats, team_is_home)
    else:
        # Rival referencia: otro equipo de la liga
        rival_name = next(
            (t for t in info["teams"] if t != team_name),
            None,
        )

    rival_stats = svc.get_team_stats(rival_name, league_code) if rival_name else None
    if not rival_stats:
        rival_stats = {
            "goals_per_game": 1.3, "conceded_per_game": 1.3,
            "form": {"avg_score": 0.5},
            "home_performance": {"win_rate": 0.5},
        }

    # Construir input para el motor según localía
    if team_is_home:
        home_data = {
            "goals_per_game": team_stats["goals_per_game"],
            "conceded_per_game": team_stats["conceded_per_game"],
            "form": {"avg_score": _form_score(team_stats["form"])},
            "home_performance": {"win_rate": team_stats["home_wr"]},
        }
        away_data = {
            "goals_per_game": rival_stats["goals_per_game"],
            "conceded_per_game": rival_stats["conceded_per_game"],
            "form": {"avg_score": _form_score(rival_stats.get("form", "EEE"))},
            "home_performance": {"win_rate": rival_stats.get("home_wr", 0.5)},
        }
        prediction = engine.predict(home_data, away_data, h2h_data=h2h_data, bankroll=bankroll, kelly_frac=kelly_frac)
    else:
        # El equipo es visitante
        home_data = {
            "goals_per_game": rival_stats["goals_per_game"],
            "conceded_per_game": rival_stats["conceded_per_game"],
            "form": {"avg_score": _form_score(rival_stats.get("form", "EEE"))},
            "home_performance": {"win_rate": rival_stats.get("home_wr", 0.5)},
        }
        away_data = {
            "goals_per_game": team_stats["goals_per_game"],
            "conceded_per_game": team_stats["conceded_per_game"],
            "form": {"avg_score": _form_score(team_stats["form"])},
            "home_performance": {"win_rate": team_stats["home_wr"]},
        }
        prediction = engine.predict(home_data, away_data, h2h_data=h2h_data, bankroll=bankroll, kelly_frac=kelly_frac)

    # Enriquecer stats para mostrar
    stats = {
        "team": team_name,
        "rival": rival_name,
        "position": team_stats.get("position"),
        "goals_per_game": team_stats["goals_per_game"],
        "conceded_per_game": team_stats["conceded_per_game"],
        "home_wr": team_stats["home_wr"],
        "form": team_stats["form"],
        "shots": team_stats["shots"],
        "corners": team_stats["corners"],
        "possession": team_stats["possession"],
        "data_source": team_stats.get("_source", "preseleccionado"),
        "is_home": team_is_home,
    }

    response = {
        "team": team_name,
        "league": info["name"],
        "rival": rival_name,
        "stats": stats,
        "expected_goals": prediction["expected_goals"],
        "probabilities": prediction["probabilities"],
        "recommendations": prediction["recommendations"],
        "mejor_opcion": _mejor_opcion(prediction["recommendations"]),
        "h2h_available": prediction.get("h2h_available", False),
        "kelly_fraction": prediction.get("kelly_fraction", kelly_frac),
        "bankroll": prediction.get("bankroll"),
    }
    
    if h2h_stats:
        response["h2h_stats"] = h2h_stats

    return response


def _mejor_opcion(recs: list) -> Optional[dict]:
    """Devuelve la recomendación con mayor probabilidad (la más destacada)."""
    if not recs:
        return None
    return max(recs, key=lambda r: r.get("probability", 0))


@app.get("/api/equipo/{league_code}/{team_name}")
def equipo_stats(league_code: str, team_name: str):
    info = get_league_info(league_code)
    if not info:
        raise HTTPException(404, detail="Liga no encontrada")
    if team_name not in info["teams"]:
        raise HTTPException(404, detail="Equipo no encontrado")

    svc = _get_stats_service()
    stats = svc.get_team_stats(team_name, league_code)
    return {
        "team": team_name,
        "league": info["name"],
        "position": stats.get("position"),
        "goals_per_game": stats.get("goals_per_game"),
        "conceded_per_game": stats.get("conceded_per_game"),
        "home_wr": stats.get("home_wr"),
        "form": stats.get("form"),
        "shots": stats.get("shots"),
        "corners": stats.get("corners"),
        "possession": stats.get("possession"),
        "data_source": stats.get("_source", "preseleccionado"),
    }


@app.get("/api/proximos/{league_code}")
def proximos_partidos(league_code: str):
    """Obtiene los próximos partidos de una liga.

    Primero intenta API-Football para esa liga específica.
    Si no hay partidos, muestra todos los partidos disponibles hoy.
    """
    info = get_league_info(league_code)
    if not info:
        raise HTTPException(404, detail="Liga no encontrada")

    league_api_id = info["api_league_id"]

    # Intentar API-Football para esa liga específica
    config_errors = _validate_api_config()
    if not config_errors:
        try:
            from collectors.api_football import APIFootballClient
            db = _get_db()
            api = APIFootballClient(db)
            fixtures = api.get_upcoming_fixtures(league_api_id, limit=10)
            if fixtures:
                return {
                    "league": info["name"],
                    "league_code": league_code,
                    "fixtures": fixtures,
                    "count": len(fixtures),
                    "source": "api-football",
                }
        except Exception:
            pass

    # Fallback: mostrar todos los partidos disponibles hoy
    try:
        from collectors.api_football import APIFootballClient
        db = _get_db()
        api = APIFootballClient(db)

        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        data = api._request("fixtures", {"date": today, "status": "NS"})

        if data and data.get("results", 0) > 0:
            fixtures = []
            for fix in data.get("response", [])[:15]:
                teams = fix.get("teams", {})
                fixture_info = fix.get("fixture", {})
                league_info_api = fix.get("league", {})
                fixtures.append({
                    "date": fixture_info.get("date", ""),
                    "home_team": teams.get("home", {}).get("name", ""),
                    "away_team": teams.get("away", {}).get("name", ""),
                    "home_logo": teams.get("home", {}).get("logo", ""),
                    "away_logo": teams.get("away", {}).get("logo", ""),
                    "league_name": league_info_api.get("name", ""),
                })
            return {
                "league": info["name"],
                "league_code": league_code,
                "fixtures": fixtures,
                "count": len(fixtures),
                "source": "api-football-all",
                "note": "No hay partidos próximos en esta liga. Mostrando partidos de hoy de otras ligas.",
            }
    except Exception:
        pass

    return {
        "league": info["name"],
        "league_code": league_code,
        "fixtures": [],
        "count": 0,
        "source": "none",
    }


@app.post("/api/actualizar/{league_code}")
def actualizar(league_code: str):
    """Actualiza datos reales de la liga desde API-Football usando standings.

    Hace 1 request por liga al endpoint /standings que devuelve TODOS los
    equipos con sus stats básicas (posición, partidos, goles, ganados/empatados/perdidos).
    Guarda cada equipo en la DB con su api_id para poder obtener stats detalladas después.
    """
    info = get_league_info(league_code)
    if not info:
        raise HTTPException(404, detail="Liga no encontrada")

    config_errors = _validate_api_config()
    if config_errors:
        raise HTTPException(503, detail={
            "action": "sin_api_config",
            "message": "No hay API-Football configurada. La app muestra los "
                       "datos preseleccionados. Añade API_FOOTBALL_KEY para "
                       "traer datos reales.",
            "errors": config_errors,
        })

    from collectors.api_football import APIFootballClient

    db = _get_db()
    api = APIFootballClient(db)
    league_api_id = info["api_league_id"]
    season = _current_season()

    # Un solo request para toda la tabla de posiciones
    standings = api.fetch_and_store_standings(league_api_id, season)

    if not standings:
        raise HTTPException(502, detail={
            "action": "sin_datos",
            "message": "No se pudieron obtener datos de la liga. "
                       "Verifica que la temporada y liga sean correctas.",
            "requests_used": api.request_count,
        })

    updated = 0
    failed = 0

    catalog_teams = {t: False for t in info["teams"]}

    for team_name, stats in standings.items():
        # Buscar equipo por nombre exacto o aproximado
        matched = _match_team_name(team_name, catalog_teams)
        if not matched:
            continue

        catalog_teams[matched] = True  # marcado como actualizado

        try:
            # Guardar o actualizar equipo con su api_id
            team_row = db.query_one(
                "SELECT id FROM teams WHERE name = ? AND league = ?",
                (matched, league_code),
            )
            if team_row:
                team_local_id = team_row["id"]
                db.execute(
                    "UPDATE teams SET api_id = ? WHERE id = ?",
                    (stats["team_api_id"], team_local_id),
                )
            else:
                team_local_id = db.upsert_team(
                    matched, league_code, stats["team_api_id"]
                )

            # Guardar stats de temporada
            db.upsert_team_stats(team_local_id, {
                "season": season,
                "league": league_code,
                "position": stats.get("position"),
                "played": stats.get("played", 0),
                "won": stats.get("won", 0),
                "drawn": stats.get("drawn", 0),
                "lost": stats.get("lost", 0),
                "goals_for": stats.get("goals_for", 0),
                "goals_against": stats.get("goals_against", 0),
                "shots_on_target": 0,
                "corners": 0,
                "possession_avg": 0.0,
                "home_won": 0,
                "home_drawn": 0,
                "home_lost": 0,
                "home_goals_for": 0,
                "home_goals_against": 0,
                "away_won": 0,
                "away_drawn": 0,
                "away_lost": 0,
                "away_goals_for": 0,
                "away_goals_against": 0,
            })
            updated += 1
        except Exception as e:
            logger.warning(f"Error guardando stats de {matched}: {e}")
            failed += 1

    # Equipos del catálogo que no se encontraron en el standings
    not_found = [t for t, ok in catalog_teams.items() if not ok]

    _reset_stats_service()

    return {
        "action": "actualizado",
        "message": f"Tabla de posiciones actualizada. "
                   f"Equipos actualizados: {updated} · Fallidos: {failed} · "
                   f"No encontrados en standings: {len(not_found)}",
        "teams_updated": updated,
        "teams_failed": failed,
        "teams_not_found": not_found,
        "requests_used": api.request_count,
        "daily_limit": api.DAILY_LIMIT,
        "has_more": False,
    }


def _match_team_name(api_name: str, catalog: dict) -> Optional[str]:
    """Busca un nombre de equipo del catálogo que coincida con el nombre de la API.

    Usa coincidencia normalizada y aliases para nombres conocidos diferentes.
    """
    import unicodedata

    # Aliases: nombre del catálogo → variantes de la API
    ALIASES = {
        "Athletic Bilbao": ["Athletic Club", "Athletic Bilbao"],
        "Valencia CF": ["Valencia", "Valencia CF"],
    }

    def normalize(s):
        nfkd = unicodedata.normalize("NFKD", s.lower().strip())
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    api_norm = normalize(api_name)

    # Buscar por aliases
    for catalog_name, variants in ALIASES.items():
        if catalog_name not in catalog:
            continue
        for variant in variants:
            if normalize(variant) == api_norm:
                return catalog_name

    # Coincidencia directa por nombre normalizado
    for catalog_name in catalog:
        cat_norm = normalize(catalog_name)
        if api_norm == cat_norm:
            return catalog_name
        if cat_norm in api_norm or api_norm in cat_norm:
            return catalog_name
    return None


def _current_season() -> str:
    """Devuelve la temporada accesible para el plan gratuito (2022-2024)."""
    from datetime import date
    year = date.today().year
    # El plan gratuito solo tiene acceso a temporadas 2022-2024
    return str(min(year - 1, 2024))


def _reset_stats_service() -> None:
    global _stats_service
    _stats_service = None


def _validate_api_config() -> list:
    from config import Config
    errors = []
    if not Config.API_FOOTBALL_KEY:
        errors.append("Falta API_FOOTBALL_KEY en .env")
    return errors


def _form_score(form: str) -> float:
    """Convierte 'VVEVD' a un score promedio (V=1, E=0.5, D=0)."""
    if not form:
        return 0.5
    score_map = {"V": 1.0, "E": 0.5, "D": 0.0}
    scores = [score_map.get(c.upper(), 0.5) for c in form]
    return sum(scores) / len(scores)


@app.get("/api/h2h/{league_code}/{team_a}/{team_b}")
def h2h_entre_equipos(league_code: str, team_a: str, team_b: str):
    """Obtiene el historial de enfrentamientos directos entre dos equipos.
    
    Primero busca en la DB, si no hay datos consulta API-Football y los almacena.
    """
    info = get_league_info(league_code)
    if not info:
        raise HTTPException(404, detail="Liga no encontrada")
    
    if team_a not in info["teams"] or team_b not in info["teams"]:
        raise HTTPException(404, detail="Uno o ambos equipos no están en la liga")
    
    if team_a == team_b:
        raise HTTPException(400, detail="No se puede hacer H2H del mismo equipo")
    
    db = _get_db()
    
    # Obtener IDs locales de los equipos
    team_a_row = db.query_one("SELECT id, api_id FROM teams WHERE name = ? AND league = ?", (team_a, league_code))
    team_b_row = db.query_one("SELECT id, api_id FROM teams WHERE name = ? AND league = ?", (team_b, league_code))
    
    if not team_a_row or not team_b_row:
        raise HTTPException(404, detail="Equipos no encontrados en la base de datos")
    
    team_a_id = team_a_row["id"]
    team_b_id = team_b_row["id"]
    team_a_api_id = team_a_row["api_id"]
    team_b_api_id = team_b_row["api_id"]
    
    # Buscar H2H en la DB
    h2h_matches = db.get_h2h(team_a_id, team_b_id, limit=20)
    
    if h2h_matches:
        # Calcular estadísticas H2H
        stats = _calculate_h2h_stats(h2h_matches, team_a, team_b)
        return {
            "league": info["name"],
            "league_code": league_code,
            "team_a": team_a,
            "team_b": team_b,
            "matches": h2h_matches[:10],
            "stats": stats,
            "total_matches": len(h2h_matches),
            "source": "database",
        }
    
    # Si no hay en DB, intentar API-Football
    config_errors = _validate_api_config()
    if not config_errors and team_a_api_id and team_b_api_id:
        try:
            from collectors.api_football import APIFootballClient
            api = APIFootballClient(db)
            api.fetch_and_store_h2h(
                team_a_id, team_b_id, team_a_api_id, team_b_api_id,
                team_a, team_b, limit=20
            )
            
            # Volver a buscar en DB después de almacenar
            h2h_matches = db.get_h2h(team_a_id, team_b_id, limit=20)
            if h2h_matches:
                stats = _calculate_h2h_stats(h2h_matches, team_a, team_b)
                return {
                    "league": info["name"],
                    "league_code": league_code,
                    "team_a": team_a,
                    "team_b": team_b,
                    "matches": h2h_matches[:10],
                    "stats": stats,
                    "total_matches": len(h2h_matches),
                    "source": "api-football",
                }
        except Exception as e:
            logger.warning(f"Error obteniendo H2H de API-Football: {e}")
    
    return {
        "league": info["name"],
        "league_code": league_code,
        "team_a": team_a,
        "team_b": team_b,
        "matches": [],
        "stats": _empty_h2h_stats(team_a, team_b),
        "total_matches": 0,
        "source": "none",
    }


def _calculate_h2h_stats(matches: list, team_a: str, team_b: str) -> dict:
    """Calcula estadísticas del historial H2H."""
    team_a_wins = 0
    team_b_wins = 0
    draws = 0
    team_a_goals = 0
    team_b_goals = 0
    team_a_home_wins = 0
    team_b_home_wins = 0
    
    for m in matches:
        home = m["home_team"]
        away = m["away_team"]
        hg = m["home_goals"]
        ag = m["away_goals"]
        
        if home == team_a:
            team_a_goals += hg
            team_b_goals += ag
            if hg > ag:
                team_a_wins += 1
                team_a_home_wins += 1
            elif hg < ag:
                team_b_wins += 1
            else:
                draws += 1
        elif home == team_b:
            team_b_goals += hg
            team_a_goals += ag
            if hg > ag:
                team_b_wins += 1
                team_b_home_wins += 1
            elif hg < ag:
                team_a_wins += 1
            else:
                draws += 1
    
    total = len(matches)
    return {
        "team_a": team_a,
        "team_b": team_b,
        "total_matches": total,
        "team_a_wins": team_a_wins,
        "team_b_wins": team_b_wins,
        "draws": draws,
        "team_a_goals": team_a_goals,
        "team_b_goals": team_b_goals,
        "team_a_avg_goals": round(team_a_goals / max(total, 1), 2),
        "team_b_avg_goals": round(team_b_goals / max(total, 1), 2),
        "team_a_win_pct": round(team_a_wins / max(total, 1) * 100, 1),
        "team_b_win_pct": round(team_b_wins / max(total, 1) * 100, 1),
        "draw_pct": round(draws / max(total, 1) * 100, 1),
        "team_a_home_wins": team_a_home_wins,
        "team_b_home_wins": team_b_home_wins,
    }


def _empty_h2h_stats(team_a: str, team_b: str) -> dict:
    return {
        "team_a": team_a,
        "team_b": team_b,
        "total_matches": 0,
        "team_a_wins": 0,
        "team_b_wins": 0,
        "draws": 0,
        "team_a_goals": 0,
        "team_b_goals": 0,
        "team_a_avg_goals": 0,
        "team_b_avg_goals": 0,
        "team_a_win_pct": 0,
        "team_b_win_pct": 0,
        "draw_pct": 0,
        "team_a_home_wins": 0,
        "team_b_home_wins": 0,
    }


def _format_h2h_for_engine(h2h_stats: dict, team_is_home: bool) -> dict:
    """Formatea stats H2H para el motor de predicción."""
    if not h2h_stats or h2h_stats.get("total_matches", 0) == 0:
        return None
    
    if team_is_home:
        return {
            "team_a_wins": h2h_stats["team_a_wins"],
            "team_b_wins": h2h_stats["team_b_wins"],
            "draws": h2h_stats["draws"],
            "total_matches": h2h_stats["total_matches"],
        }
    else:
        # Si el equipo es visitante, invertir
        return {
            "team_a_wins": h2h_stats["team_b_wins"],
            "team_b_wins": h2h_stats["team_a_wins"],
            "draws": h2h_stats["draws"],
            "total_matches": h2h_stats["total_matches"],
        }


# ===================== VALUE BETS ENDPOINTS =====================

@app.get("/api/value-bets/{league_code}")
def value_bets_liga(league_code: str, bankroll: float = 1000, kelly_frac: float = 0.25, min_edge: float = 0.02):
    """Detecta value bets para partidos de una liga (usa fallback a todos los partidos del día)."""
    info = get_league_info(league_code)
    if not info:
        raise HTTPException(404, detail="Liga no encontrada")

    config_errors = _validate_api_config()
    if config_errors:
        raise HTTPException(503, detail="API-Football no configurada")

    from collectors.api_football import APIFootballClient
    db = _get_db()
    api = APIFootballClient(db)
    svc = _get_stats_service()

    # Obtener TODOS los partidos de hoy (fallback como en /api/proximos)
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    data = api._request("fixtures", {"date": today, "status": "NS"})
    
    if not data or data.get("results", 0) == 0:
        return {
            "league": info["name"],
            "league_code": league_code,
            "value_bets": [],
            "count": 0,
            "message": "No hay partidos hoy",
        }

    # Filtrar partidos donde AMBOS equipos están en nuestro catálogo de esta liga
    league_teams = set(info["teams"])
    fixtures = []
    for fix in data.get("response", []):
        teams = fix.get("teams", {})
        fixture_info = fix.get("fixture", {})
        home_name = teams.get("home", {}).get("name", "")
        away_name = teams.get("away", {}).get("name", "")
        if home_name in league_teams and away_name in league_teams:
            fixtures.append({
                "date": fixture_info.get("date", ""),
                "home_team": home_name,
                "away_team": away_name,
            })

    if not fixtures:
        return {
            "league": info["name"],
            "league_code": league_code,
            "value_bets": [],
            "count": 0,
            "message": "No hay partidos de esta liga hoy",
        }

    value_bets = []
    
    for fix in fixtures[:15]:
        home_name = fix["home_team"]
        away_name = fix["away_team"]
        
        home_stats = svc.get_team_stats(home_name, league_code)
        away_stats = svc.get_team_stats(away_name, league_code)
        if not home_stats or not away_stats:
            continue
        
        # H2H si disponible
        h2h_data = None
        team_a_row = db.query_one("SELECT id, api_id FROM teams WHERE name = ? AND league = ?", (home_name, league_code))
        team_b_row = db.query_one("SELECT id, api_id FROM teams WHERE name = ? AND league = ?", (away_name, league_code))
        if team_a_row and team_b_row and team_a_row["api_id"] and team_b_row["api_id"]:
            h2h_matches = db.get_h2h(team_a_row["id"], team_b_row["id"], limit=10)
            if h2h_matches:
                h2h_stats = _calculate_h2h_stats(h2h_matches, home_name, away_name)
                h2h_data = _format_h2h_for_engine(h2h_stats, True)
        
        home_data = {
            "goals_per_game": home_stats["goals_per_game"],
            "conceded_per_game": home_stats["conceded_per_game"],
            "form": {"avg_score": _form_score(home_stats["form"])},
            "home_performance": {"win_rate": home_stats["home_wr"]},
        }
        away_data = {
            "goals_per_game": away_stats["goals_per_game"],
            "conceded_per_game": away_stats["conceded_per_game"],
            "form": {"avg_score": _form_score(away_stats.get("form", "EEE"))},
            "home_performance": {"win_rate": away_stats.get("home_wr", 0.5)},
        }
        
        prediction = engine.predict(home_data, away_data, h2h_data=h2h_data, bankroll=bankroll, kelly_frac=kelly_frac)
        
        for rec in prediction["recommendations"]:
            has_odds = rec.get("odds") is not None
            has_edge = rec.get("edge") is not None and rec["edge"] >= min_edge
            high_prob = rec["probability"] >= 0.70
            
            if (has_odds and has_edge) or (not has_odds and high_prob and rec["recommended"]):
                value_bets.append({
                    "match": f"{home_name} vs {away_name}",
                    "date": fix["date"],
                    "market": rec["market"],
                    "pick": rec["pick_text"],
                    "probability": rec["probability"],
                    "odds": rec["odds"],
                    "edge_pct": round(rec["edge"] * 100, 1) if rec.get("edge") else None,
                    "confidence": rec["confidence"],
                    "kelly_stake_pct": rec.get("kelly_stake_pct"),
                    "kelly_stake_units": rec.get("kelly_stake_units"),
                    "expected_goals": prediction["expected_goals"],
                    "type": "value_bet" if has_odds else "high_prob",
                })

    # Ordenar: value bets primero (por edge), luego high_prob (por prob)
    value_bets.sort(key=lambda x: (
        0 if x["type"] == "value_bet" else 1,
        -(x["edge_pct"] or 0),
        -x["probability"]
    ))
    
    return {
        "league": info["name"],
        "league_code": league_code,
        "value_bets": value_bets[:20],
        "count": len(value_bets),
        "params": {"bankroll": bankroll, "kelly_frac": kelly_frac, "min_edge": min_edge},
    }


@app.get("/api/mejores-apuestas")
def mejores_apuestas_dia(bankroll: float = 1000, kelly_frac: float = 0.25, min_edge: float = 0.02, max_per_league: int = 3, demo: bool = False):
    """Mejores value bets del día TODAS las ligas combinadas.
    
    Si demo=true: genera partidos simulados para testing de la UI.
    """
    from catalog import get_regions, get_leagues_by_region, get_league_info
    from datetime import date, timedelta
    from predictors.recommendations import kelly_fraction
    
    # MODO DEMO: datos simulados para testing UI
    if demo:
        demo_matches = [
            {"league": "La Liga (España)", "league_code": "PD", "match": "Real Madrid vs Barcelona", "home": "Real Madrid", "away": "Barcelona"},
            {"league": "Premier League (Inglaterra)", "league_code": "PL", "match": "Arsenal vs Man City", "home": "Arsenal", "away": "Man City"},
            {"league": "Serie A (Italia)", "league_code": "SA", "match": "Inter vs Juventus", "home": "Inter", "away": "Juventus"},
            {"league": "Bundesliga (Alemania)", "league_code": "BL1", "match": "Bayern vs Dortmund", "home": "Bayern", "away": "Dortmund"},
            {"league": "Ligue 1 (Francia)", "league_code": "FL1", "match": "PSG vs Marseille", "home": "PSG", "away": "Marseille"},
            {"league": "Liga MX (México)", "league_code": "MEX", "match": "America vs Chivas", "home": "America", "away": "Chivas"},
            {"league": "Brasileirão (Brasil)", "league_code": "BRA", "match": "Flamengo vs Palmeiras", "home": "Flamengo", "away": "Palmeiras"},
            {"league": "Liga Profesional (Argentina)", "league_code": "ARG", "match": "River Plate vs Boca Juniors", "home": "River Plate", "away": "Boca Juniors"},
        ]
        
        # Stats demo realistas por equipo
        demo_stats = {
            "Real Madrid": {"gpg": 2.3, "cpg": 0.8, "form": "VVVEV", "hw": 0.85},
            "Barcelona": {"gpg": 2.1, "cpg": 0.9, "form": "VVVED", "hw": 0.78},
            "Arsenal": {"gpg": 2.2, "cpg": 0.7, "form": "VVVVV", "hw": 0.82},
            "Man City": {"gpg": 2.5, "cpg": 0.6, "form": "VVVVE", "hw": 0.88},
            "Inter": {"gpg": 2.0, "cpg": 0.6, "form": "VVVVD", "hw": 0.80},
            "Juventus": {"gpg": 1.8, "cpg": 0.8, "form": "VVEDD", "hw": 0.72},
            "Bayern": {"gpg": 2.8, "cpg": 0.9, "form": "VVVVV", "hw": 0.90},
            "Dortmund": {"gpg": 2.1, "cpg": 1.2, "form": "VVEED", "hw": 0.70},
            "PSG": {"gpg": 2.6, "cpg": 0.7, "form": "VVVVV", "hw": 0.85},
            "Marseille": {"gpg": 1.7, "cpg": 1.0, "form": "VVEDD", "hw": 0.68},
            "America": {"gpg": 1.9, "cpg": 0.9, "form": "VVVED", "hw": 0.75},
            "Chivas": {"gpg": 1.5, "cpg": 1.1, "form": "VEDDD", "hw": 0.62},
            "Flamengo": {"gpg": 2.0, "cpg": 0.9, "form": "VVVEE", "hw": 0.78},
            "Palmeiras": {"gpg": 1.8, "cpg": 0.8, "form": "VVVED", "hw": 0.76},
            "River Plate": {"gpg": 1.7, "cpg": 0.7, "form": "VVVVE", "hw": 0.80},
            "Boca Juniors": {"gpg": 1.4, "cpg": 0.8, "form": "VVEDD", "hw": 0.70},
        }
        
        all_value_bets = []
        svc = _get_stats_service()
        
        for i, m in enumerate(demo_matches):
            home_name = m["home"]
            away_name = m["away"]
            
            h_stats = demo_stats.get(home_name, {"gpg": 1.5, "cpg": 1.3, "form": "EEE", "hw": 0.5})
            a_stats = demo_stats.get(away_name, {"gpg": 1.5, "cpg": 1.3, "form": "EEE", "hw": 0.5})
            
            # Simular odds de mercado (con margen ~5%)
            import random
            random.seed(hash(home_name + away_name))  # Determinístico
            
            home_data = {
                "goals_per_game": h_stats["gpg"],
                "conceded_per_game": h_stats["cpg"],
                "form": {"avg_score": _form_score(h_stats["form"])},
                "home_performance": {"win_rate": h_stats["hw"]},
            }
            away_data = {
                "goals_per_game": a_stats["gpg"],
                "conceded_per_game": a_stats["cpg"],
                "form": {"avg_score": _form_score(a_stats["form"])},
                "home_performance": {"win_rate": a_stats["hw"]},
            }
            
            prediction = engine.predict(home_data, away_data, h2h_data=None, bankroll=bankroll, kelly_frac=kelly_frac)
            
            # Simular odds: 70% casos "sharp" (edge +), 30% "bookmaker" (edge -)
            probs = prediction["probabilities"]
            for rec in prediction["recommendations"]:
                prob = rec["probability"]
                if prob < 0.55:
                    continue
                
                fair_odds = 1.0 / prob
                # Simular: a veces hay value (odds > fair), a veces no
                import random
                r = random.random()
                if r < 0.7:  # 70% value bets simulados
                    market_odds = round(fair_odds * (1 + random.uniform(0.02, 0.08)), 2)  # +2-8% value
                else:
                    market_odds = round(fair_odds * 0.95, 2)  # bookmaker margin -5%
                
                edge = prob - (1.0 / market_odds)
                
                if edge >= min_edge or prob >= 0.70:
                    kelly_pct = kelly_fraction(prob, market_odds, kelly_frac)
                    kelly_units = bankroll * kelly_pct
                    
                    all_value_bets.append({
                        "league": m["league"],
                        "league_code": m["league_code"],
                        "match": m["match"],
                        "date": (date.today() + timedelta(days=random.randint(0, 2))).isoformat() + "T20:00:00",
                        "market": rec["market"],
                        "pick": rec["pick_text"],
                        "probability": round(prob, 3),
                        "odds": market_odds,
                        "edge_pct": round(edge * 100, 1),
                        "confidence": rec["confidence"],
                        "kelly_stake_pct": round(kelly_pct * 100, 2),
                        "kelly_stake_units": round(kelly_units, 2),
                        "expected_goals": prediction["expected_goals"],
                        "type": "value_bet" if edge >= min_edge else "high_prob",
                    })
        
        # Ordenar: value bets primero (por edge), luego high_prob (por prob)
        all_value_bets.sort(key=lambda x: (
            0 if x.get("type") == "value_bet" else 1,
            -(x["edge_pct"] or 0),
            -x["probability"]
        ))
        
        # Limitar por liga
        final_bets = []
        league_count = {}
        for bet in all_value_bets:
            lc = bet["league_code"]
            if league_count.get(lc, 0) < max_per_league:
                final_bets.append(bet)
                league_count[lc] = league_count.get(lc, 0) + 1
            if len(final_bets) >= 15:
                break
        
        return {
            "date": date.today().isoformat(),
            "total_analyzed": len(all_value_bets),
            "top_bets": final_bets,
            "params": {"bankroll": bankroll, "kelly_frac": kelly_frac, "min_edge": min_edge},
            "demo": True,
        }
    
    # MODO REAL: API-Football
    config_errors = _validate_api_config()
    if config_errors:
        raise HTTPException(503, detail="API-Football no configurada")
    
    from collectors.api_football import APIFootballClient
    db = _get_db()
    api = APIFootballClient(db)
    svc = _get_stats_service()
    
    # Obtener TODOS los partidos de hoy (1 solo request)
    today = date.today().strftime("%Y-%m-%d")
    data = api._request("fixtures", {"date": today, "status": "NS"})
    
    if not data or data.get("results", 0) == 0:
        return {
            "date": date.today().isoformat(),
            "total_analyzed": 0,
            "top_bets": [],
            "params": {"bankroll": bankroll, "kelly_frac": kelly_frac, "min_edge": min_edge},
            "message": "No hay partidos hoy",
        }
    
    # Construir mapa de todos los equipos de nuestro catálogo por liga
    all_teams_by_league = {}
    regions = get_regions()
    for region in regions:
        ligas = get_leagues_by_region(region["key"])
        for liga in ligas:
            info = get_league_info(liga["code"])
            if info:
                all_teams_by_league[liga["code"]] = {
                    "name": info["name"],
                    "teams": set(info["teams"]),
                }
    
    all_value_bets = []
    
    # Procesar cada partido del día
    for fix in data.get("response", [])[:50]:
        teams = fix.get("teams", {})
        fixture_info = fix.get("fixture", {})
        league_info_api = fix.get("league", {})
        
        home_name = teams.get("home", {}).get("name", "")
        away_name = teams.get("away", {}).get("name", "")
        
        if not home_name or not away_name:
            continue
        
        matched_league_code = None
        matched_league_info = None
        for lcode, linf in all_teams_by_league.items():
            if home_name in linf["teams"] and away_name in linf["teams"]:
                matched_league_code = lcode
                matched_league_info = linf
                break
        
        if not matched_league_code:
            continue
        
        home_stats = svc.get_team_stats(home_name, matched_league_code)
        away_stats = svc.get_team_stats(away_name, matched_league_code)
        if not home_stats or not away_stats:
            continue
        
        h2h_data = None
        team_a_row = db.query_one("SELECT id FROM teams WHERE name = ? AND league = ?", (home_name, matched_league_code))
        team_b_row = db.query_one("SELECT id FROM teams WHERE name = ? AND league = ?", (away_name, matched_league_code))
        if team_a_row and team_b_row:
            h2h_matches = db.get_h2h(team_a_row["id"], team_b_row["id"], limit=10)
            if h2h_matches:
                h2h_stats = _calculate_h2h_stats(h2h_matches, home_name, away_name)
                h2h_data = _format_h2h_for_engine(h2h_stats, True)
        
        home_data = {
            "goals_per_game": home_stats["goals_per_game"],
            "conceded_per_game": home_stats["conceded_per_game"],
            "form": {"avg_score": _form_score(home_stats["form"])},
            "home_performance": {"win_rate": home_stats["home_wr"]},
        }
        away_data = {
            "goals_per_game": away_stats["goals_per_game"],
            "conceded_per_game": away_stats["conceded_per_game"],
            "form": {"avg_score": _form_score(away_stats.get("form", "EEE"))},
            "home_performance": {"win_rate": away_stats.get("home_wr", 0.5)},
        }
        
        prediction = engine.predict(home_data, away_data, h2h_data=h2h_data, bankroll=bankroll, kelly_frac=kelly_frac)
        
        for rec in prediction["recommendations"]:
            has_odds = rec.get("odds") is not None
            has_edge = rec.get("edge") is not None and rec["edge"] >= min_edge
            high_prob = rec["probability"] >= 0.70
            
            if (has_odds and has_edge) or (not has_odds and high_prob and rec["recommended"]):
                all_value_bets.append({
                    "league": matched_league_info["name"],
                    "league_code": matched_league_code,
                    "match": f"{home_name} vs {away_name}",
                    "date": fixture_info.get("date", ""),
                    "market": rec["market"],
                    "pick": rec["pick_text"],
                    "probability": rec["probability"],
                    "odds": rec["odds"],
                    "edge_pct": round(rec["edge"] * 100, 1) if rec.get("edge") else None,
                    "confidence": rec["confidence"],
                    "kelly_stake_pct": rec.get("kelly_stake_pct"),
                    "kelly_stake_units": rec.get("kelly_stake_units"),
                    "expected_goals": prediction["expected_goals"],
                    "type": "value_bet" if has_odds else "high_prob",
                })
    
    all_value_bets.sort(key=lambda x: (
        0 if x.get("type") == "value_bet" else 1,
        -(x["edge_pct"] or 0),
        -x["probability"]
    ))
    
    final_bets = []
    league_count = {}
    for bet in all_value_bets:
        lc = bet["league_code"]
        if league_count.get(lc, 0) < max_per_league:
            final_bets.append(bet)
            league_count[lc] = league_count.get(lc, 0) + 1
        if len(final_bets) >= 15:
            break
    
    return {
        "date": date.today().isoformat(),
        "total_analyzed": len(all_value_bets),
        "top_bets": final_bets,
        "params": {"bankroll": bankroll, "kelly_frac": kelly_frac, "min_edge": min_edge},
    }