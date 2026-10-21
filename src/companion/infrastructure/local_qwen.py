"""Experimental explicit local Qwen adapter; external runtime, no playback."""
import struct
from threading import Lock

from companion.domain.voice import AudioChunk, VoiceErrorCode, VoiceOperationError
from companion.infrastructure.qwen_assets import qwen_model_directory, runtime_python, work_directory
from companion.infrastructure.tts_assets import HEADER_MAGIC, MAX_PCM_BYTES, speech_text


class LocalQwenSynthesizer:
    local_only = True

    def __init__(self, directory, runtime, work, *, runner=None):
        self._directory, self._runtime, self._work = directory, runtime, work
        self._runner = runner
        self._lock = Lock()

    def _configuration(self):
        model = qwen_model_directory(self._directory)
        runtime = runtime_python(self._runtime)
        work = work_directory(self._work)
        if work == model or work.is_relative_to(model):
            raise VoiceOperationError(VoiceErrorCode.NOT_CONFIGURED)
        return model, runtime, work

    def validate_model_directory(self):
        self._configuration()

    @staticmethod
    def _cancelled(token):
        if token.is_cancelled():
            raise VoiceOperationError(VoiceErrorCode.CANCELLED)

    def synthesize(self, text, cancellation_token):
        if not self._lock.acquire(blocking=False):
            raise VoiceOperationError(VoiceErrorCode.BUSY)
        audio, transferred = None, False
        try:
            self._cancelled(cancellation_token)
            text = speech_text(text)
            model, runtime, work = self._configuration()
            self._cancelled(cancellation_token)
            runner = self._runner
            if runner is None:
                from companion.infrastructure.qwen_process import run_qwen_worker
                runner = run_qwen_worker
            output = runner({'model_directory': str(model), 'text': text}, cancellation_token,
                            runtime=runtime, work_directory=work)
            self._cancelled(cancellation_token)
            if not isinstance(output, bytes) or len(output) < 12:
                raise ValueError('Invalid PCM frame.')
            magic, rate, size = struct.unpack_from('<4sII', output)
            if (magic != HEADER_MAGIC or rate != 24000 or not 0 < size <= MAX_PCM_BYTES
                    or size % 2 or len(output) != size + 12):
                raise ValueError('Invalid PCM frame.')
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
