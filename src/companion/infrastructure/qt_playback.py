"""Explicit Qt-thread playback. Construction never enumerates output devices."""
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, QThread, QTimer, Signal

from companion.domain.voice import AudioChunk, VoiceErrorCode, VoiceOperationError


class _PlaybackResources:
    """Cleanup remains callable during QObject.destroyed, without the owner."""
    def __init__(self):
        self.driver = self.audio = self.timer = None
        self.connected = False

    def stop(self):
        timer, self.timer = self.timer, None
        if timer is not None:
            timer.stop()
            timer.timeout.disconnect()
            timer.deleteLater()
        audio, self.audio = self.audio, None
        if audio is not None:
            audio.clear()
        driver = self.driver
        if driver is None:
            return True
        # Retain a failed driver for an explicit retry; silence is unconfirmed.
        try:
            if self.connected:
                driver.finished.disconnect()
                driver.failed.disconnect()
                self.connected = False
            driver.stop()
        except Exception:
            return False
        self.driver = None
        driver.deleteLater()
        return True


class QtAudioPlayback(QObject):
    finished = Signal()
    failed = Signal(object)

    def __init__(self, parent=None, *, backend_factory=None):
        super().__init__(parent)
        self._factory = backend_factory or QtAudioOutput
        self._resources = _PlaybackResources()
        self.destroyed.connect(self._resources.stop)
        self._generation = 0

    def _check_thread(self):
        if QThread.currentThread() != self.thread():
            raise VoiceOperationError(VoiceErrorCode.SPEECH_FAILED)

    def play(self, audio):
        self._check_thread()
        if self._resources.driver is not None:
            audio.clear()
            raise VoiceOperationError(VoiceErrorCode.BUSY)
        if not isinstance(audio, AudioChunk):
            raise VoiceOperationError(VoiceErrorCode.SPEECH_FAILED)
        self._generation += 1
        generation = self._generation
        self._resources.audio = audio
        driver = None
        try:
            audio.__post_init__()
            if (audio.sample_rate_hz, audio.channels, audio.sample_width_bytes) != (24000, 1, 2):
                raise ValueError('Unsupported PCM format.')
            driver = self._resources.driver = self._factory(self)
            driver.finished.connect(lambda: self._ended(generation, driver, False))
            driver.failed.connect(lambda: self._ended(generation, driver, True))
            self._resources.connected = True
            driver.start(audio)
            if generation == self._generation and self._resources.driver is driver:
                timer = self._resources.timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(lambda: self._ended(generation, driver, True))
                timer.start(int(len(audio.pcm) / 48) + 5000)
        except Exception:
            if generation == self._generation:
                self.stop()
            raise VoiceOperationError(VoiceErrorCode.SPEECH_FAILED) from None

    def _ended(self, generation, driver, error):
        if generation != self._generation or self._resources.driver is not driver:
            return
        stopped = self.stop()
        if error or not stopped:
            self.failed.emit(VoiceErrorCode.SPEECH_FAILED)
        else:
            self.finished.emit()

    def stop(self):
        self._check_thread()
        self._generation += 1
        return self._resources.stop()


class QtAudioOutput(QObject):
    finished = Signal()
    failed = Signal()

    def __init__(self, parent=None, *, multimedia_loader=None):
        super().__init__(parent)
        self._loader = multimedia_loader or self._load
        self._sink = self._buffer = None
        self._no_error = self._idle = None
        self._connected = False

    @staticmethod
    def _load():
        from PySide6 import QtMultimedia
        return QtMultimedia

    def _check_thread(self):
        if QThread.currentThread() != self.thread():
            raise VoiceOperationError(VoiceErrorCode.SPEECH_FAILED)

    def start(self, audio):
        self._check_thread()
        try:
            multimedia = self._loader()
            fmt = multimedia.QAudioFormat()
            fmt.setSampleRate(24000)
            fmt.setChannelCount(1)
            fmt.setSampleFormat(multimedia.QAudioFormat.SampleFormat.Int16)
            device = multimedia.QMediaDevices.defaultAudioOutput()
            if device.isNull() or not device.isFormatSupported(fmt):
                raise ValueError('Output unavailable.')
            self._no_error = multimedia.QtAudio.Error.NoError
            self._idle = multimedia.QtAudio.State.IdleState
            buffer = self._buffer = QBuffer(self)
            buffer.setData(QByteArray(bytes(audio.pcm)))
            if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
                raise ValueError('Output buffer unavailable.')
            sink = self._sink = multimedia.QAudioSink(device, fmt, self)
            sink.setBufferSize(4800)
            # Qt 6.11's legacy QAudio::State signal payload may fail conversion.
            # Ignore the payload and read current state after the identity guard.
            sink.stateChanged.connect(lambda: self._state(sink))
            self._connected = True
            sink.start(buffer)
            if self._sink is sink and sink.error() != self._no_error:
                raise ValueError('Output failed.')
        except Exception:
            self.stop()
            raise VoiceOperationError(VoiceErrorCode.SPEECH_FAILED) from None

    def _state(self, sink):
        if self._sink is not sink:
            return
        if sink.error() != self._no_error:
            self.failed.emit()
        elif sink.state() == self._idle:
            self.finished.emit()

    def stop(self):
        self._check_thread()
        sink = self._sink
        if sink is not None:
            # Disconnect notifications before reset; reset discards queued audio.
            if self._connected:
                sink.stateChanged.disconnect()
                self._connected = False
            sink.reset()
            if sink.error() != self._no_error:
                raise VoiceOperationError(VoiceErrorCode.SPEECH_FAILED)
            self._sink = None
            sink.deleteLater()
        buffer, self._buffer = self._buffer, None
        if buffer is not None:
            buffer.close()
            buffer.setData(QByteArray())
            buffer.deleteLater()
