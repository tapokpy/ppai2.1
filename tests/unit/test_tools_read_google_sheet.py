from unittest.mock import AsyncMock, patch

import pytest

from app.services.sheets_import import SheetsImportError
from app.services.tools import read_google_sheet_tool


@pytest.mark.asyncio
async def test_run_formats_rows():
    spec = read_google_sheet_tool.build_tool_spec(api_key="fake-key")
    rows = [["Наименование", "Количество"], ["Модуль P2.5", "10"]]

    with patch("app.services.tools.read_google_sheet_tool.fetch_public_sheet_rows", AsyncMock(return_value=rows)):
        result = await spec.handler(url="https://docs.google.com/spreadsheets/d/abc/edit")

    assert result.success is True
    assert "Наименование | Количество" in result.text
    assert "Модуль P2.5 | 10" in result.text


@pytest.mark.asyncio
async def test_run_truncates_many_rows():
    spec = read_google_sheet_tool.build_tool_spec(api_key="fake-key")
    rows = [["header"]] + [[str(i)] for i in range(100)]

    with patch("app.services.tools.read_google_sheet_tool.fetch_public_sheet_rows", AsyncMock(return_value=rows)):
        result = await spec.handler(url="abc")

    assert "показаны первые 50 строк из 101" in result.text


@pytest.mark.asyncio
async def test_run_reports_empty_table():
    spec = read_google_sheet_tool.build_tool_spec(api_key="fake-key")

    with patch("app.services.tools.read_google_sheet_tool.fetch_public_sheet_rows", AsyncMock(return_value=[])):
        result = await spec.handler(url="abc")

    assert "пустая" in result.text


@pytest.mark.asyncio
async def test_run_reports_error_instead_of_raising():
    spec = read_google_sheet_tool.build_tool_spec(api_key="fake-key")

    with patch(
        "app.services.tools.read_google_sheet_tool.fetch_public_sheet_rows",
        AsyncMock(side_effect=SheetsImportError("Google Sheets API вернул ошибку 403.")),
    ):
        result = await spec.handler(url="abc")

    assert result.success is False
    assert "403" in result.error


def test_tool_spec_has_url_parameter():
    spec = read_google_sheet_tool.build_tool_spec(api_key="fake-key")
    assert [p.name for p in spec.parameters] == ["url"]
