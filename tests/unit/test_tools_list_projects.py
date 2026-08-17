from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.tools import list_projects_tool


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
async def test_run_lists_projects_with_customer():
    project = SimpleNamespace(id=5, name="Вокзал", customer="РЖД")
    with patch("app.services.tools.list_projects_tool.async_session_maker", lambda: _FakeSession([project])):
        result = await list_projects_tool.run()

    assert result.text == "#5 «Вокзал» — РЖД"


@pytest.mark.asyncio
async def test_run_reports_no_projects():
    with patch("app.services.tools.list_projects_tool.async_session_maker", lambda: _FakeSession([])):
        result = await list_projects_tool.run()

    assert "нет" in result.text.lower()
