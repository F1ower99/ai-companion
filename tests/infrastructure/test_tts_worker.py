import io
import json
import struct
from types import SimpleNamespace

import pytest
np = pytest.importorskip('numpy')

from companion.infrastructure.tts_worker import synthesize_pcm, main
from companion.domain.voice import VoiceOperationError


def request():
    return {'model_directory': 'unused', 'text': '今天先背单词。', 'speaker': 3, 'threads': 2}


class Backend:
    def __init__(self, samples=None):
        self.calls = []
        self.samples = np.array([-1.0, 0, 1.0], dtype=np.float32) if samples is None else samples
        self.rate = 24000
        self.speakers = 103
    def OfflineTtsKokoroModelConfig(self, **kwargs): self.calls.append(('kokoro', kwargs)); return kwargs
    def OfflineTtsModelConfig(self, **kwargs): self.calls.append(('model', kwargs)); return kwargs
    def OfflineTtsConfig(self, **kwargs):
        self.calls.append(('config', kwargs))
        return SimpleNamespace(validate=lambda: True)
    def OfflineTts(self, config):
        owner = self
        class Engine:
            sample_rate = owner.rate
            num_speakers = owner.speakers
            def generate(self, text, **kwargs):
                owner.calls.append(('generate', text, kwargs))
                assert kwargs['callback'](np.zeros(2, dtype=np.float32), 0.5) == 1
                return SimpleNamespace(samples=owner.samples, sample_rate=owner.rate)
        return Engine()


def test_native_configuration_and_pcm_conversion_without_devices(monkeypatch, tmp_path):
    import companion.infrastructure.tts_worker as worker
    monkeypatch.setattr(worker, 'model_directory', lambda path: tmp_path)
    backend = Backend()
    audio = synthesize_pcm(request(), backend_loader=lambda: backend)
    assert audio.pcm == bytearray(struct.pack('<3h', -32768, 0, 32767))
    kokoro = backend.calls[0][1]
    assert kokoro['model'] == str(tmp_path / 'model.int8.onnx')
    assert kokoro['data_dir'] == str(tmp_path / 'espeak-ng-data')
    model = backend.calls[1][1]
    assert model['provider'] == 'cpu' and model['debug'] is False and model['num_threads'] == 2
    assert backend.calls[-1][2]['sid'] == 3 and backend.calls[-1][2]['speed'] == 1.0
    audio.clear()


@pytest.mark.parametrize('samples', [np.array([]), np.array([float('nan')]), np.array([[1.0]]),
                                   np.zeros(24000 * 60 + 1, dtype=np.float32), np.zeros(4)])
def test_invalid_waveform_never_returns_partial_pcm(monkeypatch, tmp_path, samples):
    import companion.infrastructure.tts_worker as worker
    monkeypatch.setattr(worker, 'model_directory', lambda path: tmp_path)
    with pytest.raises(VoiceOperationError):
        synthesize_pcm(request(), backend_loader=lambda: Backend(samples))


def test_callback_stops_at_duration_limit_and_oversized_result_is_rejected(monkeypatch, tmp_path):
    import companion.infrastructure.tts_worker as worker
    monkeypatch.setattr(worker, 'model_directory', lambda path: tmp_path)
    backend = Backend()
    synthesize_pcm(request(), backend_loader=lambda: backend).clear()
    callback = backend.calls[-1][2]['callback']
    assert callback(np.zeros(24000 * 60, dtype=np.float32), 1.0) == 0


def test_main_outputs_only_bounded_binary_and_clears_transferred_audio():
    from companion.domain.voice import AudioChunk
    audio = AudioChunk(bytearray(b'\x01\x02'), 24000, 1, 2)
    output = io.BytesIO()
    assert main(io.BytesIO(json.dumps(request()).encode()), output, synthesizer=lambda value: audio) == 0
    assert output.getvalue() == struct.pack('<4sII', b'ACV1', 24000, 2) + b'\x01\x02'
    assert not audio.pcm


def test_main_errors_never_print_text_or_raw_native_exception():
    def fail(value): raise RuntimeError('private source text and model path')
    output = io.BytesIO()
    assert main(io.BytesIO(json.dumps(request()).encode()), output, synthesizer=fail) == 1
    assert output.getvalue() == b''
