"""Prueba rápida de envío al canal de Telegram."""
import asyncio
from telegram import Bot
from config import Config

async def test_send():
    bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
    
    channel_id = "@Apuestas_Futbol"
    
    message = "🤖 **PRUEBA DEL SISTEMA AUTOMÁTICO**\n\n"
    message += "✅ El bot está funcionando correctamente.\n"
    message += "📅 Las recomendaciones se enviarán automáticamente todos los días.\n\n"
    message += "⚽ ¡Listo para recibir análisis de apuestas!"
    
    try:
        await bot.send_message(
            chat_id=channel_id,
            text=message,
            parse_mode="Markdown"
        )
        print(f"✅ Mensaje enviado exitosamente al canal {channel_id}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_send())
