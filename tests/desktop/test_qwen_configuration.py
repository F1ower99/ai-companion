import pytest

from companion.desktop import voice_configuration as config


def environment(tmp_path):
    return {'AI_COMPANION_TTS_ENGINE': 'qwen',
            'AI_COMPANION_QWEN_MODEL_DIR': str(tmp_path / 'model'),
            'AI_COMPANION_QWEN_PYTHON': str(tmp_path / 'runtime/Scripts/python.exe'),
            'AI_COMPANION_QWEN_WORK_DIR': str(tmp_path)}


def test_qwen_opt_in_does_not_import_or_probe_parent_model_dependencies(monkeypatch, tmp_path, qapp):
    calls, probes = [], []
    class Provider:
        def __init__(self, model, runtime, work): calls.append((model, runtime, work))
        def validate_model_directory(self): calls.append('preflight')
    class Playback:
        def __init__(self, parent): calls.append(('playback', parent))
    class Controller:
        def __init__(self, provider, playback, parent, **kwargs): self.preflight = kwargs['preflight']
    monkeypatch.setattr(config, 'LocalQwenSynthesizer', Provider)
    monkeypatch.setattr(config, 'QtAudioPlayback', Playback)
    monkeypatch.setattr(config, 'SpeechController', Controller)
    result, reason = config.build_speech_controller(qapp, environ=environment(tmp_path),
                        module_available=lambda name: (probes.append(name), True)[1])
    assert reason is None and result is not None
    assert probes == ['PySide6.QtMultimedia']
    assert calls == [(tmp_path / 'model', tmp_path / 'runtime/Scripts/python.exe', tmp_path), ('playback', qapp)]
    result.preflight(); assert calls[-1] == 'preflight'


@pytest.mark.parametrize('missing', ['AI_COMPANION_QWEN_MODEL_DIR', 'AI_COMPANION_QWEN_PYTHON', 'AI_COMPANION_QWEN_WORK_DIR'])
def test_incomplete_qwen_configuration_never_falls_back_or_probes(tmp_path, missing):
    env = environment(tmp_path); del env[missing]
    env['AI_COMPANION_TTS_MODEL_DIR'] = str(tmp_path / 'kokoro')
    def forbidden(*args): pytest.fail('Unexpected model/device probe', pytrace=False)
    result, reason = config.build_speech_controller(environ=env, module_available=forbidden)
    assert result is None and 'Qwen' in reason


@pytest.mark.parametrize('bad', ['relative', r'\\server\runtime', 'https://example/runtime'])
def test_invalid_qwen_path_shape_never_probes(tmp_path, bad):
    env = environment(tmp_path); env['AI_COMPANION_QWEN_PYTHON'] = bad
    def forbidden(*args): pytest.fail('Unexpected probe', pytrace=False)
    result, reason = config.build_speech_controller(environ=env, module_available=forbidden)
    assert result is None and reason


def test_unknown_engine_and_compiled_qwen_fail_before_optional_access(tmp_path, monkeypatch):
    def forbidden(*args): pytest.fail('Unexpected probe', pytrace=False)
    env = environment(tmp_path); env['AI_COMPANION_TTS_ENGINE'] = 'unrecognized'
    assert config.build_speech_controller(environ=env, module_available=forbidden)[0] is None
    monkeypatch.setattr(config, 'source_tts_supported', lambda: False)
    result, reason = config.build_speech_controller(environ=environment(tmp_path), module_available=forbidden)
    assert result is None and '打包' in reason
