import asyncio
from functools import partial

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger
from redis.asyncio import Redis

from app.bot.handlers import admin, chat, engineer, group_chat, start
from app.bot.handlers.group_chat import send_reminder_message
from app.bot.middlewares.auth import AuthMiddleware
from app.bot.middlewares.group_activity import GroupActivityMiddleware
from app.core.config import settings
from app.core.router import CascadeRouter
from app.core.scheduler import ReminderScheduler
from app.services.cloud_llm import CloudLLMClient
from app.services.embeddings import default_embedding_function
from app.services.local_llm import LocalLLMClient
from app.services.rag_engine import RAGEngine


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


def build_cascade_router() -> CascadeRouter:
    rag_engine = RAGEngine(
        persist_dir=settings.CHROMA_PERSIST_DIR,
        score_threshold=settings.RAG_SCORE_THRESHOLD,
        embedding_function=default_embedding_function(settings.EMBEDDING_MODEL_NAME),
    )
    local_llm = LocalLLMClient(base_url=settings.OLLAMA_URL, model=settings.OLLAMA_MODEL)
    cloud_llm = CloudLLMClient(api_key=settings.ANTHROPIC_API_KEY, model=settings.CLOUD_MODEL_NAME)
    redis_client = Redis.from_url(settings.REDIS_URL)

    return CascadeRouter(
        rag_engine=rag_engine,
        local_llm=local_llm,
        cloud_llm=cloud_llm,
        redis_client=redis_client,
        cloud_daily_limit=settings.CLOUD_DAILY_LIMIT_PER_USER,
    )


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
