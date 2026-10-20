import struct
from pathlib import Path
import ctypes
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip('numpy', reason='Install the optional stt extra for waveform conversion tests.')

from companion.application.cancellation import CancellationFlag
from companion.domain.errors import ValidationError
from companion.domain.voice import AudioChunk, VoiceErrorCode, VoiceOperationError
from companion.infrastructure.local_whisper import LocalWhisperSTT


@pytest.fixture
def model_dir(tmp_path):
    for name in ['model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt']:
        (tmp_path / name).write_bytes(b'{}')
    return tmp_path


def audio():
    return AudioChunk(bytearray(struct.pack('<4h', -32768, -1, 0, 32767)), 16000, 1, 2)


class Model:
    def __init__(self):
        self.waveform = None
        self.options = None
        self.callback = None
        self.segments = [SimpleNamespace(text=' 你好'), SimpleNamespace(text='，世界。 ')]

    def transcribe(self, waveform, **kwargs):
        self.waveform, self.options = waveform, kwargs
        assert waveform.tolist() == [-1.0, -1 / 32768, 0, 32767 / 32768]
        if self.callback:
            return self.callback(), None
        return iter(self.segments), None


def provider(model_dir, model=None):
    model = model or Model()
    calls = []
    def factory(path, **options):
        calls.append((path, options))
        return model
    return LocalWhisperSTT(model_dir, model_factory=factory), model, calls


def test_lazy_cpu_local_only_load_and_pcm_cleanup(model_dir):
    stt, model, calls = provider(model_dir)
    assert calls == [] and stt.local_only is True
    assert stt.transcribe(audio(), CancellationFlag()).text == '你好，世界。'


    assert calls == [(str(model_dir.resolve()), {
        'device': 'cpu', 'compute_type': 'int8', 'cpu_threads': 4,
        'num_workers': 1, 'local_files_only': True,
    })]
    assert model.options['language'] == 'zh'
    assert model.options['task'] == 'transcribe'
    assert model.options['vad_filter'] is False
    assert model.options['condition_on_previous_text'] is False
    assert model.waveform.tolist() == [0, 0, 0, 0]
    stt.transcribe(audio(), CancellationFlag())
    assert len(calls) == 1


def test_model_preflight_never_loads_backend_and_missing_files_are_safe(model_dir):
    stt, _, calls = provider(model_dir)
    stt.validate_model_directory()
    assert calls == []
    (model_dir / 'tokenizer.json').unlink()
    with pytest.raises(VoiceOperationError) as failure:
        stt.validate_model_directory()
    assert failure.value.code == VoiceErrorCode.NOT_CONFIGURED
    assert calls == []


@pytest.mark.parametrize('filename', ['model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt'])
def test_incomplete_model_fails_before_backend_can_download(model_dir, filename):
    (model_dir / filename).unlink()
    stt, _, calls = provider(model_dir)
    with pytest.raises(VoiceOperationError) as failure:
        stt.transcribe(audio(), CancellationFlag())
    assert failure.value.code is VoiceErrorCode.NOT_CONFIGURED
    assert calls == []


def test_empty_tokenizer_is_rejected_before_model_load(model_dir):
    (model_dir / 'tokenizer.json').write_bytes(b'')
    stt, _, calls = provider(model_dir)
    with pytest.raises(VoiceOperationError):
        stt.transcribe(audio(), CancellationFlag())
    assert calls == []


@pytest.mark.parametrize('path', ['base', 'https://huggingface.co/model', r'\\server\models'])
def test_model_identifiers_and_remote_paths_never_reach_factory(path):
    stt, _, calls = provider(path)
    with pytest.raises(VoiceOperationError):
        stt.transcribe(audio(), CancellationFlag())
    assert calls == []


@pytest.mark.parametrize('rate,channels,width', [(8000, 1, 2), (16000, 2, 2), (16000, 1, 1)])
def test_unsupported_pcm_is_rejected_without_loading(model_dir, rate, channels, width):
    stt, _, calls = provider(model_dir)
    with pytest.raises(VoiceOperationError):
        stt.transcribe(AudioChunk(bytearray(8), rate, channels, width), CancellationFlag())
    assert calls == []


def test_silence_does_not_invoke_model(model_dir):
    stt, _, calls = provider(model_dir)
    with pytest.raises(VoiceOperationError):
        stt.transcribe(AudioChunk(bytearray(160), 16000, 1, 2), CancellationFlag())
    assert calls == []


