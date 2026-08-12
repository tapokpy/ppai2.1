import anthropic
import httpx

# Approximate USD-per-token pricing for the default cloud model
# (claude-3-5-sonnet), used only for the admin-only debug footer in
# Telegram — not billing-accurate, just a rough order-of-magnitude
# indicator. Update if CLOUD_MODEL_NAME moves to a different pricing tier.
_PRICE_PER_INPUT_TOKEN_USD = 3.0 / 1_000_000
_PRICE_PER_OUTPUT_TOKEN_USD = 15.0 / 1_000_000


class CloudUnavailableError(Exception):
    """Raised when the Anthropic API can't be reached or rejects the request.

    Covers a missing/invalid API key, network failures (including a VPN
    proxy that's down), rate limits, and 5xx errors — anything callers
    should treat as "cloud escalation isn't available right now" rather
    than a bug.
    """


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

    @property
    def model_name(self) -> str:
        return self._model

    async def generate(self, prompt: str, context: str | None = None) -> str:
        text, _usage = await self.generate_with_usage(prompt, context)
        return text

    async def generate_with_usage(self, prompt: str, context: str | None = None) -> tuple[str, dict]:
        """Same as generate(), but also returns token-usage + an approximate
        cost estimate (for the admin-only debug footer in Telegram) as
        {"prompt_tokens": int, "completion_tokens": int, "estimated_cost_usd": float}."""
        user_content = f"Context:\n{context}\n\nQuestion:\n{prompt}" if context else prompt

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                messages=[{"role": "user", "content": user_content}],
            )
        except Exception as exc:
            # Catches anthropic.APIError (network/HTTP-level failures) *and*
            # the plain TypeError the SDK raises client-side, before any
            # request is sent, when api_key is empty/missing — that one
            # isn't an APIError subclass, so a narrower except here silently
            # let it crash the whole request instead of degrading gracefully.
            raise CloudUnavailableError(str(exc)) from exc

        text = "".join(block.text for block in response.content if block.type == "text")
        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "estimated_cost_usd": round(
                response.usage.input_tokens * _PRICE_PER_INPUT_TOKEN_USD
                + response.usage.output_tokens * _PRICE_PER_OUTPUT_TOKEN_USD,
                4,
            ),
        }
        return text, usage
