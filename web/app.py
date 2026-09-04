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
def recomendaciones(league_code: str, team_name: str):
    """Genera recomendaciones de apuesta para un equipo según sus datos.

    Usa un rival referencia de la misma liga (o uno promedio) para calcular
    el enfrentamiento. En una versión completa, se pediría el rival.
    """
    info = get_league_info(league_code)
    if not info:
        raise HTTPException(404, detail="Liga no encontrada")

    if team_name not in info["teams"]:
        raise HTTPException(404, detail="Equipo no encontrado en la liga")

    svc = _get_stats_service()
    team_stats = svc.get_team_stats(team_name, league_code)

    # Rival referencia: otro equipo de la liga (o uno promedio)
    rival = next(
        (t for t in info["teams"] if t != team_name),
        None,
    )
    rival_stats = svc.get_team_stats(rival, league_code) if rival else None
    if not rival_stats:
        rival_stats = {
            "goals_per_game": 1.3, "conceded_per_game": 1.3,
            "form": {"avg_score": 0.5},
            "home_performance": {"win_rate": 0.5},
        }

    # Construir input para el motor
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

    prediction = engine.predict(home_data, away_data, h2h_data=None)

    # Enriquecer stats para mostrar
    stats = {
        "team": team_name,
        "rival": rival,
        "position": team_stats.get("position"),
        "goals_per_game": team_stats["goals_per_game"],
        "conceded_per_game": team_stats["conceded_per_game"],
        "home_wr": team_stats["home_wr"],
        "form": team_stats["form"],
        "shots": team_stats["shots"],
        "corners": team_stats["corners"],
        "possession": team_stats["possession"],
        "data_source": team_stats.get("_source", "preseleccionado"),
    }

    return {
        "team": team_name,
        "league": info["name"],
        "rival": rival,
        "stats": stats,
        "expected_goals": prediction["expected_goals"],
        "probabilities": prediction["probabilities"],
        "recommendations": prediction["recommendations"],
        "mejor_opcion": _mejor_opcion(prediction["recommendations"]),
    }


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


@app.post("/api/actualizar/{league_code}")
def actualizar(league_code: str):
    """Actualiza datos reales de la liga desde API-Football.

    Recorre los equipos de la liga, obtiene stats reales de la temporada
    actual (cacheado y respetando el límite diario de 100 requests) y los
    guarda en la DB. Si no hay API configurada, responde con un aviso.
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

    updated = 0
    failed = 0
    teams = info["teams"]

    for team_name in teams:
        try:
            ok = _fetch_and_store_team(api, db, team_name, league_code,
                                       league_api_id, season)
            if ok:
                updated += 1
            else:
                failed += 1
        except Exception as e:
            logger.warning(f"Error actualizando {team_name}: {e}")
            failed += 1

    # Resetear cache del servicio (los datos reales cambian)
    _reset_stats_service()

    return {
        "action": "actualizado",
        "message": f"Actualización desde API-Football completada.",
        "teams_updated": updated,
        "teams_failed": failed,
        "requests_used": api.request_count,
        "daily_limit": api.DAILY_LIMIT,
    }


def _fetch_and_store_team(api, db, team_name: str, league_code: str,
                          league_api_id: int, season: str) -> bool:
    """Obtiene stats reales de un equipo y las guarda en la DB."""
    # Resolver/cachear api_id
    team_row = db.query_one(
        "SELECT id, api_id FROM teams WHERE name = ? AND league = ?",
        (team_name, league_code),
    )
    if team_row and team_row["api_id"]:
        api_id = team_row["api_id"]
        team_local_id = team_row["id"]
    elif team_row:
        api_id = api.resolve_team_id(team_name, league_code)
        team_local_id = team_row["id"]
    else:
        api_id = api.resolve_team_id(team_name, league_code)
        team_local_id = db.upsert_team(team_name, league_code, api_id)

    if not api_id:
        logger.warning(f"No se pudo resolver api_id para {team_name}")
        return False

    # Ya hay stats reales de esta temporada?
    existing = db.get_team_stats(team_local_id, season)
    if existing:
        return True  # ya está en cache/DB

    stats = api.fetch_and_store_season_stats(
        team_local_id, league_api_id, season, api_id, league_code
    )
    if not stats:
        logger.warning(f"Sin stats para {team_name} (temporada {season})")
        return False

    return True


def _current_season() -> str:
    from datetime import date
    return str(date.today().year - 1)


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