import ollama
from loguru import logger

NEED_CLOUD_MARKER = "[NEED_CLOUD]"


class LocalLLMClient:
    def __init__(self, base_url: str, model: str):
        self._client = ollama.AsyncClient(host=base_url)
        self._model = model

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self._client.chat(model=self._model, messages=messages)
        except Exception as exc:
            logger.warning(f"Local LLM call failed, escalating to cloud: {exc}")
            return NEED_CLOUD_MARKER

        return response["message"]["content"]

    @staticmethod
    def needs_cloud(response_text: str) -> bool:
        return NEED_CLOUD_MARKER in response_text
