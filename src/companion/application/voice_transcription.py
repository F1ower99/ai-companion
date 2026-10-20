"""Single-use ownership of captured PCM, independent of Qt and device lifetime."""
from __future__ import annotations

from threading import Lock

from companion.domain.voice import AudioChunk, VoiceTranscript


class TranscriptionJob:
    def __init__(self, audio: AudioChunk, operation, finished, cancellation_token):
        self._audio = audio
        self._operation = operation
        self._finished = finished
        self._token = cancellation_token
        self._lock = Lock()
        self._running = False
        self._done = False

    def run(self) -> VoiceTranscript | None:
        with self._lock:
            if self._done or self._running:
                return None
            self._running = True
            audio = self._audio
        try:
            result = self._operation(audio)
        finally:
            audio.clear()
            with self._lock:
                self._audio = None
                self._running = False
                self._done = True
            self._finished(self)
        return None if self._token.is_cancelled() else result

    def cancel(self) -> None:
        """Cancel even active work, but never mutate actively consumed PCM."""
        with self._lock:
            if self._done:
                return
            self._token.cancel()
            if self._running:
                return
            self._audio.clear()
            self._audio = None
            self._done = True
        self._finished(self)
