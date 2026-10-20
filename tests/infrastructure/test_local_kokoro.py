import json
from pathlib import Path
import struct
import subprocess

import pytest

from companion.application.cancellation import CancellationFlag
from companion.domain.errors import ValidationError
from companion.domain.voice import VoiceErrorCode, VoiceOperationError
from companion.infrastructure.local_kokoro import LocalKokoroSynthesizer
from companion.infrastructure.tts_process import run_tts_worker


FILES = ('model.int8.onnx', 'voices.bin', 'tokens.txt', 'lexicon-us-en.txt', 'lexicon-zh.txt',
         'date-zh.fst', 'number-zh.fst', 'phone-zh.fst', 'espeak-ng-data/phontab',
         'espeak-ng-data/phonindex', 'espeak-ng-data/phondata', 'espeak-ng-data/intonations')


@pytest.fixture
def bundle(tmp_path):
    for name in FILES:
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b'xx')
    return tmp_path


def wire(pcm=b'\x01\x02' * 4):
    return struct.pack('<4sII', b'ACV1', 24000, len(pcm)) + pcm


def assert_error(code, operation):
    with pytest.raises(VoiceOperationError) as error:
        operation()
    assert error.value.code is code
    assert str(error.value) == code.value


def test_lazy_local_synthesis_validates_and_transfers_bounded_pcm(bundle):
    calls = []
    synth = LocalKokoroSynthesizer(bundle, runner=lambda request, token: (calls.append(request), wire())[1])
    assert synth.local_only is True and calls == []
    audio = synth.synthesize('  今天\n先背单词。 ', CancellationFlag())
    assert calls == [{'model_directory': str(bundle.resolve()), 'text': '今天 先背单词。', 'speaker': 3, 'threads': 2}]
    assert (audio.sample_rate_hz, audio.channels, audio.sample_width_bytes) == (24000, 1, 2)
    assert audio.pcm == bytearray(b'\x01\x02' * 4)
    audio.clear()


@pytest.mark.parametrize('path', ['model', 'https://example/model', r'\\server\model'])
def test_remote_or_relative_model_never_launches_worker(path):
    def forbidden(*args): raise AssertionError('worker launched')
    assert_error(VoiceErrorCode.NOT_CONFIGURED,
                 lambda: LocalKokoroSynthesizer(Path(path), runner=forbidden).synthesize('你好', CancellationFlag()))


@pytest.mark.parametrize('name', FILES)
def test_incomplete_bundle_rejected_before_native_loading(bundle, name):
    (bundle / name).unlink()
    calls = []
    assert_error(VoiceErrorCode.NOT_CONFIGURED,
                 lambda: LocalKokoroSynthesizer(bundle, runner=lambda *args: calls.append(True)).synthesize('你好', CancellationFlag()))
    assert calls == []


@pytest.mark.parametrize('text', ['', '   ', '中' * 201, 'hello\x00world', 'hello\ud800', '!!!'])
def test_invalid_text_never_launches_worker(bundle, text):
    calls = []
    assert_error(VoiceErrorCode.SPEECH_FAILED,
                 lambda: LocalKokoroSynthesizer(bundle, runner=lambda *args: calls.append(True)).synthesize(text, CancellationFlag()))
    assert calls == []


@pytest.mark.parametrize('options', [{'speaker': True}, {'speaker': 103}, {'threads': 0}, {'threads': False}])
def test_invalid_native_options_rejected(options):
    with pytest.raises(ValidationError):
        LocalKokoroSynthesizer(Path('not-accessed'), **options)


@pytest.mark.parametrize('payload', [b'private native error', wire()[:-1], wire() + b'x',
                                    struct.pack('<4sII', b'ACV1', 16000, 2) + b'xx',
                                    struct.pack('<4sII', b'ACV1', 24000, 2880002), wire(b'')])
def test_bad_worker_protocol_is_never_exposed(bundle, payload):
    assert_error(VoiceErrorCode.SPEECH_FAILED,
                 lambda: LocalKokoroSynthesizer(bundle, runner=lambda *args: payload).synthesize('你好', CancellationFlag()))


def test_cancellation_before_and_after_worker_never_publishes_audio(bundle):
    token, calls = CancellationFlag(), []
    token.cancel()
    assert_error(VoiceErrorCode.CANCELLED,
                 lambda: LocalKokoroSynthesizer(bundle, runner=lambda *args: calls.append(True)).synthesize('你好', token))
    assert calls == []
    token = CancellationFlag()
    def runner(request, flag):
        flag.cancel()
        return wire()
    assert_error(VoiceErrorCode.CANCELLED,
                 lambda: LocalKokoroSynthesizer(bundle, runner=runner).synthesize('你好', token))


def test_overlap_fails_busy_and_does_not_interrupt_current_synthesis(bundle):
    def runner(request, token):
        assert_error(VoiceErrorCode.BUSY, lambda: synth.synthesize('另一段', token))
        return wire()
    synth = LocalKokoroSynthesizer(bundle, runner=runner)
    synth.synthesize('你好', CancellationFlag()).clear()


