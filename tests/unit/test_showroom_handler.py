from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.handlers.admin import ACCESS_DENIED_MESSAGE
from app.bot.handlers.showroom import (
    ASK_COLUMN_REPLY,
    NO_SCREENS_CONFIGURED_REPLY,
    RESOLUME_UNAVAILABLE_REPLY,
    UNKNOWN_COMMAND_REPLY,
    handle_showroom_command,
)
from app.core.showroom_parser import ClipCommand, PresetCommand
from app.services.resolume_controller import ResolumeUnavailableError, ScreensMap


def _screens_map(screens: dict[str, int] | None = None, presets: dict | None = None) -> ScreensMap:
    from app.services.resolume_controller import ScreenTarget

    sm = ScreensMap(
        screens={name: ScreenTarget(layer=layer) for name, layer in (screens or {}).items()},
        presets=presets or {},
    )
    return sm


@pytest.mark.asyncio
async def test_denies_non_admin():
    message = SimpleNamespace(text="шоурум3 запусти x", from_user=SimpleNamespace(id=999), answer=AsyncMock())

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await handle_showroom_command(message, AsyncMock(), MagicMock(), _screens_map())

    message.answer.assert_awaited_once_with(ACCESS_DENIED_MESSAGE)


@pytest.mark.asyncio
async def test_reports_when_no_screens_configured():
    message = SimpleNamespace(text="шоурум3 запусти x", from_user=SimpleNamespace(id=111), answer=AsyncMock())

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await handle_showroom_command(message, AsyncMock(), MagicMock(), _screens_map())

    message.answer.assert_awaited_once_with(NO_SCREENS_CONFIGURED_REPLY)


@pytest.mark.asyncio
async def test_asks_clarifying_question_when_screen_ambiguous():
    message = SimpleNamespace(text="шоурум3 включи 2 колонку", from_user=SimpleNamespace(id=111), answer=AsyncMock())
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value='{"type": "clip", "screen": null, "column": 2}')
    screens_map = _screens_map({"Главный фасад": 1})

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await handle_showroom_command(message, local_llm, MagicMock(), screens_map)

    reply = message.answer.call_args.args[0]
    assert "Главный фасад" in reply


@pytest.mark.asyncio
async def test_asks_for_column_when_screen_known_but_column_missing():
    message = SimpleNamespace(
        text="шоурум3 включи на главном фасаде", from_user=SimpleNamespace(id=111), answer=AsyncMock()
    )
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(
        return_value='{"type": "clip", "screen": "Главный фасад", "column": null}'
    )
    screens_map = _screens_map({"Главный фасад": 1})

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await handle_showroom_command(message, local_llm, MagicMock(), screens_map)

    message.answer.assert_awaited_once_with(ASK_COLUMN_REPLY)


@pytest.mark.asyncio
async def test_triggers_clip_when_screen_and_column_known():
    message = SimpleNamespace(
        text="шоурум3 3 колонку на главном фасаде", from_user=SimpleNamespace(id=111), answer=AsyncMock()
    )
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(
        return_value='{"type": "clip", "screen": "Главный фасад", "column": 3}'
    )
    resolume_controller = MagicMock()
    screens_map = _screens_map({"Главный фасад": 1})

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await handle_showroom_command(message, local_llm, resolume_controller, screens_map)

    resolume_controller.trigger_clip.assert_called_once_with(1, 3)
    assert "Главный фасад" in message.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_reports_resolume_unavailable():
    message = SimpleNamespace(
        text="шоурум3 3 колонку на главном фасаде", from_user=SimpleNamespace(id=111), answer=AsyncMock()
    )
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(
        return_value='{"type": "clip", "screen": "Главный фасад", "column": 3}'
    )
    resolume_controller = MagicMock()
    resolume_controller.trigger_clip.side_effect = ResolumeUnavailableError("no route to host")
    screens_map = _screens_map({"Главный фасад": 1})

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await handle_showroom_command(message, local_llm, resolume_controller, screens_map)

    message.answer.assert_awaited_once_with(RESOLUME_UNAVAILABLE_REPLY.format(error="no route to host"))


@pytest.mark.asyncio
async def test_runs_preset_triggering_every_step():
    message = SimpleNamespace(text="шоурум3 ночной режим", from_user=SimpleNamespace(id=111), answer=AsyncMock())
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value='{"type": "preset", "preset": "Ночной режим"}')
    resolume_controller = MagicMock()
    screens_map = _screens_map(
        {"Главный фасад": 1, "Левый пилон": 2},
        {"Ночной режим": [{"screen": "Главный фасад", "column": 3}, {"screen": "Левый пилон", "column": 3}]},
    )

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await handle_showroom_command(message, local_llm, resolume_controller, screens_map)

    assert resolume_controller.trigger_clip.call_count == 2
    resolume_controller.trigger_clip.assert_any_call(1, 3)
    resolume_controller.trigger_clip.assert_any_call(2, 3)
    message.answer.assert_awaited_once_with("Пресет «Ночной режим» запущен.")


@pytest.mark.asyncio
async def test_reports_unknown_command_when_llm_response_unparseable():
    message = SimpleNamespace(text="шоурум3 бла бла бла", from_user=SimpleNamespace(id=111), answer=AsyncMock())
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value="не json")
    screens_map = _screens_map({"Главный фасад": 1})

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await handle_showroom_command(message, local_llm, MagicMock(), screens_map)

    message.answer.assert_awaited_once_with(UNKNOWN_COMMAND_REPLY)
