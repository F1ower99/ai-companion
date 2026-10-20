from pathlib import Path

import pytest

from companion.desktop import voice_configuration as config


def test_default_off_does_not_probe_modules_or_construct_capture(monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('startup touched optional runtime')
    monkeypatch.setattr(config, 'QtMicrophoneCapture', forbidden)
    controller, reason = config.build_voice_controller(environ={}, module_available=forbidden)
    assert controller is None and 'AI_COMPANION_STT_MODEL_DIR' in reason


@pytest.mark.parametrize('path', ['relative/model', 'https://example/model', r'\\server\model'])
def test_invalid_path_shape_disables_before_optional_probe(path):
    def forbidden(*args): raise AssertionError('invalid configuration probed runtime')
    result, reason = config.build_voice_controller(environ={'AI_COMPANION_STT_MODEL_DIR': path},
                                                  module_available=forbidden)
    assert result is None and reason


def test_missing_optional_modules_produce_specific_reason(tmp_path):
    result, reason = config.build_voice_controller(
        environ={'AI_COMPANION_STT_MODEL_DIR': str(tmp_path)}, module_available=lambda name: False)
    assert result is None and 'voice' in reason


def test_configured_model_is_lazy_and_preflight_is_deferred(monkeypatch, tmp_path, qapp):
    calls = []
    class Provider:
        local_only = True
        def __init__(self, path): calls.append(('provider', path))
        def validate_model_directory(self): calls.append(('preflight',))
    class Capture:
        def __init__(self, parent): calls.append(('capture', parent))
    class Controller:
        def __init__(self, session, capture, parent, **kwargs): self.preflight = kwargs['preflight']
    monkeypatch.setattr(config, 'LocalWhisperSTT', Provider)
    monkeypatch.setattr(config, 'QtMicrophoneCapture', Capture)
    monkeypatch.setattr(config, 'VoiceController', Controller)
    controller, reason = config.build_voice_controller(
        qapp, environ={'AI_COMPANION_STT_MODEL_DIR': str(tmp_path)}, module_available=lambda name: True)
    assert reason is None
    assert calls == [('provider', Path(tmp_path)), ('capture', qapp)]
    controller.preflight()
    assert calls[-1] == ('preflight',)


def test_tts_default_off_never_probes_optional_runtime():
    def forbidden(*args): raise AssertionError('default off touched runtime')
    result,reason=config.build_speech_controller(environ={},module_available=forbidden)
    assert result is None and 'AI_COMPANION_TTS_MODEL_DIR' in reason

@pytest.mark.parametrize('path',['relative/model','https://example/model',r'\\server\model','C:/comma,model'])
def test_tts_invalid_path_does_not_probe(path):
    def forbidden(*args): raise AssertionError('invalid path probed runtime')
    result,reason=config.build_speech_controller(environ={'AI_COMPANION_TTS_MODEL_DIR':path},module_available=forbidden)
    assert result is None and reason

def test_tts_missing_runtime_is_safe(tmp_path):
    result,reason=config.build_speech_controller(environ={'AI_COMPANION_TTS_MODEL_DIR':str(tmp_path)},module_available=lambda name:False)
    assert result is None and 'tts' in reason

def test_tts_independent_of_stt_and_lazy(monkeypatch,tmp_path,qapp):
    calls=[]
    class Synth:
        def __init__(self,path): calls.append(('provider',path))
        def validate_model_directory(self): calls.append(('preflight',))
    class Player:
        def __init__(self,parent): calls.append(('playback',parent))
    class Controller:
        def __init__(self,synth,player,parent,**kwargs): self.preflight=kwargs['preflight']
    monkeypatch.setattr(config,'LocalKokoroSynthesizer',Synth)
    monkeypatch.setattr(config,'QtAudioPlayback',Player)
    monkeypatch.setattr(config,'SpeechController',Controller)
    result,reason=config.build_speech_controller(qapp,environ={'AI_COMPANION_TTS_MODEL_DIR':str(tmp_path)},module_available=lambda name:True)
    assert reason is None and calls==[('provider',Path(tmp_path)),('playback',qapp)]
    result.preflight(); assert calls[-1]==('preflight',)


@pytest.mark.parametrize('marker', ['nuitka', 'frozen'])
def test_compiled_tts_is_disabled_before_dependency_or_device_access(monkeypatch, tmp_path, marker):
    from companion.infrastructure import tts_process
    if marker == 'nuitka':
        monkeypatch.setattr(tts_process, '__compiled__', object(), raising=False)
    else:
        monkeypatch.setattr(tts_process.sys, 'frozen', True, raising=False)
    def forbidden(*args):
        raise AssertionError('Compiled TTS must fail before module/device setup')
    result, reason = config.build_speech_controller(
        environ={'AI_COMPANION_TTS_MODEL_DIR': str(tmp_path)}, module_available=forbidden)
    assert result is None and '打包' in reason
