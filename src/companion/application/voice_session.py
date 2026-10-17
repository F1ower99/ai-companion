from __future__ import annotations

from threading import RLock

from companion.application.cancellation import CancellationFlag
from companion.domain.errors import ValidationError
from companion.domain.voice import (
    AudioChunk, VoiceErrorCode, VoiceOperationError, VoiceState, VoiceStatus, VoiceTranscript,
)
from companion.ports.voice import AudioCaptureSource, STTProvider, TTSProvider


class VoiceSession:
    """Blocking local voice operations; callers own worker scheduling.

    No hardware is queried by construction. Cancellation invalidates late
    results immediately; another capture waits until prior processing releases
    its buffer. Provider calls do not hold the state lock.
    """

    def __init__(
        self, capture: AudioCaptureSource | None = None,
        stt: STTProvider | None = None, tts: TTSProvider | None = None,
    ) -> None:
        for provider in (stt, tts):
            if provider is not None and getattr(provider, 'local_only', None) is not True:
                raise ValidationError('Voice providers must explicitly run locally.')
        self._capture, self._stt, self._tts = capture, stt, tts
        self._lock = RLock()
        self._closed = False
        self._generation = 0
        self._capture_working = False
        self._capture_cleaning = 0
        self._capture_running = False
        self._capture_token: CancellationFlag | None = None
        self._speech_token: CancellationFlag | None = None
        self._status = VoiceStatus(self._rest_state())

    @property
    def can_capture(self) -> bool:
        return not self._closed and self._capture is not None and self._stt is not None

    @property
    def can_speak(self) -> bool:
        return not self._closed and self._tts is not None

    @property
    def status(self) -> VoiceStatus:
        with self._lock:
            return self._status

    def _rest_state(self) -> VoiceState:
        return VoiceState.IDLE if self.can_capture or self.can_speak else VoiceState.UNAVAILABLE

    def _busy(self) -> VoiceStatus:
        return VoiceStatus(self._status.state, VoiceErrorCode.BUSY)

    @staticmethod
    def _discard_capture(capture: AudioCaptureSource) -> None:
        try:
            capture.cancel()
        except Exception:
            # Never leak a device exception or mask the primary safe error.
            pass

    def start_push_to_talk(self) -> VoiceStatus:
        with self._lock:
            if not self.can_capture:
                return VoiceStatus(VoiceState.UNAVAILABLE, VoiceErrorCode.NOT_CONFIGURED)
            if self._capture_working or self._capture_running or self._capture_cleaning:
                return self._busy()
            speaking = self._speech_token is not None
        if speaking:
            stopped = self.interrupt_output()
            if stopped.error_code is VoiceErrorCode.SPEECH_FAILED:
                return stopped
        with self._lock:
            if not self.can_capture:
                return VoiceStatus(VoiceState.UNAVAILABLE, VoiceErrorCode.NOT_CONFIGURED)
            if self._capture_working or self._capture_running or self._capture_cleaning:
                return self._busy()
            self._generation += 1
            generation = self._generation
            self._capture_token = CancellationFlag()
            self._capture_working = True
            self._status = VoiceStatus(VoiceState.LISTENING)
        try:
            self._capture.start()
        except Exception as error:
            self._discard_capture(self._capture)
            code = error.code if isinstance(error, VoiceOperationError) else VoiceErrorCode.CAPTURE_FAILED
            with self._lock:
                if generation == self._generation:
                    self._status = VoiceStatus(VoiceState.ERROR, code)
        else:
            with self._lock:
                stale = generation != self._generation
                self._capture_running = not stale
            if stale:
                self._discard_capture(self._capture)
        finally:
            with self._lock:
                self._capture_working = False
        return self.status

    def stop_capture(self) -> VoiceTranscript | None:
        with self._lock:
            if self._capture_working or not self._capture_running:
                return None
            generation, token = self._generation, self._capture_token
            self._capture_working = True
            self._status = VoiceStatus(VoiceState.TRANSCRIBING)
        audio = None
        phase_error = VoiceErrorCode.CAPTURE_FAILED
        try:
            audio = self._capture.stop()
            with self._lock:
                self._capture_running = False
            if not isinstance(audio, AudioChunk):
                raise ValidationError('Capture must return bounded PCM.')
            audio.__post_init__()  # Revalidate the transferred mutable buffer.
            if token.is_cancelled():
                return None
            phase_error = VoiceErrorCode.TRANSCRIPTION_FAILED
            transcript = self._stt.transcribe(audio, token)
            if not isinstance(transcript, VoiceTranscript):
                raise ValidationError('STT must return a validated transcript.')
            with self._lock:
                if generation != self._generation or token.is_cancelled():
                    return None
                self._status = VoiceStatus(VoiceState.TRANSCRIPT_READY)
                return transcript
        except Exception:
            if phase_error is VoiceErrorCode.CAPTURE_FAILED:
                self._discard_capture(self._capture)
            with self._lock:
                if generation == self._generation:
                    self._status = VoiceStatus(VoiceState.ERROR, phase_error)
            return None
        finally:
            if isinstance(audio, AudioChunk):
                audio.clear()
            with self._lock:
                self._capture_running = False
                self._capture_working = False
                if generation == self._generation:
                    self._capture_token = None

    def cancel_capture(self) -> VoiceStatus:
        with self._lock:
            active = self._capture_running or self._capture_working
            if not active:
                return self._status
            self._generation += 1
            if self._capture_token:
                self._capture_token.cancel()
            self._capture_running = False
            self._capture_cleaning += 1
            self._status = VoiceStatus(self._rest_state())
        try:
            self._discard_capture(self._capture)
        finally:
            with self._lock:
                self._capture_cleaning -= 1
        return self.status

    def speak(self, text: str) -> VoiceStatus:
        with self._lock:
            if not self.can_speak:
                return VoiceStatus(VoiceState.UNAVAILABLE, VoiceErrorCode.NOT_CONFIGURED)
            if self._capture_working or self._capture_running or self._capture_cleaning or self._speech_token:
                return self._busy()
            try:
                text = VoiceTranscript(text).text
            except ValidationError:
                return VoiceStatus(VoiceState.ERROR, VoiceErrorCode.SPEECH_FAILED)
            self._generation += 1
            generation = self._generation
            token = self._speech_token = CancellationFlag()
            self._status = VoiceStatus(VoiceState.SPEAKING)
        failed = False
        try:
            self._tts.speak(text, token)
        except Exception:
            failed = True
            try:
                self._tts.stop()
            except Exception:
                pass
        finally:
            with self._lock:
                if generation == self._generation:
                    self._speech_token = None
                    self._status = VoiceStatus(
                        VoiceState.ERROR if failed else self._rest_state(),
                        VoiceErrorCode.SPEECH_FAILED if failed else None,
                    )
        return self.status

    def interrupt_output(self) -> VoiceStatus:
        with self._lock:
            if self._speech_token is None:
                return self._status
            self._speech_token.cancel()
            self._speech_token = None
            self._generation += 1
            self._status = VoiceStatus(self._rest_state())
        try:
            self._tts.stop()
        except Exception:
            with self._lock:
                self._status = VoiceStatus(VoiceState.ERROR, VoiceErrorCode.SPEECH_FAILED)
        return self.status

    def close(self) -> None:
        with self._lock:
            self._closed = True
        self.cancel_capture()
        self.interrupt_output()
        with self._lock:
            self._status = VoiceStatus(VoiceState.UNAVAILABLE)
