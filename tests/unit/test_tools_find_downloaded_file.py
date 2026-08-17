from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.tools import find_downloaded_file_tool


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        m = MagicMock()
        m.all.return_value = self._rows
        return m


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


@pytest.mark.asyncio
async def test_run_returns_title_path_and_size():
    media = SimpleNamespace(title="Крутое видео", file_path="/app/data/media/abc.mp4", file_size_bytes=50_000_000)
    with patch("app.services.tools.find_downloaded_file_tool.async_session_maker", lambda: _FakeSession([media])):
        result = await find_downloaded_file_tool.run(query="крутое")

    assert "Крутое видео" in result.text
    assert "/app/data/media/abc.mp4" in result.text
    assert "МБ" in result.text


@pytest.mark.asyncio
async def test_run_reports_no_matches():
    with patch("app.services.tools.find_downloaded_file_tool.async_session_maker", lambda: _FakeSession([])):
        result = await find_downloaded_file_tool.run(query="несуществующее")

    assert "не нашёл" in result.text.lower()
