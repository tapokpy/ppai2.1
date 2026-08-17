from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import func, select

from app.core.database import async_session_maker
from app.models.sqlalchemy.document import Document
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.user import User
from app.services.history_search import search_messages

router = Router(name="rag_memory")

NO_DOCUMENTS_LINE = "— пока пусто"
NO_MEMORY_LINE = "— пока не о чем вспоминать, вы ещё не задавали вопросов"
_PROMPT_PREVIEW_LEN = 100

FIND_USAGE = "Использование: /find <текст для поиска>"
_FIND_RESULT_LIMIT = 10


@router.message(Command("memory"))
async def handle_rag_memory_overview(message: Message, db_user: User) -> None:
    async with async_session_maker() as session:
        doc_rows = (
            await session.execute(
                select(Document.source, func.count(), func.coalesce(func.sum(Document.chunk_count), 0))
                .group_by(Document.source)
            )
        ).all()
        # created_at ties are possible (Postgres now() is transaction-start
        # time, so messages inserted in the same transaction share a
        # timestamp) — id DESC breaks ties deterministically, matching the
        # same pattern in app/api/v1/endpoints/admin.py::list_messages.
        recent_messages = (
            await session.execute(
                select(MessageModel)
                .where(MessageModel.user_id == db_user.id)
                .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
                .limit(5)
            )
        ).scalars().all()

    lines = ["📚 База знаний (RAG):"]
    if doc_rows:
        lines.extend(
            f"— {source}: {doc_count} документов, {chunk_count} фрагментов"
            for source, doc_count, chunk_count in doc_rows
        )
    else:
        lines.append(NO_DOCUMENTS_LINE)

    lines.append("")
    lines.append("🧠 Последние вопросы (память):")
    if recent_messages:
        for m in recent_messages:
            preview = m.prompt[:_PROMPT_PREVIEW_LEN]
            if len(m.prompt) > _PROMPT_PREVIEW_LEN:
                preview += "…"
            lines.append(f"— {preview}")
    else:
        lines.append(NO_MEMORY_LINE)

    await message.answer("\n".join(lines))


@router.message(Command("find"))
async def cmd_find(message: Message, command: CommandObject, db_user: User) -> None:
    if not command.args:
        await message.answer(FIND_USAGE)
        return

    query = command.args.strip()
    matches = await search_messages(db_user.id, query, limit=_FIND_RESULT_LIMIT)

    if not matches:
        await message.answer(f"Ничего не нашёл по «{query}» в вашей истории.")
        return

    lines = [f"🔎 Найдено по «{query}»:"]
    for m in matches:
        prompt_preview = m.prompt[:_PROMPT_PREVIEW_LEN] + ("…" if len(m.prompt) > _PROMPT_PREVIEW_LEN else "")
        response_preview = m.response[:_PROMPT_PREVIEW_LEN] + (
            "…" if len(m.response) > _PROMPT_PREVIEW_LEN else ""
        )
        lines.append(f"— «{prompt_preview}»\n   → {response_preview}")

    await message.answer("\n".join(lines))
