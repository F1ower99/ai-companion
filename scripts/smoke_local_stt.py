"""Explicit local WAV recognition check; never accesses a microphone."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from time import perf_counter
import wave

from companion.application.cancellation import CancellationFlag
from companion.domain.voice import AudioChunk, VoiceErrorCode, VoiceOperationError
from companion.infrastructure.local_whisper import LocalWhisperSTT


def read_pcm_wav(path: Path) -> AudioChunk:
    try:
        with wave.open(str(path), 'rb') as source:
            frames = source.getnframes()
            if (source.getframerate(), source.getnchannels(), source.getsampwidth(), source.getcomptype()) != (16000, 1, 2, 'NONE') or not 1 <= frames <= 960000:
                raise ValueError('Unsupported bounded WAV format.')
            pcm = bytearray(source.readframes(frames))
            if len(pcm) != frames * 2:
                pcm.clear()
                raise ValueError('Truncated WAV.')
        return AudioChunk(pcm, 16000, 1, 2)
    except Exception:
        raise VoiceOperationError(VoiceErrorCode.CAPTURE_FAILED) from None


def main(argv=None, provider_factory=LocalWhisperSTT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--wav', type=Path, required=True)
    parser.add_argument('--language', choices=['zh', 'en'], default='zh')
    parser.add_argument('--show-transcript', action='store_true', help='Explicitly print recognized text; use public fixtures only.')
    args = parser.parse_args(argv)
    audio = None
    try:
        audio = read_pcm_wav(args.wav)
        duration = audio.duration_seconds
        started = perf_counter()
        result = provider_factory(args.model_dir, language=args.language).transcribe(audio, CancellationFlag())
        elapsed = perf_counter() - started
        print(f'Local STT passed: {duration:.2f}s audio, {elapsed:.2f}s processing, {len(result.text)} characters.')
        if args.show_transcript:
            print(result.text)
        return 0
    except Exception as error:
        code = error.code.value if isinstance(error, VoiceOperationError) else VoiceErrorCode.TRANSCRIPTION_FAILED.value
        print(f'Local STT failed: {code}', file=sys.stderr)
        return 1
    finally:
        if audio is not None:
            audio.clear()


if __name__ == '__main__':
    raise SystemExit(main())
