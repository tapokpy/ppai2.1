from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import ReplyKeyboardRemove

from app.bot.handlers.start import cmd_start


@pytest.mark.asyncio
async def test_cmd_start_sends_welcome_and_clears_any_old_menu():
    message = SimpleNamespace(answer=AsyncMock())

    await cmd_start(message)

    message.answer.assert_awaited_once()
    text, kwargs = message.answer.call_args.args, message.answer.call_args.kwargs
    assert "Привет" in text[0]
    # Explicitly removes the reply-keyboard menu (in case a user still has
    # the old one showing from before it was removed) rather than just
    # omitting reply_markup, which would leave an existing menu in place.
    assert isinstance(kwargs["reply_markup"], ReplyKeyboardRemove)
