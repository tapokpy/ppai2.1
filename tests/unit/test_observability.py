from unittest.mock import MagicMock, patch

from app.core.observability import NullTrace, get_tracer


def test_get_tracer_is_disabled_when_langfuse_keys_missing():
    with patch("app.core.observability.settings") as settings_mock:
        settings_mock.LANGFUSE_PUBLIC_KEY = ""
        settings_mock.LANGFUSE_SECRET_KEY = ""

        tracer = get_tracer()
        trace = tracer.trace_chat(user_id=1, prompt="hello")

    assert isinstance(trace, NullTrace)
    trace.update(output="anything")  # should not raise


def test_get_tracer_creates_langfuse_trace_when_configured():
    fake_langfuse_module = MagicMock()
    fake_client = MagicMock()
    fake_langfuse_module.Langfuse.return_value = fake_client
    fake_client.trace.return_value = "a-trace"

    with (
        patch("app.core.observability.settings") as settings_mock,
        patch.dict("sys.modules", {"langfuse": fake_langfuse_module}),
    ):
        settings_mock.LANGFUSE_PUBLIC_KEY = "pk"
        settings_mock.LANGFUSE_SECRET_KEY = "sk"
        settings_mock.LANGFUSE_HOST = "https://cloud.langfuse.com"

        tracer = get_tracer()
        trace = tracer.trace_chat(user_id=7, prompt="hello")

    fake_langfuse_module.Langfuse.assert_called_once_with(
        public_key="pk", secret_key="sk", host="https://cloud.langfuse.com"
    )
    fake_client.trace.assert_called_once_with(name="web_chat", user_id="7", input="hello")
    assert trace == "a-trace"
