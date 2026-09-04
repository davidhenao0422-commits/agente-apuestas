"""Punto de entrada del bot de Telegram.

Ejecución:
    python main.py

Requisitos:
    - Configurar TELEGRAM_BOT_TOKEN en .env
    - Configurar al menos una API de datos (API-Football o football-data.org)
"""
import logging

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from bot.handlers import BetBotHandlers
from bot.keyboards import REPLY_KEYBOARD
from config import Config

logger = logging.getLogger(__name__)


def main() -> None:
    errors = Config.validate()
    if errors:
        raise SystemExit(
            "Configuración incompleta:\n"
            + "\n".join(f"  - {e}" for e in errors)
            + "\n\nRevisa tu archivo .env (usa .env.example como referencia)."
        )

    from predictors.engine import PredictionEngine
    from storage.database import Database

    db = Database()
    engine = PredictionEngine()
    handlers = BetBotHandlers(db, engine)

    app = ApplicationBuilder().token(Config.TELEGRAM_BOT_TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help))
    app.add_handler(CommandHandler("ayuda", handlers.help))
    app.add_handler(CommandHandler("historial", handlers.history))
    app.add_handler(CommandHandler("history", handlers.history))
    app.add_handler(CommandHandler("analizar", handlers.analyze))
    app.add_handler(CommandHandler("analyze", handlers.analyze))

    # Mensajes de texto con listas de equipos
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,
                                   handlers.handle_message))

    logger.info("Agente de apuestas iniciado. Presiona Ctrl+C para detener.")
    app.run_polling()


if __name__ == "__main__":
    main()