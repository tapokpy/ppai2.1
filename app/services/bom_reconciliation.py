from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sqlalchemy.stock_item import StockItem
from app.models.sqlalchemy.warehouse import Cell, Rack, Shelf, Warehouse

# Maps a stock item_type to the LedBomResult fields (dict form, via
# dataclasses.asdict) whose sum is the total required quantity of that
# type — the base count plus its own ZIP spares line, per golden-standard
# BOM. Deliberately keyed by item_type category, not specific item_name:
# the BOM is computed from a formula (Ш×В+шаг+тип экрана), so it only
# knows "N modules", never a specific SKU like "Модуль P2.5" — matching by
# name would be fabricating precision the BOM doesn't actually have.
REQUIRED_FIELDS_BY_TYPE: dict[str, tuple[str, str]] = {
    "module": ("unit_count", "zip_modules"),
    "psu": ("psu_count", "zip_psu"),
    "card": ("card_count", "zip_cards"),
}


@dataclass
class StockDeficit:
    item_type: str
    required: int
    in_stock: int

    @property
    def shortage(self) -> int:
        return max(0, self.required - self.in_stock)


async def check_bom_against_stock(session: AsyncSession, bom_data: dict) -> list[StockDeficit]:
    """No reservation/batch tracking (per v6 spec) — in_stock is the raw
    sum across every cell in every warehouse, not scoped to this project."""
    deficits = []
    for item_type, fields in REQUIRED_FIELDS_BY_TYPE.items():
        required = sum(int(bom_data.get(field, 0) or 0) for field in fields)
        result = await session.execute(
            select(func.coalesce(func.sum(StockItem.quantity), 0)).where(StockItem.item_type == item_type)
        )
        in_stock = int(result.scalar_one())
        deficits.append(StockDeficit(item_type=item_type, required=required, in_stock=in_stock))
    return deficits


def format_deficits(deficits: list[StockDeficit]) -> str:
    lines = []
    for deficit in deficits:
        status = f"⚠️ не хватает {deficit.shortage}" if deficit.shortage > 0 else "✅ достаточно"
        lines.append(f"{deficit.item_type}: нужно {deficit.required}, на складе {deficit.in_stock} — {status}")
    return "\n".join(lines)


async def build_pick_list(session: AsyncSession, bom_data: dict) -> str:
    """Greedy allocation across cells, largest-quantity-first, within one
    item_type — doesn't distinguish between different item_name SKUs of
    the same type (the BOM has no SKU-level detail to match against, see
    REQUIRED_FIELDS_BY_TYPE's docstring)."""
    sections = []
    for item_type, fields in REQUIRED_FIELDS_BY_TYPE.items():
        required = sum(int(bom_data.get(field, 0) or 0) for field in fields)
        if required <= 0:
            continue

        result = await session.execute(
            select(StockItem, Cell, Shelf, Rack, Warehouse)
            .join(Cell, StockItem.cell_id == Cell.id)
            .join(Shelf, Cell.shelf_id == Shelf.id)
            .join(Rack, Shelf.rack_id == Rack.id)
            .join(Warehouse, Rack.warehouse_id == Warehouse.id)
            .where(StockItem.item_type == item_type, StockItem.quantity > 0)
            .order_by(StockItem.quantity.desc())
        )

        lines = [f"— {item_type} (нужно {required}):"]
        remaining = required
        for stock_item, cell, shelf, rack, warehouse in result.all():
            if remaining <= 0:
                break
            take = min(remaining, stock_item.quantity)
            lines.append(
                f"  {take} шт «{stock_item.item_name}» — {warehouse.name}/{rack.name}/{shelf.name}/{cell.name}"
            )
            remaining -= take

        if remaining > 0:
            lines.append(f"  ⚠️ не хватает {remaining} шт")

        sections.append("\n".join(lines))

    return "\n\n".join(sections) if sections else "В расчёте BOM нет позиций."
