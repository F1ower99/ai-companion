from threading import Thread

import pytest
from PySide6.QtCore import QObject, Signal

from companion.domain.voice import VoiceErrorCode, VoiceOperationError
from companion.infrastructure.qt_microphone import QtAudioInput, QtMicrophoneCapture


class FakeInput(QObject):
    ready = Signal()
    failed = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.data = bytearray()
        self.stopped = False
        self.start_error = None
        self.stop_error = False
        self.read_error = False

    def start(self):
        if self.start_error:
            raise self.start_error

    def read(self, maximum):
        if self.read_error:
            raise RuntimeError('private device detail')
        data = bytes(self.data[:maximum])
        del self.data[:maximum]
        return data

    def stop(self):
        self.stopped = True
        if self.stop_error:
            raise RuntimeError('private device detail')

    def feed(self, data):
        self.data.extend(data)
        self.ready.emit()


@pytest.fixture
def capture(qapp):
    drivers = []
    def factory(parent):
        driver = FakeInput(parent)
        drivers.append(driver)
        return driver
    result = QtMicrophoneCapture(backend_factory=factory)
    yield result, drivers
    result.cancel()


def assert_error(code, operation):
    with pytest.raises(VoiceOperationError) as error:
        operation()
    assert error.value.code == code
    assert str(error.value) == code.value


def test_lazy_start_stop_transfers_exact_pcm_and_releases_device(capture):
    source, drivers = capture
    assert not drivers
    source.cancel()
    source.start()
    drivers[0].feed(b'\x01\x02' * 160)
    audio = source.stop()
    assert drivers[0].stopped
    assert audio.pcm == bytearray(b'\x01\x02' * 160)
    assert (audio.sample_rate_hz, audio.channels, audio.sample_width_bytes) == (16000, 1, 2)
    source.cancel()
    assert len(audio.pcm) == 320  # ownership transferred, cancel cannot mutate it
    audio.clear()


def test_cancel_clears_owned_buffer_and_allows_explicit_retry(capture):
    source, drivers = capture
    source.start()
    drivers[0].feed(b'\x01\x02' * 20)
    owned = source._buffer
    source.cancel()
    assert owned == bytearray()
    assert drivers[0].stopped
    source.cancel()
    source.start()
    assert len(drivers) == 2


def test_byte_limit_stops_at_exact_sixty_seconds(capture, qtbot):
    source, drivers = capture
    source.start()
    with qtbot.waitSignal(source.captureFinished):
        drivers[0].feed(b'\x01\x02' * (16000 * 61))
    assert drivers[0].stopped
    assert_error(VoiceErrorCode.BUSY, source.start)
    audio = source.stop()
    assert audio.duration_seconds == 60
    assert len(audio.pcm) == 1920000
    audio.clear()


def test_timer_finishes_short_capture_and_empty_timer_fails(capture, qtbot):
    source, drivers = capture
    source.start()
    drivers[0].feed(b'\x01\x02' * 3)
    assert source._timer.interval() == 60000
    source._timer.setInterval(1)
    with qtbot.waitSignal(source.captureFinished):
        pass
    source.stop().clear()
    source.start()
    source._timer.setInterval(1)
    with qtbot.waitSignal(source.captureFailed) as signal:
        pass
    assert signal.args == [VoiceErrorCode.CAPTURE_FAILED]
    assert drivers[-1].stopped


@pytest.mark.parametrize('payload', [b'', b'\x01'])
def test_empty_or_incomplete_final_pcm_is_rejected_and_cleared(capture, payload):
    source, drivers = capture
    source.start()
    drivers[0].feed(payload)
    owned = source._buffer
    assert_error(VoiceErrorCode.CAPTURE_FAILED, source.stop)
    assert drivers[0].stopped
    assert not owned


def test_partial_frames_can_be_completed_by_later_reads(capture):
    source, drivers = capture
    source.start()
    drivers[0].feed(b'\x01')
    drivers[0].feed(b'\x02')
    audio = source.stop()
    assert audio.pcm == bytearray(b'\x01\x02')
    audio.clear()


