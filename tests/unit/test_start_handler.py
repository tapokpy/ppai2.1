from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers.start import cmd_start


@pytest.mark.asyncio
async def test_cmd_start_sends_welcome_with_main_menu():
    message = SimpleNamespace(answer=AsyncMock())

    await cmd_start(message)

    message.answer.assert_awaited_once()
    text, kwargs = message.answer.call_args.args, message.answer.call_args.kwargs
    assert "Привет" in text[0]
    assert kwargs["reply_markup"] is not None
