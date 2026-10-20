"""Opt-in, thread-affine Qt capture; no multimedia import or hardware on construction."""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from companion.domain.voice import AudioChunk, VoiceErrorCode, VoiceOperationError


class QtMicrophoneCapture(QObject):
    captureFinished = Signal()
    captureFailed = Signal(object)
    MAX_BYTES = 16000 * 2 * 60

    def __init__(self, parent=None, *, backend_factory=None):
        super().__init__(parent)
        self._factory = backend_factory or QtAudioInput
        self._driver = None
        self._timer = None
        self._buffer = bytearray()
        self._pending = False
        self._error = None
        self._generation = 0

    def _check_thread(self):
        if QThread.currentThread() != self.thread():
            raise VoiceOperationError(VoiceErrorCode.CAPTURE_FAILED)

    def _clear(self):
        self._buffer[:] = bytes(len(self._buffer))
        self._buffer.clear()
        self._pending = False

    def _retire(self):
        driver, self._driver = self._driver, None
        timer, self._timer = self._timer, None
        if timer is not None:
            timer.stop()
            timer.timeout.disconnect()
            timer.deleteLater()
        if driver is not None:
            try:
                driver.ready.disconnect()
                driver.failed.disconnect()
                driver.stop()
            finally:
                driver.deleteLater()

    def _abort(self, code=VoiceErrorCode.CAPTURE_FAILED, *, notify=True):
        try:
            self._retire()
        except Exception:
            code = VoiceErrorCode.CAPTURE_FAILED
        self._clear()
        self._error = code
        if notify:
            self.captureFailed.emit(code)

    def start(self):
        self._check_thread()
        if self._driver is not None or self._pending:
            raise VoiceOperationError(VoiceErrorCode.BUSY)
        self._error = None
        self._generation += 1
        generation = self._generation
        try:
            driver = self._driver = self._factory(self)
            driver.ready.connect(lambda: self._drain(generation))
            driver.failed.connect(lambda: self._device_failed(generation))
            driver.start()
            if generation != self._generation:
                raise VoiceOperationError(VoiceErrorCode.CANCELLED)
            if self._error:
                raise VoiceOperationError(self._error)
            if self._driver is driver:
                timer = self._timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(lambda: self._deadline(generation))
                timer.start(60000)
        except Exception as error:
            code = error.code if isinstance(error, VoiceOperationError) else VoiceErrorCode.CAPTURE_FAILED
            if generation == self._generation:
                self._abort(code, notify=False)
                code = self._error
            raise VoiceOperationError(code) from None

    def _device_failed(self, generation):
        if generation == self._generation and self._driver is not None:
            self._abort()

    def _drain(self, generation, *, notify=True):
        if generation != self._generation or self._driver is None:
            return
        driver = self._driver
        try:
            while generation == self._generation and self._driver is driver:
                maximum = min(8192, self.MAX_BYTES - len(self._buffer))
                data = driver.read(maximum)
                # Backend calls may synchronously emit failure; its handler
                # may already have started a new recording before read returns.
                if generation != self._generation or self._driver is not driver:
                    return
                if not isinstance(data, bytes) or len(data) > maximum:
                    raise ValueError('Invalid bounded PCM read.')
                if not data:
                    break
                self._buffer.extend(data)
                if len(self._buffer) == self.MAX_BYTES:
                    self._complete(notify=notify)
                    break
        except Exception:
            if generation == self._generation and self._driver is driver:
                self._abort(notify=notify)

    def _complete(self, *, notify=True):
        try:
            self._retire()
            if not self._buffer or len(self._buffer) % 2:
                raise ValueError('Incomplete PCM.')
        except Exception:
            self._abort(notify=notify)
            return
        self._pending = True
        if notify:
            self.captureFinished.emit()

    def _deadline(self, generation):
        if generation == self._generation and self._driver is not None:
            self._drain(generation)
            if generation == self._generation and self._driver is not None:
                self._complete()

    def stop(self) -> AudioChunk:
        self._check_thread()
        generation = self._generation
        if self._driver is not None:
            self._drain(generation, notify=False)
            if generation != self._generation:
                raise VoiceOperationError(VoiceErrorCode.CANCELLED)
            try:
                self._retire()
            except Exception:
                self._abort(notify=False)
        if self._error or not self._buffer or len(self._buffer) % 2:
            self._clear()
            raise VoiceOperationError(self._error or VoiceErrorCode.CAPTURE_FAILED)
        audio = AudioChunk(self._buffer, 16000, 1, 2)
        self._buffer = bytearray()
        self._pending = False
        return audio

    def cancel(self):
        self._check_thread()
        self._generation += 1
        failed = False
        try:
            self._retire()
        except Exception:
            failed = True
        finally:
            self._clear()
            self._error = None
        if failed:
            raise VoiceOperationError(VoiceErrorCode.CAPTURE_FAILED)


