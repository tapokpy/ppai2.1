from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.filters import ShouldRespondFilter


def _bot(bot_id: int = 1, username: str = "ppai_bot"):
    bot = SimpleNamespace(id=bot_id)
    bot.get_me = AsyncMock(return_value=SimpleNamespace(username=username))
    return bot


@pytest.mark.asyncio
async def test_always_responds_in_private_chat():
    message = SimpleNamespace(chat=SimpleNamespace(type="private"), text="привет", reply_to_message=None)

    assert await ShouldRespondFilter()(message, _bot()) is True


@pytest.mark.asyncio
async def test_ignores_unrelated_group_message():
    message = SimpleNamespace(
        chat=SimpleNamespace(type="supergroup"), text="просто болтовня", reply_to_message=None
    )

    assert await ShouldRespondFilter()(message, _bot()) is False


@pytest.mark.asyncio
async def test_responds_when_mentioned_in_group():
    message = SimpleNamespace(
        chat=SimpleNamespace(type="group"), text="@ppai_bot посчитай модули", reply_to_message=None
    )

    assert await ShouldRespondFilter()(message, _bot()) is True


@pytest.mark.asyncio
async def test_responds_when_replying_to_bot_message():
    bot = _bot(bot_id=42)
    message = SimpleNamespace(
        chat=SimpleNamespace(type="group"),
        text="а как насчёт этого?",
        reply_to_message=SimpleNamespace(from_user=SimpleNamespace(id=42)),
    )

    assert await ShouldRespondFilter()(message, bot) is True


@pytest.mark.asyncio
async def test_ignores_reply_to_another_user_in_group():
    bot = _bot(bot_id=42)
    message = SimpleNamespace(
        chat=SimpleNamespace(type="group"),
        text="согласен",
        reply_to_message=SimpleNamespace(from_user=SimpleNamespace(id=999)),
    )

    assert await ShouldRespondFilter()(message, bot) is False
