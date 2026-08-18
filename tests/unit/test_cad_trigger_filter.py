from types import SimpleNamespace

import pytest

from app.bot.filters import CadTriggerFilter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "чертеж3",
        "чертёж3 рамка 1000х500",
        "cad3 plate 200x100",
        # Voice messages always get a space before a spoken digit.
        "чертеж 3 рамка 1000х500",
    ],
)
async def test_matches_trigger_examples(text):
    message = SimpleNamespace(text=text)

    assert await CadTriggerFilter()(message) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "какой у нас чертёж?",
        "обычное сообщение без триггера",
        "3 чертежа готово",
    ],
)
async def test_does_not_match_plain_text(text):
    message = SimpleNamespace(text=text)

    assert await CadTriggerFilter()(message) is False


@pytest.mark.asyncio
async def test_returns_false_when_text_is_none():
    message = SimpleNamespace(text=None)

    assert await CadTriggerFilter()(message) is False
