from aiogram.fsm.state import State, StatesGroup


class StockAddStates(StatesGroup):
    """Ввод остатка: склад -> стеллаж -> полка -> ячейка -> наименование ->
    тип -> количество. Admin-only (enforced in the handler, not here)."""

    waiting_warehouse = State()
    waiting_rack = State()
    waiting_shelf = State()
    waiting_cell = State()
    waiting_item_name = State()
    waiting_item_type = State()
    waiting_quantity = State()


class ProjectCreateStates(StatesGroup):
    waiting_name = State()
    waiting_customer = State()
