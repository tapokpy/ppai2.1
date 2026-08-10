from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.stt import Transcriber


def _make_transcriber() -> Transcriber:
    return Transcriber(model_size="tiny", device="cpu", compute_type="int8", language="ru")


@pytest.mark.asyncio
async def test_transcribe_joins_segment_text():
    transcriber = _make_transcriber()
    fake_model = MagicMock()
    fake_model.transcribe.return_value = (
        [SimpleNamespace(text=" Привет "), SimpleNamespace(text="мир! ")],
        SimpleNamespace(language="ru"),
    )

    with patch("app.services.stt.WhisperModel", return_value=fake_model) as whisper_model_cls:
        result = await transcriber.transcribe("data/temp/voice.ogg")

    assert result == "Привет мир!"
    whisper_model_cls.assert_called_once_with("tiny", device="cpu", compute_type="int8")
    fake_model.transcribe.assert_called_once_with("data/temp/voice.ogg", language="ru")


@pytest.mark.asyncio
async def test_transcribe_loads_model_lazily_once():
    transcriber = _make_transcriber()
    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([], SimpleNamespace(language="ru"))

    with patch("app.services.stt.WhisperModel", return_value=fake_model) as whisper_model_cls:
        await transcriber.transcribe("a.ogg")
        await transcriber.transcribe("b.ogg")

    whisper_model_cls.assert_called_once()


@pytest.mark.asyncio
async def test_transcribe_returns_empty_string_for_silent_audio():
    transcriber = _make_transcriber()
    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([], SimpleNamespace(language="ru"))

    with patch("app.services.stt.WhisperModel", return_value=fake_model):
        result = await transcriber.transcribe("silence.ogg")

    assert result == ""
