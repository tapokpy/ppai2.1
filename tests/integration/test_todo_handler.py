from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.bot.handlers.todo import GITHUB_UNAVAILABLE_REPLY, handle_todo
from app.core.database import async_session_maker
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.user import User
from app.services.github_planning import GitHubPlanningError
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


async def _seed_user(telegram_id: int = 601) -> User:
    async with async_session_maker() as session:
        user = User(telegram_id=telegram_id, username="engineer", is_approved=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_handle_todo_saves_message_and_replies_on_success(clean_db):
    user = await _seed_user()

    cascade_router = MagicMock()
    cascade_router.rag_engine.query.return_value = {"documents": ["Контекст про расчёт питания"]}
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(
        return_value='{"title": "Доработать расчёт потребления", "description": "Учесть КПД"}'
    )
    github_planning_client = AsyncMock()

    message = SimpleNamespace(
        text="тодолист3 доработать расчёт потребления",
        message_id=11,
        chat=SimpleNamespace(id=2001, type="private"),
        answer=AsyncMock(),
    )

    await handle_todo(message, cascade_router, local_llm, github_planning_client, user)

    github_planning_client.append_todo_entry.assert_awaited_once()
    message.answer.assert_awaited_once()
    assert "Доработать расчёт потребления" in message.answer.call_args.args[0]

    async with async_session_maker() as session:
        stored = (await session.execute(select(MessageModel))).scalars().all()

    assert len(stored) == 1
    assert stored[0].source == "todo"
    assert stored[0].structured_data["title"] == "Доработать расчёт потребления"
    assert stored[0].structured_data["github_synced"] is True
    assert stored[0].context_used is True


@pytest.mark.asyncio
async def test_handle_todo_saves_message_when_github_unavailable(clean_db):
    user = await _seed_user(602)

    cascade_router = MagicMock()
    cascade_router.rag_engine.query.return_value = {"documents": []}
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value='{"title": "Задача", "description": null}')
    github_planning_client = AsyncMock()
    github_planning_client.append_todo_entry = AsyncMock(side_effect=GitHubPlanningError("boom"))

    message = SimpleNamespace(
        text="план3 задача",
        message_id=12,
        chat=SimpleNamespace(id=2002, type="private"),
        answer=AsyncMock(),
    )

    await handle_todo(message, cascade_router, local_llm, github_planning_client, user)

    message.answer.assert_awaited_once_with(GITHUB_UNAVAILABLE_REPLY)

    async with async_session_maker() as session:
        stored = (await session.execute(select(MessageModel))).scalars().all()

    assert len(stored) == 1
    assert stored[0].structured_data["github_synced"] is False
