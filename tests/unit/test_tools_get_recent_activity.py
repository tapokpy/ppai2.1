from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.tools import get_recent_activity_tool


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


def _row(command_text="/find X", module="cascade_router", decision="tool_call", status="success"):
    return SimpleNamespace(command_text=command_text, module=module, decision=decision, status=status)


@pytest.mark.asyncio
async def test_run_formats_recent_rows():
    with patch(
        "app.services.tools.get_recent_activity_tool.async_session_maker",
        lambda: _FakeSession([_row()]),
    ):
        result = await get_recent_activity_tool.run(user_id=1)

    assert "cascade_router/tool_call" in result.text
    assert "success" in result.text


@pytest.mark.asyncio
async def test_run_reports_no_activity():
    with patch("app.services.tools.get_recent_activity_tool.async_session_maker", lambda: _FakeSession([])):
        result = await get_recent_activity_tool.run(user_id=1)

    assert "не найдено" in result.text.lower() or "ничего" in result.text.lower()


@pytest.mark.asyncio
async def test_run_reports_no_matches_with_query():
    with patch("app.services.tools.get_recent_activity_tool.async_session_maker", lambda: _FakeSession([])):
        result = await get_recent_activity_tool.run(user_id=1, query="котики")

    assert "котики" in result.text


def test_tool_spec_query_parameter_is_optional():
    param = next(p for p in get_recent_activity_tool.TOOL_SPEC.parameters if p.name == "query")
    assert param.required is False


def test_tool_spec_needs_user_id():
    assert get_recent_activity_tool.TOOL_SPEC.needs_user_id is True
