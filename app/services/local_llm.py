import re

import ollama
from loguru import logger

from app.core.tool_registry import try_parse_json

NEED_CLOUD_MARKER = "[NEED_CLOUD]"

# Rare (live-observed, not reliably reproducible) failure mode: instead of
# populating the native tool_calls field, the model sometimes leaks a tool
# call as plain text — e.g. "...garbage\n{\"name\": \"find_downloaded_file\",
# \"arguments\": {\"query\": \"Claude\"}}\n</tool_call>" — which would
# otherwise be shown to the user as raw JSON. Only matches flat (non-nested)
# argument objects, which covers every tool registered today.
_LEAKED_TOOL_CALL_PATTERN = re.compile(r'\{[^{}]*"name"\s*:\s*"[^"]+"[^{}]*"arguments"\s*:\s*\{[^{}]*\}[^{}]*\}')


def _extract_leaked_tool_call(content: str) -> dict | None:
    match = _LEAKED_TOOL_CALL_PATTERN.search(content)
    if not match:
        return None
    parsed = try_parse_json(match.group(0))
    if isinstance(parsed, dict) and isinstance(parsed.get("name"), str) and isinstance(parsed.get("arguments"), dict):
        return {"name": parsed["name"], "arguments": parsed["arguments"]}
    return None


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

    async def generate(
        self, prompt: str, system_prompt: str | None = None, history: list[dict] | None = None
    ) -> str:
        text, _usage = await self.generate_with_usage(prompt, system_prompt, history)
        return text

    async def generate_with_usage(
        self, prompt: str, system_prompt: str | None = None, history: list[dict] | None = None
    ) -> tuple[str, dict]:
        """Same as generate(), but also returns token-usage metrics (for the
        admin-only debug footer in Telegram) as
        {"prompt_tokens": int, "completion_tokens": int}. Usage is an empty
        dict if the call failed (NEED_CLOUD_MARKER returned instead).

        history is prior conversation turns as [{"role": "user"|"assistant",
        "content": str}, ...] in chronological order, inserted between the
        system prompt and the current prompt — see
        CascadeRouter._load_recent_history, the only real caller."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
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

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict],
        system_prompt: str | None = None,
        history: list[dict] | None = None,
    ) -> tuple[str, list[dict], dict]:
        """Same shape as generate_with_usage, but passes `tools` (Ollama/
        OpenAI-style function schemas — see ToolRegistry.to_ollama_schema)
        so the model can respond with a tool call instead of plain text.

        Returns (text, tool_calls, usage). tool_calls is a normalized list
        of {"name": str, "arguments": dict}, empty when the model answered
        normally instead of calling a tool. See CascadeRouter._process_query,
        the only real caller."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self._client.chat(
                model=self._model, messages=messages, tools=tools, options=self._options
            )
        except Exception as exc:
            logger.warning(f"Local LLM tool-calling call failed, escalating to cloud: {exc}")
            return NEED_CLOUD_MARKER, [], {}

        usage = {
            "prompt_tokens": response.get("prompt_eval_count"),
            "completion_tokens": response.get("eval_count"),
        }
        message = response["message"]
        tool_calls = [
            {"name": call["function"]["name"], "arguments": dict(call["function"]["arguments"])}
            for call in (message.get("tool_calls") or [])
        ]
        content = message.get("content") or ""

        if not tool_calls and content:
            leaked = _extract_leaked_tool_call(content)
            if leaked:
                logger.warning(f"Recovered a tool call leaked as plain text: {leaked['name']}")
                return "", [leaked], usage

        return content, tool_calls, usage
