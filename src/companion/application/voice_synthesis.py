"""Single-use local synthesis; PCM stays owned until explicitly taken."""
from threading import Lock

from companion.application.cancellation import CancellationFlag
from companion.domain.voice import AudioChunk, VoiceErrorCode, VoiceOperationError


class SynthesisJob:
    def __init__(self, synthesizer, text):
        if getattr(synthesizer, 'local_only', None) is not True:
            raise VoiceOperationError(VoiceErrorCode.NOT_CONFIGURED)
        self._synthesizer, self._text = synthesizer, text
        self._token = CancellationFlag()
        self._lock = Lock()
        self._running = self._done = False
        self._audio = None

    def run(self):
        with self._lock:
            if self._running or self._done:
                return
            self._running = True
            text, self._text = self._text, None
        audio = None
        try:
            audio = self._synthesizer.synthesize(text, self._token)
            if not isinstance(audio, AudioChunk):
                raise ValueError('Invalid local synthesis result.')
            audio.__post_init__()
            with self._lock:
                if not self._token.is_cancelled():
                    self._audio, audio = audio, None
        except Exception:
            if not self._token.is_cancelled():
                raise VoiceOperationError(VoiceErrorCode.SPEECH_FAILED) from None
        finally:
            if isinstance(audio, AudioChunk):
                audio.clear()
            with self._lock:
                self._running, self._done = False, True

    def take_audio(self):
        with self._lock:
            if not self._done or self._token.is_cancelled():
                return None
            audio, self._audio = self._audio, None
            return audio

    def cancel(self):
        with self._lock:
            self._token.cancel()
            self._text = None
            audio, self._audio = self._audio, None
            if not self._running:
                self._done = True
        if audio is not None:
            audio.clear()
