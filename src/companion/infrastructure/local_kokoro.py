"""Optional local text-to-PCM backend. It never plays sound."""
from pathlib import Path
from threading import Lock
import struct

from companion.domain.errors import ValidationError
from companion.domain.voice import AudioChunk, VoiceErrorCode, VoiceOperationError
from companion.infrastructure.tts_assets import HEADER_MAGIC, MAX_PCM_BYTES, model_directory, speech_text
from companion.infrastructure.tts_process import run_tts_worker


class LocalKokoroSynthesizer:
    local_only = True

    def __init__(self, directory: Path, speaker=3, threads=2, *, runner=None):
        if type(speaker) is not int or not 0 <= speaker <= 102 or type(threads) is not int or not 1 <= threads <= 8:
            raise ValidationError('Invalid local synthesis options.')
        self._directory, self._speaker, self._threads = directory, speaker, threads
        self._runner = runner or run_tts_worker
        self._lock = Lock()

    def validate_model_directory(self):
        model_directory(self._directory)

    @staticmethod
    def _cancelled(token):
        if token.is_cancelled():
            raise VoiceOperationError(VoiceErrorCode.CANCELLED)

    def synthesize(self, text, cancellation_token) -> AudioChunk:
        if not self._lock.acquire(blocking=False):
            raise VoiceOperationError(VoiceErrorCode.BUSY)
        audio, transferred = None, False
        try:
            self._cancelled(cancellation_token)
            text = speech_text(text)
            directory = model_directory(self._directory)
            self._cancelled(cancellation_token)
            output = self._runner({'model_directory': str(directory), 'text': text,
                                   'speaker': self._speaker, 'threads': self._threads}, cancellation_token)
            self._cancelled(cancellation_token)
            if not isinstance(output, bytes) or len(output) < 12:
                raise ValueError('Invalid PCM protocol.')
            magic, rate, size = struct.unpack_from('<4sII', output)
            if magic != HEADER_MAGIC or rate != 24000 or not 0 < size <= MAX_PCM_BYTES or size % 2 or len(output) != size + 12:
                raise ValueError('Invalid PCM protocol.')
            audio = AudioChunk(bytearray(memoryview(output)[12:]), 24000, 1, 2)
            self._cancelled(cancellation_token)
            transferred = True
            return audio
        except VoiceOperationError:
            raise
        except Exception:
            raise VoiceOperationError(VoiceErrorCode.SPEECH_FAILED) from None
        finally:
            if audio is not None and not transferred:
                audio.clear()
            self._lock.release()
