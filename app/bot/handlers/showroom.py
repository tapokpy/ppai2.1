from aiogram import Router
from aiogram.types import Message
from loguru import logger

from app.bot.filters import SHOWROOM_TRIGGER_PATTERN, ShouldRespondFilter, ShowroomTriggerFilter
from app.bot.handlers.admin import ACCESS_DENIED_MESSAGE, is_admin
from app.core.showroom_parser import ClipCommand, PresetCommand, parse_showroom_command
from app.services.local_llm import LocalLLMClient
from app.services.resolume_controller import ResolumeController, ResolumeUnavailableError, ScreenNotFoundError, ScreensMap

router = Router(name="showroom")

# Controls physical showroom displays — admin-only, unlike chat/todo which
# any approved user can use.
NO_SCREENS_CONFIGURED_REPLY = "Экраны шоурума ещё не настроены (screens_map.yaml пуст)."
UNKNOWN_COMMAND_REPLY = "Не понял команду для шоурума. Укажите экран и номер ролика, или название пресета."
RESOLUME_UNAVAILABLE_REPLY = "Resolume сейчас не отвечает: {error}"
ASK_COLUMN_REPLY = "На какой ролик (номер колонки в Resolume) переключить?"


def _clarify_screen_reply(screen_names: list[str]) -> str:
    return f"На какой именно экран вывести этот контент? Доступные: {', '.join(screen_names)}"


def _preset_not_found_reply(name: str, preset_names: list[str]) -> str:
    return f"Пресет «{name}» не найден. Доступные: {', '.join(preset_names) or 'нет'}"


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
        for layer, column in steps:
            resolume_controller.trigger_clip(layer, column)
    except ResolumeUnavailableError as exc:
        logger.warning(f"Resolume unavailable while running preset '{command.preset}': {exc}")
        await message.answer(RESOLUME_UNAVAILABLE_REPLY.format(error=str(exc)))
        return

    await message.answer(f"Пресет «{command.preset}» запущен.")


async def _run_clip(
    message: Message, command: ClipCommand, resolume_controller: ResolumeController, screens_map: ScreensMap
) -> None:
    if command.screen is None:
        await message.answer(_clarify_screen_reply(screens_map.screen_names))
        return

    try:
        target = screens_map.get_screen(command.screen)
    except ScreenNotFoundError:
        await message.answer(_clarify_screen_reply(screens_map.screen_names))
        return

    if command.column is None:
        await message.answer(ASK_COLUMN_REPLY)
        return

    try:
        resolume_controller.trigger_clip(target.layer, command.column)
    except ResolumeUnavailableError as exc:
        logger.warning(f"Resolume unavailable: {exc}")
        await message.answer(RESOLUME_UNAVAILABLE_REPLY.format(error=str(exc)))
        return

    await message.answer(f"Переключил «{command.screen}» на ролик {command.column}.")
