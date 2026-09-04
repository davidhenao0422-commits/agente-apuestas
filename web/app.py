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
def recomendaciones(league_code: str, team_name: str, rival: str = None, is_home: bool = True):
    """Genera recomendaciones de apuesta para un equipo contra un rival específico.
    
    Si se proporciona 'rival', usa datos H2H reales entre ambos equipos.
    Si no, usa un rival promedio de la liga.
    
    Args:
        league_code: Código de la liga
        team_name: Nombre del equipo local
        rival: (opcional) Nombre del rival visitante
        is_home: (opcional) Si el equipo juega en casa (default: true)
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
        prediction = engine.predict(home_data, away_data, h2h_data=h2h_data)
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
        prediction = engine.predict(home_data, away_data, h2h_data=h2h_data)

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