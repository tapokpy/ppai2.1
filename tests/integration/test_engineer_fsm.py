from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

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
from app.services.business_rules import BusinessRulesEngine
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


def _new_state():
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    from aiogram.fsm.context import FSMContext

    return FSMContext(storage=storage, key=key)


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
    await module_pixel_pitch_entered(message, state)

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
    await power_module_power_entered(message, state)

    assert await state.get_state() == PowerCalculatorStates.waiting_module_power.state
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_module_calculator_full_flow(clean_db):
    state = _new_state()

    message = SimpleNamespace(text=BTN_MODULE_CALC, answer=AsyncMock())
    await start_module_calculator(message, state)
    assert await state.get_state() == ModuleCalculatorStates.waiting_width.state

    message.text = "3.0"
    await module_width_entered(message, state)
    assert await state.get_state() == ModuleCalculatorStates.waiting_height.state

    message.text = "2.0"
    await module_height_entered(message, state)
    assert await state.get_state() == ModuleCalculatorStates.waiting_pixel_pitch.state

    message.text = "2.5"
    await module_pixel_pitch_entered(message, state)
    assert await state.get_state() is None

    final_text = message.answer.call_args.args[0]
    assert "Модулей: 24" in final_text


@pytest.mark.asyncio
async def test_module_calculator_shows_business_rule_warning(clean_db):
    async with async_session_maker() as session:
        await BusinessRulesEngine(session).add_rule(
            "При шаге пикселя 2.5 нужно согласование с инженером"
        )

    state = _new_state()
    message = SimpleNamespace(text=BTN_MODULE_CALC, answer=AsyncMock())
    await start_module_calculator(message, state)
    message.text = "3.0"
    await module_width_entered(message, state)
    message.text = "2.0"
    await module_height_entered(message, state)
    message.text = "2.5"
    await module_pixel_pitch_entered(message, state)

    final_text = message.answer.call_args.args[0]
    assert "⚠️ Предупреждения" in final_text
    assert "согласование" in final_text


@pytest.mark.asyncio
async def test_power_calculator_full_flow(clean_db):
    state = _new_state()

    message = SimpleNamespace(text=BTN_POWER_CALC, answer=AsyncMock())
    await start_power_calculator(message, state)

    message.text = "10"
    await power_module_count_entered(message, state)

    message.text = "100"
    await power_module_power_entered(message, state)

    assert await state.get_state() is None
    final_text = message.answer.call_args.args[0]
    assert "Номинал автомата: 10 А" in final_text
