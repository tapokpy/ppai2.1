import asyncio
from functools import partial

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from app.bot.handlers import admin, chat, engineer, group_chat, start
from app.bot.handlers.group_chat import send_reminder_message
from app.bot.middlewares.auth import AuthMiddleware
from app.bot.middlewares.group_activity import GroupActivityMiddleware
from app.core.config import settings
from app.core.dependencies import build_cascade_router
from app.core.scheduler import ReminderScheduler


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.message.middleware(AuthMiddleware())
    dp.message.middleware(GroupActivityMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(group_chat.router)
    dp.include_router(engineer.router)
    dp.include_router(chat.router)
    return dp


async def main() -> None:
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    cascade_router = build_cascade_router()

    scheduler = ReminderScheduler(send_reminder_callback=partial(send_reminder_message, bot))
    scheduler.start()

    logger.info("Starting bot polling")
    await dp.start_polling(
        bot,
        cascade_router=cascade_router,
        local_llm=cascade_router.local_llm,
        scheduler=scheduler,
    )


if __name__ == "__main__":
    asyncio.run(main())
