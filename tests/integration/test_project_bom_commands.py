from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.fsm.calculators import BomCalculatorStates
from app.bot.handlers.projects import cmd_project_bom, cmd_project_check_stock, cmd_project_pick_list
from app.core.database import async_session_maker
from app.models.sqlalchemy.project import Project
from app.services.stock_import import StockRow, upsert_stock_rows
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres

ADMIN_ID = 960
NON_ADMIN_ID = 961


def _new_state():
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


def _message(user_id: int = NON_ADMIN_ID):
    return SimpleNamespace(from_user=SimpleNamespace(id=user_id), answer=AsyncMock())


async def _seed_project(bom_data: dict | None = None) -> Project:
    async with async_session_maker() as session:
        project = Project(name="Объект 1", bom_data=bom_data)
        session.add(project)
        await session.commit()
        await session.refresh(project)
    return project


@pytest.mark.asyncio
async def test_project_bom_requires_admin(clean_db):
    project = await _seed_project()
    state = _new_state()

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [ADMIN_ID]
        message = _message(NON_ADMIN_ID)
        await cmd_project_bom(message, SimpleNamespace(args=str(project.id)), state)

    assert "администратор" in message.answer.call_args.args[0].lower()


@pytest.mark.asyncio
async def test_project_bom_starts_fsm_with_project_context(clean_db):
    project = await _seed_project()
    state = _new_state()

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [ADMIN_ID]
        message = _message(ADMIN_ID)
        await cmd_project_bom(message, SimpleNamespace(args=str(project.id)), state)

    assert await state.get_state() == BomCalculatorStates.waiting_screen_type.state
    data = await state.get_data()
    assert data["bom_target_project_id"] == project.id


@pytest.mark.asyncio
async def test_project_bom_unknown_project(clean_db):
    state = _new_state()
    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [ADMIN_ID]
        message = _message(ADMIN_ID)
        await cmd_project_bom(message, SimpleNamespace(args="99999"), state)

    assert "не найден" in message.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_check_stock_without_bom_prompts_to_calculate(clean_db):
    project = await _seed_project(bom_data=None)
    message = _message(NON_ADMIN_ID)
    await cmd_project_check_stock(message, SimpleNamespace(args=str(project.id)))

    assert "/project_bom" in message.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_check_stock_reports_deficit_and_sufficiency(clean_db):
    bom_data = {
        "unit_count": 21,
        "zip_modules": 2,
        "psu_count": 3,
        "zip_psu": 1,
        "card_count": 21,
        "zip_cards": 1,
    }
    project = await _seed_project(bom_data=bom_data)

    async with async_session_maker() as session:
        await upsert_stock_rows(
            session,
            [
                StockRow(warehouse="О", rack="А1", shelf="1", cell="1", item_name="Модуль", quantity=10, item_type="module"),
                StockRow(warehouse="О", rack="А1", shelf="1", cell="2", item_name="БП", quantity=10, item_type="psu"),
            ],
        )

    message = _message(NON_ADMIN_ID)
    await cmd_project_check_stock(message, SimpleNamespace(args=str(project.id)))

    reply = message.answer.call_args.args[0]
    assert "module: нужно 23" in reply
    assert "не хватает 13" in reply
    assert "psu: нужно 4, на складе 10 — ✅ достаточно" in reply
    assert "card: нужно 22, на складе 0" in reply


@pytest.mark.asyncio
async def test_pick_list_allocates_from_cells(clean_db):
    bom_data = {"unit_count": 5, "zip_modules": 0, "psu_count": 0, "zip_psu": 0, "card_count": 0, "zip_cards": 0}
    project = await _seed_project(bom_data=bom_data)

    async with async_session_maker() as session:
        await upsert_stock_rows(
            session,
            [
                StockRow(warehouse="О", rack="А1", shelf="1", cell="1", item_name="Модуль A", quantity=3, item_type="module"),
                StockRow(warehouse="О", rack="А1", shelf="1", cell="2", item_name="Модуль B", quantity=10, item_type="module"),
            ],
        )

    message = _message(NON_ADMIN_ID)
    await cmd_project_pick_list(message, SimpleNamespace(args=str(project.id)))

    reply = message.answer.call_args.args[0]
    assert "Модуль B" in reply
    assert "нужно 5" in reply
