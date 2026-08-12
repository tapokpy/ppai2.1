import ollama
from loguru import logger

NEED_CLOUD_MARKER = "[NEED_CLOUD]"


class LocalLLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        temperature: float = 0.35,
        top_p: float = 0.85,
        top_k: int = 40,
        repeat_penalty: float = 1.15,
        num_predict: int = 512,
    ):
        """Generation options default to a lower-temperature, more
        deterministic configuration than Ollama's own defaults (temperature
        0.8, top_p 0.9) — a small local model is far more prone to
        confidently inventing specifics (prices, part numbers, dates) at
        higher sampling randomness, so we trade a bit of variety for
        consistency. All five are also exposed as Settings so they can be
        tuned via .env without a code change.
        """
        self._client = ollama.AsyncClient(host=base_url)
        self._model = model
        self._options = {
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "repeat_penalty": repeat_penalty,
            "num_predict": num_predict,
        }

    @property
    def model_name(self) -> str:
        return self._model

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        text, _usage = await self.generate_with_usage(prompt, system_prompt)
        return text

    async def generate_with_usage(self, prompt: str, system_prompt: str | None = None) -> tuple[str, dict]:
        """Same as generate(), but also returns token-usage metrics (for the
        admin-only debug footer in Telegram) as
        {"prompt_tokens": int, "completion_tokens": int}. Usage is an empty
        dict if the call failed (NEED_CLOUD_MARKER returned instead)."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self._client.chat(model=self._model, messages=messages, options=self._options)
        except Exception as exc:
            logger.warning(f"Local LLM call failed, escalating to cloud: {exc}")
            return NEED_CLOUD_MARKER, {}

        usage = {
            "prompt_tokens": response.get("prompt_eval_count"),
            "completion_tokens": response.get("eval_count"),
        }
        return response["message"]["content"], usage

    @staticmethod
    def needs_cloud(response_text: str) -> bool:
        return NEED_CLOUD_MARKER in response_text
