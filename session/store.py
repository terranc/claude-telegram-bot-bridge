import asyncio
import json
import logging
from typing import Optional, Dict, Any
from telegram_bot.utils.config import config

logger = logging.getLogger(__name__)


class SessionStore:
    def __init__(self):
        self._local_data: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._storage_path = config.session_store_path
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_local_data()
        logger.info(f"Using local JSON storage at {self._storage_path}")

    def _load_local_data(self):
        if self._storage_path.exists():
            try:
                with open(self._storage_path, "r", encoding="utf-8") as f:
                    self._local_data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load local session data: {e}")
                self._local_data = {}

    def _save_local_data(self):
        try:
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(self._local_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save local session data: {e}")

    def _key(self, user_id: int) -> str:
        return f"telegram_session:{user_id}"

    async def get(self, user_id: int) -> Optional[Dict[str, Any]]:
        key = self._key(user_id)
        async with self._lock:
            return self._local_data.get(key)

    async def set(
        self, user_id: int, data: Dict[str, Any], ttl: Optional[int] = None
    ) -> None:
        del ttl  # kept for API compatibility; local JSON storage has no TTL
        key = self._key(user_id)
        async with self._lock:
            self._local_data[key] = data
            self._save_local_data()

    async def delete(self, user_id: int) -> None:
        key = self._key(user_id)
        async with self._lock:
            if key in self._local_data:
                del self._local_data[key]
                self._save_local_data()

    async def update(self, user_id: int, updates: Dict[str, Any]) -> None:
        key = self._key(user_id)
        async with self._lock:
            data = self._local_data.get(key, {})
            data.update(updates)
            self._local_data[key] = data
            self._save_local_data()


session_store = SessionStore()
