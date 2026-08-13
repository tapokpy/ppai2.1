import pytest

from app.services.stock_import import StockTableError, parse_stock_table


def test_parses_rows_by_header_name_regardless_of_order():
    rows = [
        ["Наименование", "Склад", "Количество", "Стеллаж", "Полка", "Ячейка"],
        ["Модуль P2.5", "Основной", "24", "А1", "2", "3"],
    ]
    parsed = parse_stock_table(rows)

    assert len(parsed) == 1
    assert parsed[0].item_name == "Модуль P2.5"
    assert parsed[0].warehouse == "Основной"
    assert parsed[0].rack == "А1"
    assert parsed[0].shelf == "2"
    assert parsed[0].cell == "3"
    assert parsed[0].quantity == 24
    assert parsed[0].item_type == "other"
    assert parsed[0].unit == "шт"


def test_optional_columns_default_when_absent():
    rows = [
        ["Склад", "Стеллаж", "Полка", "Ячейка", "Наименование", "Количество"],
        ["Осн", "А1", "1", "1", "БП NovaStar 400W", "5"],
    ]
    parsed = parse_stock_table(rows)

    assert parsed[0].item_type == "other"
    assert parsed[0].unit == "шт"


def test_skips_blank_rows():
    rows = [
        ["Склад", "Стеллаж", "Полка", "Ячейка", "Наименование", "Количество"],
        ["", "", "", "", "", ""],
        ["Осн", "А1", "1", "1", "Модуль", "10"],
    ]
    parsed = parse_stock_table(rows)

    assert len(parsed) == 1


def test_raises_on_missing_required_columns():
    rows = [["Наименование", "Количество"], ["Модуль", "1"]]
    with pytest.raises(StockTableError, match="не хватает колонок"):
        parse_stock_table(rows)


def test_raises_on_empty_table():
    with pytest.raises(StockTableError, match="пуста"):
        parse_stock_table([])


def test_raises_on_non_numeric_quantity():
    rows = [
        ["Склад", "Стеллаж", "Полка", "Ячейка", "Наименование", "Количество"],
        ["Осн", "А1", "1", "1", "Модуль", "много"],
    ]
    with pytest.raises(StockTableError, match="Некорректное количество"):
        parse_stock_table(rows)


def test_accepts_decimal_comma_quantity():
    rows = [
        ["Склад", "Стеллаж", "Полка", "Ячейка", "Наименование", "Количество"],
        ["Осн", "А1", "1", "1", "Кабель, м", "10,0"],
    ]
    parsed = parse_stock_table(rows)
    assert parsed[0].quantity == 10
