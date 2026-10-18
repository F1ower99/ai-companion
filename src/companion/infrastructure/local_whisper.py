"""Optional local CPU recognition. No model acquisition or audio I/O here."""
from __future__ import annotations

from pathlib import Path
from threading import Lock
import sys

from companion.domain.chat import CancellationToken
from companion.domain.errors import ValidationError
from companion.domain.voice import AudioChunk, VoiceErrorCode, VoiceOperationError, VoiceTranscript


class LocalWhisperSTT:
    local_only = True

    def __init__(self, model_directory: Path, language: str = 'zh', cpu_threads: int = 4, model_factory=None) -> None:
        if language not in ('zh', 'en') or type(cpu_threads) is not int or not 1 <= cpu_threads <= 8:
            raise ValidationError('Local STT requires zh/en and 1–8 CPU threads.')
        self._directory = model_directory
        self._language, self._threads = language, cpu_threads
        self._factory = model_factory
        self._model = None
        self._lock = Lock()

    def _validated_directory(self) -> Path:
        raw = str(self._directory)
        path = Path(raw)
        if '://' in raw or not path.is_absolute() or not self._is_local_location(path):
            raise VoiceOperationError(VoiceErrorCode.NOT_CONFIGURED)
        path = path.resolve(strict=True)
        if not self._is_local_location(path):
            raise VoiceOperationError(VoiceErrorCode.NOT_CONFIGURED)
        required = [path / name for name in ('model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt')]
        if not path.is_dir() or any(
            not file.is_file() or file.resolve().parent != path or file.stat().st_size <= 0 for file in required
        ) or sum(file.stat().st_size for file in required) > 1024 ** 3:
            raise VoiceOperationError(VoiceErrorCode.NOT_CONFIGURED)
        return path

    @staticmethod
    def _is_local_location(path: Path) -> bool:
        if str(path).startswith(('\\\\', '//')):
            return False
        if sys.platform != 'win32':
            return True
        try:
            import ctypes
            reader = ctypes.WinDLL('kernel32', use_last_error=True).GetDriveTypeW
            reader.argtypes = [ctypes.c_wchar_p]
            reader.restype = ctypes.c_uint
            # Reject remote, unknown, and nonexistent drive roots before
            # resolving/inspecting model files on a mapped network share.
            return reader(path.anchor) in (2, 3, 5, 6)
        except Exception:
            return False

    @staticmethod
    def _check_cancelled(token: CancellationToken) -> None:
        if token.is_cancelled():
            raise VoiceOperationError(VoiceErrorCode.CANCELLED)

    def transcribe(self, audio: AudioChunk, cancellation_token: CancellationToken) -> VoiceTranscript:
        if not self._lock.acquire(blocking=False):
            raise VoiceOperationError(VoiceErrorCode.BUSY)
        waveform, segments = None, None
        try:
            self._check_cancelled(cancellation_token)
            if not isinstance(audio, AudioChunk):
                raise VoiceOperationError(VoiceErrorCode.TRANSCRIPTION_FAILED)
            audio.__post_init__()
            if (audio.sample_rate_hz, audio.channels, audio.sample_width_bytes) != (16000, 1, 2) or not any(audio.pcm):
                raise VoiceOperationError(VoiceErrorCode.TRANSCRIPTION_FAILED)
            try:
                directory = self._validated_directory()
            except (OSError, ValueError, RuntimeError):
                raise VoiceOperationError(VoiceErrorCode.NOT_CONFIGURED) from None
            import numpy as np

            if self._model is None:
                factory = self._factory
                if factory is None:
                    from faster_whisper import WhisperModel
                    factory = WhisperModel
                self._check_cancelled(cancellation_token)
                self._model = factory(
                    str(directory), device='cpu', compute_type='int8',
                    cpu_threads=self._threads, num_workers=1, local_files_only=True,
                )
            self._check_cancelled(cancellation_token)
            waveform = np.frombuffer(audio.pcm, dtype='<i2').astype(np.float32)
            waveform /= 32768.0
            segments, _ = self._model.transcribe(
                waveform, language=self._language, task='transcribe', beam_size=1,
                temperature=0.0, condition_on_previous_text=False, vad_filter=False,
                without_timestamps=True, word_timestamps=False, log_progress=False,
            )
            self._check_cancelled(cancellation_token)
            texts, length, count = [], 0, 0
            iterator = iter(segments)
            while True:
                self._check_cancelled(cancellation_token)
                try:
                    segment = next(iterator)
                except StopIteration:
                    break
                self._check_cancelled(cancellation_token)
                count += 1
                text = segment.text
                if count > 256 or not isinstance(text, str):
                    raise VoiceOperationError(VoiceErrorCode.TRANSCRIPTION_FAILED)
                length += len(text)
                if length > 8000:
                    raise VoiceOperationError(VoiceErrorCode.TRANSCRIPTION_FAILED)
                texts.append(text)
            self._check_cancelled(cancellation_token)
            return VoiceTranscript(''.join(texts))
        except VoiceOperationError:
            raise
        except Exception:
            raise VoiceOperationError(VoiceErrorCode.TRANSCRIPTION_FAILED) from None
        finally:
            if waveform is not None:
                waveform.fill(0)
            try:
                close = getattr(segments, 'close', None)
                if close:
                    close()
            except Exception:
                pass
            self._lock.release()
