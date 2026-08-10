import asyncio

from faster_whisper import WhisperModel


class Transcriber:
    """Lazily-loaded Faster-Whisper wrapper for transcribing voice messages.

    The model is loaded on first use (not at import time) and reused for
    subsequent calls, since loading it is expensive. Transcription itself is
    blocking CPU work, so it's offloaded to a thread to avoid stalling the
    bot's event loop.
    """

    def __init__(self, model_size: str, device: str, compute_type: str, language: str):
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._language = language
        self._model: WhisperModel | None = None

    def _get_model(self) -> WhisperModel:
        if self._model is None:
            self._model = WhisperModel(self._model_size, device=self._device, compute_type=self._compute_type)
        return self._model

    async def transcribe(self, audio_path: str) -> str:
        return await asyncio.to_thread(self._transcribe_sync, audio_path)

    def _transcribe_sync(self, audio_path: str) -> str:
        segments, _ = self._get_model().transcribe(audio_path, language=self._language)
        return " ".join(segment.text.strip() for segment in segments).strip()
