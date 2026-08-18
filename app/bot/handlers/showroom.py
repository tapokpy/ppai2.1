from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger

from app.bot.filters import SHOWROOM_TRIGGER_PATTERN, ShouldRespondFilter, ShowroomTriggerFilter
from app.bot.handlers.admin import ACCESS_DENIED_MESSAGE, is_admin
from app.core.showroom_parser import ClipCommand, PresetCommand, parse_showroom_command
from app.services.local_llm import LocalLLMClient
from app.services.resolume_controller import (
    ColumnInfo,
    ResolumeController,
    ResolumeUnavailableError,
    ScreenNotFoundError,
    ScreensMap,
)

router = Router(name="showroom")

# Controls physical showroom displays — admin-only, unlike chat/todo which
# any approved user can use.
NO_SCREENS_CONFIGURED_REPLY = "Экраны шоурума ещё не настроены (screens_map.yaml пуст)."
UNKNOWN_COMMAND_REPLY = "Не понял команду для шоурума. Укажите экран и номер ролика, или название пресета."
RESOLUME_UNAVAILABLE_REPLY = "Resolume сейчас не отвечает: {error}"
ASK_COLUMN_REPLY = "На какой ролик (номер колонки в Resolume) переключить?"
NO_OCCUPIED_COLUMNS_REPLY = "В Resolume сейчас нет ни одного занятого ролика."
PICK_COLUMN_REPLY = "На какой ролик переключить?"


def _clarify_screen_reply(screen_names: list[str]) -> str:
    return f"На какой именно экран вывести этот контент? Доступные: {', '.join(screen_names)}"


def _preset_not_found_reply(name: str, preset_names: list[str]) -> str:
    return f"Пресет «{name}» не найден. Доступные: {', '.join(preset_names) or 'нет'}"


def _columns_keyboard(screen_name: str, columns: list[ColumnInfo]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"{c.column}. {c.name}", callback_data=f"showroom_col:{screen_name}:{c.column}")]
        for c in columns
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(ShowroomTriggerFilter(), ShouldRespondFilter())
async def handle_showroom_command(
    message: Message,
    local_llm: LocalLLMClient,
    resolume_controller: ResolumeController,
    screens_map: ScreensMap,
) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(ACCESS_DENIED_MESSAGE)
        return

    if not screens_map.screen_names:
        await message.answer(NO_SCREENS_CONFIGURED_REPLY)
        return

    cleaned_text = SHOWROOM_TRIGGER_PATTERN.sub("", message.text).strip() or message.text
    command = await parse_showroom_command(
        cleaned_text, local_llm, screens_map.screen_names, screens_map.preset_names
    )

    if command is None:
        await message.answer(UNKNOWN_COMMAND_REPLY)
        return

    if isinstance(command, PresetCommand):
        await _run_preset(message, command, resolume_controller, screens_map)
        return

    await _run_clip(message, command, resolume_controller, screens_map)


async def _run_preset(
    message: Message, command: PresetCommand, resolume_controller: ResolumeController, screens_map: ScreensMap
) -> None:
    try:
        steps = screens_map.get_preset_steps(command.preset)
    except ScreenNotFoundError:
        await message.answer(_preset_not_found_reply(command.preset, screens_map.preset_names))
        return

    try:
        # Column-connect (not per-layer clip-connect) — the real showroom
        # is one physical screen composited from several layers, so
        # "activate this step" means switching the whole column, which
        # moves every layer's clip together. The per-step layer number in
        # screens_map.yaml is unused here (kept only so presets can still
        # be authored the same way if a second physical screen is ever
        # added); only the column matters for a single-screen setup.
        for _layer, column in steps:
            resolume_controller.trigger_column(column)
    except ResolumeUnavailableError as exc:
        logger.warning(f"Resolume unavailable while running preset '{command.preset}': {exc}")
        await message.answer(RESOLUME_UNAVAILABLE_REPLY.format(error=str(exc)))
        return

    await message.answer(f"Пресет «{command.preset}» запущен.")


async def _run_clip(
    message: Message, command: ClipCommand, resolume_controller: ResolumeController, screens_map: ScreensMap
) -> None:
    screen_name = command.screen
    # A single configured screen never needs disambiguation — the real
    # showroom is one physical output, so asking "on which screen" for
    # every command would just be friction for a question with only one
    # possible answer. Multiple screens still ask, same as before.
    if screen_name is None:
        if len(screens_map.screen_names) == 1:
            screen_name = screens_map.screen_names[0]
        else:
            await message.answer(_clarify_screen_reply(screens_map.screen_names))
            return

    try:
        screens_map.get_screen(screen_name)
    except ScreenNotFoundError:
        await message.answer(_clarify_screen_reply(screens_map.screen_names))
        return

    if command.column is None:
        # Show real, tappable buttons for whatever's actually loaded in
        # Resolume right now instead of asking the user to guess a column
        # number blind — falls back to the old plain-text prompt only if
        # Resolume can't be reached at all to list them.
        try:
            columns = await resolume_controller.list_occupied_columns()
        except ResolumeUnavailableError:
            await message.answer(ASK_COLUMN_REPLY)
            return

        if not columns:
            await message.answer(NO_OCCUPIED_COLUMNS_REPLY)
            return

        await message.answer(PICK_COLUMN_REPLY, reply_markup=_columns_keyboard(screen_name, columns))
        return

    try:
        # Column-connect, not per-layer clip-connect — see _run_preset's
        # comment above for why: this showroom is one physical screen
        # composited from several layers, so switching "the clip" means
        # switching the whole column (every layer moves together), not
        # just one layer while the others stay on their old clip.
        resolume_controller.trigger_column(command.column)
    except ResolumeUnavailableError as exc:
        logger.warning(f"Resolume unavailable: {exc}")
        await message.answer(RESOLUME_UNAVAILABLE_REPLY.format(error=str(exc)))
        return

    await message.answer(f"Переключил «{screen_name}» на ролик {command.column}.")


@router.callback_query(F.data.startswith("showroom_col:"))
async def handle_showroom_column_choice(
    callback: CallbackQuery, resolume_controller: ResolumeController
) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(ACCESS_DENIED_MESSAGE, show_alert=True)
        return

    _prefix, screen_name, column_str = callback.data.split(":", 2)
    column = int(column_str)

    try:
        resolume_controller.trigger_column(column)
    except ResolumeUnavailableError as exc:
        logger.warning(f"Resolume unavailable: {exc}")
        await callback.answer(RESOLUME_UNAVAILABLE_REPLY.format(error=str(exc)), show_alert=True)
        return

    if callback.message is not None:
        await callback.message.edit_text(f"Переключил «{screen_name}» на ролик {column}.")
    await callback.answer()
