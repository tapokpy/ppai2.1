import re

import httpx

_DOC_URL_ID_PATTERN = re.compile(r"/d/([a-zA-Z0-9_-]+)")
_BARE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

# Plain-text export endpoint works for any PUBLICLY shared doc ("anyone
# with the link can view") via a bare HTTP GET — no API key, no OAuth, no
# Google Cloud project/API to enable. Mirrors sheets_import.py's
# "no credential file" approach, but even lighter since the Docs API
# itself isn't involved at all.
DOC_EXPORT_URL = "https://docs.google.com/document/d/{doc_id}/export"


class DocsImportError(Exception):
    pass


def extract_document_id(url_or_id: str) -> str:
    """Accepts either a full Google Docs URL or a bare document id."""
    url_or_id = url_or_id.strip()
    match = _DOC_URL_ID_PATTERN.search(url_or_id)
    if match:
        return match.group(1)
    if _BARE_ID_PATTERN.match(url_or_id):
        return url_or_id
    raise DocsImportError("Не удалось распознать ссылку/ID Google-документа.")


async def fetch_public_doc_text(url_or_id: str) -> str:
    document_id = extract_document_id(url_or_id)
    url = DOC_EXPORT_URL.format(doc_id=document_id)

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        try:
            response = await client.get(url, params={"format": "txt"})
        except httpx.HTTPError as exc:
            raise DocsImportError(f"Не удалось обратиться к Google Docs: {exc}") from exc

    # A private doc redirects to an HTML login/permission page (status 200,
    # but not the plain-text export) rather than a clean 4xx — so a
    # non-text content-type is the actual signal of "not public", not just
    # the status code.
    content_type = response.headers.get("content-type", "")
    if response.status_code != 200 or "text/plain" not in content_type:
        raise DocsImportError(
            "Не удалось прочитать документ — он должен быть открыт по ссылке "
            "('Anyone with the link can view')."
        )

    return response.text
