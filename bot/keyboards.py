"""Teclados y botones interactivos para el bot de Telegram."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🔍 Analizar", "📋 Historial"],
        ["⚙️ Configuración", "❓ Ayuda"],
    ],
    resize_keyboard=True,
    input_field_placeholder="Elige una opción o escribe 'Real Madrid - La Liga, Barcelona - La Liga'",
)


def markets_keyboard() -> InlineKeyboardMarkup:
    """Teclado inline para seleccionar mercados de apuesta."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("1X2", callback_data="market:1x2"),
                InlineKeyboardButton("Over/Under", callback_data="market:over_under"),
                InlineKeyboardButton("BTTS", callback_data="market:btts"),
            ],
            [InlineKeyboardButton("Todos los mercados", callback_data="market:all")],
        ]
    )


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Sí, analizar", callback_data="confirm_yes"),
                InlineKeyboardButton("❌ Cancelar", callback_data="confirm_no"),
            ]
        ]
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔍 Nuevo análisis", callback_data="menu:analyze")],
            [InlineKeyboardButton("📋 Historial", callback_data="menu:history")],
            [InlineKeyboardButton("❓ Ayuda", callback_data="menu:help")],
        ]
    )
