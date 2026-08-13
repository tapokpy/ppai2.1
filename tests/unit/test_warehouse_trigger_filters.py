from types import SimpleNamespace

import pytest

from app.bot.filters import ProjectTriggerFilter, StockAddTriggerFilter, WarehouseTriggerFilter


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["склад3", "склад3 модуль P2.5", "warehouse3 module"])
async def test_warehouse_trigger_matches(text):
    assert await WarehouseTriggerFilter()(SimpleNamespace(text=text)) is True


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["на складе пусто", "3 склада", None])
async def test_warehouse_trigger_does_not_match(text):
    assert await WarehouseTriggerFilter()(SimpleNamespace(text=text)) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["остаток3", "stock3"])
async def test_stock_add_trigger_matches(text):
    assert await StockAddTriggerFilter()(SimpleNamespace(text=text)) is True


@pytest.mark.asyncio
async def test_stock_add_trigger_does_not_match_plain_text():
    assert await StockAddTriggerFilter()(SimpleNamespace(text="остаток на складе")) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["проект3", "project3 Объект 1"])
async def test_project_trigger_matches(text):
    assert await ProjectTriggerFilter()(SimpleNamespace(text=text)) is True


@pytest.mark.asyncio
async def test_project_trigger_does_not_match_plain_text():
    assert await ProjectTriggerFilter()(SimpleNamespace(text="хороший проект")) is False
