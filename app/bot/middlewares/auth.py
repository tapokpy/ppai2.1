from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_maker
from app.models.sqlalchemy.user import User

ACCESS_PENDING_MESSAGE = (
    "Доступ ограничен. Ваш аккаунт ещё не подтверждён администратором бота. "
    "Обратитесь к администратору, чтобы получить доступ."
)


class AuthMiddleware(BaseMiddleware):
    """Registers Telegram users on first contact but blocks unapproved ones.

    New users are created in an unapproved state (except admins from
    ADMIN_IDS, who are auto-approved) and must be approved by an admin via
    /add_user before the bot will process their messages.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        is_admin = tg_user.id in settings.admin_ids

        async with async_session_maker() as session:
            result = await session.execute(select(User).where(User.telegram_id == tg_user.id))
            user = result.scalar_one_or_none()

            if user is None:
                user = User(
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    full_name=tg_user.full_name,
                    is_approved=is_admin,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
            elif is_admin and not user.is_approved:
                user.is_approved = True
                await session.commit()
                await session.refresh(user)

        if not user.is_approved:
            await self._deny_access(event)
            return None

        data["db_user"] = user
        return await handler(event, data)

    @staticmethod
    async def _deny_access(event: TelegramObject) -> None:
        answer = getattr(event, "answer", None)
        if callable(answer):
            await answer(ACCESS_PENDING_MESSAGE)
