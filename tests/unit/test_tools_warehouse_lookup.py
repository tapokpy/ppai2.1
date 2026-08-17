from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.tools import warehouse_lookup_tool


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


def _match_row():
    stock_item = SimpleNamespace(item_name="Блок питания 400Вт", quantity=12, unit="шт")
    cell = SimpleNamespace(name="Я1")
    shelf = SimpleNamespace(name="П2")
    rack = SimpleNamespace(name="С3")
    warehouse = SimpleNamespace(name="Основной склад")
    return stock_item, cell, shelf, rack, warehouse


@pytest.mark.asyncio
async def test_run_formats_matches_with_full_location():
    with patch("app.services.tools.warehouse_lookup_tool.async_session_maker", lambda: _FakeSession([_match_row()])):
        result = await warehouse_lookup_tool.run(query="блок питания")

    assert "Блок питания 400Вт" in result.text
    assert "Основной склад / С3 / П2 / Я1" in result.text


@pytest.mark.asyncio
async def test_run_reports_no_matches():
    with patch("app.services.tools.warehouse_lookup_tool.async_session_maker", lambda: _FakeSession([])):
        result = await warehouse_lookup_tool.run(query="несуществующее")

    assert "не найдено" in result.text.lower()
