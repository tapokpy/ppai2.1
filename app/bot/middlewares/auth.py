from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.sqlalchemy.user import User


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        async with async_session_maker() as session:
            result = await session.execute(select(User).where(User.telegram_id == tg_user.id))
            user = result.scalar_one_or_none()

            if user is None:
                user = User(telegram_id=tg_user.id, username=tg_user.username, full_name=tg_user.full_name)
                session.add(user)
                await session.commit()
                await session.refresh(user)

        data["db_user"] = user
        return await handler(event, data)
