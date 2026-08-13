import re

import httpx

_SHEET_URL_ID_PATTERN = re.compile(r"/d/([a-zA-Z0-9_-]+)")
_BARE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

SHEETS_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"


class SheetsImportError(Exception):
    pass


def extract_spreadsheet_id(url_or_id: str) -> str:
    """Accepts either a full Google Sheets URL or a bare spreadsheet id."""
    url_or_id = url_or_id.strip()
    match = _SHEET_URL_ID_PATTERN.search(url_or_id)
    if match:
        return match.group(1)
    if _BARE_ID_PATTERN.match(url_or_id):
        return url_or_id
    raise SheetsImportError("Не удалось распознать ссылку/ID Google-таблицы.")


async def fetch_public_sheet_rows(url_or_id: str, api_key: str, range_: str = "A:Z") -> list[list[str]]:
    """Reads a PUBLIC ("anyone with link can view") Google Sheet via API
    key — no OAuth/service account, so no credential file ever needs to be
    stored (per the plan's decision on Google Sheets auth). A private
    sheet returns 403/404 from the API; that's surfaced as-is via
    SheetsImportError rather than guessed at."""
    if not api_key:
        raise SheetsImportError(
            "Импорт из Google-таблиц не настроен — GOOGLE_SHEETS_API_KEY пуст."
        )

    spreadsheet_id = extract_spreadsheet_id(url_or_id)
    url = f"{SHEETS_API_BASE}/{spreadsheet_id}/values/{range_}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(url, params={"key": api_key})
        except httpx.HTTPError as exc:
            raise SheetsImportError(f"Не удалось обратиться к Google Sheets API: {exc}") from exc

    if response.status_code != 200:
        raise SheetsImportError(
            f"Google Sheets API вернул ошибку {response.status_code} — таблица должна быть "
            "открыта по ссылке ('Anyone with the link can view')."
        )

    data = response.json()
    return data.get("values", [])
