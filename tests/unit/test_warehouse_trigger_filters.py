from types import SimpleNamespace

import pytest

from app.bot.filters import StockAddTriggerFilter, WarehouseTriggerFilter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "склад3",
        "склад3 модуль P2.5",
        "warehouse3 module",
        # Voice messages always get a space before a spoken digit.
        "склад 3 модуль P2.5",
    ],
)
async def test_warehouse_trigger_matches(text):
    assert await WarehouseTriggerFilter()(SimpleNamespace(text=text)) is True


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["на складе пусто", "3 склада", None])
async def test_warehouse_trigger_does_not_match(text):
    assert await WarehouseTriggerFilter()(SimpleNamespace(text=text)) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["остаток3", "stock3", "остаток 3 модуль P2.5"])
async def test_stock_add_trigger_matches(text):
    assert await StockAddTriggerFilter()(SimpleNamespace(text=text)) is True


@pytest.mark.asyncio
async def test_stock_add_trigger_does_not_match_plain_text():
    assert await StockAddTriggerFilter()(SimpleNamespace(text="остаток на складе")) is False
