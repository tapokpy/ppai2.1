from types import SimpleNamespace

import pytest

from app.bot.filters import TodoTriggerFilter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "тодолист3",
        "добавь в тодолист3 доработку расчёта потребления",
        "план3",
        "запиши в план3 проверить блоки питания",
        "список задач3",
        "бэклог3",
        "backlog3 fix the power calculator",
        "todo3",
    ],
)
async def test_matches_trigger_examples(text):
    message = SimpleNamespace(text=text)

    assert await TodoTriggerFilter()(message) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "план на завтра — поехать на склад",
        "какой у нас план?",
        "обычное сообщение без триггера",
        "3 модуля нужно докупить",
    ],
)
async def test_does_not_match_plain_text(text):
    message = SimpleNamespace(text=text)

    assert await TodoTriggerFilter()(message) is False


@pytest.mark.asyncio
async def test_returns_false_when_text_is_none():
    message = SimpleNamespace(text=None)

    assert await TodoTriggerFilter()(message) is False
