from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select

from app.bot.fsm.calculators import ModuleCalculatorStates, PowerCalculatorStates
from app.bot.handlers.engineer import (
    module_height_entered,
    module_pixel_pitch_entered,
    module_width_entered,
    power_module_count_entered,
    power_module_power_entered,
    start_module_calculator,
    start_power_calculator,
)
from app.bot.keyboards.reply import BTN_MODULE_CALC, BTN_POWER_CALC
from app.core.database import async_session_maker
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.user import User
from app.services.business_rules import BusinessRulesEngine
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


def _new_state():
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    from aiogram.fsm.context import FSMContext

    return FSMContext(storage=storage, key=key)


async def _seed_user(telegram_id: int) -> User:
    async with async_session_maker() as session:
        user = User(telegram_id=telegram_id, username="engineer", is_approved=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_module_width_entered_rejects_invalid_number(clean_db):
    state = _new_state()
    await state.set_state(ModuleCalculatorStates.waiting_width)

    message = SimpleNamespace(text="abc", answer=AsyncMock())
    await module_width_entered(message, state)

    assert await state.get_state() == ModuleCalculatorStates.waiting_width.state
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_module_height_entered_rejects_invalid_number(clean_db):
    state = _new_state()
    await state.set_state(ModuleCalculatorStates.waiting_height)
    await state.update_data(width=3.0)

    message = SimpleNamespace(text="abc", answer=AsyncMock())
    await module_height_entered(message, state)

    assert await state.get_state() == ModuleCalculatorStates.waiting_height.state
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_module_pixel_pitch_entered_rejects_invalid_number(clean_db):
    state = _new_state()
    await state.set_state(ModuleCalculatorStates.waiting_pixel_pitch)
    await state.update_data(width=3.0, height=2.0)

    message = SimpleNamespace(text="abc", answer=AsyncMock())
    await module_pixel_pitch_entered(message, state, db_user=None)

    assert await state.get_state() == ModuleCalculatorStates.waiting_pixel_pitch.state
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_power_module_count_entered_rejects_invalid_number(clean_db):
    state = _new_state()
    await state.set_state(PowerCalculatorStates.waiting_module_count)

    message = SimpleNamespace(text="abc", answer=AsyncMock())
    await power_module_count_entered(message, state)

    assert await state.get_state() == PowerCalculatorStates.waiting_module_count.state
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_power_module_power_entered_rejects_invalid_number(clean_db):
    state = _new_state()
    await state.set_state(PowerCalculatorStates.waiting_module_power)
    await state.update_data(module_count=10)

    message = SimpleNamespace(text="abc", answer=AsyncMock())
    await power_module_power_entered(message, state, db_user=None)

    assert await state.get_state() == PowerCalculatorStates.waiting_module_power.state
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_module_calculator_full_flow(clean_db):
    user = await _seed_user(701)
    state = _new_state()

    message = SimpleNamespace(text=BTN_MODULE_CALC, message_id=1, answer=AsyncMock())
    await start_module_calculator(message, state)
    assert await state.get_state() == ModuleCalculatorStates.waiting_width.state

    message.text = "3.0"
    await module_width_entered(message, state)
    assert await state.get_state() == ModuleCalculatorStates.waiting_height.state

    message.text = "2.0"
    await module_height_entered(message, state)
    assert await state.get_state() == ModuleCalculatorStates.waiting_pixel_pitch.state

    message.text = "2.5"
    await module_pixel_pitch_entered(message, state, db_user=user)
    assert await state.get_state() is None

    final_text = message.answer.call_args.args[0]
    assert "Модулей: 24" in final_text

    async with async_session_maker() as session:
        stored = (await session.execute(select(MessageModel))).scalars().all()

    assert len(stored) == 1
    assert stored[0].source == "calculator"
    assert stored[0].structured_data["kind"] == "module_calculation"
    assert stored[0].structured_data["items"][0]["quantity"] == 24


@pytest.mark.asyncio
async def test_module_calculator_shows_business_rule_warning(clean_db):
    user = await _seed_user(702)
    async with async_session_maker() as session:
        await BusinessRulesEngine(session).add_rule(
            "При шаге пикселя 2.5 нужно согласование с инженером"
        )

    state = _new_state()
    message = SimpleNamespace(text=BTN_MODULE_CALC, message_id=2, answer=AsyncMock())
    await start_module_calculator(message, state)
    message.text = "3.0"
    await module_width_entered(message, state)
    message.text = "2.0"
    await module_height_entered(message, state)
    message.text = "2.5"
    await module_pixel_pitch_entered(message, state, db_user=user)

    final_text = message.answer.call_args.args[0]
    assert "⚠️ Предупреждения" in final_text
    assert "согласование" in final_text


@pytest.mark.asyncio
async def test_power_calculator_full_flow(clean_db):
    user = await _seed_user(703)
    state = _new_state()

    message = SimpleNamespace(text=BTN_POWER_CALC, message_id=3, answer=AsyncMock())
    await start_power_calculator(message, state)

    message.text = "10"
    await power_module_count_entered(message, state)

    message.text = "100"
    await power_module_power_entered(message, state, db_user=user)

    assert await state.get_state() is None
    final_text = message.answer.call_args.args[0]
    assert "Номинал автомата: 10 А" in final_text

    async with async_session_maker() as session:
        stored = (await session.execute(select(MessageModel))).scalars().all()

    assert len(stored) == 1
    assert stored[0].structured_data["kind"] == "power_calculation"
