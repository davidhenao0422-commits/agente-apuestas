import logging
import hashlib
from typing import Any, Optional

from config import Config
from storage.database import Database

logger = logging.getLogger(__name__)


class CacheManager:
    """Caché para respuestas de APIs externas usando SQLite con TTL."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    @staticmethod
    def _make_key(prefix: str, *parts) -> str:
        raw = ":".join([prefix] + [str(p) for p in parts])
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, prefix: str, *parts) -> Optional[Any]:
        key = self._make_key(prefix, *parts)
        data = self.db.cache_get(key)
        if data:
            import json
            return json.loads(data)
        return None

    def set(self, value: Any, prefix: str, *parts, ttl_hours: Optional[int] = None) -> None:
        import json
        key = self._make_key(prefix, *parts)
        ttl = ttl_hours or Config.CACHE_TTL_HOURS
        self.db.cache_set(key, value, ttl_hours=ttl)

    def clear(self, prefix: Optional[str] = None) -> None:
        """Limpia el caché, opcionalmente por prefijo."""
        if prefix:
            self.db.execute("DELETE FROM api_cache WHERE cache_key LIKE ?", (f"%{prefix}%",))
        else:
            self.db.execute("DELETE FROM api_cache")
