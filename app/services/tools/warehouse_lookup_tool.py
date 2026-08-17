from sqlalchemy import select

from app.core.database import async_session_maker
from app.core.tool_registry import ToolParameter, ToolResult, ToolSpec
from app.models.sqlalchemy.stock_item import StockItem
from app.models.sqlalchemy.warehouse import Cell, Rack, Shelf, Warehouse

_RESULT_LIMIT = 20


async def run(query: str) -> ToolResult:
    async with async_session_maker() as session:
        rows = (
            await session.execute(
                select(StockItem, Cell, Shelf, Rack, Warehouse)
                .join(Cell, StockItem.cell_id == Cell.id)
                .join(Shelf, Cell.shelf_id == Shelf.id)
                .join(Rack, Shelf.rack_id == Rack.id)
                .join(Warehouse, Rack.warehouse_id == Warehouse.id)
                .where(StockItem.item_name.ilike(f"%{query}%"))
                .limit(_RESULT_LIMIT)
            )
        ).all()

    if not rows:
        return ToolResult(text="Ничего похожего на складе не найдено.")

    lines = [
        f"«{stock_item.item_name}»: {stock_item.quantity} {stock_item.unit} — "
        f"{warehouse.name} / {rack.name} / {shelf.name} / {cell.name}"
        for stock_item, cell, shelf, rack, warehouse in rows
    ]
    return ToolResult(text="\n".join(lines))


TOOL_SPEC = ToolSpec(
    name="warehouse_lookup",
    description=(
        "Ищет позицию на складе по названию и показывает точное расположение "
        "(склад/стеллаж/полка/ячейка) и остаток — например «где у нас блок питания на 400вт», "
        "«сколько на складе модулей P2.5»."
    ),
    parameters=[ToolParameter(name="query", type="string", description="Название позиции для поиска")],
    handler=run,
)
