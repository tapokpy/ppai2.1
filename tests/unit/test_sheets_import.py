from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.sheets_import import SheetsImportError, extract_spreadsheet_id, fetch_public_sheet_rows


def test_extract_spreadsheet_id_from_full_url():
    url = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOp/edit#gid=0"
    assert extract_spreadsheet_id(url) == "1AbCdEfGhIjKlMnOp"


def test_extract_spreadsheet_id_from_bare_id():
    assert extract_spreadsheet_id("1AbCdEfGhIjKlMnOp") == "1AbCdEfGhIjKlMnOp"


def test_extract_spreadsheet_id_raises_on_garbage():
    with pytest.raises(SheetsImportError):
        extract_spreadsheet_id("not a url or id!!")


@pytest.mark.asyncio
async def test_fetch_raises_when_api_key_missing():
    with pytest.raises(SheetsImportError, match="не настроен"):
        await fetch_public_sheet_rows("1AbCdEfGhIjKlMnOp", api_key="")


@pytest.mark.asyncio
async def test_fetch_returns_values_on_success():
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {"values": [["a", "b"], ["1", "2"]]}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.sheets_import.httpx.AsyncClient", return_value=mock_client):
        rows = await fetch_public_sheet_rows("1AbCdEfGhIjKlMnOp", api_key="fake-key")

    assert rows == [["a", "b"], ["1", "2"]]


@pytest.mark.asyncio
async def test_fetch_raises_on_non_200():
    mock_response = MagicMock(status_code=403)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.sheets_import.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(SheetsImportError, match="403"):
            await fetch_public_sheet_rows("1AbCdEfGhIjKlMnOp", api_key="fake-key")


@pytest.mark.asyncio
async def test_fetch_wraps_network_errors():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.sheets_import.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(SheetsImportError):
            await fetch_public_sheet_rows("1AbCdEfGhIjKlMnOp", api_key="fake-key")