@pytest.mark.parametrize('failure', ['read', 'stop', 'signal'])
def test_device_failures_never_publish_audio(capture, failure):
    source, drivers = capture
    source.start()
    driver = drivers[0]
    driver.feed(b'\x01\x02' * 20)
    owned = source._buffer
    if failure == 'read':
        driver.read_error = True
        driver.ready.emit()
    elif failure == 'signal':
        driver.failed.emit()
    else:
        driver.stop_error = True
    assert_error(VoiceErrorCode.CAPTURE_FAILED, source.stop)
    assert driver.stopped
    assert not owned


def test_start_denial_is_safe_and_backend_released(qapp):
    driver = FakeInput(None)
    driver.start_error = VoiceOperationError(VoiceErrorCode.PERMISSION_DENIED)
    source = QtMicrophoneCapture(backend_factory=lambda parent: driver)
    assert_error(VoiceErrorCode.PERMISSION_DENIED, source.start)
    assert driver.stopped
    source.cancel()


def test_busy_does_not_replace_running_capture(capture):
    source, drivers = capture
    source.start()
    assert_error(VoiceErrorCode.BUSY, source.start)
    assert len(drivers) == 1
    assert not drivers[0].stopped


def test_stale_callbacks_cannot_stop_new_recording(capture):
    source, drivers = capture
    source.start()
    old = drivers[0]
    source.cancel()
    source.start()
    old.ready.emit()
    old.failed.emit()
    assert not drivers[1].stopped
    drivers[1].feed(b'\x01\x02')
    source.stop().clear()


def test_deadline_callback_cannot_finish_recording_started_by_completion_handler(capture):
    source, drivers = capture
    def completed():
        source.stop().clear()
        source.start()
    source.captureFinished.connect(completed)
    source.start()
    # Data is already available when the deadline drains the native device.
    drivers[0].data.extend(b'\x01\x02' * (16000 * 60))
    source._deadline(source._generation)
    assert len(drivers) == 2
    assert not drivers[1].stopped


def test_explicit_stop_does_not_emit_automatic_completion_signal(capture):
    source, drivers = capture
    finished = []
    source.captureFinished.connect(lambda: finished.append(True))
    source.start()
    drivers[0].data.extend(b'\x01\x02' * (16000 * 60))
    source.stop().clear()
    assert finished == []


def test_failed_start_cannot_abort_retry_started_by_failure_handler(qapp):
    drivers = []
    def factory(parent):
        driver = FakeInput(parent)
        if not drivers:
            def failed_start():
                driver.failed.emit()
                raise VoiceOperationError(VoiceErrorCode.CAPTURE_FAILED)
            driver.start = failed_start
        drivers.append(driver)
        return driver
    source = QtMicrophoneCapture(backend_factory=factory)
    source.captureFailed.connect(lambda code: source.start())
    try:
        assert_error(VoiceErrorCode.CAPTURE_FAILED, source.start)
        assert len(drivers) == 2
        assert drivers[0].stopped
        assert not drivers[1].stopped
        drivers[1].feed(b'\x03\x04')
        audio = source.stop()
        assert audio.pcm == bytearray(b'\x03\x04')
        audio.clear()
    finally:
        source.cancel()


@pytest.mark.parametrize('raises_after_signal', [False, True])
def test_failed_read_never_contaminates_or_stops_retry(capture, raises_after_signal):
    source, drivers = capture
    source.start()
    source.captureFailed.connect(lambda code: source.start())
    old = drivers[0]
    def failed_read(maximum):
        old.failed.emit()
        if raises_after_signal:
            raise RuntimeError('old device exception')
        return b'\x01\x02'
    old.read = failed_read
    assert_error(VoiceErrorCode.CANCELLED, source.stop)
    assert len(drivers) == 2
    assert not drivers[1].stopped
    drivers[1].feed(b'\x03\x04')
    audio = source.stop()
    assert audio.pcm == bytearray(b'\x03\x04')
    audio.clear()


def test_wrong_thread_rejected_before_backend_or_qt_mutation(capture):
    source, drivers = capture
    failures = []
    def work():
        for operation in (source.start, source.stop, source.cancel):
            try:
                operation()
            except VoiceOperationError as error:
                failures.append(error.code)
    thread = Thread(target=work)
    thread.start()
    thread.join()
    assert failures == [VoiceErrorCode.CAPTURE_FAILED] * 3
    assert not drivers


