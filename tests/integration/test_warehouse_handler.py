from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.fsm.warehouse import StockAddStates
from app.bot.handlers.warehouse import (
    cmd_import_sheet,
    handle_warehouse_lookup,
    start_stock_add,
    stock_add_cell,
    stock_add_item_name,
    stock_add_item_type,
    stock_add_quantity,
    stock_add_rack,
    stock_add_shelf,
    stock_add_warehouse,
)
from app.services.stock_import import StockRow, upsert_stock_rows
from app.core.database import async_session_maker
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres

ADMIN_ID = 900
NON_ADMIN_ID = 901


def _new_state():
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


def _message(text: str, user_id: int = NON_ADMIN_ID):
    return SimpleNamespace(text=text, from_user=SimpleNamespace(id=user_id), answer=AsyncMock())


@pytest.mark.asyncio
async def test_lookup_without_query_asks_for_one(clean_db):
    message = _message("склад3")
    await handle_warehouse_lookup(message)
    assert "Что искать" in message.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_lookup_with_no_matches(clean_db):
    message = _message("склад3 несуществующий модуль")
    await handle_warehouse_lookup(message)
    assert "не найдено" in message.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_lookup_finds_and_formats_location(clean_db):
    row = StockRow(warehouse="Основной", rack="А1", shelf="2", cell="3", item_name="Модуль P2.5", quantity=24)
    async with async_session_maker() as session:
        await upsert_stock_rows(session, [row])

    message = _message("склад3 P2.5")
    await handle_warehouse_lookup(message)

    reply = message.answer.call_args.args[0]
    assert "Модуль P2.5" in reply
    assert "24" in reply
    assert "Основной / А1 / 2 / 3" in reply


@pytest.mark.asyncio
async def test_stock_add_rejects_non_admin(clean_db):
    state = _new_state()
    message = _message("остаток3", user_id=NON_ADMIN_ID)

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [ADMIN_ID]
        await start_stock_add(message, state)

    assert "администратор" in message.answer.call_args.args[0].lower()
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_stock_add_full_flow_creates_stock_item(clean_db):
    state = _new_state()

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [ADMIN_ID]

        message = _message("остаток3", user_id=ADMIN_ID)
        await start_stock_add(message, state)
        assert await state.get_state() == StockAddStates.waiting_warehouse.state

        message.text = "Основной"
        await stock_add_warehouse(message, state)
        assert await state.get_state() == StockAddStates.waiting_rack.state

        message.text = "А1"
        await stock_add_rack(message, state)

        message.text = "2"
        await stock_add_shelf(message, state)

        message.text = "3"
        await stock_add_cell(message, state)

        message.text = "Модуль P2.5"
        await stock_add_item_name(message, state)

        message.text = "module"
        await stock_add_item_type(message, state)

        message.text = "24"
        await stock_add_quantity(message, state)

    assert await state.get_state() is None
    final_text = message.answer.call_args.args[0]
    assert "Модуль P2.5" in final_text
    assert "24" in final_text


@pytest.mark.asyncio
async def test_stock_add_quantity_rejects_non_numeric(clean_db):
    state = _new_state()
    await state.set_state(StockAddStates.waiting_quantity)
    await state.update_data(warehouse="О", rack="А1", shelf="1", cell="1", item_name="X", item_type="other")

    message = _message("много")
    await stock_add_quantity(message, state)

    assert await state.get_state() == StockAddStates.waiting_quantity.state


@pytest.mark.asyncio
async def test_import_sheet_requires_admin(clean_db):
    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [ADMIN_ID]
        message = _message("/import_sheet", user_id=NON_ADMIN_ID)
        command = SimpleNamespace(args="some-id")
        await cmd_import_sheet(message, command)

    assert "администратор" in message.answer.call_args.args[0].lower()


@pytest.mark.asyncio
async def test_import_sheet_without_args_shows_usage(clean_db):
    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [ADMIN_ID]
        message = _message("/import_sheet", user_id=ADMIN_ID)
        command = SimpleNamespace(args=None)
        await cmd_import_sheet(message, command)

    assert "Использование" in message.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_import_sheet_imports_rows(clean_db):
    fake_rows = [
        ["Склад", "Стеллаж", "Полка", "Ячейка", "Наименование", "Количество"],
        ["Осн", "А1", "1", "1", "Модуль", "8"],
    ]

    with patch("app.bot.handlers.admin.settings") as settings_mock, patch(
        "app.bot.handlers.warehouse.fetch_public_sheet_rows", AsyncMock(return_value=fake_rows)
    ):
        settings_mock.admin_ids = [ADMIN_ID]
        message = _message("/import_sheet", user_id=ADMIN_ID)
        command = SimpleNamespace(args="1AbCdEfGhIjKlMnOp")
        await cmd_import_sheet(message, command)

    assert "Импортировано позиций: 1" in message.answer.call_args.args[0]
