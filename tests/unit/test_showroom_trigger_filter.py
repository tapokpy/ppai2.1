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
        "шоурум переключи на ролик 7",
        "шоурум поменяй ролик",
        # Voice messages always get a space before a spoken digit — never
        # glued the way someone would type "шоурум3".
        "шоурум 3 переключи ролик 6",
        # Real Whisper transcription of an actual voice message this
        # session dropped the unstressed "о" — confirmed live.
        "Шурум 3, переключи ролик 6.",
    ],
)
async def test_matches_trigger_examples(text):
    message = SimpleNamespace(text=text)

    assert await ShowroomTriggerFilter()(message) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "обычное сообщение без триггера",
        # A grammatical-case ending after the word boundary — not an
        # exact standalone "шоурум"/"шурум" token.
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
