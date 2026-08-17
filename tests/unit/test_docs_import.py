from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.docs_import import DocsImportError, extract_document_id, fetch_public_doc_text


def test_extract_document_id_from_full_url():
    url = "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOp/edit"
    assert extract_document_id(url) == "1AbCdEfGhIjKlMnOp"


def test_extract_document_id_from_bare_id():
    assert extract_document_id("1AbCdEfGhIjKlMnOp") == "1AbCdEfGhIjKlMnOp"


def test_extract_document_id_raises_on_garbage():
    with pytest.raises(DocsImportError):
        extract_document_id("not a url or id!!")


@pytest.mark.asyncio
async def test_fetch_returns_text_on_success():
    mock_response = MagicMock(status_code=200, headers={"content-type": "text/plain; charset=UTF-8"})
    mock_response.text = "Привет, это документ."

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.docs_import.httpx.AsyncClient", return_value=mock_client):
        text = await fetch_public_doc_text("1AbCdEfGhIjKlMnOp")

    assert text == "Привет, это документ."


@pytest.mark.asyncio
async def test_fetch_raises_on_non_200():
    mock_response = MagicMock(status_code=403, headers={"content-type": "text/html"})
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.docs_import.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(DocsImportError, match="открыт по ссылке"):
            await fetch_public_doc_text("1AbCdEfGhIjKlMnOp")


@pytest.mark.asyncio
async def test_fetch_raises_when_private_doc_redirects_to_html():
    # A private doc still returns HTTP 200, but as an HTML login/permission
    # page rather than the plain-text export — status code alone can't
    # distinguish this from a real success.
    mock_response = MagicMock(status_code=200, headers={"content-type": "text/html; charset=UTF-8"})
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.docs_import.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(DocsImportError, match="открыт по ссылке"):
            await fetch_public_doc_text("1AbCdEfGhIjKlMnOp")


@pytest.mark.asyncio
async def test_fetch_wraps_network_errors():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.docs_import.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(DocsImportError):
            await fetch_public_doc_text("1AbCdEfGhIjKlMnOp")
