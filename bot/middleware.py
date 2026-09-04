"""Middleware: rate limiting y configuración de logging."""
import logging
import time
from collections import defaultdict
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class RateLimiter:
    """Limita la cantidad de requests por usuario por ventana de tiempo."""

    def __init__(self, max_requests: int = 20, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict = defaultdict(list)

    def is_allowed(self, user_id: int) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds
        self._requests[user_id] = [
            ts for ts in self._requests[user_id] if ts > cutoff
        ]
        if len(self._requests[user_id]) >= self.max_requests:
            return False
        self._requests[user_id].append(now)
        return True

    def remaining(self, user_id: int) -> int:
        now = time.time()
        cutoff = now - self.window_seconds
        active = [ts for ts in self._requests[user_id] if ts > cutoff]
        return max(0, self.max_requests - len(active))


class TelegramMiddleware:
    """Helpers de logging y permisos para handlers."""

    @staticmethod
    def require_private_chat(update: Update) -> bool:
        """Sólo permite uso en chats privados (1 a 1 con el bot)."""
        return (
            update.effective_chat is not None
            and update.effective_chat.type == "private"
        )

    @staticmethod
    def log_command(update: Update) -> None:
        user = update.effective_user
        command = update.message.text[:50] if update.message else "(callback)"
        logger.info(
            f"[{user.id}] {user.username or user.full_name}: {command}"
        )

    @staticmethod
    async def notify_typing(update: Update, context: ContextTypes.DEFAULT_TYPE,
                            delay: float = 0.5) -> None:
        """Envía el indicador de 'escribiendo...' brevemente."""
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action="typing"
        )
        await asyncio.sleep(delay)


import asyncio  # noqa: E402  (import al final para evitar circularidad)
