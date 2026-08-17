from app.core.tool_registry import ToolParameter, ToolResult, ToolSpec
from app.services.web_search import WebSearchError, search_web

_SNIPPET_PREVIEW_LEN = 200


def build_tool_spec(api_key: str) -> ToolSpec:
    async def run(query: str) -> ToolResult:
        try:
            results = await search_web(query, api_key)
        except WebSearchError as exc:
            return ToolResult(text=str(exc), success=False, error=str(exc))

        if not results:
            return ToolResult(text=f"Ничего не нашёл в интернете по «{query}».")

        lines = [f"🌐 Результаты поиска по «{query}»:"]
        lines.extend(
            f"— {r['title']}\n   {r['url']}\n   {r['snippet'][:_SNIPPET_PREVIEW_LEN]}" for r in results
        )
        return ToolResult(text="\n".join(lines))

    return ToolSpec(
        name="web_search",
        description=(
            "Ищет актуальную информацию в интернете. Используй ТОЛЬКО если пользователь явно просит "
            "поискать в интернете, узнать что-то новое/актуальное снаружи проекта («поищи в интернете X», "
            "«что нового у Y», «загугли Z»). НЕ используй как замену обычному ответу или вопросу по базе "
            "знаний проекта — только по явной просьбе поискать именно в интернете."
        ),
        parameters=[ToolParameter(name="query", type="string", description="Поисковый запрос")],
        handler=run,
    )
