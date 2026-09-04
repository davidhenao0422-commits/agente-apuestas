"""Manejadores de comandos para el bot de Telegram.

Flujo:
1. El usuario envía `/analizar` con la lista de equipos.
2. El bot parsea los equipos y ligas.
3. Obtiene datos de las APIs, analiza y genera recomendaciones.
4. Formatea y envía el mensaje con tablas y recomendaciones.
"""
import logging
import re
from typing import List, Optional, Tuple

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from config import Config

logger = logging.getLogger(__name__)

# Parseo de equipos
TEAM_PATTERN = re.compile(
    r"^(?P<team>.+?)\s*-\s*(?P<league>.+)$"
)


class BetBotHandlers:
    def __init__(self, db, engine):
        self.db = db
        self.engine = engine

    # ---------- Comandos básicos ----------

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "👋 ¡Bienvenido al Agente de Apuestas Deportivas!\n\n"
            "Soy un bot que analiza estadísticas históricas de equipos de fútbol "
            "para generar recomendaciones de apuestas basadas en datos.\n\n"
            "📝 **Cómo usarme:**\n"
            "Envía una lista de equipos en este formato:\n\n"
            "`Real Madrid - La Liga, Barcelona - La Liga, Atlético Madrid - La Liga`\n\n"
            "O usa los comandos:\n"
            "/analizar - Analizar equipos\n"
            "/historial - Ver predicciones anteriores\n"
            "/ayuda - Más información"
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "🤖 **Ayuda del Agente de Apuestas**\n\n"
            "**Comandos:**\n"
            "/analizar - Analizar equipos\n"
            "/historial - Ver predicciones anteriores\n"
            "/ayuda - Esta ayuda\n\n"
            "**Formato de equipos:**\n"
            "`Equipo - Liga, Equipo - Liga`\n\n"
            "**Ejemplo:**\n"
            "`Real Madrid - La Liga, Barcelona - La Liga`\n\n"
            "**Mercados analizados:**\n"
            "• 1X2 (resultado final)\n"
            "• Over/Under 2.5 goles\n"
            "• Ambos equipos anotan (BTTS)\n\n"
            "⚠️ **Aviso legal:** Las apuestas conllevan riesgo. "
            "Este bot ofrece análisis estadístico, no garantiza resultados."
        )

    async def history(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from bot.formatters import format_history_message
        predictions = self.db.get_recent_predictions(limit=10)
        message = format_history_message(predictions)
        await update.message.reply_text(message, parse_mode="Markdown")

    # ---------- Análisis ----------

    async def analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Manejador para /analizar [equipos]."""
        text = update.message.text
        args = text.replace("/analizar", "").strip()

        if not args:
            await update.message.reply_text(
                "📝 Por favor, envía la lista de equipos.\n\n"
                "**Formato:**\n"
                "`/analizar Real Madrid - La Liga, Barcelona - La Liga`"
            )
            return

        await self._process_teams(update, context, args)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Maneja mensajes normales que contienen listas de equipos."""
        text = update.message.text.strip()

        # Si contiene un patrón de equipos, iniciar análisis
        if "-" in text and ("-" in text):
            await self._process_teams(update, context, text)
        else:
            await update.message.reply_text(
                "❓ No entiendo eso. Envía algo como:\n"
                "`Real Madrid - La Liga, Barcelona - La Liga`\n"
                "o usa /ayuda para más info."
            )

    # ---------- Procesamiento interno ----------

    async def _process_teams(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                             raw_input: str) -> None:
        """Orquesta la recolección, análisis y entrega de recomendaciones."""
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action="typing"
        )

        teams = self._parse_teams(raw_input)
        if not teams:
            await update.message.reply_text(
                "❌ No pude leer los equipos. Formato: `Equipo - Liga` "
                "separados por comas."
            )
            return

        # Mostrar progreso
        team_names = ", ".join(f"**{t[0]}** ({t[1]})" for t in teams)
        progress_msg = await update.message.reply_text(
            f"⏳ Analizando: {team_names}\n"
            "Esto puede tomar un minuto mientras recolecto datos históricos..."
        )

        try:
            results = self._run_full_analysis(teams)
        except Exception as e:
            logger.exception("Error en análisis")
            await progress_msg.edit_text(
                f"❌ Ocurrió un error durante el análisis: {e}"
            )
            return

        if not results:
            await progress_msg.edit_text(
                "⚠️ No se pudieron obtener datos suficientes. "
                "Verifica que los nombres de equipos y ligas sean correctos."
            )
            return

        # Enviar resultados
        await progress_msg.delete()

        for result in results:
            prediction = result["prediction"]
            home_name = result["home"]
            away_name = result["away"]
            stats_match = result.get("stats")

            # Comparación de stats
            if stats_match:
                from bot.formatters import format_comparison_table
                await update.message.reply_text(
                    format_comparison_table(
                        {"home": stats_match["home"], "away": stats_match["away"]},
                        home_name, away_name,
                    ),
                    parse_mode="Markdown",
                )

            # Recomendaciones
            from bot.formatters import format_prediction_message
            await update.message.reply_text(
                format_prediction_message(prediction, home_name, away_name)
            )

            # Guardar en historial
            self.db.save_prediction({
                "match_description": f"{home_name} vs {away_name}",
                "recommendations": prediction["recommendations"],
                "confidence": self._overall_confidence(prediction),
                "probabilities": prediction["probabilities"],
                "expected_goals": prediction["expected_goals"]["total"],
                "reasoning": "Análisis basado en forma, H2H y estadísticas de temporada.",
            })

        await update.message.reply_text(
            "✅ Análisis completado. Recuerda: las apuestas conllevan riesgo. "
            "Analiza críticamente cada recomendación."
        )

    def _parse_teams(self, raw_input: str) -> List[Tuple[str, str]]:
        """Parsea 'Equipo - Liga, Equipo - Liga' a lista de tuplas."""
        teams = []
        for part in raw_input.split(","):
            part = part.strip()
            match = TEAM_PATTERN.match(part)
            if match:
                teams.append((match.group("team").strip(),
                              match.group("league").strip()))
        return teams

    def _run_full_analysis(self, teams: List[Tuple[str, str]]) -> List[dict]:
        """Ejecuta análisis completo sobre todos los partidos del round robin.

        Optimiza el uso de la API gratis: reutiliza api_id guardado,
        cachea stats y evita llamadas innecesarias.

        Retorna lista de dicts:
            {'home', 'away', 'prediction', 'stats'}
        """
        from collectors.api_football import APIFootballClient

        db = self.db
        api = APIFootballClient(db)

        # Resolver todos los equipos de una vez (1 request/equipo si no está en DB)
        resolved = []
        for name, league in teams:
            api_id = api.resolve_team_id(name, league)
            team_id = db.upsert_team(name, league, api_id)
            resolved.append({"name": name, "league": league,
                             "api_id": api_id, "team_id": team_id})

        # Lista de temporadas a consultar (actual + 4 anteriores)
        seasons = self._recent_seasons()

        results = []
        n = len(resolved)

        for i in range(n):
            for j in range(i + 1, n):
                home = resolved[i]
                away = resolved[j]
                league = home["league"] if home["league"] == away["league"] \
                    else home["league"]

                try:
                    league_api_id = self._league_id(api, league)
                    if not league_api_id:
                        logger.warning(
                            f"No se pudo determinar league_id para '{league}'"
                        )

                    home_data = self._collect_team_data(
                        api, db, home, league, league_api_id, seasons
                    )
                    away_data = self._collect_team_data(
                        api, db, away, league, league_api_id, seasons
                    )

                    if not home_data or not away_data:
                        continue

                    h2h = self._collect_h2h(
                        api, db, home, away
                    )

                    prediction = self.engine.predict(home_data, away_data, h2h)

                    results.append({
                        "home": home["name"],
                        "away": away["name"],
                        "prediction": prediction,
                        "stats": {"home": home_data, "away": away_data},
                        "requests_used": api.request_count,
                    })
                except Exception as e:
                    logger.error(
                        f"Error analizando {home['name']} vs {away['name']}: {e}"
                    )

        # Aviso de uso de requests
        if api.request_count:
            logger.info(
                "Análisis completo. Requests usados de API-Football: %d/%d",
                api.request_count, api.DAILY_LIMIT,
            )

        return results

    def _recent_seasons(self) -> List[str]:
        """Devuelve las últimas 5 temporadas (formato '2021', ..., actual)."""
        from datetime import date
        current_year = date.today().year
        # Aún no empezó la nueva temporada europea en septiembre -> usar
        # temporadas completas de años anteriores.
        return [str(current_year - k - 1) for k in range(5)]

    def _league_id(self, api, league: str) -> Optional[int]:
        """Busca (y cachea) el league_id de la liga."""
        return api.get_league_by_name(league)

    def _collect_team_data(self, api, db, team: dict, league: str,
                           league_api_id: Optional[int],
                           seasons: List[str]) -> Optional[dict]:
        """Recopila y agrega datos de un equipo para las temporadas dadas."""
        name = team["name"]
        team_id = team["team_id"]
        api_id = team["api_id"]

        if not api_id:
            logger.warning(f"Sin api_id para {name}; no se pueden obtener stats.")
            return None

        from storage.models import TeamStats

        stats_objs = []

        # Para cada temporada: obtener stats (cacheado o de la DB)
        for season in seasons:
            stat_dict = None
            existing = db.get_team_stats(team_id, season)
            if existing:
                stat_dict = existing
            elif league_api_id:
                stat_dict = api.fetch_and_store_season_stats(
                    team_id, league_api_id, season, api_id, league
                )
            if stat_dict:
                stats_objs.append(TeamStats(
                    team=name, league=league, season=stat_dict.get("season", season),
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
            logger.warning(f"No hay stats para {name} en las temporadas dadas.")
            return None

        from analyzers.stats import compute_summary_stats, get_home_away_split

        summary = compute_summary_stats(stats_objs)
        splits = get_home_away_split(stats_objs)

        # Forma reciente desde partidos de la DB
        from analyzers.form import analyze_form
        recent_matches = db.get_recent_matches(team_id)
        form = analyze_form(recent_matches, name)

        return {
            **summary,
            "home_performance": {
                "win_rate": splits["home"]["won"]
                            / max(splits["home"]["played"], 1),
                "played": splits["home"]["played"],
                "gf": splits["home"]["gf"],
                "ga": splits["home"]["ga"],
            },
            "away_performance": splits["away"],
            "form": form,
        }

    def _collect_h2h(self, api, db, home: dict, away: dict) -> Optional[dict]:
        """Recopila y analiza enfrentamientos directos entre dos equipos."""
        from analyzers.h2h import analyze_h2h

        h2h_rows = db.get_h2h(home["team_id"], away["team_id"], limit=10)

        # Si no hay H2H guardado y tenemos api_ids, intentarlo desde la API una vez
        if not h2h_rows and home["api_id"] and away["api_id"]:
            api.fetch_and_store_h2h(
                home["team_id"], away["team_id"],
                home["api_id"], away["api_id"],
                home["name"], away["name"],
            )
            h2h_rows = db.get_h2h(home["team_id"], away["team_id"], limit=10)

        if not h2h_rows:
            return None

        matches = [
            {
                "home_team": h["home_team"],
                "away_team": h["away_team"],
                "home_goals": h["home_goals"],
                "away_goals": h["away_goals"],
                "home_corners": h["home_corners"],
                "away_corners": h["away_corners"],
                "match_date": h["match_date"],
            }
            for h in h2h_rows
        ]
        h2h_obj = analyze_h2h(matches, home["name"], away["name"])

        return {
            "total_matches": h2h_obj.total_matches,
            "team_a_wins": h2h_obj.team_a_wins,
            "team_b_wins": h2h_obj.team_b_wins,
            "draws": h2h_obj.draws,
            "avg_goals_per_match": h2h_obj.avg_goals_per_match,
            "avg_corners_per_match": h2h_obj.avg_corners_per_match,
        }

    def _overall_confidence(self, prediction: dict) -> str:
        """Calcula confianza general basada en el promedio de recomendaciones."""
        recs = prediction.get("recommendations", [])
        if not recs:
            return "N/A"
        avg_prob = sum(r["probability"] for r in recs) / len(recs)
        if avg_prob >= 0.70:
            return "ALTA"
        if avg_prob >= 0.60:
            return "MEDIA"
        return "BAJA"
