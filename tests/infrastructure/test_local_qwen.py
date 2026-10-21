import hashlib
import struct

import pytest

from companion.application.cancellation import CancellationFlag
from companion.domain.voice import VoiceErrorCode, VoiceOperationError
from companion.infrastructure import qwen_assets
from companion.infrastructure.local_qwen import LocalQwenSynthesizer


@pytest.fixture
def paths(tmp_path, monkeypatch):
    model = tmp_path / 'model'; model.mkdir()
    (model / 'config.json').write_bytes(b'{}')
    monkeypatch.setattr(qwen_assets, 'MODEL_ASSETS', (
        ('config.json', 2, 'sha256', hashlib.sha256(b'{}').hexdigest()),
    ))
    runtime = tmp_path / 'runtime'; scripts = runtime / 'Scripts'; scripts.mkdir(parents=True)
    (runtime / 'pyvenv.cfg').write_text('fixture')
    python = scripts / 'python.exe'; python.write_bytes(b'fixture')
    return model, python, tmp_path


def frame(pcm=b'\x01\x02' * 5):
    return struct.pack('<4sII', b'ACV1', 24000, len(pcm)) + pcm


def test_adapter_is_lazy_and_forwards_only_bounded_request(paths):
    calls = []
    def runner(request, token, **kwargs):
        calls.append((request, kwargs)); return frame()
    model, python, work = paths
    synth = LocalQwenSynthesizer(model, python, work, runner=runner)
    assert synth.local_only is True and calls == []
    synth.validate_model_directory(); assert calls == []
    audio = synth.synthesize('  你好\n慢慢来。 ', CancellationFlag())
    assert calls == [({'model_directory': str(model.resolve()), 'text': '你好 慢慢来。'},
                      {'runtime': python.resolve(), 'work_directory': work.resolve()})]
    assert audio.sample_rate_hz == 24000 and audio.pcm == bytearray(b'\x01\x02' * 5)
    audio.clear()


@pytest.mark.parametrize('output', [b'', b'bad', frame() + b'x', frame(b'x'),
                                     struct.pack('<4sII', b'BAD!', 24000, 2) + b'12'])
def test_malformed_worker_output_fails_without_echo(paths, output):
    with pytest.raises(VoiceOperationError) as error:
        LocalQwenSynthesizer(*paths, runner=lambda *a, **k: output).synthesize('你好', CancellationFlag())
    assert error.value.code is VoiceErrorCode.SPEECH_FAILED
    assert str(error.value) == 'speech_failed'


def test_cancel_before_and_after_worker_never_transfers_audio(paths):
    token = CancellationFlag(); calls = []
    def runner(*args, **kwargs):
        calls.append(1); token.cancel(); return frame()
    synth = LocalQwenSynthesizer(*paths, runner=runner)
    token.cancel()
    with pytest.raises(VoiceOperationError) as error: synth.synthesize('你好', token)
    assert error.value.code is VoiceErrorCode.CANCELLED and not calls
    token = CancellationFlag()
    with pytest.raises(VoiceOperationError) as error: synth.synthesize('你好', token)
    assert error.value.code is VoiceErrorCode.CANCELLED and calls == [1]


def test_reentrant_synthesis_is_busy(paths):
    nested = []
    def runner(*args, **kwargs):
        with pytest.raises(VoiceOperationError) as error:
            synth.synthesize('第二句', CancellationFlag())
        nested.append(error.value.code)
        return frame()
    synth = LocalQwenSynthesizer(*paths, runner=runner)
    synth.synthesize('你好', CancellationFlag()).clear()
    assert nested == [VoiceErrorCode.BUSY]


def test_bad_paths_and_work_inside_model_never_launch(paths):
    model, python, _ = paths
    calls = []
    synth = LocalQwenSynthesizer(model, python, model, runner=lambda *a, **k: calls.append(1))
    with pytest.raises(VoiceOperationError) as error: synth.validate_model_directory()
    assert error.value.code is VoiceErrorCode.NOT_CONFIGURED and not calls