class QtAudioInput(QObject):
    """Private native boundary; all lifecycle calls belong to its Qt thread."""

    ready = Signal()
    failed = Signal()

    def __init__(self, parent=None, *, permission_checker=None, multimedia_loader=None):
        super().__init__(parent)
        self._permission_checker = permission_checker or self._permission_granted
        self._loader = multimedia_loader or self._load_multimedia
        self._source = None
        self._device = None
        self._no_error = None

    @staticmethod
    def _permission_granted():
        from PySide6.QtCore import QCoreApplication, QMicrophonePermission, Qt
        app = QCoreApplication.instance()
        return app is not None and app.checkPermission(QMicrophonePermission()) == Qt.PermissionStatus.Granted

    @staticmethod
    def _load_multimedia():
        from PySide6 import QtMultimedia
        return QtMultimedia

    def _check_thread(self):
        if QThread.currentThread() != self.thread():
            raise VoiceOperationError(VoiceErrorCode.CAPTURE_FAILED)

    def start(self):
        self._check_thread()
        if self._source is not None:
            raise VoiceOperationError(VoiceErrorCode.BUSY)
        try:
            if self._permission_checker() is not True:
                raise VoiceOperationError(VoiceErrorCode.PERMISSION_DENIED)
            try:
                multimedia = self._loader()
            except ImportError:
                raise VoiceOperationError(VoiceErrorCode.NOT_CONFIGURED) from None
            device = multimedia.QMediaDevices.defaultAudioInput()
            audio_format = multimedia.QAudioFormat()
            audio_format.setSampleRate(16000)
            audio_format.setChannelCount(1)
            audio_format.setSampleFormat(multimedia.QAudioFormat.SampleFormat.Int16)
            if device.isNull() or not device.isFormatSupported(audio_format):
                raise VoiceOperationError(VoiceErrorCode.CAPTURE_FAILED)
            self._no_error = multimedia.QtAudio.Error.NoError
            source = self._source = multimedia.QAudioSource(device, audio_format, self)
            source.setBufferSize(3200)
            source.stateChanged.connect(self._state_changed)
            stream = source.start()
            if stream is None or source.error() != self._no_error or self._source is not source:
                raise VoiceOperationError(VoiceErrorCode.CAPTURE_FAILED)
            self._device = stream
            stream.readyRead.connect(self._ready)
        except Exception as error:
            code = error.code if isinstance(error, VoiceOperationError) else VoiceErrorCode.CAPTURE_FAILED
            try:
                self.stop()
            except Exception:
                code = VoiceErrorCode.CAPTURE_FAILED
            raise VoiceOperationError(code) from None

    def _ready(self):
        if self._source is not None:
            self.ready.emit()

    def _state_changed(self):
        # No enum payload conversion: capture errors only need the live source.
        if self._source is not None and self._source.error() != self._no_error:
            self.failed.emit()

    def read(self, maximum):
        self._check_thread()
        return bytes(self._device.read(maximum)) if self._device is not None else b''

    def stop(self):
        self._check_thread()
        source, self._source = self._source, None
        stream, self._device = self._device, None
        if stream is not None:
            stream.readyRead.disconnect(self._ready)
        if source is not None:
            try:
                source.stateChanged.disconnect(self._state_changed)
                source.stop()
            finally:
                source.deleteLater()
