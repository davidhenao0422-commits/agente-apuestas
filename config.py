import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")
    API_FOOTBALL_BASE_URL = os.getenv("API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io")
    FOOTBALL_DATA_KEY = os.getenv("FOOTBALL_DATA_KEY", "")
    FOOTBALL_DATA_BASE_URL = os.getenv("FOOTBALL_DATA_BASE_URL", "https://api.football-data.org/v4")

    BOT_LANGUAGE = os.getenv("BOT_LANGUAGE", "es")
    DEFAULT_MARKETS = os.getenv("DEFAULT_MARKETS", "1X2,BTS,OVER_UNDER").split(",")
    DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Europe/Madrid")

    DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "betting_agent.db"))

    # Cache
    CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", "24"))

    # Modelo de predicción
    FORM_WEIGHT = float(os.getenv("FORM_WEIGHT", "0.40"))
    H2H_WEIGHT = float(os.getenv("H2H_WEIGHT", "0.30"))
    SEASON_WEIGHT = float(os.getenv("SEASON_WEIGHT", "0.20"))
    HOME_AWAY_WEIGHT = float(os.getenv("HOME_AWAY_WEIGHT", "0.10"))

    # Umbral minimo de confianza para recomendar apuesta
    MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.60"))

    # Umbral de valor minimo para value betting
    MIN_VALUE_EDGE = float(os.getenv("MIN_VALUE_EDGE", "0.05"))

    @classmethod
    def validate(cls):
        errors = []
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN no configurado")
        if not cls.API_FOOTBALL_KEY and not cls.FOOTBALL_DATA_KEY:
            errors.append("Al menos una API de datos debe estar configurada")
        return errors