class FakeNativeSource(QObject):
    stateChanged = Signal(object)
    readyRead = Signal()

    def __init__(self, device, audio_format, parent):
        super().__init__(parent)
        self.audio_format = audio_format
        self.buffer_size = None
        self.stopped = False
        self.error_code = 0
        self.data = bytearray(b'\x01\x02' * 4)

    def setBufferSize(self, value):
        self.buffer_size = value

    def start(self):
        return self

    def error(self):
        return self.error_code

    def read(self, maximum):
        data = bytes(self.data[:maximum])
        del self.data[:maximum]
        return data

    def stop(self):
        self.stopped = True


@pytest.fixture
def native(qapp):
    from types import SimpleNamespace
    class Format:
        SampleFormat = SimpleNamespace(Int16=16)
        def setSampleRate(self, value): self.rate = value
        def setChannelCount(self, value): self.channels = value
        def setSampleFormat(self, value): self.width = value
    class Device:
        missing = False
        supported = True
        def isNull(self): return self.missing
        def isFormatSupported(self, value): return self.supported
    device = Device()
    calls = []
    sources = []
    def default_device():
        calls.append('device')
        return device
    def source_factory(*args):
        result = FakeNativeSource(*args)
        sources.append(result)
        return result
    module = SimpleNamespace(
        QAudioFormat=Format, QAudioSource=source_factory,
        QMediaDevices=SimpleNamespace(defaultAudioInput=default_device),
        QtAudio=SimpleNamespace(Error=SimpleNamespace(NoError=0)),
    )
    return module, device, calls, sources


def test_native_permission_is_checked_before_module_load_or_discovery(qapp):
    calls = []
    backend = QtAudioInput(permission_checker=lambda: False,
                           multimedia_loader=lambda: calls.append('load'))
    assert_error(VoiceErrorCode.PERMISSION_DENIED, backend.start)
    assert calls == []
    backend.stop()


@pytest.mark.parametrize('condition', ['missing', 'unsupported'])
def test_native_rejects_missing_device_and_unsupported_format(native, condition):
    module, device, calls, sources = native
    if condition == 'missing':
        device.missing = True
    else:
        device.supported = False
    backend = QtAudioInput(permission_checker=lambda: True, multimedia_loader=lambda: module)
    assert_error(VoiceErrorCode.CAPTURE_FAILED, backend.start)
    assert calls == ['device']
    assert sources == []
    backend.stop()


def test_native_sets_exact_format_and_bounded_buffer_and_forwards_read(native, qtbot):
    module, device, calls, sources = native
    backend = QtAudioInput(permission_checker=lambda: True, multimedia_loader=lambda: module)
    backend.start()
    source = sources[0]
    assert (source.audio_format.rate, source.audio_format.channels, source.audio_format.width) == (16000, 1, 16)
    assert source.buffer_size == 3200
    with qtbot.waitSignal(backend.ready):
        source.readyRead.emit()
    assert backend.read(2) == b'\x01\x02'
    with qtbot.waitSignal(backend.failed):
        source.error_code = 1
        source.stateChanged.emit('stopped')
    backend.stop()
    assert source.stopped
    assert backend.read(2) == b''


def test_native_failed_start_releases_partially_created_source(native):
    module, device, calls, sources = native
    make_source = module.QAudioSource
    def failing(*args):
        result = make_source(*args)
        result.start = lambda: None
        return result
    module.QAudioSource = failing
    backend = QtAudioInput(permission_checker=lambda: True, multimedia_loader=lambda: module)
    assert_error(VoiceErrorCode.CAPTURE_FAILED, backend.start)
    assert sources[0].stopped
    backend.stop()


def test_native_missing_optional_runtime_is_safe(qapp):
    def missing(): raise ImportError('private installation path')
    backend = QtAudioInput(permission_checker=lambda: True, multimedia_loader=missing)
    assert_error(VoiceErrorCode.NOT_CONFIGURED, backend.start)
