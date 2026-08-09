from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.core.database import async_session_maker
from app.models.sqlalchemy.activity_log import ActivityLog

GROUP_CHAT_TYPES = {"group", "supergroup"}


class GroupActivityMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat = getattr(event, "chat", None)
        text = getattr(event, "text", None)

        if chat is not None and chat.type in GROUP_CHAT_TYPES and text:
            db_user = data.get("db_user")
            if db_user is not None:
                async with async_session_maker() as session:
                    session.add(
                        ActivityLog(
                            user_id=db_user.id,
                            chat_id=event.chat.id,
                            message_type="group_message",
                            summary=event.text[:200],
                        )
                    )
                    await session.commit()

        return await handler(event, data)
