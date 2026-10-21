"""Private experimental Qwen child. Native models stay outside the desktop."""
import os
import socket
import sys

from companion.domain.voice import AudioChunk, VoiceErrorCode, VoiceOperationError
from companion.infrastructure.qwen_assets import verify_qwen_model, work_directory
from companion.infrastructure.tts_assets import MAX_PCM_BYTES, speech_text
from companion.infrastructure.tts_worker import main as pcm_main

GENTLE_STYLE = '用自然、柔和、温暖的女声说话，像日常聊天一样放松。语气平稳，有自然的停顿，不要播音腔。'


def _deny_network(*args, **kwargs):
    raise RuntimeError('Networking is disabled in local speech.')


def prepare_offline():
    root = work_directory(os.environ.get('AI_COMPANION_QWEN_WORK_DIR', ''))
    for name in ('cache/pycache', 'cache/huggingface', 'cache/torch', 'cache/numba', 'cache/cuda', 'tmp'):
        (root / name).mkdir(parents=True, exist_ok=True)
    for name in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'HF_HUB_DISABLE_TELEMETRY', 'DO_NOT_TRACK'):
        os.environ[name] = '1'
    socket.socket.connect = _deny_network
    socket.socket.connect_ex = _deny_network
    socket.create_connection = _deny_network
    socket.getaddrinfo = _deny_network


def _backend():
    import torch
    from qwen_tts import Qwen3TTSModel
    return torch, Qwen3TTSModel


def synthesize_pcm(request, *, backend_loader=None):
    samples = scaled = pcm = waves = None
    try:
        if not isinstance(request, dict) or set(request) != {'text', 'model_directory'}:
            raise ValueError('Invalid request.')
        text = speech_text(request['text'])
        root = verify_qwen_model(request['model_directory'])
        torch, loader = (backend_loader or _backend)()
        import numpy as np
        if (not torch.cuda.is_available() or not torch.cuda.is_bf16_supported()
                or torch.cuda.mem_get_info()[0] < 5 * 1024**3):
            raise ValueError('Unsupported or insufficient GPU.')
        torch.set_num_threads(2)
        model = loader.from_pretrained(
            str(root), device_map='cuda:0', dtype=torch.bfloat16, attn_implementation='sdpa',
            trust_remote_code=False, local_files_only=True, use_safetensors=True,
        )
        if 'serena' not in model.get_supported_speakers():
            raise ValueError('Unexpected model speakers.')
        torch.manual_seed(1234)
        torch.cuda.manual_seed_all(1234)
        with torch.inference_mode():
            waves, rate = model.generate_custom_voice(
                text=text, language='Chinese', speaker='Serena', instruct=GENTLE_STYLE,
                max_new_tokens=720,
            )
        if not isinstance(waves, (list, tuple)) or len(waves) != 1 or rate != 24000:
            raise ValueError('Unexpected generated format.')
        samples = np.array(waves[0], dtype=np.float32, copy=True)
        if (samples.ndim != 1 or not 0 < len(samples) <= MAX_PCM_BYTES // 2
                or not np.isfinite(samples).all() or not np.any(samples)):
            raise ValueError('Invalid generated waveform.')
        scaled = np.clip(samples * 32768.0, -32768, 32767).astype('<i2')
        pcm = bytearray(memoryview(scaled).cast('B'))
        audio = AudioChunk(pcm, 24000, 1, 2)
        pcm = None
        return audio
    except Exception:
        raise VoiceOperationError(VoiceErrorCode.SPEECH_FAILED) from None
    finally:
        for owned in (samples, scaled):
            if owned is not None:
                owned.fill(0)
        if isinstance(waves, (list, tuple)):
            for wave in waves:
                if hasattr(wave, 'fill'):
                    wave.fill(0)
        if pcm is not None:
            pcm[:] = bytes(len(pcm))
            pcm.clear()


def main(source=None, sink=None, *, prepare=None, synthesizer=None):
    try:
        (prepare or prepare_offline)()
        return pcm_main(source, sink, synthesizer=synthesizer or synthesize_pcm)
    except Exception:
        return 1


def cli(main_function=main):
    # Duplicate the original protocol pipe before muting Python and native fd 1
    # for the entire child lifetime, including late native finalizers/loggers.
    with os.fdopen(os.dup(sys.stdout.fileno()), 'wb') as sink:
        with open(os.devnull, 'w') as muted:
            os.dup2(muted.fileno(), sys.stdout.fileno())
            sys.stdout = muted
            return main_function(sink=sink)


if __name__ == '__main__':
    raise SystemExit(cli())
