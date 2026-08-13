from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.bot.handlers.admin import ACCESS_DENIED_MESSAGE
from app.bot.handlers.todo import TODO_LIST_EMPTY_REPLY, cmd_todo, handle_todo
from app.core.database import async_session_maker
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.todo import Todo
from app.models.sqlalchemy.user import User
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
async def test_handle_todo_saves_todo_and_message_and_replies(clean_db):
    user = await _seed_user()

    cascade_router = MagicMock()
    cascade_router.rag_engine.query.return_value = {"documents": ["Контекст про расчёт питания"]}
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(
        return_value='{"title": "Доработать расчёт потребления", "description": "Учесть КПД"}'
    )

    message = SimpleNamespace(
        text="тодолист3 доработать расчёт потребления",
        message_id=11,
        chat=SimpleNamespace(id=2001, type="private"),
        answer=AsyncMock(),
    )

    await handle_todo(message, cascade_router, local_llm, user)

    message.answer.assert_awaited_once()
    assert "Доработать расчёт потребления" in message.answer.call_args.args[0]

    async with async_session_maker() as session:
        todos = (await session.execute(select(Todo))).scalars().all()
        stored_messages = (await session.execute(select(MessageModel))).scalars().all()

    assert len(todos) == 1
    assert todos[0].title == "Доработать расчёт потребления"
    assert todos[0].description == "Учесть КПД"
    assert todos[0].author_id == user.id
    assert todos[0].done is False

    assert len(stored_messages) == 1
    assert stored_messages[0].source == "todo"
    assert stored_messages[0].structured_data["todo_id"] == todos[0].id
    assert stored_messages[0].context_used is True


@pytest.mark.asyncio
async def test_cmd_todo_denies_non_admin(clean_db):
    user = await _seed_user(602)
    message = SimpleNamespace(from_user=SimpleNamespace(id=999), answer=AsyncMock())
    command = SimpleNamespace(args=None)

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await cmd_todo(message, command, MagicMock(), AsyncMock(), user)

    message.answer.assert_awaited_once_with(ACCESS_DENIED_MESSAGE)


@pytest.mark.asyncio
async def test_cmd_todo_lists_saved_todos_for_admin(clean_db):
    user = await _seed_user(603)
    async with async_session_maker() as session:
        session.add(Todo(title="Первая задача", author_id=user.id))
        session.add(Todo(title="Вторая задача (сделана)", author_id=user.id, done=True))
        await session.commit()

    message = SimpleNamespace(from_user=SimpleNamespace(id=111), answer=AsyncMock())
    command = SimpleNamespace(args=None)

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await cmd_todo(message, command, MagicMock(), AsyncMock(), user)

    reply = message.answer.call_args.args[0]
    assert "Первая задача" in reply
    assert "Вторая задача (сделана)" in reply
    assert "✅" in reply
    assert "▫️" in reply


@pytest.mark.asyncio
async def test_cmd_todo_reports_empty_list(clean_db):
    user = await _seed_user(604)
    message = SimpleNamespace(from_user=SimpleNamespace(id=111), answer=AsyncMock())
    command = SimpleNamespace(args=None)

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await cmd_todo(message, command, MagicMock(), AsyncMock(), user)

    message.answer.assert_awaited_once_with(TODO_LIST_EMPTY_REPLY)


@pytest.mark.asyncio
async def test_cmd_todo_with_args_adds_entry(clean_db):
    user = await _seed_user(605)
    cascade_router = MagicMock()
    cascade_router.rag_engine.query.return_value = {"documents": []}
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value='{"title": "Проверить блоки питания", "description": null}')

    message = SimpleNamespace(
        text="/todo проверить блоки питания",
        message_id=13,
        chat=SimpleNamespace(id=2003, type="private"),
        from_user=SimpleNamespace(id=111),
        answer=AsyncMock(),
    )
    command = SimpleNamespace(args="проверить блоки питания")

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await cmd_todo(message, command, cascade_router, local_llm, user)

    assert "Проверить блоки питания" in message.answer.call_args.args[0]

    async with async_session_maker() as session:
        todos = (await session.execute(select(Todo))).scalars().all()

    assert len(todos) == 1
    assert todos[0].title == "Проверить блоки питания"