@pytest.mark.parametrize('when', ['before', 'after_load', 'during_segments'])
def test_cancelled_transcription_never_publishes_partial_text(model_dir, when):
    token, model = CancellationFlag(), Model()
    if when == 'before':
        token.cancel()
    def factory(*args, **kwargs):
        if when == 'after_load':
            token.cancel()
        return model
    def segments():
        yield SimpleNamespace(text='partial')
        token.cancel()
        yield SimpleNamespace(text='late')
    if when == 'during_segments':
        model.callback = segments
    stt = LocalWhisperSTT(model_dir, model_factory=factory)
    with pytest.raises(VoiceOperationError) as failure:
        stt.transcribe(audio(), token)
    assert failure.value.code is VoiceErrorCode.CANCELLED
    if model.waveform is not None:
        assert model.waveform.tolist() == [0, 0, 0, 0]


@pytest.mark.parametrize('segments', [
    [], [SimpleNamespace(text=' ')], [SimpleNamespace(text=None)],
    [SimpleNamespace(text='x' * 8001)], [SimpleNamespace(text='x')] * 257,
])
def test_invalid_or_excessive_output_is_rejected_and_waveform_cleared(model_dir, segments):
    stt, model, _ = provider(model_dir)
    model.segments = segments
    with pytest.raises(VoiceOperationError):
        stt.transcribe(audio(), CancellationFlag())
    assert model.waveform.tolist() == [0, 0, 0, 0]


def test_generator_failure_is_sanitized_and_clears_audio(model_dir):
    stt, model, _ = provider(model_dir)
    def fail():
        yield SimpleNamespace(text='private text')
        raise RuntimeError('private model path and transcript')
    model.callback = fail
    with pytest.raises(VoiceOperationError) as failure:
        stt.transcribe(audio(), CancellationFlag())
    assert str(failure.value) == 'transcription_failed'
    assert model.waveform.tolist() == [0, 0, 0, 0]


def test_overlap_is_rejected_without_affecting_current_call(model_dir):
    stt, model, _ = provider(model_dir)
    def overlapping():
        with pytest.raises(VoiceOperationError):
            stt.transcribe(audio(), CancellationFlag())
        yield SimpleNamespace(text='outer result')
    model.callback = overlapping
    assert stt.transcribe(audio(), CancellationFlag()).text == 'outer result'


def test_cancel_during_preprocessing_never_enters_lazy_decoder(model_dir):
    stt, model, _ = provider(model_dir)
    token, entered = CancellationFlag(), []
    def preprocess():
        token.cancel()
        def decode():
            entered.append(True)
            yield SimpleNamespace(text='late')
        return decode()
    model.callback = preprocess
    with pytest.raises(VoiceOperationError):
        stt.transcribe(audio(), token)
    assert entered == []


def test_cancellation_is_checked_before_each_lazy_advance(model_dir):
    stt, model, _ = provider(model_dir)
    token, advances = CancellationFlag(), []
    class Segment:
        @property
        def text(self):
            token.cancel()
            return 'first'
    def decode():
        advances.append(1)
        yield Segment()
        advances.append(2)
        yield SimpleNamespace(text='second')
    model.callback = decode
    with pytest.raises(VoiceOperationError):
        stt.transcribe(audio(), token)
    assert advances == [1]


def test_resolved_unc_model_is_rejected_before_remote_inspection(model_dir, monkeypatch):
    stt, _, calls = provider(model_dir)
    network = Path(r'\\server\models')
    resolve, is_dir = Path.resolve, Path.is_dir
    inspected = []
    def mapped_resolve(self, **kwargs):
        return network if self == model_dir else resolve(self, **kwargs)
    def inspect_directory(self):
        if self == network:
            inspected.append(self)
            return False
        return is_dir(self)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'resolve', mapped_resolve)
        patch.setattr(Path, 'is_dir', inspect_directory)
        with pytest.raises(VoiceOperationError):
            stt.transcribe(audio(), CancellationFlag())
    assert inspected == [] and calls == []


def test_mapped_remote_drive_is_rejected_before_factory(model_dir, monkeypatch):
    stt, _, calls = provider(model_dir)
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **kw: SimpleNamespace(GetDriveTypeW=lambda root: 4), raising=False)
    with pytest.raises(VoiceOperationError):
        stt.transcribe(audio(), CancellationFlag())
    assert calls == []


@pytest.mark.parametrize('kwargs', [{'language': 'auto'}, {'cpu_threads': 0}, {'cpu_threads': True}, {'cpu_threads': 9}])
def test_invalid_configuration_is_rejected(model_dir, kwargs):
    with pytest.raises(ValidationError):
        LocalWhisperSTT(model_dir, **kwargs)
