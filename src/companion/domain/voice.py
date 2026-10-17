from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from companion.domain.errors import ValidationError


class VoiceState(str, Enum):
    UNAVAILABLE = 'unavailable'
    IDLE = 'idle'
    LISTENING = 'listening'
    TRANSCRIBING = 'transcribing'
    TRANSCRIPT_READY = 'transcript_ready'
    SPEAKING = 'speaking'
    ERROR = 'error'


class VoiceErrorCode(str, Enum):
    NOT_CONFIGURED = 'not_configured'
    BUSY = 'busy'
    PERMISSION_DENIED = 'permission_denied'
    CAPTURE_FAILED = 'capture_failed'
    TRANSCRIPTION_FAILED = 'transcription_failed'
    SPEECH_FAILED = 'speech_failed'
    CANCELLED = 'cancelled'


class VoiceOperationError(RuntimeError):
    """Adapters report a stable code without exposing device/provider details."""

    def __init__(self, code: VoiceErrorCode) -> None:
        self.code = VoiceErrorCode(code)
        super().__init__(self.code.value)


@dataclass(frozen=True)
class VoiceStatus:
    state: VoiceState
    error_code: VoiceErrorCode | None = None


@dataclass(frozen=True)
class AudioChunk:
    """Ownership of the mutable PCM buffer transfers to the voice operation."""

    pcm: bytearray = field(repr=False, compare=False)
    sample_rate_hz: int
    channels: int
    sample_width_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.pcm, bytearray) or not self.pcm:
            raise ValidationError('Audio requires a non-empty mutable PCM buffer.')
        if any(type(value) is not int or value <= 0 for value in (
            self.sample_rate_hz, self.channels, self.sample_width_bytes
        )):
            raise ValidationError('PCM format values must be positive integers.')
        frame_size = self.channels * self.sample_width_bytes
        if len(self.pcm) % frame_size or len(self.pcm) > frame_size * self.sample_rate_hz * 60:
            raise ValidationError('PCM must contain complete frames and at most 60 seconds.')

    @property
    def duration_seconds(self) -> float:
        return len(self.pcm) / (self.sample_rate_hz * self.channels * self.sample_width_bytes)

    def clear(self) -> None:
        self.pcm[:] = bytes(len(self.pcm))
        try:
            self.pcm.clear()
        except BufferError:
            # A provider may still hold a view. Its contents are now zeroed;
            # Python cannot resize the buffer until that view is released.
            pass


@dataclass(frozen=True)
class VoiceTranscript:
    text: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not 1 <= len(self.text.strip()) <= 8000:
            raise ValidationError('Voice transcript must contain 1–8,000 characters.')
        object.__setattr__(self, 'text', self.text.strip())
