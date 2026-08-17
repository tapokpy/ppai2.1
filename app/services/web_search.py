import httpx

TAVILY_API_URL = "https://api.tavily.com/search"
DEFAULT_MAX_RESULTS = 5


class WebSearchError(Exception):
    pass


async def search_web(query: str, api_key: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    if not api_key:
        raise WebSearchError("Веб-поиск не настроен — TAVILY_API_KEY пуст.")

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(
                TAVILY_API_URL,
                json={"api_key": api_key, "query": query, "max_results": max_results},
            )
        except httpx.HTTPError as exc:
            raise WebSearchError(f"Не удалось обратиться к Tavily API: {exc}") from exc

    if response.status_code != 200:
        raise WebSearchError(f"Tavily API вернул ошибку {response.status_code}.")

    data = response.json()
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
        for r in data.get("results", [])
    ]
