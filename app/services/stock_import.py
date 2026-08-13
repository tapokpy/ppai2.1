from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sqlalchemy.warehouse import Cell, Rack, Shelf, Warehouse
from app.models.sqlalchemy.stock_item import StockItem

# Case-insensitive header aliases -> canonical field name. Shared by both
# the Excel/CSV upload path (documents.py) and the Google Sheets import
# path (sheets_import.py) so a warehouse admin can prepare one table
# format regardless of which way they get it into the bot.
_HEADER_ALIASES = {
    "склад": "warehouse",
    "warehouse": "warehouse",
    "стеллаж": "rack",
    "rack": "rack",
    "полка": "shelf",
    "shelf": "shelf",
    "ячейка": "cell",
    "cell": "cell",
    "наименование": "item_name",
    "название": "item_name",
    "item_name": "item_name",
    "тип": "item_type",
    "type": "item_type",
    "количество": "quantity",
    "кол-во": "quantity",
    "quantity": "quantity",
    "ед": "unit",
    "единица": "unit",
    "unit": "unit",
}
_REQUIRED_FIELDS = ("warehouse", "rack", "shelf", "cell", "item_name", "quantity")


class StockTableError(ValueError):
    pass


@dataclass
class StockRow:
    warehouse: str
    rack: str
    shelf: str
    cell: str
    item_name: str
    quantity: int
    item_type: str = "other"
    unit: str = "шт"


def parse_stock_table(rows: list[list[str]]) -> list[StockRow]:
    """rows[0] is the header row. Column order doesn't matter — matched by
    name via _HEADER_ALIASES — so an admin's existing spreadsheet layout
    doesn't need to be rearranged to import it."""
    if not rows:
        raise StockTableError("Таблица пуста.")

    header = [str(cell or "").strip().lower() for cell in rows[0]]
    field_by_index: dict[int, str] = {}
    for i, raw_header in enumerate(header):
        field = _HEADER_ALIASES.get(raw_header)
        if field:
            field_by_index[i] = field

    missing = [f for f in _REQUIRED_FIELDS if f not in field_by_index.values()]
    if missing:
        raise StockTableError(
            f"В таблице не хватает колонок: {', '.join(missing)}. "
            f"Ожидаются: Склад, Стеллаж, Полка, Ячейка, Наименование, Количество (Тип и Ед — опционально)."
        )

    parsed: list[StockRow] = []
    for row in rows[1:]:
        if not any(str(cell or "").strip() for cell in row):
            continue

        values: dict[str, str] = {}
        for i, value in enumerate(row):
            field = field_by_index.get(i)
            if field:
                values[field] = str(value or "").strip()

        if not values.get("item_name"):
            continue

        try:
            quantity = int(float(values.get("quantity", "0").replace(",", ".")))
        except ValueError:
            raise StockTableError(f"Некорректное количество у позиции «{values.get('item_name')}».") from None

        parsed.append(
            StockRow(
                warehouse=values.get("warehouse", ""),
                rack=values.get("rack", ""),
                shelf=values.get("shelf", ""),
                cell=values.get("cell", ""),
                item_name=values["item_name"],
                quantity=quantity,
                item_type=values.get("item_type") or "other",
                unit=values.get("unit") or "шт",
            )
        )

    return parsed


async def _get_or_create_warehouse(session: AsyncSession, name: str) -> Warehouse:
    result = await session.execute(select(Warehouse).where(Warehouse.name == name))
    obj = result.scalar_one_or_none()
    if obj is None:
        obj = Warehouse(name=name)
        session.add(obj)
        await session.flush()
    return obj


async def _get_or_create_rack(session: AsyncSession, warehouse_id: int, name: str) -> Rack:
    result = await session.execute(select(Rack).where(Rack.warehouse_id == warehouse_id, Rack.name == name))
    obj = result.scalar_one_or_none()
    if obj is None:
        obj = Rack(warehouse_id=warehouse_id, name=name)
        session.add(obj)
        await session.flush()
    return obj


async def _get_or_create_shelf(session: AsyncSession, rack_id: int, name: str) -> Shelf:
    result = await session.execute(select(Shelf).where(Shelf.rack_id == rack_id, Shelf.name == name))
    obj = result.scalar_one_or_none()
    if obj is None:
        obj = Shelf(rack_id=rack_id, name=name)
        session.add(obj)
        await session.flush()
    return obj


async def _get_or_create_cell(session: AsyncSession, shelf_id: int, name: str) -> Cell:
    result = await session.execute(select(Cell).where(Cell.shelf_id == shelf_id, Cell.name == name))
    obj = result.scalar_one_or_none()
    if obj is None:
        obj = Cell(shelf_id=shelf_id, name=name)
        session.add(obj)
        await session.flush()
    return obj


async def upsert_stock_rows(session: AsyncSession, rows: list[StockRow]) -> int:
    """Each import row SETS the quantity for its (cell, item_name) pair —
    it's a snapshot of current stock, not an incremental delta. Repeating
    the same import twice is therefore idempotent, matching how an admin
    would actually re-upload a refreshed inventory sheet."""
    count = 0
    for row in rows:
        warehouse = await _get_or_create_warehouse(session, row.warehouse)
        rack = await _get_or_create_rack(session, warehouse.id, row.rack)
        shelf = await _get_or_create_shelf(session, rack.id, row.shelf)
        cell = await _get_or_create_cell(session, shelf.id, row.cell)

        result = await session.execute(
            select(StockItem).where(StockItem.cell_id == cell.id, StockItem.item_name == row.item_name)
        )
        stock_item = result.scalar_one_or_none()
        if stock_item is None:
            session.add(
                StockItem(
                    cell_id=cell.id,
                    item_name=row.item_name,
                    item_type=row.item_type,
                    quantity=row.quantity,
                    unit=row.unit,
                )
            )
        else:
            stock_item.quantity = row.quantity
            stock_item.item_type = row.item_type
            stock_item.unit = row.unit

        count += 1

    await session.commit()
    return count
