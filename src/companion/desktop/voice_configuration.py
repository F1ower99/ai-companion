"""Developer opt-in composition. No model load, device discovery or downloads."""
from __future__ import annotations

from importlib.util import find_spec
import os
from pathlib import Path

# Native engines remain lazy: these modules do not import sherpa/QtMultimedia.
from companion.desktop.speech_controller import SpeechController
from companion.infrastructure.local_kokoro import LocalKokoroSynthesizer
from companion.infrastructure.qt_playback import QtAudioPlayback

from companion.application.voice_session import VoiceSession
from companion.desktop.voice_controller import VoiceController
from companion.infrastructure.local_whisper import LocalWhisperSTT
from companion.infrastructure.qt_microphone import QtMicrophoneCapture


def build_voice_controller(parent=None, *, environ=None, module_available=None):
    environment = os.environ if environ is None else environ
    directory = environment.get('AI_COMPANION_STT_MODEL_DIR', '').strip()
    if not directory:
        return None, '本地语音未配置：请设置 AI_COMPANION_STT_MODEL_DIR。'
    if '://' in directory or directory.startswith(('\\\\', '//')) or not Path(directory).is_absolute():
        return None, '本地语音需要绝对本地模型目录。'
    available = module_available or (lambda name: find_spec(name) is not None)
    try:
        installed = available('PySide6.QtMultimedia') and available('faster_whisper')
    except (ImportError, ValueError, AttributeError):
        installed = False
    if not installed:
        return None, '本地语音依赖未就绪：请安装 voice 和 stt 可选依赖。'
    provider = LocalWhisperSTT(Path(directory))
    capture = QtMicrophoneCapture(parent)
    controller = VoiceController(VoiceSession(capture, provider), capture, parent,
                                 preflight=provider.validate_model_directory)
    return controller, None


def build_speech_controller(parent=None, *, environ=None, module_available=None):
    environment = os.environ if environ is None else environ
    directory = environment.get('AI_COMPANION_TTS_MODEL_DIR', '').strip()
    if not directory:
        return None, '本地朗读未配置：请设置 AI_COMPANION_TTS_MODEL_DIR。'
    if ('://' in directory or ',' in directory or directory.startswith(('\\\\', '//'))
            or not Path(directory).is_absolute()):
        return None, '本地朗读需要绝对本地模型目录。'
    available = module_available or (lambda name: find_spec(name) is not None)
    try:
        installed = all(available(name) for name in ('PySide6.QtMultimedia', 'sherpa_onnx', 'numpy'))
    except (ImportError, ValueError, AttributeError):
        installed = False
    if not installed:
        return None, '本地朗读依赖未就绪：请安装 voice 和 tts 可选依赖。'
    provider = LocalKokoroSynthesizer(Path(directory))
    playback = QtAudioPlayback(parent)
    return SpeechController(provider, playback, parent, preflight=provider.validate_model_directory), None
