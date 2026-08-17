from app.core.tool_registry import ToolParameter, ToolResult, ToolSpec
from app.services.sheets_import import SheetsImportError, fetch_public_sheet_rows

# Same rationale as read_google_doc_tool._MAX_TEXT_LENGTH — bounds how much
# of a large sheet gets stuffed into the model's context in one tool call.
_MAX_ROWS = 50


def build_tool_spec(api_key: str) -> ToolSpec:
    async def run(url: str) -> ToolResult:
        try:
            rows = await fetch_public_sheet_rows(url, api_key)
        except SheetsImportError as exc:
            return ToolResult(text=str(exc), success=False, error=str(exc))

        if not rows:
            return ToolResult(text="Таблица пустая.")

        truncated = len(rows) > _MAX_ROWS
        shown_rows = rows[:_MAX_ROWS]
        lines = [" | ".join(str(cell) for cell in row) for row in shown_rows]
        text = "\n".join(lines)
        if truncated:
            text += f"\n\n[…показаны первые {_MAX_ROWS} строк из {len(rows)}]"

        return ToolResult(text=text)

    return ToolSpec(
        name="read_google_sheet",
        description=(
            "Читает содержимое публичной Google-таблицы по ссылке или ID (первый лист, столбцы A:Z). "
            "Таблица должна быть открыта по ссылке ('Anyone with the link can view'). Используй, когда "
            "пользователь просит прочитать/найти/пересказать что-то из конкретной Google-таблицы — "
            "НЕ для складских остатков (для них есть warehouse_lookup)."
        ),
        parameters=[ToolParameter(name="url", type="string", description="Ссылка на Google-таблицу или её ID")],
        handler=run,
    )
