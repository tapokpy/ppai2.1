from unittest.mock import AsyncMock, patch

import pytest

from app.services.docs_import import DocsImportError
from app.services.tools import read_google_doc_tool


@pytest.mark.asyncio
async def test_run_returns_doc_text():
    with patch(
        "app.services.tools.read_google_doc_tool.fetch_public_doc_text",
        AsyncMock(return_value="Содержимое документа."),
    ):
        result = await read_google_doc_tool.run(url="https://docs.google.com/document/d/abc/edit")

    assert result.success is True
    assert result.text == "Содержимое документа."


@pytest.mark.asyncio
async def test_run_truncates_long_text():
    long_text = "а" * 7000
    with patch(
        "app.services.tools.read_google_doc_tool.fetch_public_doc_text",
        AsyncMock(return_value=long_text),
    ):
        result = await read_google_doc_tool.run(url="abc")

    assert len(result.text) < len(long_text)
    assert "обрезан" in result.text


@pytest.mark.asyncio
async def test_run_reports_empty_document():
    with patch(
        "app.services.tools.read_google_doc_tool.fetch_public_doc_text",
        AsyncMock(return_value="   "),
    ):
        result = await read_google_doc_tool.run(url="abc")

    assert "пустой" in result.text


@pytest.mark.asyncio
async def test_run_reports_error_instead_of_raising():
    with patch(
        "app.services.tools.read_google_doc_tool.fetch_public_doc_text",
        AsyncMock(side_effect=DocsImportError("должен быть открыт по ссылке")),
    ):
        result = await read_google_doc_tool.run(url="abc")

    assert result.success is False
    assert "открыт по ссылке" in result.error


def test_tool_spec_has_url_parameter():
    assert [p.name for p in read_google_doc_tool.TOOL_SPEC.parameters] == ["url"]
