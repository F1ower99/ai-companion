import pytest

from companion.application.cancellation import CancellationFlag
from companion.domain.voice import VoiceErrorCode, VoiceOperationError
from companion.infrastructure import tts_process


@pytest.mark.parametrize('marker', ['nuitka', 'frozen'])
def test_compiled_runtime_never_spawns_a_source_python_worker(monkeypatch, marker):
    if marker == 'nuitka':
        monkeypatch.setattr(tts_process, '__compiled__', object(), raising=False)
    else:
        monkeypatch.setattr(tts_process.sys, 'frozen', True, raising=False)
    def forbidden(*args, **kwargs):
        pytest.fail('Compiled desktop executable must not be spawned as Python', pytrace=False)
    with pytest.raises(VoiceOperationError) as error:
        tts_process.run_tts_worker({}, CancellationFlag(), process_factory=forbidden)
    assert error.value.code == VoiceErrorCode.NOT_CONFIGURED


def test_cancellation_precedes_runtime_availability(monkeypatch):
    monkeypatch.setattr(tts_process.sys, 'frozen', True, raising=False)
    token = CancellationFlag()
    token.cancel()
    with pytest.raises(VoiceOperationError) as error:
        tts_process.run_tts_worker({}, token)
    assert error.value.code == VoiceErrorCode.CANCELLED
