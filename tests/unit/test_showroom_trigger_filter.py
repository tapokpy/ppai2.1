from types import SimpleNamespace

import pytest

from app.bot.filters import ShowroomTriggerFilter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "шоурум3",
        "шоурум3 запусти ночной режим",
        "showroom3 turn on the main facade",
    ],
)
async def test_matches_trigger_examples(text):
    message = SimpleNamespace(text=text)

    assert await ShowroomTriggerFilter()(message) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "какой у нас шоурум?",
        "обычное сообщение без триггера",
        "3 экрана в шоуруме",
    ],
)
async def test_does_not_match_plain_text(text):
    message = SimpleNamespace(text=text)

    assert await ShowroomTriggerFilter()(message) is False


@pytest.mark.asyncio
async def test_returns_false_when_text_is_none():
    message = SimpleNamespace(text=None)

    assert await ShowroomTriggerFilter()(message) is False
