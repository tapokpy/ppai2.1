import anthropic
import httpx


class CloudLLMClient:
    def __init__(self, api_key: str, model: str, proxy_url: str | None = None):
        """proxy_url routes Claude API traffic through an HTTP(S) proxy.

        Used in production to send Anthropic requests through a VPN
        sidecar (e.g. Gluetun) without affecting any other outbound
        traffic. Leave unset for direct connections (local development).
        """
        http_client = httpx.AsyncClient(proxy=proxy_url) if proxy_url else None
        self._client = anthropic.AsyncAnthropic(api_key=api_key, http_client=http_client)
        self._model = model

    async def generate(self, prompt: str, context: str | None = None) -> str:
        user_content = f"Context:\n{context}\n\nQuestion:\n{prompt}" if context else prompt

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            messages=[{"role": "user", "content": user_content}],
        )

        return "".join(block.text for block in response.content if block.type == "text")
