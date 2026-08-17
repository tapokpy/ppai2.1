from app.core.tool_registry import ToolParameter, ToolResult, ToolSpec
from app.services.docs_import import DocsImportError, fetch_public_doc_text

# Keeps a single tool result well within what the local model's context
# window can comfortably hold alongside the rest of the prompt (system
# prompt + RAG context + history) — a full doc can be many times this.
_MAX_TEXT_LENGTH = 6000


async def run(url: str) -> ToolResult:
    try:
        text = await fetch_public_doc_text(url)
    except DocsImportError as exc:
        return ToolResult(text=str(exc), success=False, error=str(exc))

    if not text.strip():
        return ToolResult(text="Документ пустой.")

    truncated = len(text) > _MAX_TEXT_LENGTH
    body = text[:_MAX_TEXT_LENGTH]
    if truncated:
        body += "\n\n[…текст обрезан, документ длиннее]"

    return ToolResult(text=body)


TOOL_SPEC = ToolSpec(
    name="read_google_doc",
    description=(
        "Читает текст публичного Google-документа по ссылке или ID. Документ должен быть "
        "открыт по ссылке ('Anyone with the link can view'), иначе доступ будет отклонён. "
        "Используй, когда пользователь просит прочитать/пересказать/найти что-то в конкретном "
        "Google Docs."
    ),
    parameters=[ToolParameter(name="url", type="string", description="Ссылка на Google-документ или его ID")],
    handler=run,
)
