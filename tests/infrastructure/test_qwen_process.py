import json
import subprocess

import pytest

from companion.application.cancellation import CancellationFlag
from companion.domain.voice import VoiceErrorCode, VoiceOperationError
from companion.infrastructure import qwen_process
from test_local_qwen import paths
from test_local_kokoro import Process, wire


def test_selected_runtime_and_fixed_module_with_minimal_offline_environment(paths, monkeypatch):
    model, runtime, work = paths
    monkeypatch.setenv('PRIVATE_PROVIDER_TOKEN', 'private fixture')
    monkeypatch.setenv('PYTHONPATH', 'unrelated-private-path')
    token = CancellationFlag(); process = Process(token); calls = []
    def factory(command, **options):
        calls.append((command, options)); return process
    assert qwen_process.run_qwen_worker(
        {'text': 'private sentence', 'model_directory': str(model)}, token,
        runtime=runtime, work_directory=work, process_factory=factory,
    ) == wire()
    command, options = calls[0]
    assert command == [str(runtime.resolve()), '-s', '-m', 'companion.infrastructure.qwen_tts_worker']
    assert 'private sentence' not in ' '.join(command)
    assert options['shell'] is False and options['stderr'] == subprocess.DEVNULL
    env = options['env']
    assert 'PRIVATE_PROVIDER_TOKEN' not in env and 'unrelated-private-path' not in env['PYTHONPATH']
    assert env['HF_HUB_OFFLINE'] == env['TRANSFORMERS_OFFLINE'] == '1'
    assert env['PYTHONNOUSERSITE'] == '1'
    assert env['CUDA_CACHE_PATH'] == str(work.resolve() / 'cache' / 'cuda')
    assert env['TEMP'] == env['TMP'] == str(work.resolve() / 'tmp')
    assert json.loads(process.inputs[0])['text'] == 'private sentence'
    assert process.reaped


@pytest.mark.parametrize('reason', ['cancel', 'timeout', 'overflow'])
def test_qwen_owned_child_is_killed_and_reaped(paths, reason):
    model, runtime, work = paths
    token = CancellationFlag()
    from companion.infrastructure.tts_assets import MAX_PCM_BYTES
    process = Process(token, cancel=reason == 'cancel', timeout=reason != 'cancel',
                      output=b'x' * (MAX_PCM_BYTES + 13) if reason == 'overflow' else None)
    ticks = iter([0, 0, 121])
    with pytest.raises(VoiceOperationError) as error:
        qwen_process.run_qwen_worker({}, token, runtime=runtime, work_directory=work,
                                     process_factory=lambda *a, **k: process,
                                     monotonic=lambda: next(ticks))
    assert error.value.code is (VoiceErrorCode.CANCELLED if reason == 'cancel' else VoiceErrorCode.SPEECH_FAILED)
    assert process.killed and process.reaped


def test_cancelled_or_compiled_runtime_never_spawns(paths, monkeypatch):
    _, runtime, work = paths
    def forbidden(*a, **k): pytest.fail('Unexpected process launch', pytrace=False)
    monkeypatch.setattr(qwen_process, 'source_tts_supported', lambda: False)
    token = CancellationFlag(); token.cancel()
    for token, expected in [(token, VoiceErrorCode.CANCELLED),
                            (CancellationFlag(), VoiceErrorCode.NOT_CONFIGURED)]:
        with pytest.raises(VoiceOperationError) as error:
            qwen_process.run_qwen_worker({}, token, runtime=runtime, work_directory=work,
                                         process_factory=forbidden)
        assert error.value.code is expected
