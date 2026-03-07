from typing import Dict, Any, Optional
from telegram_bot.session.store import session_store


class SessionManager:
    def __init__(self):
        self.store = session_store

    async def get_session(self, user_id: int) -> Dict[str, Any]:
        session = await self.store.get(user_id)
        return session or {}

    async def update_session(self, user_id: int, data: Dict[str, Any]) -> None:
        await self.store.update(user_id, data)

    async def clear_session(self, user_id: int) -> None:
        await self.store.delete(user_id)

    async def set_pending_question(
        self, user_id: int, question_id: str, question_data: Dict[str, Any]
    ) -> None:
        await self.update_session(
            user_id, {"pending_question": {"id": question_id, **question_data}}
        )

    async def get_pending_question(self, user_id: int) -> Optional[Dict[str, Any]]:
        session = await self.get_session(user_id)
        return session.get("pending_question")

    async def clear_pending_question(self, user_id: int) -> None:
        session = await self.get_session(user_id)
        if "pending_question" in session:
            del session["pending_question"]
            await self.update_session(user_id, session)


session_manager = SessionManager()
