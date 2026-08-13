import pytest
from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.sqlalchemy.stock_item import StockItem
from app.models.sqlalchemy.warehouse import Cell, Rack, Shelf, Warehouse
from app.services.stock_import import StockRow, upsert_stock_rows
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


@pytest.mark.asyncio
async def test_upsert_creates_full_hierarchy(clean_db):
    row = StockRow(
        warehouse="Основной", rack="А1", shelf="2", cell="3", item_name="Модуль P2.5", quantity=24
    )

    async with async_session_maker() as session:
        count = await upsert_stock_rows(session, [row])

    assert count == 1

    async with async_session_maker() as session:
        warehouses = (await session.execute(select(Warehouse))).scalars().all()
        racks = (await session.execute(select(Rack))).scalars().all()
        shelves = (await session.execute(select(Shelf))).scalars().all()
        cells = (await session.execute(select(Cell))).scalars().all()
        items = (await session.execute(select(StockItem))).scalars().all()

    assert [w.name for w in warehouses] == ["Основной"]
    assert [r.name for r in racks] == ["А1"]
    assert [s.name for s in shelves] == ["2"]
    assert [c.name for c in cells] == ["3"]
    assert items[0].item_name == "Модуль P2.5"
    assert items[0].quantity == 24


@pytest.mark.asyncio
async def test_upsert_reuses_existing_hierarchy_for_same_names(clean_db):
    row_a = StockRow(warehouse="Осн", rack="А1", shelf="1", cell="1", item_name="Модуль A", quantity=5)
    row_b = StockRow(warehouse="Осн", rack="А1", shelf="1", cell="2", item_name="Модуль B", quantity=7)

    async with async_session_maker() as session:
        await upsert_stock_rows(session, [row_a, row_b])

    async with async_session_maker() as session:
        warehouses = (await session.execute(select(Warehouse))).scalars().all()
        racks = (await session.execute(select(Rack))).scalars().all()
        shelves = (await session.execute(select(Shelf))).scalars().all()
        cells = (await session.execute(select(Cell))).scalars().all()

    # Same warehouse/rack/shelf reused across both rows — only the cell differs.
    assert len(warehouses) == 1
    assert len(racks) == 1
    assert len(shelves) == 1
    assert len(cells) == 2


@pytest.mark.asyncio
async def test_reimporting_same_item_overwrites_quantity_not_duplicates(clean_db):
    row = StockRow(warehouse="Осн", rack="А1", shelf="1", cell="1", item_name="Модуль", quantity=10)

    async with async_session_maker() as session:
        await upsert_stock_rows(session, [row])

    row_updated = StockRow(warehouse="Осн", rack="А1", shelf="1", cell="1", item_name="Модуль", quantity=15)
    async with async_session_maker() as session:
        await upsert_stock_rows(session, [row_updated])

    async with async_session_maker() as session:
        items = (await session.execute(select(StockItem))).scalars().all()

    assert len(items) == 1
    assert items[0].quantity == 15
