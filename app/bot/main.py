import asyncio
from functools import partial

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from app.bot.handlers import admin, chat, documents, engineer, group_chat, media, showroom, start, todo
from app.bot.handlers.group_chat import send_reminder_message
from app.bot.middlewares.auth import AuthMiddleware
from app.bot.middlewares.group_activity import GroupActivityMiddleware
from app.core.config import settings
from app.core.dependencies import (
    build_cascade_router,
    build_media_downloader,
    build_resolume_controller,
    build_screens_map,
    build_transcriber,
)
from app.core.scheduler import ReminderScheduler
from app.services.project_docs_ingest import sync_project_docs


RESTART_NOTIFICATION = "🔄 Бот перезапущен и снова принимает сообщения."


async def notify_admins_of_restart(bot: Bot) -> None:
    """Best-effort admin-only ping on startup. Also the practical signal for
    "the whole PPAI stack came back up" — the bot container is the only
    piece of this system capable of sending a Telegram message, and it
    restarts whenever the stack does, so a single message here covers both
    "bot restarted" and "everything restarted" from the operator's side.
    A failure to notify one admin (e.g. they blocked the bot) must not stop
    the others or block startup.
    """
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, RESTART_NOTIFICATION)
        except Exception as exc:
            logger.warning(f"Failed to notify admin {admin_id} of restart: {exc}")


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.message.middleware(AuthMiddleware())
    dp.message.middleware(GroupActivityMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(group_chat.router)
    dp.include_router(engineer.router)
    dp.include_router(documents.router)
    dp.include_router(todo.router)
    dp.include_router(media.router)
    dp.include_router(showroom.router)
    dp.include_router(chat.router)
    return dp


async def main() -> None:
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    cascade_router = build_cascade_router()
    transcriber = build_transcriber()
    media_downloader = build_media_downloader()
    resolume_controller = build_resolume_controller()
    screens_map = build_screens_map()

    await sync_project_docs(cascade_router.rag_engine)

    scheduler = ReminderScheduler(send_reminder_callback=partial(send_reminder_message, bot))
    scheduler.start()

    await notify_admins_of_restart(bot)

    logger.info("Starting bot polling")
    await dp.start_polling(
        bot,
        cascade_router=cascade_router,
        local_llm=cascade_router.local_llm,
        scheduler=scheduler,
        transcriber=transcriber,
        media_downloader=media_downloader,
        resolume_controller=resolume_controller,
        screens_map=screens_map,
    )


if __name__ == "__main__":
    asyncio.run(main())
