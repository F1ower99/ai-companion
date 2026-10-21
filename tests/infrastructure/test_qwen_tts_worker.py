from contextlib import nullcontext
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import socket

import numpy as np
import pytest

from companion.domain.voice import VoiceOperationError
from companion.infrastructure import qwen_tts_worker as worker


class CUDA:
    def is_available(self): return True
    def is_bf16_supported(self): return True
    def mem_get_info(self): return (6 * 1024**3, 8 * 1024**3)
    def manual_seed_all(self, seed): pass


class Torch:
    cuda = CUDA()
    bfloat16 = 'bf16'
    def set_num_threads(self, count): assert count == 2
    def manual_seed(self, seed): assert seed == 1234
    def inference_mode(self): return nullcontext()


class Model:
    def __init__(self, wave=None, rate=24000):
        self.wave = np.array([-1., 0., 1.], dtype=np.float32) if wave is None else wave
        self.rate, self.calls = rate, []
    def get_supported_speakers(self): return ['serena']
    def generate_custom_voice(self, **kwargs):
        self.calls.append(kwargs); return [self.wave], self.rate


def prepare(monkeypatch, tmp_path, model=None, torch=None):
    model, torch = model or Model(), torch or Torch()
    calls = []
    monkeypatch.setattr(worker, 'verify_qwen_model', lambda path: tmp_path)
    class Loader:
        @staticmethod
        def from_pretrained(path, **options):
            calls.append((path, options)); return model
    return model, calls, lambda: (torch, Loader)


def request(): return {'text': '你好，慢慢来。', 'model_directory': 'public-fixture'}


def test_verified_local_bf16_loading_and_pcm_conversion(monkeypatch, tmp_path):
    model, calls, backend = prepare(monkeypatch, tmp_path)
    audio = worker.synthesize_pcm(request(), backend_loader=backend)
    assert calls == [(str(tmp_path), {
        'device_map': 'cuda:0', 'dtype': 'bf16', 'attn_implementation': 'sdpa',
        'trust_remote_code': False, 'local_files_only': True, 'use_safetensors': True,
    })]
    assert model.calls[0]['speaker'] == 'Serena' and model.calls[0]['language'] == 'Chinese'
    assert model.calls[0]['max_new_tokens'] == 720
    assert audio.pcm == bytearray(struct.pack('<3h', -32768, 0, 32767))
    assert not np.any(model.wave)
    audio.clear()


@pytest.mark.parametrize('wave', [np.array([]), np.array([np.nan]), np.zeros((2, 2)),
                                  np.zeros(4), np.ones(24000 * 60 + 1)])
def test_invalid_waveforms_never_escape(monkeypatch, tmp_path, wave):
    _, _, backend = prepare(monkeypatch, tmp_path, Model(wave))
    with pytest.raises(VoiceOperationError): worker.synthesize_pcm(request(), backend_loader=backend)


@pytest.mark.parametrize('failure', ['no_cuda', 'no_bf16', 'low_memory'])
def test_gpu_preflight_never_loads_model_or_falls_back(monkeypatch, tmp_path, failure):
    torch = Torch(); torch.cuda = CUDA()
    if failure == 'no_cuda': torch.cuda.is_available = lambda: False
    elif failure == 'no_bf16': torch.cuda.is_bf16_supported = lambda: False
    else: torch.cuda.mem_get_info = lambda: (1024**3, 8 * 1024**3)
    _, calls, backend = prepare(monkeypatch, tmp_path, torch=torch)
    with pytest.raises(VoiceOperationError): worker.synthesize_pcm(request(), backend_loader=backend)
    assert calls == []


def test_asset_verification_precedes_native_import_and_errors_are_sanitized(monkeypatch):
    def reject(path): raise ValueError('private asset path')
    monkeypatch.setattr(worker, 'verify_qwen_model', reject)
    def forbidden(): pytest.fail('Native import before verification', pytrace=False)
    with pytest.raises(VoiceOperationError) as error:
        worker.synthesize_pcm(request(), backend_loader=forbidden)
    assert str(error.value) == 'speech_failed'


def test_worker_protocol_prepares_before_synthesis_and_clears_audio():
    from companion.domain.voice import AudioChunk
    audio = AudioChunk(bytearray(b'12'), 24000, 1, 2)
    events, sink = [], io.BytesIO()
    def synth(value):
        assert events == ['offline']; return audio
    result = worker.main(io.BytesIO(json.dumps(request()).encode()), sink,
                         prepare=lambda: events.append('offline'), synthesizer=synth)
    assert result == 0 and sink.getvalue() == struct.pack('<4sII', b'ACV1', 24000, 2) + b'12'
    assert not audio.pcm


def test_cli_mutes_python_and_native_stdout_but_keeps_protocol():
    source = str(Path(__file__).resolve().parents[2] / 'src')
    environment = os.environ.copy(); environment['PYTHONPATH'] = source
    code = '''
import os
from companion.infrastructure.qwen_tts_worker import cli
def fake(*, sink):
    print('private python log')
    os.write(1, b'private native log')
    sink.write(b'public-binary-frame'); sink.flush()
    return 0
raise SystemExit(cli(fake))
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, env=environment,
                            timeout=10, check=False)
    assert result.returncode == 0 and result.stdout == b'public-binary-frame'


def test_offline_preparation_blocks_connections_and_creates_only_local_cache(monkeypatch, tmp_path):
    class Socket:
        def connect(self, address): pass
        def connect_ex(self, address): pass
    monkeypatch.setattr(socket, 'socket', Socket)
    for name in ('create_connection', 'getaddrinfo'):
        monkeypatch.setattr(socket, name, getattr(socket, name))
    monkeypatch.setenv('AI_COMPANION_QWEN_WORK_DIR', str(tmp_path))
    for name in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'HF_HUB_DISABLE_TELEMETRY', 'DO_NOT_TRACK'):
        monkeypatch.setenv(name, '0')
    worker.prepare_offline()
    for call in (lambda: Socket().connect(('example.test', 443)),
                 lambda: Socket().connect_ex(('example.test', 443)),
                 lambda: socket.create_connection(('example.test', 443)),
                 lambda: socket.getaddrinfo('example.test', 443)):
        with pytest.raises(RuntimeError): call()
    assert os.environ['HF_HUB_OFFLINE'] == os.environ['TRANSFORMERS_OFFLINE'] == '1'
    assert (tmp_path / 'cache/pycache').is_dir() and (tmp_path / 'tmp').is_dir()
