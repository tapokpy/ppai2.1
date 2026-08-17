from aiogram import Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import func, select

from app.bot.filters import (
    WAREHOUSE_TRIGGER_PATTERN,
    ShouldRespondFilter,
    StockAddTriggerFilter,
    WarehouseTriggerFilter,
)
from app.bot.fsm.warehouse import StockAddStates
from app.bot.handlers.admin import ACCESS_DENIED_MESSAGE, is_admin
from app.core.config import settings
from app.core.database import async_session_maker
from app.models.sqlalchemy.user import User
from app.models.sqlalchemy.warehouse import Cell, Rack, Shelf, Warehouse
from app.models.sqlalchemy.stock_item import StockItem
from app.services.audit import log_action
from app.services.sheets_import import SheetsImportError, fetch_public_sheet_rows
from app.services.stock_import import (
    StockRow,
    StockTableError,
    normalize_item_type,
    parse_stock_table,
    upsert_stock_rows,
)

router = Router(name="warehouse")

NO_QUERY_REPLY = "Что искать? Например: «склад3 модуль P2.5»."
NOT_FOUND_REPLY = "Ничего похожего на складе не найдено."
IMPORT_SHEET_USAGE = "Использование: /import_sheet <ссылка или ID Google-таблицы>"
IMPORT_DONE_REPLY = "Импортировано позиций: {count}."
EMPTY_STOCK_REPLY = "На складе пока нет ни одной позиции."


def _format_stock_matches(rows: list[tuple[StockItem, Cell, Shelf, Rack, Warehouse]]) -> str:
    lines = []
    for stock_item, cell, shelf, rack, warehouse in rows:
        lines.append(
            f"«{stock_item.item_name}»: {stock_item.quantity} {stock_item.unit} — "
            f"{warehouse.name} / {rack.name} / {shelf.name} / {cell.name}"
        )
    return "\n".join(lines)


@router.message(WarehouseTriggerFilter(), ShouldRespondFilter())
async def handle_warehouse_lookup(message: Message) -> None:
    query = WAREHOUSE_TRIGGER_PATTERN.sub("", message.text).strip()
    if not query:
        await message.answer(NO_QUERY_REPLY)
        return

    async with async_session_maker() as session:
        result = await session.execute(
            select(StockItem, Cell, Shelf, Rack, Warehouse)
            .join(Cell, StockItem.cell_id == Cell.id)
            .join(Shelf, Cell.shelf_id == Shelf.id)
            .join(Rack, Shelf.rack_id == Rack.id)
            .join(Warehouse, Rack.warehouse_id == Warehouse.id)
            .where(StockItem.item_name.ilike(f"%{query}%"))
            .limit(20)
        )
        rows = result.all()

    if not rows:
        await message.answer(NOT_FOUND_REPLY)
        return

    await message.answer(_format_stock_matches(rows))


@router.message(StockAddTriggerFilter(), ShouldRespondFilter())
async def start_stock_add(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(ACCESS_DENIED_MESSAGE)
        return

    await state.set_state(StockAddStates.waiting_warehouse)
    await message.answer("Склад (название):")


@router.message(StateFilter(StockAddStates.waiting_warehouse))
async def stock_add_warehouse(message: Message, state: FSMContext) -> None:
    await state.update_data(warehouse=message.text.strip())
    await state.set_state(StockAddStates.waiting_rack)
    await message.answer("Стеллаж:")


@router.message(StateFilter(StockAddStates.waiting_rack))
async def stock_add_rack(message: Message, state: FSMContext) -> None:
    await state.update_data(rack=message.text.strip())
    await state.set_state(StockAddStates.waiting_shelf)
    await message.answer("Полка:")


@router.message(StateFilter(StockAddStates.waiting_shelf))
async def stock_add_shelf(message: Message, state: FSMContext) -> None:
    await state.update_data(shelf=message.text.strip())
    await state.set_state(StockAddStates.waiting_cell)
    await message.answer("Ячейка:")


@router.message(StateFilter(StockAddStates.waiting_cell))
async def stock_add_cell(message: Message, state: FSMContext) -> None:
    await state.update_data(cell=message.text.strip())
    await state.set_state(StockAddStates.waiting_item_name)
    await message.answer("Наименование позиции:")


@router.message(StateFilter(StockAddStates.waiting_item_name))
async def stock_add_item_name(message: Message, state: FSMContext) -> None:
    await state.update_data(item_name=message.text.strip())
    await state.set_state(StockAddStates.waiting_item_type)
    await message.answer("Тип (module/psu/card/other):")


@router.message(StateFilter(StockAddStates.waiting_item_type))
async def stock_add_item_type(message: Message, state: FSMContext) -> None:
    # Normalized (not stored verbatim) — bom_reconciliation.py only
    # matches on exactly these categories; anything else would silently
    # never reconcile against a calculated BOM.
    await state.update_data(item_type=normalize_item_type(message.text))
    await state.set_state(StockAddStates.waiting_quantity)
    await message.answer("Количество:")


@router.message(StateFilter(StockAddStates.waiting_quantity))
async def stock_add_quantity(message: Message, state: FSMContext, db_user: User) -> None:
    try:
        quantity = int(message.text.strip())
    except ValueError:
        await message.answer("Введите целое число, например: 24")
        return

    data = await state.get_data()
    await state.clear()

    row = StockRow(
        warehouse=data["warehouse"],
        rack=data["rack"],
        shelf=data["shelf"],
        cell=data["cell"],
        item_name=data["item_name"],
        quantity=quantity,
        item_type=data.get("item_type", "other"),
    )

    async with async_session_maker() as session:
        await upsert_stock_rows(session, [row])
        await log_action(
            session,
            user_id=db_user.id,
            command_text=f"остаток3: {row.item_name} x{quantity}",
            module="warehouse",
            decision="stock_added",
        )

    await message.answer(
        f"Записано: «{row.item_name}» — {quantity} шт, {row.warehouse}/{row.rack}/{row.shelf}/{row.cell}."
    )


@router.message(Command("stock_summary"))
async def handle_stock_summary(message: Message) -> None:
    async with async_session_maker() as session:
        result = await session.execute(
            select(StockItem.item_type, func.sum(StockItem.quantity)).group_by(StockItem.item_type)
        )
        rows = result.all()

    if not rows:
        await message.answer(EMPTY_STOCK_REPLY)
        return

    lines = [f"{item_type}: {total} шт" for item_type, total in rows]
    await message.answer("Сводка по складу:\n" + "\n".join(lines))


@router.message(Command("import_sheet"))
async def cmd_import_sheet(message: Message, command: CommandObject, db_user: User) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(ACCESS_DENIED_MESSAGE)
        return

    if not command.args:
        await message.answer(IMPORT_SHEET_USAGE)
        return

    try:
        raw_rows = await fetch_public_sheet_rows(command.args.strip(), settings.GOOGLE_SHEETS_API_KEY)
        stock_rows = parse_stock_table(raw_rows)
    except (SheetsImportError, StockTableError) as exc:
        await message.answer(str(exc))
        return

    async with async_session_maker() as session:
        count = await upsert_stock_rows(session, stock_rows)
        await log_action(
            session,
            user_id=db_user.id,
            command_text=f"/import_sheet {command.args.strip()}",
            module="warehouse",
            decision="sheet_imported",
            detail={"count": count},
        )

    await message.answer(IMPORT_DONE_REPLY.format(count=count))