def test_bundle_tree_limit_rejected(bundle):
    for index in range(1001):
        (bundle / f'extra-{index}').write_bytes(b'x')
    assert_error(VoiceErrorCode.NOT_CONFIGURED,
                 lambda: LocalKokoroSynthesizer(bundle).validate_model_directory())


def test_auxiliary_resolving_outside_bundle_is_rejected(bundle, monkeypatch, tmp_path_factory):
    outside = tmp_path_factory.mktemp('outside') / 'phontab'
    outside.write_bytes(b'outside')
    original = Path.resolve
    def resolve(path, *args, **kwargs):
        if path == bundle / 'espeak-ng-data/phontab':
            return outside
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'resolve', resolve)
    assert_error(VoiceErrorCode.NOT_CONFIGURED,
                 lambda: LocalKokoroSynthesizer(bundle).validate_model_directory())


def test_excessive_bundle_size_and_native_path_delimiter_rejected(bundle, monkeypatch):
    import os
    original = Path.stat
    def stat(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path == bundle / 'model.int8.onnx':
            values = list(result)
            values[6] = 256 * 1024 * 1024 + 1
            return os.stat_result(values)
        return result
    monkeypatch.setattr(Path, 'stat', stat)
    assert_error(VoiceErrorCode.NOT_CONFIGURED,
                 lambda: LocalKokoroSynthesizer(bundle).validate_model_directory())
    assert_error(VoiceErrorCode.NOT_CONFIGURED,
                 lambda: LocalKokoroSynthesizer(bundle / 'comma,directory').validate_model_directory())


def test_native_exception_is_sanitized_and_next_call_can_retry(bundle):
    def fail(*args): raise RuntimeError('private source text and path')
    synth = LocalKokoroSynthesizer(bundle, runner=fail)
    assert_error(VoiceErrorCode.SPEECH_FAILED, lambda: synth.synthesize('你好', CancellationFlag()))
    synth._runner = lambda *args: wire()
    synth.synthesize('你好', CancellationFlag()).clear()


class Process:
    def __init__(self, token, *, cancel=False, timeout=False, output=None):
        import io
        self.token, self.cancel, self.timeout = token, cancel, timeout
        self.returncode = None
        self.killed = self.reaped = False
        self.inputs = []
        owner = self
        class Input(io.BytesIO):
            def close(inner):
                owner.inputs.append(inner.getvalue())
                super().close()
        class Output(io.BytesIO):
            def read(inner, size=-1):
                if owner.cancel:
                    owner.token.cancel()
                chunk = super().read(size)
                if not chunk and not (owner.cancel or owner.timeout):
                    owner.returncode = 0
                return chunk
            read1 = read
        self.stdin = Input()
        self.stdout = Output(wire() if output is None else output)
    def communicate(self, input=None, timeout=None):
        self.returncode = 0
        return self.stdout.read(), None
    def poll(self): return self.returncode
    def kill(self):
        self.killed = True
        self.returncode = -1
    def wait(self, timeout=None):
        self.reaped = True
        return self.returncode


@pytest.mark.parametrize('reason', ['cancel', 'timeout'])
def test_runner_kills_and_reaps_on_cancellation_or_timeout(reason):
    token = CancellationFlag()
    process = Process(token, cancel=reason == 'cancel', timeout=reason == 'timeout')
    ticks = iter([0, 0, 91])
    code = VoiceErrorCode.CANCELLED if reason == 'cancel' else VoiceErrorCode.SPEECH_FAILED
    assert_error(code, lambda: run_tts_worker({'text': 'private'}, token,
                 process_factory=lambda *args, **kwargs: process, monotonic=lambda: next(ticks)))
    assert process.killed and process.reaped


def test_runner_keeps_text_off_arguments_and_discards_stderr():
    token, calls = CancellationFlag(), []
    process = Process(token)
    def factory(args, **kwargs):
        calls.append((args, kwargs))
        return process
    assert run_tts_worker({'text': 'private sentence'}, token, process_factory=factory) == wire()
    args, options = calls[0]
    assert 'private sentence' not in ' '.join(args)
    assert options['stderr'] == subprocess.DEVNULL and options['shell'] is False
    assert json.loads(process.inputs[0])['text'] == 'private sentence'


def test_runner_caps_stdout_while_child_is_still_running():
    from companion.infrastructure.tts_assets import MAX_PCM_BYTES
    token = CancellationFlag()
    process = Process(token, timeout=True, output=b'x' * (MAX_PCM_BYTES + 13))
    assert_error(VoiceErrorCode.SPEECH_FAILED, lambda: run_tts_worker(
        {'text': 'public'}, token, process_factory=lambda *args, **kwargs: process))
    assert process.killed and process.reaped
