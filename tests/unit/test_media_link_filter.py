from types import SimpleNamespace

import pytest

from app.bot.filters import MediaLinkFilter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "https://www.youtube.com/watch?v=abc123",
        "  http://example.com/video.mp4  ",
        "https://vimeo.com/123456789",
    ],
)
async def test_matches_bare_link(text):
    message = SimpleNamespace(text=text)

    assert await MediaLinkFilter()(message) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "смотри вот это https://example.com/video что думаешь?",
        "обычное сообщение без ссылки",
        "ftp://example.com/file",
    ],
)
async def test_does_not_match_link_with_extra_text(text):
    message = SimpleNamespace(text=text)

    assert await MediaLinkFilter()(message) is False


@pytest.mark.asyncio
async def test_returns_false_when_text_is_none():
    message = SimpleNamespace(text=None)

    assert await MediaLinkFilter()(message) is False
