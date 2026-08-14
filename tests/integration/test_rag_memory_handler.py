from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers.rag_memory import handle_rag_memory_overview
from app.core.database import async_session_maker
from app.models.sqlalchemy.document import Document
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.user import User
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


async def _seed_user(telegram_id: int) -> User:
    async with async_session_maker() as session:
        user = User(telegram_id=telegram_id, username="u", is_approved=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


def _message() -> SimpleNamespace:
    return SimpleNamespace(answer=AsyncMock())


@pytest.mark.asyncio
async def test_shows_placeholders_when_nothing_exists(clean_db):
    user = await _seed_user(1)
    message = _message()

    await handle_rag_memory_overview(message, db_user=user)

    reply = message.answer.call_args.args[0]
    assert "пока пусто" in reply
    assert "не о чем вспоминать" in reply


@pytest.mark.asyncio
async def test_shows_document_counts_grouped_by_source(clean_db):
    user = await _seed_user(2)
    async with async_session_maker() as session:
        session.add_all(
            [
                Document(source="pdf_upload", filename="a.pdf", chunk_count=3, embedding_model="m"),
                Document(source="pdf_upload", filename="b.pdf", chunk_count=5, embedding_model="m"),
                Document(source="text_upload", filename="c.txt", chunk_count=2, embedding_model="m"),
            ]
        )
        await session.commit()

    message = _message()
    await handle_rag_memory_overview(message, db_user=user)

    reply = message.answer.call_args.args[0]
    assert "pdf_upload: 2 документов, 8 фрагментов" in reply
    assert "text_upload: 1 документов, 2 фрагментов" in reply


@pytest.mark.asyncio
async def test_shows_last_5_messages_for_this_user_only(clean_db):
    user = await _seed_user(3)
    other_user = await _seed_user(4)

    async with async_session_maker() as session:
        for i in range(7):
            session.add(
                MessageModel(
                    user_id=user.id, telegram_message_id=None, prompt=f"вопрос {i}", response="r", source="local",
                    context_used=False,
                )
            )
        session.add(
            MessageModel(
                user_id=other_user.id, telegram_message_id=None, prompt="чужой вопрос", response="r",
                source="local", context_used=False,
            )
        )
        await session.commit()

    message = _message()
    await handle_rag_memory_overview(message, db_user=user)

    reply = message.answer.call_args.args[0]
    assert "вопрос 6" in reply  # most recent
    assert "чужой вопрос" not in reply
    assert reply.count("вопрос ") == 5


@pytest.mark.asyncio
async def test_long_prompt_is_truncated_with_ellipsis(clean_db):
    user = await _seed_user(5)
    long_prompt = "а" * 200

    async with async_session_maker() as session:
        session.add(
            MessageModel(
                user_id=user.id, telegram_message_id=None, prompt=long_prompt, response="r", source="local",
                context_used=False,
            )
        )
        await session.commit()

    message = _message()
    await handle_rag_memory_overview(message, db_user=user)

    reply = message.answer.call_args.args[0]
    assert "…" in reply
    assert long_prompt not in reply
