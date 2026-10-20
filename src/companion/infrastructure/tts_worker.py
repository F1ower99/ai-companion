"""Private source-runtime synthesis helper. Parent discards native stderr."""
import json
import struct
import sys

from companion.domain.voice import AudioChunk, VoiceErrorCode, VoiceOperationError
from companion.infrastructure.tts_assets import HEADER_MAGIC, MAX_PCM_BYTES, model_directory, speech_text


def _backend():
    import sherpa_onnx
    return sherpa_onnx


def synthesize_pcm(request, *, backend_loader=None):
    samples = scaled = pcm = None
    try:
        text = speech_text(request['text'])
        speaker, threads = request['speaker'], request['threads']
        if type(speaker) is not int or not 0 <= speaker <= 102 or type(threads) is not int or not 1 <= threads <= 8:
            raise ValueError('Invalid synthesis options.')
        root = model_directory(request['model_directory'])
        backend = (backend_loader or _backend)()
        import numpy as np
        kokoro = backend.OfflineTtsKokoroModelConfig(
            model=str(root / 'model.int8.onnx'), voices=str(root / 'voices.bin'),
            tokens=str(root / 'tokens.txt'), data_dir=str(root / 'espeak-ng-data'),
            lexicon=','.join(str(root / name) for name in ('lexicon-us-en.txt', 'lexicon-zh.txt')),
        )
        model = backend.OfflineTtsModelConfig(kokoro=kokoro, provider='cpu', debug=False, num_threads=threads)
        config = backend.OfflineTtsConfig(
            model=model, max_num_sentences=1,
            rule_fsts=','.join(str(root / name) for name in ('date-zh.fst', 'number-zh.fst', 'phone-zh.fst')),
        )
        if not config.validate():
            raise ValueError('Invalid native configuration.')
        engine = backend.OfflineTts(config)
        if engine.sample_rate != 24000 or engine.num_speakers != 103:
            raise ValueError('Unexpected model metadata.')
        count, overflow = 0, False
        def callback(chunk, progress):
            nonlocal count, overflow
            count += len(chunk)
            overflow = overflow or count > MAX_PCM_BYTES // 2
            return 0 if overflow else 1  # native source: zero stops, nonzero continues
        result = engine.generate(text, sid=speaker, speed=1.0, callback=callback)
        native = result.samples
        if overflow or result.sample_rate != 24000 or not 0 < len(native) <= MAX_PCM_BYTES // 2:
            raise ValueError('Invalid generated duration.')
        samples = np.array(native, dtype=np.float32, copy=True)
        if samples.ndim != 1 or not np.isfinite(samples).all() or not np.any(samples):
            raise ValueError('Invalid generated samples.')
        scaled = np.clip(samples * 32768.0, -32768, 32767).astype('<i2')
        pcm = bytearray(memoryview(scaled).cast('B'))
        audio = AudioChunk(pcm, 24000, 1, 2)
        pcm = None  # ownership transfers to caller
        return audio
    except Exception:
        raise VoiceOperationError(VoiceErrorCode.SPEECH_FAILED) from None
    finally:
        for owned in (samples, scaled):
            if owned is not None:
                owned.fill(0)
        if pcm is not None:
            pcm[:] = bytes(len(pcm))
            pcm.clear()


def main(source=None, sink=None, *, synthesizer=None):
    source = source if source is not None else sys.stdin.buffer
    sink = sink if sink is not None else sys.stdout.buffer
    audio = None
    try:
        payload = source.read(16385)
        if len(payload) > 16384:
            raise ValueError('Oversized request.')
        request = json.loads(payload)
        audio = (synthesizer or synthesize_pcm)(request)
        if not isinstance(audio, AudioChunk):
            raise ValueError('Invalid synthesis response.')
        audio.__post_init__()
        if (audio.sample_rate_hz, audio.channels, audio.sample_width_bytes) != (24000, 1, 2):
            raise ValueError('Invalid synthesis format.')
        sink.write(struct.pack('<4sII', HEADER_MAGIC, 24000, len(audio.pcm)))
        sink.write(audio.pcm)
        sink.flush()
        return 0
    except Exception:
        return 1
    finally:
        if isinstance(audio, AudioChunk):
            audio.clear()


if __name__ == '__main__':
    raise SystemExit(main())
