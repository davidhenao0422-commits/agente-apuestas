"""Scheduler para recomendaciones automáticas diarias.

Ejecución:
    python scheduler.py

Funciona junto con el bot de Telegram para enviar recomendaciones
automáticamente a un canal configurado.
"""
import asyncio
import logging
import schedule
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from telegram import Bot
from telegram.ext import Application

from config import Config
from catalog import CATALOGO
from collectors.api_football import APIFootballClient
from storage.database import Database
from predictors.engine import PredictionEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class BettingScheduler:
    def __init__(self):
        self.db = Database()
        self.api = APIFootballClient(self.db)
        self.engine = PredictionEngine()
        self.bot: Optional[Bot] = None
        self.channel_id: Optional[str] = None
        
    def set_channel(self, channel_id: str):
        self.channel_id = channel_id
        
    async def init_bot(self):
        app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        await app.initialize()
        self.bot = app.bot
        
    def get_priority_leagues(self) -> List[Dict]:
        leagues = []
        priority_order = ["PD", "PL", "SA", "BL1", "FL1", "CL"]
        
        for code in priority_order:
            for region_key, region in CATALOGO.items():
                if code in region["leagues"]:
                    league = region["leagues"][code]
                    leagues.append({
                        "code": code,
                        "name": league["name"],
                        "api_league_id": league["api_league_id"],
                        "teams": league["teams"]
                    })
                    break
        return leagues
    
    def get_all_leagues(self) -> List[Dict]:
        leagues = []
        for region_key, region in CATALOGO.items():
            for code, league in region["leagues"].items():
                leagues.append({
                    "code": code,
                    "name": league["name"],
                    "api_league_id": league["api_league_id"],
                    "teams": league["teams"]
                })
        return leagues
    
    def fetch_tomorrow_fixtures(self, leagues: List[Dict]) -> List[Dict]:
        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%Y-%m-%d")
        
        all_fixtures = []
        
        for league in leagues:
            logger.info(f"Obteniendo partidos de {league['name']} para {tomorrow_str}")
            
            data = self.api._request(
                "fixtures",
                {
                    "league": league["api_league_id"],
                    "date": tomorrow_str,
                    "status": "NS"
                },
                use_cache=False
            )
            
            if not data or data.get("results", 0) == 0:
                continue
                
            for fixture in data.get("response", []):
                teams = fixture.get("teams", {})
                fixture_info = fixture.get("fixture", {})
                
                home_team = teams.get("home", {}).get("name", "")
                away_team = teams.get("away", {}).get("name", "")
                
                if not home_team or not away_team:
                    continue
                    
                all_fixtures.append({
                    "date": fixture_info.get("date", ""),
                    "league": league["name"],
                    "league_code": league["code"],
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_logo": teams.get("home", {}).get("logo", ""),
                    "away_logo": teams.get("away", {}).get("logo", ""),
                })
                
            time.sleep(7)
        
        logger.info(f"Total partidos encontrados: {len(all_fixtures)}")
        return all_fixtures
    
    def analyze_fixture(self, fixture: Dict) -> Optional[Dict]:
        home_team = fixture["home_team"]
        away_team = fixture["away_team"]
        league = fixture["league"]
        
        logger.info(f"Analizando: {home_team} vs {away_team} ({league})")
        
        try:
            home_api_id = self.api.resolve_team_id(home_team, league)
            away_api_id = self.api.resolve_team_id(away_team, league)
            
            if not home_api_id or not away_api_id:
                logger.warning(f"No se pudieron resolver IDs para {home_team} o {away_team}")
                return None
            
            home_team_id = self.db.upsert_team(home_team, league, home_api_id)
            away_team_id = self.db.upsert_team(away_team, league, away_api_id)
            
            seasons = [str(datetime.now().year - k - 1) for k in range(5)]
            
            home_data = self._collect_team_data(
                home_api_id, home_team_id, league, seasons
            )
            away_data = self._collect_team_data(
                away_api_id, away_team_id, league, seasons
            )
            
            if not home_data or not away_data:
                return None
            
            h2h = self._collect_h2h(home_team_id, away_team_id, home_api_id, away_api_id,
                                    home_team, away_team)
            
            prediction = self.engine.predict(home_data, away_data, h2h)
            
            return {
                "fixture": fixture,
                "prediction": prediction,
                "home_data": home_data,
                "away_data": away_data
            }
            
        except Exception as e:
            logger.error(f"Error analizando {home_team} vs {away_team}: {e}")
            return None
    
    def _collect_team_data(self, api_id: int, team_id: int, league: str, 
                          seasons: List[str]) -> Optional[Dict]:
        league_api_id = self.api.get_league_by_name(league)
        
        stats_objs = []
        for season in seasons:
            stat_dict = self.api.fetch_and_store_season_stats(
                team_id, league_api_id, season, api_id, league
            )
            if stat_dict:
                from storage.models import TeamStats
                stats_objs.append(TeamStats(
                    team="", league=league, season=stat_dict.get("season", season),
                    position=stat_dict.get("position"),
                    played=stat_dict.get("played", 0),
                    won=stat_dict.get("won", 0),
                    drawn=stat_dict.get("drawn", 0),
                    lost=stat_dict.get("lost", 0),
                    goals_for=stat_dict.get("goals_for", 0),
                    goals_against=stat_dict.get("goals_against", 0),
                    shots_on_target=stat_dict.get("shots_on_target", 0),
                    corners=stat_dict.get("corners", 0),
                    possession_avg=stat_dict.get("possession_avg", 0.0),
                    home_won=stat_dict.get("home_won", 0),
                    home_drawn=stat_dict.get("home_drawn", 0),
                    home_lost=stat_dict.get("home_lost", 0),
                    home_goals_for=stat_dict.get("home_goals_for", 0),
                    home_goals_against=stat_dict.get("home_goals_against", 0),
                    away_won=stat_dict.get("away_won", 0),
                    away_drawn=stat_dict.get("away_drawn", 0),
                    away_lost=stat_dict.get("away_lost", 0),
                    away_goals_for=stat_dict.get("away_goals_for", 0),
                    away_goals_against=stat_dict.get("away_goals_against", 0),
                ))
        
        if not stats_objs:
            return None
        
        from analyzers.stats import compute_summary_stats, get_home_away_split
        from analyzers.form import analyze_form
        
        summary = compute_summary_stats(stats_objs)
        splits = get_home_away_split(stats_objs)
        
        recent_matches = self.db.get_recent_matches(team_id)
        form = analyze_form(recent_matches, "")
        
        return {
            **summary,
            "home_performance": {
                "win_rate": splits["home"]["won"] / max(splits["home"]["played"], 1),
                "played": splits["home"]["played"],
                "gf": splits["home"]["gf"],
                "ga": splits["home"]["ga"],
            },
            "away_performance": splits["away"],
            "form": form,
        }
    
    def _collect_h2h(self, team_id_a: int, team_id_b: int, 
                     api_id_a: int, api_id_b: int,
                     name_a: str, name_b: str) -> Optional[Dict]:
        from analyzers.h2h import analyze_h2h
        
        h2h_rows = self.db.get_h2h(team_id_a, team_id_b, limit=10)
        
        if not h2h_rows:
            self.api.fetch_and_store_h2h(
                team_id_a, team_id_b, api_id_a, api_id_b, name_a, name_b
            )
            h2h_rows = self.db.get_h2h(team_id_a, team_id_b, limit=10)
        
        if not h2h_rows:
            return None
        
        matches = [
            {
                "home_team": h["home_team"],
                "away_team": h["away_team"],
                "home_goals": h["home_goals"],
                "away_goals": h["away_goals"],
                "home_corners": h.get("home_corners"),
                "away_corners": h.get("away_corners"),
                "match_date": h["match_date"],
            }
            for h in h2h_rows
        ]
        
        h2h_obj = analyze_h2h(matches, name_a, name_b)
        
        return {
            "total_matches": h2h_obj.total_matches,
            "team_a_wins": h2h_obj.team_a_wins,
            "team_b_wins": h2h_obj.team_b_wins,
            "draws": h2h_obj.draws,
            "avg_goals_per_match": h2h_obj.avg_goals_per_match,
            "avg_corners_per_match": h2h_obj.avg_corners_per_match,
        }
    
    def format_recommendation(self, analysis: Dict) -> str:
        fixture = analysis["fixture"]
        prediction = analysis["prediction"]
        
        home_team = fixture["home_team"]
        away_team = fixture["away_team"]
        league = fixture["league"]
        match_date = fixture["date"]
        
        if match_date:
            try:
                dt = datetime.fromisoformat(match_date.replace("Z", "+00:00"))
                date_str = dt.strftime("%d/%m/%Y %H:%M")
            except:
                date_str = match_date
        else:
            date_str = "Por confirmar"
        
        message = f"⚽ **{home_team} vs {away_team}**\n"
        message += f"🏆 {league}\n"
        message += f"📅 {date_str}\n\n"
        
        message += "📊 **Análisis:**\n"
        
        probs = prediction.get("probabilities", {})
        if probs:
            home_win = probs.get("home_win", 0) * 100
            draw = probs.get("draw", 0) * 100
            away_win = probs.get("away_win", 0) * 100
            
            message += f"• Victoria local: {home_win:.1f}%\n"
            message += f"• Empate: {draw:.1f}%\n"
            message += f"• Victoria visitante: {away_win:.1f}%\n\n"
        
        expected_goals = prediction.get("expected_goals", {})
        if expected_goals:
            total_goals = expected_goals.get("total", 0)
            message += f"⚽ Goles esperados: {total_goals:.1f}\n\n"
        
        recommendations = prediction.get("recommendations", [])
        if recommendations:
            message += "💡 **Recomendaciones:**\n"
            for i, rec in enumerate(recommendations[:3], 1):
                market = rec.get("market", "N/A")
                outcome = rec.get("outcome", "N/A")
                prob = rec.get("probability", 0) * 100
                confidence = rec.get("confidence", "N/A")
                
                message += f"{i}. {market} - {outcome} ({prob:.1f}%) [{confidence}]\n"
        
        message += "\n⚠️ _Las apuestas conllevan riesgo. Analiza críticamente._"
        
        return message
    
    async def send_recommendations(self, recommendations: List[str]):
        if not self.bot or not self.channel_id:
            logger.error("Bot o canal no configurado")
            return
        
        logger.info(f"Enviando {len(recommendations)} recomendaciones al canal {self.channel_id}")
        
        header = f"🎯 **RECOMENDACIONES DEL DÍA**\n"
        header += f"📅 {datetime.now().strftime('%d/%m/%Y')}\n"
        header += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        try:
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=header,
                parse_mode="Markdown"
            )
            
            for rec in recommendations:
                try:
                    await self.bot.send_message(
                        chat_id=self.channel_id,
                        text=rec,
                        parse_mode="Markdown"
                    )
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Error enviando recomendación: {e}")
                    
        except Exception as e:
            logger.error(f"Error enviando al canal: {e}")
    
    async def run_daily_job(self, use_priority: bool = True):
        logger.info("=" * 50)
        logger.info("INICIANDO TAREA DIARIA DE RECOMENDACIONES")
        logger.info("=" * 50)
        
        if use_priority:
            leagues = self.get_priority_leagues()
            logger.info(f"Usando {len(leagues)} ligas prioritarias")
        else:
            leagues = self.get_all_leagues()
            logger.info(f"Usando todas las {len(leagues)} ligas")
        
        fixtures = self.fetch_tomorrow_fixtures(leagues)
        
        if not fixtures:
            logger.info("No hay partidos para mañana")
            return
        
        logger.info(f"Analizando {len(fixtures)} partidos...")
        
        recommendations = []
        for fixture in fixtures:
            analysis = self.analyze_fixture(fixture)
            if analysis:
                message = self.format_recommendation(analysis)
                recommendations.append(message)
                time.sleep(7)
        
        if recommendations:
            await self.send_recommendations(recommendations)
        else:
            logger.info("No se generaron recomendaciones")
        
        logger.info("=" * 50)
        logger.info(f"TAREA COMPLETADA. Requests API usados: {self.api.request_count}")
        logger.info("=" * 50)


def run_scheduler():
    scheduler = BettingScheduler()
    
    channel_id = input("Ingresa el ID del canal de Telegram (ej: @mi_canal): ").strip()
    if not channel_id:
        print("Error: Debes proporcionar un ID de canal")
        return
    
    scheduler.set_channel(channel_id)
    
    async def daily_task():
        await scheduler.init_bot()
        await scheduler.run_daily_job(use_priority=True)
    
    print("\nEl scheduler está configurado para ejecutarse todos los días a las 8:00 AM")
    print("También puedes ejecutarlo manualmente ahora mismo.\n")
    
    choice = input("¿Ejecutar ahora? (s/n): ").strip().lower()
    if choice == "s":
        asyncio.run(daily_task())
    
    schedule.every().day.at("08:00").do(lambda: asyncio.run(daily_task()))
    
    print("\nScheduler ejecutándose. Presiona Ctrl+C para detener.")
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    run_scheduler()
