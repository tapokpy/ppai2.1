import anthropic


class CloudLLMClient:
    def __init__(self, api_key: str, model: str):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def generate(self, prompt: str, context: str | None = None) -> str:
        user_content = f"Context:\n{context}\n\nQuestion:\n{prompt}" if context else prompt

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            messages=[{"role": "user", "content": user_content}],
        )

        return "".join(block.text for block in response.content if block.type == "text")
