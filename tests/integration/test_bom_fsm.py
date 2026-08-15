from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select

from app.bot.fsm.calculators import BomCalculatorStates
from app.bot.handlers.engineer import (
    bom_height_entered,
    bom_module_power_entered,
    bom_module_size_entered,
    bom_pixel_pitch_entered,
    bom_psu_power_entered,
    bom_screen_type_entered,
    bom_width_entered,
    start_bom_calculator,
)
from app.core.database import async_session_maker
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.user import User
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


def _new_state():
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def _seed_user(telegram_id: int) -> User:
    async with async_session_maker() as session:
        user = User(telegram_id=telegram_id, username="engineer", is_approved=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_bom_screen_type_rejects_unknown_value(clean_db):
    state = _new_state()
    await state.set_state(BomCalculatorStates.waiting_screen_type)

    message = SimpleNamespace(text="что-то странное", answer=AsyncMock())
    await bom_screen_type_entered(message, state)

    assert await state.get_state() == BomCalculatorStates.waiting_screen_type.state


@pytest.mark.asyncio
async def test_outdoor_bom_flow_skips_extra_questions(clean_db):
    user = await _seed_user(801)
    state = _new_state()

    message = SimpleNamespace(text="/calc_bom", message_id=1, answer=AsyncMock())
    await start_bom_calculator(message, state)
    assert await state.get_state() == BomCalculatorStates.waiting_screen_type.state

    message.text = "outdoor"
    await bom_screen_type_entered(message, state)
    assert await state.get_state() == BomCalculatorStates.waiting_width.state

    message.text = "6720"
    await bom_width_entered(message, state)
    message.text = "960"
    await bom_height_entered(message, state)
    message.text = "2.5"
    await bom_pixel_pitch_entered(message, state)

    message.text = "10"
    await bom_module_power_entered(message, state, db_user=user)

    # Outdoor has a golden-standard PSU table -> flow ends here, no extra questions.
    assert await state.get_state() is None
    final_text = message.answer.call_args.args[0]
    assert "Кабинетов/модулей: 7" in final_text
    assert "БП" in final_text

    async with async_session_maker() as session:
        stored = (await session.execute(select(MessageModel))).scalars().all()
    assert len(stored) == 1
    assert stored[0].structured_data["kind"] == "led_bom_calculation"


@pytest.mark.asyncio
async def test_open_frame_bom_flow_asks_module_size_and_psu(clean_db):
    user = await _seed_user(802)
    state = _new_state()

    message = SimpleNamespace(text="/calc_bom", message_id=2, answer=AsyncMock())
    await start_bom_calculator(message, state)

    message.text = "open_frame"
    await bom_screen_type_entered(message, state)
    message.text = "1000"
    await bom_width_entered(message, state)
    message.text = "1000"
    await bom_height_entered(message, state)
    message.text = "2.5"
    await bom_pixel_pitch_entered(message, state)

    message.text = "50"
    await bom_module_power_entered(message, state, db_user=user)
    assert await state.get_state() == BomCalculatorStates.waiting_module_size.state

    message.text = "250"
    await bom_module_size_entered(message, state, db_user=user)
    assert await state.get_state() == BomCalculatorStates.waiting_psu_power.state

    message.text = "300"
    await bom_psu_power_entered(message, state, db_user=user)

    assert await state.get_state() is None
    final_text = message.answer.call_args.args[0]
    assert "Кабинетов/модулей: 16" in final_text


@pytest.mark.asyncio
async def test_invalid_module_power_reprompts(clean_db):
    state = _new_state()
    await state.set_state(BomCalculatorStates.waiting_module_power)
    await state.update_data(screen_type="outdoor", width_mm=960, height_mm=960, pixel_pitch_mm=2.5)

    message = SimpleNamespace(text="много", answer=AsyncMock())
    await bom_module_power_entered(message, state, db_user=None)

    assert await state.get_state() == BomCalculatorStates.waiting_module_power.state
