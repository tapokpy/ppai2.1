import asyncio
from functools import partial

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from app.bot.handlers import admin, chat, documents, engineer, group_chat, start, todo
from app.bot.handlers.group_chat import send_reminder_message
from app.bot.middlewares.auth import AuthMiddleware
from app.bot.middlewares.group_activity import GroupActivityMiddleware
from app.core.config import settings
from app.core.dependencies import build_cascade_router, build_github_planning_client, build_transcriber
from app.core.scheduler import ReminderScheduler
from app.services.project_docs_ingest import sync_project_docs


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
    dp.include_router(chat.router)
    return dp


async def main() -> None:
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    cascade_router = build_cascade_router()
    transcriber = build_transcriber()
    github_planning_client = build_github_planning_client()

    sync_project_docs(cascade_router.rag_engine)

    scheduler = ReminderScheduler(send_reminder_callback=partial(send_reminder_message, bot))
    scheduler.start()

    logger.info("Starting bot polling")
    await dp.start_polling(
        bot,
        cascade_router=cascade_router,
        local_llm=cascade_router.local_llm,
        scheduler=scheduler,
        transcriber=transcriber,
        github_planning_client=github_planning_client,
    )


if __name__ == "__main__":
    asyncio.run(main())
