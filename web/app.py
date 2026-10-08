"""Backend FastAPI para la aplicación web de recomendaciones de apuestas.

Reutiliza la lógica de análisis probada de los módulos existentes
(analyzers/poisson, predictors/engine). Los datos consultan primero los
REALES guardados en la DB (recolectados desde API-Football) y, si no
existen, usan los preseleccionados.
"""
import json
import logging
from collections import defaultdict
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


@app.get("/api/proximos-todos")
def proximos_todos(days_ahead: int = 1):
    """Próximos partidos de TODAS las ligas del catálogo con 1-2 requests a la API.

    Hace un solo request por fecha (sin filtrar por liga) y luego agrupa los
    fixtures según los equipos del catálogo. Mucho más rápido y económico que
    consultar liga por liga.
    """
    from datetime import date, timedelta

    config_errors = _validate_api_config()
    if config_errors:
        return {"leagues": [], "total_fixtures": 0, "source": "none"}

    from collectors.api_football import APIFootballClient
    db = _get_db()
    api = APIFootballClient(db)

    all_teams_by_league = _get_all_teams_by_league()

    all_fixtures = []
    for day_offset in range(max(0, days_ahead) + 1):
        check_date = (date.today() + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        data = api._request("fixtures", {"date": check_date, "status": "NS"})
        if data and data.get("results", 0) > 0:
            all_fixtures.extend(data.get("response", []))

    if not all_fixtures:
        return {
            "leagues": [],
            "total_fixtures": 0,
            "source": "api-football",
            "requests_used": api.request_count,
        }

    fixtures_by_league = {code: [] for code in all_teams_by_league}

    for fix in all_fixtures:
        teams = fix.get("teams", {})
        fixture_info = fix.get("fixture", {})
        home_name = teams.get("home", {}).get("name", "")
        away_name = teams.get("away", {}).get("name", "")
        if not home_name or not away_name:
            continue

        matched = None
        for lcode, linf in all_teams_by_league.items():
            if home_name in linf["teams"] and away_name in linf["teams"]:
                matched = lcode
                break
        if not matched:
            continue

        fixtures_by_league[matched].append({
            "date": fixture_info.get("date", ""),
            "home_team": home_name,
            "away_team": away_name,
            "home_logo": teams.get("home", {}).get("logo", ""),
            "away_logo": teams.get("away", {}).get("logo", ""),
            "status": (fixture_info.get("status") or {}).get("short", ""),
        })

    leagues_result = []
    for lcode, linf in all_teams_by_league.items():
        if fixtures_by_league[lcode]:
            leagues_result.append({
                "league": linf["name"],
                "league_code": lcode,
                "fixtures": fixtures_by_league[lcode],
                "count": len(fixtures_by_league[lcode]),
            })

    return {
        "leagues": leagues_result,
        "total_fixtures": sum(len(f) for f in fixtures_by_league.values()),
        "source": "api-football",
        "requests_used": api.request_count,
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


def _get_all_teams_by_league() -> dict:
    """Construye mapa de todos los equipos del catálogo por liga."""
    from catalog import get_regions, get_leagues_by_region, get_league_info
    result = {}
    regions = get_regions()
    for region in regions:
        ligas = get_leagues_by_region(region["key"])
        for liga in ligas:
            info = get_league_info(liga["code"])
            if info:
                result[liga["code"]] = {
                    "name": info["name"],
                    "teams": set(info["teams"]),
                }
    return result


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
def mejores_apuestas_dia(bankroll: float = 1000, kelly_frac: float = 0.25, min_edge: float = 0.02, max_per_league: int = 3, demo: bool = False, days_ahead: int = 0, fast: bool = True):
    """Mejores value bets del día TODAS las ligas combinadas.
    
    Si demo=true: genera partidos simulados para testing de la UI.
    days_ahead: 0 = solo hoy, 1 = hoy + mañana (default), 2 = hoy + 2 días
    fast=true (default): solo ligas prioritarias, sin odds API, max 30 partidos
    """
    from catalog import get_regions, get_leagues_by_region, get_league_info, CATALOGO
    from datetime import date, timedelta
    from predictors.recommendations import kelly_fraction
    
    # MODO DEMO: datos simulados para testing de la UI
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
            "params": {"bankroll": bankroll, "kelly_frac": kelly_frac, "min_edge": min_edge, "days_ahead": days_ahead, "fast": fast},
            "demo": True,
        }
    
    # MODO REAL: API-Football + Odds API
    from collectors.api_football import APIFootballClient
    from collectors.odds_api import OddsAPIClient
    from catalog import CATALOGO
    db = _get_db()
    api = APIFootballClient(db)
    odds_client = OddsAPIClient(db)
    svc = _get_stats_service()
    
    # Ligas prioritarias (las 6 principales) para ahorrar API quota
    PRIORITY_LEAGUES = {"PD", "PL", "SA", "BL1", "FL1", "CL"}
    
    # Obtener partidos de HOY + MAÑANA (según days_ahead)
    all_fixtures = []
    for day_offset in range(days_ahead + 1):
        check_date = (date.today() + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        data = api._request("fixtures", {"date": check_date, "status": "NS"})
        if data and data.get("results", 0) > 0:
            all_fixtures.extend(data.get("response", []))
    
    if not all_fixtures:
        return {
            "date": date.today().isoformat(),
            "total_analyzed": 0,
            "top_bets": [],
            "params": {"bankroll": bankroll, "kelly_frac": kelly_frac, "min_edge": min_edge, "days_ahead": days_ahead, "fast": fast},
            "message": f"No hay partidos en los próximos {days_ahead + 1} día(s)",
        }
    
    # Filtrar solo ligas de nuestro catálogo (y prioridad si fast)
    all_teams_by_league = _get_all_teams_by_league()
    filtered_fixtures = []
    for fix in all_fixtures:
        teams_info = fix.get("teams", {})
        home_name = teams_info.get("home", {}).get("name", "")
        away_name = teams_info.get("away", {}).get("name", "")
        if not home_name or not away_name:
            continue
        # Buscar liga en catálogo
        matched_lcode = None
        for lcode, linf in all_teams_by_league.items():
            if home_name in linf["teams"] and away_name in linf["teams"]:
                matched_lcode = lcode
                break
        if matched_lcode:
            if fast and matched_lcode not in PRIORITY_LEAGUES:
                continue
            fix["_matched_league_code"] = matched_lcode
            filtered_fixtures.append(fix)
    
    if not filtered_fixtures:
        return {
            "date": date.today().isoformat(),
            "total_analyzed": 0,
            "top_bets": [],
            "params": {"bankroll": bankroll, "kelly_frac": kelly_frac, "min_edge": min_edge, "days_ahead": days_ahead, "fast": fast},
            "message": "No hay partidos de ligas seguidas en los próximos días",
        }
    
    # Modo FAST: limitar partidos, saltar odds API
    if fast:
        all_fixtures = filtered_fixtures[:30]
        odds_by_league = {}
    else:
        # Obtener odds reales de The Odds API por cada liga que tenga partidos
        from config import Config
        odds_api_key = Config.ODDS_API_KEY
        odds_by_league = {}
        if odds_api_key:
            leagues_with_fixtures = set()
            for fix in filtered_fixtures:
                lcode = fix.get("_matched_league_code")
                if lcode:
                    leagues_with_fixtures.add(lcode)
            
            for lcode in leagues_with_fixtures:
                try:
                    odds_matches = odds_client.get_odds(lcode)
                    if odds_matches:
                        odds_by_league[lcode] = {}
                        for om in odds_matches:
                            match_key = f"{om['home_team']}|{om['away_team']}"
                            odds_by_league[lcode][match_key] = om
                except Exception as e:
                    logger.warning(f"Error obteniendo odds para {lcode}: {e}")
        # Usar todos los partidos filtrados (sin límite 30)
        all_fixtures = filtered_fixtures
    
    all_value_bets = []
    
    # Procesar cada partido
    for fix in all_fixtures[:80]:
        teams = fix.get("teams", {})
        fixture_info = fix.get("fixture", {})
        
        home_name = teams.get("home", {}).get("name", "")
        away_name = teams.get("away", {}).get("name", "")
        
        if not home_name or not away_name:
            continue
        
        # Usar liga ya pre-filtrada
        matched_league_code = fix.get("_matched_league_code")
        if not matched_league_code:
            continue
        matched_league_info = all_teams_by_league.get(matched_league_code)
        if not matched_league_info:
            continue
        
        home_stats = svc.get_team_stats(home_name, matched_league_code)
        away_stats = svc.get_team_stats(away_name, matched_league_code)
        if not home_stats or not away_stats:
            continue
        
        # Buscar odds reales para este partido
        match_odds = None
        if matched_league_code in odds_by_league:
            match_key = f"{home_name}|{away_name}"
            match_odds = odds_by_league[matched_league_code].get(match_key)
            if not match_odds:
                # Intentar invertido
                match_key_inv = f"{away_name}|{home_name}"
                match_odds_raw = odds_by_league[matched_league_code].get(match_key_inv)
                if match_odds_raw:
                    # Invertir probabilidades
                    match_odds = match_odds_raw
        
        h2h_data = None
        team_a_row = db.query_one("SELECT id FROM teams WHERE name = ? AND league = ?", (home_name, matched_league_code))
        team_b_row = db.query_one("SELECT id FROM teams WHERE name = ? AND league = ?", (away_name, matched_league_code))
        if team_a_row and team_b_row:
            h2h_matches = db.get_h2h(team_a_row["id"], team_b_row["id"], limit=10)
            if h2h_matches:
                h2h_stats = _calculate_h2h_stats(h2h_matches, home_name, away_name)
                h2h_data = _format_h2h_for_engine(h2h_stats, True)
        
        # Construir datos para el motor con odds reales si disponibles
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
        
        # Si hay odds reales, pasarlas al motor
        if match_odds and match_odds.get("odds_avg"):
            home_data["odds"] = match_odds["odds_avg"]
        
        prediction = engine.predict(home_data, away_data, h2h_data=h2h_data, bankroll=bankroll, kelly_frac=kelly_frac)
        
        for rec in prediction["recommendations"]:
            has_odds = rec.get("odds") is not None
            has_edge = rec.get("edge") is not None and rec["edge"] >= min_edge
            high_prob = rec["probability"] >= 0.70
            
            # Si hay odds reales: value bet si edge > min_edge
            # Si no hay odds: high probability pick
            if (has_odds and has_edge) or (not has_odds and high_prob and rec["recommended"]):
                # Buscar mejor cuota y bookmaker de The Odds API
                best_odds_info = None
                if match_odds and match_odds.get("odds_best"):
                    best_odds_info = match_odds["odds_best"].get(rec["choice"])
                
                entry = {
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
                }
                
                # Agregar info del best bookmaker si tenemos odds reales
                if best_odds_info:
                    entry["best_odds"] = best_odds_info["odds"]
                    entry["best_bookmaker"] = best_odds_info["bookmaker"]
                    entry["odds_source"] = "the_odds_api"
                elif has_odds:
                    entry["odds_source"] = "the_odds_api"
                
                all_value_bets.append(entry)
    
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
        "params": {"bankroll": bankroll, "kelly_frac": kelly_frac, "min_edge": min_edge, "days_ahead": days_ahead, "fast": fast},
    }


# ===================== TRANSPARENCY ENDPOINTS =====================

@app.get("/api/transparency/predictions-locked")
def get_locked_predictions(limit: int = 50):
    """Predicciones bloqueadas (inmutables) para auditoría."""
    db = _get_db()
    locks = db.get_all_prediction_locks(limit)
    
    for lock in locks:
        lock["probabilities"] = json.loads(lock["probabilities"])
        lock["expected_goals"] = json.loads(lock["expected_goals"])
        lock["recommendations"] = json.loads(lock["recommendations"])
        lock["ensemble_weights"] = json.loads(lock["ensemble_weights"])
        lock["brier_scores"] = json.loads(lock["brier_scores"])
        if lock["confidence_breakdown"]:
            lock["confidence_breakdown"] = json.loads(lock["confidence_breakdown"])
        if lock["kelly_stakes"]:
            lock["kelly_stakes"] = json.loads(lock["kelly_stakes"])
    
    return {"predictions": locks, "count": len(locks)}


@app.get("/api/transparency/calibration")
def get_calibration_dashboard(model: str = None, league: str = None, limit: int = 50):
    """Dashboard de calibración por modelo/liga."""
    db = _get_db()
    records = db.get_calibration_history(model, league, limit)
    
    for r in records:
        if r["reliability_data"]:
            r["reliability_data"] = json.loads(r["reliability_data"])
    
    summary = {}
    if records:
        models = set(r["model_name"] for r in records)
        for m in models:
            m_records = [r for r in records if r["model_name"] == m]
            summary[m] = {
                "avg_brier": round(sum(r["brier_score"] for r in m_records) / len(m_records), 4),
                "avg_log_loss": round(sum(r["log_loss"] for r in m_records) / len(m_records), 4),
                "avg_ece": round(sum(r["ece"] for r in m_records) / len(m_records), 4),
                "total_samples": sum(r["sample_size"] for r in m_records),
                "last_updated": max(r["date"] for r in m_records),
            }
    
    return {"records": records, "summary": summary, "count": len(records)}


@app.get("/api/transparency/clv")
def get_clv_dashboard(league: str = None, days: int = 30):
    """Dashboard de Closing Line Value."""
    db = _get_db()
    stats = db.get_clv_stats(league, days)
    records = db.get_clv_history(league, 200)
    
    for r in records:
        r["opening_odds"] = json.loads(r["opening_odds"])
        r["closing_odds"] = json.loads(r["closing_odds"])
        r["model_probs"] = json.loads(r["model_probs"])
    
    by_league = defaultdict(list)
    for r in records:
        by_league[r["league"]].append(r)
    
    league_stats = {}
    for l, recs in by_league.items():
        beat = sum(1 for r in recs if r["beat_closing_line"])
        league_stats[l] = {
            "total": len(recs),
            "beat_rate": round(beat / len(recs) * 100, 1),
            "avg_clv": round(sum(r["clv_home"] + r["clv_draw"] + r["clv_away"] for r in recs) / len(recs) / 3 * 100, 2),
        }
    
    return {"overall": stats, "by_league": league_stats, "recent": records[:50]}


@app.get("/api/transparency/bookmakers")
def get_bookmaker_scores(league: str = None, period_days: int = 30):
    """Scores de calidad/integridad de bookmakers."""
    db = _get_db()
    scores = db.get_bookmaker_scores(league, period_days)
    return {"bookmakers": scores, "count": len(scores)}


@app.get("/api/confidence/{league_code}/{home_team}/{away_team}")
def get_confidence_breakdown(league_code: str, home_team: str, away_team: str):
    """Desglose completo de confidence score para un partido."""
    info = get_league_info(league_code)
    if not info:
        raise HTTPException(404, detail="Liga no encontrada")
    
    svc = _get_stats_service()
    home_stats = svc.get_team_stats(home_team, league_code)
    away_stats = svc.get_team_stats(away_team, league_code)
    
    if not home_stats or not away_stats:
        raise HTTPException(404, detail="Equipo no encontrado")
    
    from predictors.engine import PredictionEngine
    engine = PredictionEngine()
    
    home_data = {
        "team_name": home_team,
        "league": league_code,
        "goals_per_game": home_stats["goals_per_game"],
        "conceded_per_game": home_stats["conceded_per_game"],
        "form": home_stats.get("form", "EEE"),
        "home_performance": {"win_rate": home_stats.get("home_wr", 0.5)},
    }
    away_data = {
        "team_name": away_team,
        "league": league_code,
        "goals_per_game": away_stats["goals_per_game"],
        "conceded_per_game": away_stats["conceded_per_game"],
        "form": away_stats.get("form", "EEE"),
        "home_performance": {"win_rate": away_stats.get("home_wr", 0.5)},
    }
    
    prediction = engine.predict(home_data, away_data, lock_prediction=False)
    
    return {
        "match": f"{home_team} vs {away_team}",
        "league": info["name"],
        "confidence_score": prediction.get("confidence_score", 0),
        "confidence_breakdown": prediction.get("confidence_breakdown", {}),
        "ensemble_weights": prediction.get("ensemble_weights", {}),
        "brier_scores": prediction.get("brier_scores", {}),
        "kelly_stakes": prediction.get("kelly_stakes", {}),
        "probabilities": prediction["probabilities"],
        "expected_goals": prediction["expected_goals"],
        "recommendations": prediction["recommendations"],
    }


@app.get("/api/monte-carlo/{league_code}/{home_team}/{away_team}")
def get_monte_carlo_simulation(league_code: str, home_team: str, away_team: str,
                                num_sims: int = 10000, kelly_mult: float = 0.5):
    """Simulación Monte Carlo de crecimiento de bankroll."""
    info = get_league_info(league_code)
    if not info:
        raise HTTPException(404, detail="Liga no encontrada")
    
    svc = _get_stats_service()
    home_stats = svc.get_team_stats(home_team, league_code)
    away_stats = svc.get_team_stats(away_team, league_code)
    
    if not home_stats or not away_stats:
        raise HTTPException(404, detail="Equipo no encontrado")
    
    from predictors.engine import PredictionEngine
    from predictors.staking import simulate_growth
    
    engine = PredictionEngine()
    home_data = {"goals_per_game": home_stats["goals_per_game"], "team_name": home_team}
    away_data = {"goals_per_game": away_stats["goals_per_game"], "team_name": away_team}
    
    prediction = engine.predict(home_data, away_data, lock_prediction=False)
    
    best_rec = max(prediction["recommendations"], key=lambda r: r.get("probability", 0))
    
    if best_rec.get("odds") and best_rec.get("probability"):
        mc_result = simulate_growth(
            win_prob=best_rec["probability"],
            odds=best_rec["odds"],
            num_bets=500,
            kelly_mult=kelly_mult,
            num_paths=2000,
        )
        
        return {
            "match": f"{home_team} vs {away_team}",
            "league": info["name"],
            "best_pick": {
                "market": best_rec["market"],
                "pick": best_rec["pick_text"],
                "probability": best_rec["probability"],
                "odds": best_rec["odds"],
            },
            "monte_carlo": {
                "median_growth": round(mc_result.median_growth, 3),
                "mean_growth": round(mc_result.mean_growth, 3),
                "pct_profitable": round(mc_result.pct_profitable * 100, 1),
                "max_drawdown_median": round(mc_result.max_drawdown_median * 100, 1),
                "max_drawdown_p95": round(mc_result.max_drawdown_p95 * 100, 1),
                "risk_of_ruin": round(mc_result.risk_of_ruin * 100, 1),
                "final_bankroll_p10": round(mc_result.final_bankroll_p10, 2),
                "final_bankroll_p50": round(mc_result.final_bankroll_p50, 2),
                "final_bankroll_p90": round(mc_result.final_bankroll_p90, 2),
                "sample_paths": mc_result.paths[:20],
            },
            "params": {"num_sims": num_sims, "kelly_mult": kelly_mult},
        }
    
    return {"error": "No valid recommendation with odds found"}


@app.post("/api/refresh-odds")
def refresh_odds(league_code: str = None):
    """Refresca odds desde todas las fuentes configuradas."""
    from collectors.odds_aggregator import create_odds_aggregator
    from config import Config
    
    api_keys = {
        "opticodds": getattr(Config, "OPTICODDS_API_KEY", None),
        "the_odds_api": getattr(Config, "ODDS_API_KEY", None),
    }
    
    aggregator = create_odds_aggregator(api_keys)
    aggregator.refresh_all()
    
    if league_code:
        matches = aggregator.get_all_matches_odds(league_code)
    else:
        matches = aggregator.get_all_matches_odds()
    
    return {
        "refreshed": True,
        "matches_count": len(matches),
        "matches": matches[:20],
    }


@app.get("/api/odds/{league_code}/{home_team}/{away_team}")
def get_match_odds(league_code: str, home_team: str, away_team: str):
    """Mejores odds disponibles para un partido específico."""
    from collectors.odds_aggregator import create_odds_aggregator
    from config import Config
    
    api_keys = {
        "opticodds": getattr(Config, "OPTICODDS_API_KEY", None),
        "the_odds_api": getattr(Config, "ODDS_API_KEY", None),
    }
    
    aggregator = create_odds_aggregator(api_keys)
    best_odds = aggregator.get_best_odds(home_team, away_team, league_code)
    
    if not best_odds:
        raise HTTPException(404, detail="No odds found for this match")
    
    return best_odds


# ===================== STEAM MOVES ENDPOINTS =====================

@app.get("/api/steam-moves")
def get_steam_moves(
    hours_back: int = 2,
    min_severity: str = "medium",
    match_id: str = None,
    limit: int = 50
):
    """Detecta steam moves (movimientos bruscos de líneas en bookmakers sharp).
    
    Args:
        hours_back: Ventana temporal hacia atrás (default 2h)
        min_severity: Severidad mínima (low, medium, high, extreme)
        match_id: Filtrar por partido específico
        limit: Máximo resultados
    """
    from analyzers.steam_moves import create_steam_detector
    db = _get_db()
    detector = create_steam_detector(db)
    
    moves = detector.detect_steam_moves(
        match_id=match_id,
        hours_back=hours_back,
        min_severity=min_severity
    )
    
    return {
        "moves": [
            {
                "match_id": m.match_id,
                "match": f"{m.home_team} vs {m.away_team}",
                "league": m.league,
                "kickoff": m.kickoff,
                "bookmaker": m.bookmaker,
                "market": m.market,
                "direction": m.direction,
                "old_odds": m.old_odds,
                "new_odds": m.new_odds,
                "pct_change": m.pct_change,
                "time_elapsed_min": m.time_elapsed_min,
                "severity": m.severity,
                "timestamp": m.timestamp,
                "implied_prob_change": m.implied_prob_change,
            }
            for m in moves[:limit]
        ],
        "count": len(moves),
        "params": {"hours_back": hours_back, "min_severity": min_severity, "match_id": match_id},
    }


@app.get("/api/steam-moves/summary")
def get_steam_summary(hours_back: int = 24):
    """Resumen agregado de steam moves para dashboard."""
    from analyzers.steam_moves import create_steam_detector
    db = _get_db()
    detector = create_steam_detector(db)
    
    return detector.get_steam_summary(hours_back=hours_back)


@app.get("/api/steam-moves/{match_id}/history")
def get_match_odds_history(match_id: str, market: str = "h2h", hours_back: int = 24):
    """Historial de odds para un partido específico (para gráficos)."""
    db = _get_db()
    snapshots = db.get_odds_snapshots(match_id, market=market, hours_back=hours_back)
    
    # Separar por bookmaker para visualización
    by_bookmaker = {}
    for snap in snapshots:
        bm = snap["bookmaker"]
        if bm not in by_bookmaker:
            by_bookmaker[bm] = []
        by_bookmaker[bm].append({
            "timestamp": snap["snapshot_at"],
            "odds_home": snap["odds_home"],
            "odds_draw": snap["odds_draw"],
            "odds_away": snap["odds_away"],
            "odds_over": snap["odds_over"],
            "odds_under": snap["odds_under"],
            "odds_btts_yes": snap["odds_btts_yes"],
            "odds_btts_no": snap["odds_btts_no"],
            "is_sharp": snap["is_sharp"],
        })
    
    return {
        "match_id": match_id,
        "market": market,
        "by_bookmaker": by_bookmaker,
        "total_snapshots": len(snapshots),
    }


@app.post("/api/steam-moves/poll")
def trigger_odds_poll():
    """Dispara manualmente el polling de odds (para testing)."""
    from analyzers.steam_moves import poll_and_store_odds
    from collectors.odds_api import OddsAPIClient
    db = _get_db()
    odds_client = OddsAPIClient(db)
    
    saved = poll_and_store_odds(db, odds_client)
    return {"polling_completed": True, "snapshots_saved": saved}


# ===================== BOOKMAKER RANKING ENDPOINTS =====================

@app.get("/api/bookmakers/ranking")
def get_bookmakers_ranking(
    league: str = None,
    period_days: int = 30,
    top: int = 20,
    min_markets: int = 50
):
    """Ranking de bookmakers por Sharp Factor (CLV + Accuracy + Consistency + Volume).
    
    Args:
        league: Filtrar por liga (ej: PD, PL, SA, BL1, FL1)
        period_days: Ventana temporal (default 30 días)
        top: Top N bookmakers
        min_markets: Mínimo mercados para calificar
    """
    from analyzers.bookmaker_ranking import create_bookmaker_ranker
    db = _get_db()
    ranker = create_bookmaker_ranker(db)
    
    ranking = ranker.get_ranking(league=league, period_days=period_days, top=top)
    
    # Añadir badges por categorías
    for bm in ranking:
        bm["badges"] = []
        if bm["clv_beat_rate"] > 60:
            bm["badges"].append("🏆 CLV King")
        if bm["accuracy_score"] > 0.8:
            bm["badges"].append("🎯 Precisión")
        if bm["consistency_score"] > 0.8:
            bm["badges"].append("📏 Consistencia")
        if bm["total_markets"] > 500:
            bm["badges"].append("🌊 Volumen")
    
    return {
        "ranking": ranking,
        "count": len(ranking),
        "params": {"league": league, "period_days": period_days, "top": top, "min_markets": min_markets},
        "weights": {"clv": 0.40, "accuracy": 0.25, "consistency": 0.20, "volume": 0.15},
    }


@app.get("/api/bookmakers/{bookmaker}/detail")
def get_bookmaker_detail(bookmaker: str, league: str = None, period_days: int = 30):
    """Detalle completo de métricas de un bookmaker específico."""
    from analyzers.bookmaker_ranking import create_bookmaker_ranker
    db = _get_db()
    ranker = create_bookmaker_ranker(db)
    
    detail = ranker.get_bookmaker_detail(bookmaker, league=league, period_days=period_days)
    
    if not detail:
        raise HTTPException(404, detail=f"Bookmaker '{bookmaker}' no encontrado o datos insuficientes")
    
    return detail


@app.post("/api/bookmakers/refresh-scores")
def refresh_bookmaker_scores(period_days: int = 30, min_markets: int = 50):
    """Recalcula y guarda scores de todos los bookmakers (job manual)."""
    from analyzers.bookmaker_ranking import create_bookmaker_ranker
    db = _get_db()
    ranker = create_bookmaker_ranker(db)
    
    scores = ranker.calculate_all_scores(period_days=period_days, min_markets=min_markets)
    saved = ranker.save_scores(scores)
    
    return {
        "refreshed": True,
        "bookmakers_scored": len(scores),
        "saved_to_db": saved,
        "period_days": period_days,
        "top_5": [
            {"rank": s.rank, "bookmaker": s.bookmaker, "league": s.league, "sharp_factor": s.sharp_factor}
            for s in scores[:5]
        ],
    }


@app.get("/api/bookmakers/leagues")
def get_bookmaker_leagues():
    """Ligas disponibles con datos de bookmakers."""
    db = _get_db()
    leagues = db.query(
        """SELECT DISTINCT league, COUNT(DISTINCT bookmaker) as bookmakers_count,
                  COUNT(*) as total_snapshots
           FROM odds_snapshots 
           WHERE is_sharp = 1
           GROUP BY league
           ORDER BY total_snapshots DESC"""
    )
    return {"leagues": leagues, "count": len(leagues)}


# ===================== PAPER TRADING ENDPOINTS =====================

@app.get("/api/paper/portfolios")
def get_paper_portfolios():
    """Lista todos los portfolios de paper trading."""
    db = _get_db()
    portfolios = db.get_all_portfolios()
    return {"portfolios": portfolios, "count": len(portfolios)}


@app.post("/api/paper/portfolios")
def create_paper_portfolio(name: str = "Default", initial_bankroll: float = 1000,
                            kelly_fraction: float = 0.25, max_bet_pct: float = 0.05,
                            currency: str = "EUR"):
    """Crea un nuevo portfolio de paper trading."""
    from analyzers.paper_trading import create_paper_trading_engine
    engine = create_paper_trading_engine(_get_db())
    
    portfolio_id = engine.create_portfolio(
        name=name, initial_bankroll=initial_bankroll,
        kelly_fraction=kelly_fraction, max_bet_pct=max_bet_pct,
        currency=currency
    )
    
    portfolio = engine.get_portfolio(portfolio_id)
    return {"success": True, "portfolio": portfolio}


@app.get("/api/paper/portfolios/{portfolio_id}")
def get_paper_portfolio(portfolio_id: int):
    """Obtiene detalle de un portfolio."""
    from analyzers.paper_trading import create_paper_trading_engine
    engine = create_paper_trading_engine(_get_db())
    
    portfolio = engine.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(404, detail="Portfolio no encontrado")
    
    return portfolio


@app.put("/api/paper/portfolios/{portfolio_id}/settings")
def update_paper_portfolio_settings(portfolio_id: int, kelly_fraction: float = None,
                                     max_bet_pct: float = None):
    """Actualiza configuración del portfolio."""
    from analyzers.paper_trading import create_paper_trading_engine
    engine = create_paper_trading_engine(_get_db())
    
    engine.update_portfolio_settings(portfolio_id, kelly_fraction, max_bet_pct)
    portfolio = engine.get_portfolio(portfolio_id)
    
    return {"success": True, "portfolio": portfolio}


@app.get("/api/paper/portfolios/{portfolio_id}/performance")
def get_paper_performance(portfolio_id: int, days: int = 30):
    """Métricas de rendimiento del portfolio."""
    from analyzers.paper_trading import create_paper_trading_engine
    engine = create_paper_trading_engine(_get_db())
    
    perf = engine.get_performance(portfolio_id, days)
    summary = engine.get_performance_summary(portfolio_id)
    
    return {
        "period_days": days,
        "performance": {
            "total_picks": perf.total_picks,
            "wins": perf.wins,
            "losses": perf.losses,
            "pushes": perf.pushes,
            "total_staked": perf.total_staked,
            "total_pnl": perf.total_pnl,
            "roi_pct": perf.roi_pct,
            "win_rate": perf.win_rate,
            "avg_odds": perf.avg_odds,
            "sharpe": perf.sharpe,
            "max_drawdown": perf.max_drawdown,
            "current_bankroll": perf.current_bankroll,
            "by_market": perf.by_market,
            "by_league": perf.by_league,
        },
        "summary": summary,
    }


@app.get("/api/paper/portfolios/{portfolio_id}/picks")
def get_paper_picks(portfolio_id: int, status: str = None, limit: int = 100):
    """Historial de picks del portfolio."""
    from analyzers.paper_trading import create_paper_trading_engine
    engine = create_paper_trading_engine(_get_db())
    
    picks = engine.get_picks(portfolio_id, status, limit)
    return {"picks": picks, "count": len(picks)}


@app.get("/api/paper/portfolios/{portfolio_id}/pending")
def get_pending_picks(portfolio_id: int):
    """Picks pendientes de liquidar."""
    from analyzers.paper_trading import create_paper_trading_engine
    engine = create_paper_trading_engine(_get_db())
    
    picks = engine.get_pending_picks(portfolio_id)
    return {"picks": picks, "count": len(picks)}


@app.post("/api/paper/portfolios/{portfolio_id}/picks")
def place_paper_pick(portfolio_id: int, 
                      match_id: str,
                      home_team: str,
                      away_team: str,
                      league: str,
                      kickoff: str,
                      market: str,
                      choice: str,
                      odds: float,
                      probability: float,
                      stake_units: float = None,
                      edge: float = None,
                      source: str = "manual",
                      kelly_fraction: float = None,
                      max_bet_pct: float = None):
    """Coloca un pick manual en paper trading."""
    from analyzers.paper_trading import create_paper_trading_engine
    engine = create_paper_trading_engine(_get_db())
    
    if stake_units:
        # Pick manual con stake fijo
        result = engine.place_manual_pick(
            portfolio_id, match_id, home_team, away_team, league,
            kickoff, market, choice, odds, probability, stake_units, source
        )
    else:
        # Pick con Kelly automático
        result = engine.place_pick_from_recommendation(
            portfolio_id, league, home_team, away_team,
            market, choice, odds, probability, edge,
            kelly_fraction=kelly_fraction, max_bet_pct=max_bet_pct
        )
    
    if not result.get("success"):
        raise HTTPException(400, detail=result.get("error"))
    
    return result


@app.post("/api/paper/portfolios/{portfolio_id}/picks/from-recommendation")
def place_pick_from_recommendation(portfolio_id: int,
                                    league_code: str,
                                    home_team: str,
                                    away_team: str,
                                    market: str,
                                    choice: str,
                                    odds: float,
                                    probability: float,
                                    edge: float = None,
                                    confidence_score: int = None,
                                    kelly_fraction: float = None,
                                    max_bet_pct: float = None):
    """Coloca un pick basado en recomendación del ensemble (usa Kelly)."""
    from analyzers.paper_trading import create_paper_trading_engine
    engine = create_paper_trading_engine(_get_db())
    
    result = engine.place_pick_from_recommendation(
        portfolio_id, league_code, home_team, away_team,
        market, choice, odds, probability, edge,
        confidence_score=confidence_score,
        kelly_fraction=kelly_fraction, max_bet_pct=max_bet_pct
    )
    
    if not result.get("success"):
        raise HTTPException(400, detail=result.get("error"))
    
    return result


@app.post("/api/paper/picks/{pick_id}/cancel")
def cancel_paper_pick(pick_id: int):
    """Cancela un pick pendiente y devuelve el stake."""
    from analyzers.paper_trading import create_paper_trading_engine
    engine = create_paper_trading_engine(_get_db())
    
    result = engine.cancel_pick(pick_id)
    if not result.get("success"):
        raise HTTPException(400, detail=result.get("error"))
    
    return result


@app.post("/api/paper/picks/{pick_id}/settle")
def settle_paper_pick(pick_id: int, actual_score: str):
    """Liquida un pick con el resultado real (ej: '2-1')."""
    from analyzers.paper_trading import create_paper_trading_engine
    engine = create_paper_trading_engine(_get_db())
    
    result = engine.settle_pick(pick_id, actual_score)
    if not result.get("success"):
        raise HTTPException(400, detail=result.get("error"))
    
    return result


@app.post("/api/paper/portfolios/{portfolio_id}/auto-settle")
def auto_settle_pending(portfolio_id: int):
    """Intenta liquidar automáticamente picks de partidos finalizados."""
    from analyzers.paper_trading import create_paper_trading_engine
    engine = create_paper_trading_engine(_get_db())
    
    result = engine.auto_settle_pending(portfolio_id)
    return result


@app.get("/api/paper/portfolios/{portfolio_id}/activity")
def get_recent_activity(portfolio_id: int, limit: int = 20):
    """Actividad reciente del portfolio."""
    from analyzers.paper_trading import create_paper_trading_engine
    engine = create_paper_trading_engine(_get_db())
    
    activity = engine.get_recent_activity(portfolio_id, limit)
    return {"activity": activity, "count": len(activity)}


# ===================== RISK MANAGEMENT ENDPOINTS =====================

@app.get("/api/risk/portfolio/{portfolio_id}/dashboard")
def get_risk_dashboard(portfolio_id: int):
    """Dashboard completo de riesgo del portfolio."""
    from analyzers.risk_management import create_risk_manager
    rm = create_risk_manager(_get_db())
    
    dashboard = rm.get_risk_dashboard(portfolio_id)
    return dashboard


@app.get("/api/risk/portfolio/{portfolio_id}/metrics")
def get_risk_metrics(portfolio_id: int):
    """Métricas de riesgo actuales (exposición, drawdown, VaR, Sharpe)."""
    from analyzers.risk_management import create_risk_manager
    rm = create_risk_manager(_get_db())
    
    metrics = rm.analyze_portfolio_risk(portfolio_id)
    
    return {
        "portfolio_id": portfolio_id,
        "bankroll": metrics.bankroll,
        "total_exposure": metrics.total_exposure,
        "exposure_pct": metrics.exposure_pct,
        "available_capital": metrics.bankroll - metrics.total_exposure,
        "current_drawdown": metrics.current_drawdown,
        "max_drawdown": metrics.max_drawdown,
        "sharpe_ratio": metrics.sharpe_ratio,
        "var_95": metrics.var_95,
        "limits": [
            {
                "type": l.limit_type,
                "limit": l.limit_value,
                "current": l.current_value,
                "utilization": l.utilization_pct,
                "status": l.status,
            }
            for l in metrics.limits
        ],
        "correlations": [
            {
                "match_a": c.match_a,
                "match_b": c.match_b,
                "correlation": c.correlation,
                "shared_team": c.shared_team,
                "shared_league": c.shared_league,
                "shared_market": c.shared_market,
            }
            for c in metrics.correlations
        ],
        "alerts": metrics.alerts,
    }


@app.get("/api/risk/portfolio/{portfolio_id}/limits")
def get_risk_limits(portfolio_id: int):
    """Límites de riesgo configurados y su estado actual."""
    from analyzers.risk_management import create_risk_manager
    rm = create_risk_manager(_get_db())
    
    metrics = rm.analyze_portfolio_risk(portfolio_id)
    
    return {
        "portfolio_id": portfolio_id,
        "limits": [
            {
                "type": l.limit_type,
                "limit_value": l.limit_value,
                "current_value": l.current_value,
                "utilization_pct": l.utilization_pct,
                "status": l.status,
            }
            for l in metrics.limits
        ],
        "summary": {
            "ok": sum(1 for l in metrics.limits if l.status == "ok"),
            "warning": sum(1 for l in metrics.limits if l.status == "warning"),
            "breach": sum(1 for l in metrics.limits if l.status == "breach"),
        },
    }


@app.post("/api/risk/portfolio/{portfolio_id}/limits")
def set_risk_limit(portfolio_id: int, limit_type: str, limit_value: float):
    """Configura un límite de riesgo personalizado."""
    db = _get_db()
    limit_id = db.set_risk_limit(portfolio_id, limit_type, limit_value)
    return {"success": True, "limit_id": limit_id, "limit_type": limit_type, "limit_value": limit_value}


@app.get("/api/risk/portfolio/{portfolio_id}/correlations")
def get_risk_correlations(portfolio_id: int, min_correlation: float = 0.3):
    """Correlaciones entre picks activos del portfolio."""
    from analyzers.risk_management import create_risk_manager
    rm = create_risk_manager(_get_db())
    
    metrics = rm.analyze_portfolio_risk(portfolio_id)
    
    return {
        "portfolio_id": portfolio_id,
        "correlations": [
            {
                "match_a": c.match_a,
                "match_b": c.match_b,
                "correlation": c.correlation,
                "shared_team": c.shared_team,
                "shared_league": c.shared_league,
                "shared_market": c.shared_market,
            }
            for c in metrics.correlations
            if c.correlation >= min_correlation
        ],
        "count": len([c for c in metrics.correlations if c.correlation >= min_correlation]),
    }


@app.get("/api/risk/portfolio/{portfolio_id}/alerts")
def get_risk_alerts(portfolio_id: int, acknowledged: int = None, limit: int = 50):
    """Alertas de riesgo activas/históricas."""
    db = _get_db()
    alerts = db.get_risk_alerts(portfolio_id, acknowledged, limit)
    return {"alerts": alerts, "count": len(alerts)}


@app.post("/api/risk/alerts/{alert_id}/acknowledge")
def acknowledge_risk_alert(alert_id: int):
    """Marca una alerta como reconocida."""
    db = _get_db()
    db.acknowledge_risk_alert(alert_id)
    return {"success": True, "alert_id": alert_id}


@app.post("/api/risk/portfolio/{portfolio_id}/check")
def check_risk_limits(portfolio_id: int):
    """Ejecuta verificación de límites y genera alertas si es necesario."""
    from analyzers.risk_management import create_risk_manager
    rm = create_risk_manager(_get_db())
    
    alerts = rm.check_and_alert(portfolio_id)
    
    return {
        "portfolio_id": portfolio_id,
        "alerts_generated": len(alerts),
        "alerts": alerts,
    }


@app.post("/api/risk/portfolio/{portfolio_id}/optimize-kelly")
def optimize_kelly(portfolio_id: int, probability: float, odds: float, 
                   base_kelly_fraction: float = 0.25):
    """Calcula fracción Kelly optimizada según riesgo actual."""
    from analyzers.risk_management import create_risk_manager
    rm = create_risk_manager(_get_db())
    
    optimized = rm.optimize_kelly_for_risk(
        portfolio_id, probability, odds, base_kelly_fraction
    )
    
    return {
        "portfolio_id": portfolio_id,
        "base_kelly_fraction": base_kelly_fraction,
        "optimized_kelly_fraction": optimized,
        "reduction_factor": round(optimized / base_kelly_fraction, 3) if base_kelly_fraction > 0 else 0,
    }


@app.post("/api/risk/portfolio/{portfolio_id}/init-defaults")
def init_default_risk_limits(portfolio_id: int):
    """Inicializa límites de riesgo por defecto para el portfolio."""
    from analyzers.risk_management import create_risk_manager
    rm = create_risk_manager(_get_db())
    
    count = rm.set_default_limits(portfolio_id)
    
    return {"success": True, "limits_created": count}


# ===================== ML PIPELINE ENDPOINTS =====================

@app.get("/api/ml/models")
def list_model_versions(model_name: str = None, status: str = None):
    """Lista versiones de modelos registradas."""
    from analyzers.ml_pipeline import create_ml_pipeline
    pipeline = create_ml_pipeline(_get_db())
    
    versions = pipeline.registry.get_model_versions(model_name, status)
    return {"models": versions, "count": len(versions)}


@app.get("/api/ml/models/{model_name}/champion")
def get_champion_model(model_name: str):
    """Obtiene el modelo campeón (en producción) para un modelo."""
    from analyzers.ml_pipeline import create_ml_pipeline
    pipeline = create_ml_pipeline(_get_db())
    
    champion = pipeline.registry.db.get_champion_model(model_name)
    if not champion:
        raise HTTPException(404, detail=f"No hay campeón para {model_name}")
    
    return champion


@app.get("/api/ml/models/{model_name}/lineage")
def get_model_lineage(model_name: str, version: str):
    """Obtiene el lineage (historial de versiones) de un modelo."""
    from analyzers.ml_pipeline import create_ml_pipeline
    pipeline = create_ml_pipeline(_get_db())
    
    lineage = pipeline.registry.get_lineage(model_name, version)
    return {"model_name": model_name, "version": version, "lineage": lineage}


@app.get("/api/ml/models/compare")
def compare_model_versions(model_name: str, version_a: str, version_b: str):
    """Compara dos versiones del mismo modelo."""
    from analyzers.ml_pipeline import create_ml_pipeline
    pipeline = create_ml_pipeline(_get_db())
    
    comparison = pipeline.registry.compare_versions(model_name, version_a, version_b)
    return comparison


@app.post("/api/ml/models/{model_name}/promote")
def promote_model(model_name: str, version: str):
    """Promueve una versión a campeón (producción)."""
    from analyzers.ml_pipeline import create_ml_pipeline
    pipeline = create_ml_pipeline(_get_db())
    
    pipeline.registry.promote_to_champion(model_name, version)
    return {"success": True, "model_name": model_name, "version": version, "status": "champion"}


@app.post("/api/ml/models/{model_name}/archive")
def archive_model(model_name: str, version: str):
    """Archiva una versión del modelo."""
    from analyzers.ml_pipeline import create_ml_pipeline
    pipeline = create_ml_pipeline(_get_db())
    
    pipeline.registry.archive_model(model_name, version)
    return {"success": True, "model_name": model_name, "version": version, "status": "archived"}


@app.get("/api/ml/training-runs")
def list_training_runs(model_name: str = None, status: str = None, limit: int = 50):
    """Lista runs de entrenamiento."""
    from analyzers.ml_pipeline import create_ml_pipeline
    pipeline = create_ml_pipeline(_get_db())
    
    runs = pipeline.registry.db.get_training_runs(model_name, status, limit)
    return {"runs": runs, "count": len(runs)}


@app.post("/api/ml/retrain")
def trigger_retrain(model_name: str = "ensemble", run_type: str = "manual"):
    """Dispara reentrenamiento manual de un modelo."""
    from analyzers.ml_pipeline import create_ml_pipeline
    pipeline = create_ml_pipeline(_get_db())
    
    result = pipeline.run_scheduled_retrain(model_name)
    return result


@app.post("/api/ml/retrain-all")
def trigger_retrain_all():
    """Reentrena todos los modelos."""
    from analyzers.ml_pipeline import create_ml_pipeline
    pipeline = create_ml_pipeline(_get_db())
    
    results = pipeline.retrain_all_models()
    return {"results": results}


@app.post("/api/ml/optimize-ensemble")
def optimize_ensemble_weights(n_trials: int = 50, timeout: int = 1800, 
                               leagues: str = None, lookback_days: int = 180):
    """Optimiza pesos del ensemble con Optuna."""
    from analyzers.ml_pipeline import create_ml_pipeline
    pipeline = create_ml_pipeline(_get_db())
    
    league_list = leagues.split(",") if leagues else None
    weights = pipeline.tuner.optimize_ensemble_weights(
        n_trials=n_trials,
        timeout=timeout,
        leagues=league_list,
        lookback_days=lookback_days,
    )
    
    return {"weights": weights, "trials": n_trials, "timeout": timeout}


# A/B Testing Endpoints
@app.post("/api/ml/ab-experiments")
def create_ab_experiment(name: str, model_a: str, model_b: str,
                          traffic_split: float = 0.5, min_sample_size: int = 1000,
                          primary_metric: str = "brier_score"):
    """Crea un experimento A/B (model_a y model_b en formato 'model:version')."""
    from analyzers.ml_pipeline import create_ml_pipeline
    pipeline = create_ml_pipeline(_get_db())
    
    exp_id = pipeline.ab_framework.create_experiment(
        name, model_a, model_b, traffic_split, min_sample_size, primary_metric
    )
    return {"success": True, "experiment_id": exp_id}


@app.get("/api/ml/ab-experiments")
def list_ab_experiments(status: str = None):
    """Lista experimentos A/B."""
    from analyzers.ml_pipeline import create_ml_pipeline
    pipeline = create_ml_pipeline(_get_db())
    
    experiments = pipeline.ab_framework.db.get_ab_experiments(status)
    return {"experiments": experiments, "count": len(experiments)}


@app.get("/api/ml/ab-experiments/{exp_id}")
def get_ab_experiment(exp_id: int):
    """Obtiene detalle de un experimento A/B."""
    from analyzers.ml_pipeline import create_ml_pipeline
    pipeline = create_ml_pipeline(_get_db())
    
    exp = pipeline.ab_framework.db.get_ab_experiment(exp_id)
    if not exp:
        raise HTTPException(404, detail="Experimento no encontrado")
    return exp


@app.post("/api/ml/ab-experiments/{exp_id}/start")
def start_ab_experiment(exp_id: int):
    """Inicia un experimento A/B."""
    from analyzers.ml_pipeline import create_ml_pipeline
    pipeline = create_ml_pipeline(_get_db())
    
    pipeline.ab_framework.start_experiment(exp_id)
    return {"success": True, "experiment_id": exp_id, "status": "running"}


@app.post("/api/ml/ab-experiments/{exp_id}/analyze")
def analyze_ab_experiment(exp_id: int):
    """Analiza resultados de un experimento A/B."""
    from analyzers.ml_pipeline import create_ml_pipeline
    pipeline = create_ml_pipeline(_get_db())
    
    results = pipeline.ab_framework.analyze_experiment(exp_id)
    return results


@app.get("/api/ml/features")
def list_features(feature_group: str = None):
    """Lista features del feature store."""
    from analyzers.ml_pipeline import create_ml_pipeline
    pipeline = create_ml_pipeline(_get_db())
    
    features = pipeline.registry.db.get_features(feature_group)
    return {"features": features, "count": len(features)}


# ===================== ADVANCED ANALYTICS ENDPOINTS =====================

@app.get("/api/analytics/attribution/{portfolio_id}")
def get_performance_attribution(portfolio_id: int, period_days: int = 30):
    """Atribución de rendimiento (Brinson): descompone ROI por modelo, liga, mercado, timing."""
    from analyzers.analytics import create_analytics_engine
    engine = create_analytics_engine(_get_db())
    
    result = engine.run_performance_attribution(portfolio_id, period_days)
    
    return {
        "portfolio_id": portfolio_id,
        "period_days": period_days,
        "total_roi": result.total_roi,
        "total_pnl": result.total_pnl,
        "by_model": result.by_model,
        "by_league": result.by_league,
        "by_market": result.by_market,
        "by_timing": result.by_timing,
        "by_luck": result.by_luck,
        "selection_effect": result.selection_effect,
        "allocation_effect": result.allocation_effect,
        "interaction_effect": result.interaction_effect,
    }


@app.get("/api/analytics/regime")
def get_market_regime(portfolio_id: int = None, lookback_days: int = 60):
    """Detecta régimen actual del mercado (bull, bear, volatile, calm, trending, mean_reverting)."""
    from analyzers.analytics import create_analytics_engine
    engine = create_analytics_engine(_get_db())
    
    regime = engine.detect_market_regime(portfolio_id, lookback_days)
    
    return {
        "regime_type": regime.regime_type,
        "start_date": regime.start_date,
        "end_date": regime.end_date,
        "metrics": regime.metrics,
        "confidence": regime.confidence,
        "description": regime.description,
    }


@app.get("/api/analytics/regime/history")
def get_regime_history(regime_type: str = None, limit: int = 50):
    """Historial de regímenes detectados."""
    db = _get_db()
    regimes = db.get_regime_history(regime_type, limit)
    return {"regimes": regimes, "count": len(regimes)}


@app.get("/api/analytics/regime/current")
def get_current_regime():
    """Régimen actualmente activo."""
    db = _get_db()
    regime = db.get_current_regime()
    if regime:
        regime["metrics"] = json.loads(regime["metrics"])
    return {"regime": regime}


@app.post("/api/analytics/stress-test")
def run_stress_test(portfolio_id: int, scenario: str = "market_crash", runs: int = 2000):
    """Ejecuta stress test Monte Carlo para un escenario."""
    from analyzers.analytics import create_analytics_engine
    engine = create_analytics_engine(_get_db())
    
    result = engine.run_stress_test(portfolio_id, scenario, runs)
    
    return {
        "portfolio_id": portfolio_id,
        "scenario": scenario,
        "runs": runs,
        "max_drawdown": result.max_drawdown,
        "var_95": result.var_95,
        "expected_shortfall": result.expected_shortfall,
        "survival_probability": result.survival_probability,
        "median_final_bankroll": result.median_final_bankroll,
        "worst_case_bankroll": result.worst_case_bankroll,
        "recovery_time_days": result.recovery_time_days,
    }


@app.get("/api/analytics/stress-tests")
def list_stress_tests(portfolio_id: int = None, limit: int = 50):
    """Lista stress tests guardados."""
    db = _get_db()
    tests = db.get_stress_tests(portfolio_id, limit)
    return {"tests": tests, "count": len(tests)}


@app.post("/api/analytics/monte-carlo")
def run_monte_carlo(portfolio_id: int, num_sims: int = 2000, horizon_days: int = 90):
    """Simulación Monte Carlo del portfolio."""
    from analyzers.analytics import create_analytics_engine
    engine = create_analytics_engine(_get_db())
    
    result = engine.run_monte_carlo_portfolio(portfolio_id, num_sims, horizon_days)
    
    return {
        "portfolio_id": portfolio_id,
        "num_sims": num_sims,
        "horizon_days": horizon_days,
        **result,
    }


@app.post("/api/analytics/factor-analysis")
def run_factor_analysis(portfolio_id: int, period_days: int = 90, method: str = "ridge"):
    """Análisis de factores (PCA o Ridge Regression) para drivers de rendimiento."""
    from analyzers.analytics import create_analytics_engine
    engine = create_analytics_engine(_get_db())
    
    result = engine.run_factor_analysis(portfolio_id, period_days, method)
    
    return {
        "portfolio_id": portfolio_id,
        "period_days": period_days,
        "method": method,
        **result,
    }


@app.get("/api/analytics/factor-analysis")
def list_factor_analysis(portfolio_id: int = None, limit: int = 10):
    """Lista análisis de factores guardados."""
    db = _get_db()
    analyses = db.get_factor_analysis(portfolio_id, limit)
    return {"analyses": analyses, "count": len(analyses)}


@app.post("/api/analytics/full-report")
def generate_full_report(portfolio_id: int, period_days: int = 30):
    """Genera reporte completo de analytics (attribution + regime + stress + MC + factors)."""
    from analyzers.analytics import create_analytics_engine
    engine = create_analytics_engine(_get_db())
    
    result = engine.generate_full_report(portfolio_id, period_days)
    
    return result


@app.get("/api/analytics/reports")
def list_analytics_reports(report_type: str = None, portfolio_id: int = None, limit: int = 50):
    """Lista reportes de analytics generados."""
    db = _get_db()
    reports = db.get_analytics_reports(report_type, portfolio_id, limit)
    return {"reports": reports, "count": len(reports)}