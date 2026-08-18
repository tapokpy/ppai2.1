from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.handlers.admin import ACCESS_DENIED_MESSAGE
from app.bot.handlers.showroom import (
    ASK_COLUMN_REPLY,
    NO_OCCUPIED_COLUMNS_REPLY,
    NO_SCREENS_CONFIGURED_REPLY,
    PICK_COLUMN_REPLY,
    RESOLUME_UNAVAILABLE_REPLY,
    UNKNOWN_COMMAND_REPLY,
    handle_showroom_column_choice,
    handle_showroom_command,
)
from app.services.resolume_controller import ColumnInfo, ResolumeUnavailableError, ScreensMap


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
    # Only ambiguous with 2+ screens configured — a single screen never
    # needs disambiguation (see the dedicated auto-select test below).
    message = SimpleNamespace(text="шоурум3 включи 2 колонку", from_user=SimpleNamespace(id=111), answer=AsyncMock())
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value='{"type": "clip", "screen": null, "column": 2}')
    screens_map = _screens_map({"Главный фасад": 1, "Левый пилон": 2})

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await handle_showroom_command(message, local_llm, MagicMock(), screens_map)

    reply = message.answer.call_args.args[0]
    assert "Главный фасад" in reply
    assert "Левый пилон" in reply


@pytest.mark.asyncio
async def test_auto_selects_screen_when_only_one_configured():
    # The real showroom is a single physical screen — asking "on which
    # screen" would be pure friction when there's only one possible answer.
    message = SimpleNamespace(text="шоурум3 6 колонку", from_user=SimpleNamespace(id=111), answer=AsyncMock())
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value='{"type": "clip", "screen": null, "column": 6}')
    resolume_controller = MagicMock()
    screens_map = _screens_map({"Шоурум": 1})

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await handle_showroom_command(message, local_llm, resolume_controller, screens_map)

    resolume_controller.trigger_column.assert_called_once_with(6)
    assert "Шоурум" in message.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_falls_back_to_plain_prompt_when_resolume_unreachable_for_column_list():
    message = SimpleNamespace(
        text="шоурум3 включи на главном фасаде", from_user=SimpleNamespace(id=111), answer=AsyncMock()
    )
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(
        return_value='{"type": "clip", "screen": "Главный фасад", "column": null}'
    )
    resolume_controller = MagicMock()
    resolume_controller.list_occupied_columns = AsyncMock(
        side_effect=ResolumeUnavailableError("no route to host")
    )
    screens_map = _screens_map({"Главный фасад": 1})

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await handle_showroom_command(message, local_llm, resolume_controller, screens_map)

    message.answer.assert_awaited_once_with(ASK_COLUMN_REPLY)


@pytest.mark.asyncio
async def test_shows_column_buttons_when_screen_known_but_column_missing():
    message = SimpleNamespace(
        text="шоурум3 включи на главном фасаде", from_user=SimpleNamespace(id=111), answer=AsyncMock()
    )
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(
        return_value='{"type": "clip", "screen": "Главный фасад", "column": null}'
    )
    resolume_controller = MagicMock()
    resolume_controller.list_occupied_columns = AsyncMock(
        return_value=[ColumnInfo(column=6, name="ттт"), ColumnInfo(column=7, name="аватар")]
    )
    screens_map = _screens_map({"Главный фасад": 1})

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await handle_showroom_command(message, local_llm, resolume_controller, screens_map)

    message.answer.assert_awaited_once()
    assert message.answer.call_args.args[0] == PICK_COLUMN_REPLY
    keyboard = message.answer.call_args.kwargs["reply_markup"]
    button_texts = [row[0].text for row in keyboard.inline_keyboard]
    assert button_texts == ["6. ттт", "7. аватар"]
    assert keyboard.inline_keyboard[0][0].callback_data == "showroom_col:Главный фасад:6"


@pytest.mark.asyncio
async def test_reports_no_occupied_columns():
    message = SimpleNamespace(
        text="шоурум3 включи на главном фасаде", from_user=SimpleNamespace(id=111), answer=AsyncMock()
    )
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(
        return_value='{"type": "clip", "screen": "Главный фасад", "column": null}'
    )
    resolume_controller = MagicMock()
    resolume_controller.list_occupied_columns = AsyncMock(return_value=[])
    screens_map = _screens_map({"Главный фасад": 1})

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await handle_showroom_command(message, local_llm, resolume_controller, screens_map)

    message.answer.assert_awaited_once_with(NO_OCCUPIED_COLUMNS_REPLY)


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

    resolume_controller.trigger_column.assert_called_once_with(3)
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
    resolume_controller.trigger_column.side_effect = ResolumeUnavailableError("no route to host")
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

    assert resolume_controller.trigger_column.call_count == 2
    resolume_controller.trigger_column.assert_any_call(3)
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


def _callback(column: str = "showroom_col:Шоурум:7", user_id: int = 111):
    return SimpleNamespace(
        data=column,
        from_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(edit_text=AsyncMock()),
        answer=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_callback_denies_non_admin():
    callback = _callback(user_id=999)

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await handle_showroom_column_choice(callback, MagicMock())

    callback.answer.assert_awaited_once_with(ACCESS_DENIED_MESSAGE, show_alert=True)
    callback.message.edit_text.assert_not_called()


@pytest.mark.asyncio
async def test_callback_triggers_column_and_edits_message():
    callback = _callback()
    resolume_controller = MagicMock()

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await handle_showroom_column_choice(callback, resolume_controller)

    resolume_controller.trigger_column.assert_called_once_with(7)
    callback.message.edit_text.assert_awaited_once_with("Переключил «Шоурум» на ролик 7.")
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_callback_reports_resolume_unavailable():
    callback = _callback()
    resolume_controller = MagicMock()
    resolume_controller.trigger_column.side_effect = ResolumeUnavailableError("no route to host")

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await handle_showroom_column_choice(callback, resolume_controller)

    callback.answer.assert_awaited_once_with(
        RESOLUME_UNAVAILABLE_REPLY.format(error="no route to host"), show_alert=True
    )
    callback.message.edit_text.assert_not_called()
