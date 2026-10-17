from typing import Protocol

from companion.domain.chat import CancellationToken
from companion.domain.voice import AudioChunk, VoiceTranscript


class AudioCaptureSource(Protocol):
    """No I/O at construction. Start gates permission; buffer at most 60 seconds.

    Stop releases the device and transfers buffer ownership. Cancel releases
    the device and discards any owned buffer, including after a failed start.
    """

    def start(self) -> None: ...
    def stop(self) -> AudioChunk: ...
    def cancel(self) -> None: ...


class STTProvider(Protocol):
    local_only: bool

    def transcribe(self, audio: AudioChunk, cancellation_token: CancellationToken) -> VoiceTranscript: ...


class TTSProvider(Protocol):
    local_only: bool

    def speak(self, text: str, cancellation_token: CancellationToken) -> None: ...
    def stop(self) -> None: ...
