from threading import Event, get_ident

import pytest
from PySide6.QtCore import QObject, QThreadPool, Signal

from companion.application.voice_session import VoiceSession
from companion.desktop.voice_controller import VoiceController, QtMicrophonePermissionRequester
from companion.domain.voice import AudioChunk, VoiceErrorCode, VoiceTranscript


class Capture(QObject):
    captureFinished = Signal()
    captureFailed = Signal(object)

    def __init__(self):
        super().__init__()
        self.owner = get_ident()
        self.starts = self.stops = self.cancels = 0
        self.buffer = None
        self.last_audio = None
        self.instant_limit = False

    def start(self):
        assert get_ident() == self.owner
        self.starts += 1
        self.buffer = bytearray(b'\x01\x02' * 10)
        if self.instant_limit:
            self.captureFinished.emit()

    def stop(self):
        assert get_ident() == self.owner
        self.stops += 1
        self.last_audio = AudioChunk(self.buffer, 16000, 1, 2)
        self.buffer = None
        return self.last_audio

    def cancel(self):
        assert get_ident() == self.owner
        self.cancels += 1
        if self.buffer is not None:
            self.buffer[:] = b'\0' * len(self.buffer)
            self.buffer.clear()
            self.buffer = None


class STT:
    local_only = True
    def __init__(self):
        self.calls = 0
        self.threads = []
        self.callback = None
    def transcribe(self, audio, token):
        self.calls += 1
        self.threads.append(get_ident())
        return self.callback(token) if self.callback else VoiceTranscript('识别草稿')


class Permission:
    def __init__(self): self.callbacks = []
    def request(self, callback): self.callbacks.append(callback)


class Pool:
    def __init__(self): self.workers = []
    def start(self, worker): self.workers.append(worker)


@pytest.fixture
def voice(qapp, qtbot):
    capture, stt, permission, pool = Capture(), STT(), Permission(), Pool()
    controller = VoiceController(VoiceSession(capture, stt), capture,
                                 permission_requester=permission, pool=pool)
    yield controller, capture, stt, permission, pool
    controller.close()
    for worker in pool.workers:
        worker.run()
    qapp.processEvents()


def begin(voice):
    controller, capture, stt, permission, pool = voice
    controller.press()
    permission.callbacks[-1](True)
    assert controller.state == 'listening'


@pytest.mark.parametrize('cancel_method', ['release', 'cancel', 'close'])
def test_delayed_permission_after_release_cancel_or_close_never_captures(voice, cancel_method):
    controller, capture, stt, permission, pool = voice
    controller.press()
    assert controller.state == 'permission' and capture.starts == 0
    getattr(controller, cancel_method)()
    permission.callbacks[0](True)
    assert capture.starts == 0 and stt.calls == 0 and not pool.workers


def test_duplicate_permission_reply_starts_once_and_denial_is_safe(voice):
    controller, capture, stt, permission, pool = voice
    controller.press()
    permission.callbacks[-1](False)
    assert controller.state == 'error'
    assert controller.error_code == VoiceErrorCode.PERMISSION_DENIED
    begin(voice)
    permission.callbacks[-1](True)
    assert capture.starts == 1


def test_release_stops_capture_before_dispatch_and_result_is_only_signal(voice, qtbot):
    controller, capture, stt, permission, pool = voice
    drafts = []
    controller.transcriptReady.connect(drafts.append)
    begin(voice)
    controller.release()
    assert capture.stops == 1 and stt.calls == 0
    assert controller.state == 'transcribing'
    assert not controller.can_record
    pool.workers[0].run()
    qtbot.waitUntil(lambda: controller.state == 'idle')
    assert drafts[0].text == '识别草稿'
    assert not capture.last_audio.pcm


def test_pending_cancel_clears_audio_and_never_publishes_late_result(voice, qtbot):
    controller, capture, stt, permission, pool = voice
    drafts = []
    controller.transcriptReady.connect(drafts.append)
    begin(voice)
    controller.release()
    controller.cancel()
    assert not capture.last_audio.pcm
    controller.press()
    assert capture.starts == 1  # wait for old queued worker's acknowledgement
    pool.workers[0].run()
    qtbot.waitUntil(lambda: controller.state == 'idle')
    assert stt.calls == 0 and drafts == []


@pytest.mark.parametrize('during_start', [False, True])
def test_capture_limit_dispatches_once_and_later_button_release_is_noop(voice, during_start):
    controller, capture, stt, permission, pool = voice
    capture.instant_limit = during_start
    controller.press()
    permission.callbacks[-1](True)
    if not during_start:
        capture.captureFinished.emit()
    controller.release()
    assert capture.stops == 1 and len(pool.workers) == 1


def test_async_capture_failure_cleans_up_without_transcribing(voice):
    controller, capture, stt, permission, pool = voice
    begin(voice)
    capture.captureFailed.emit(VoiceErrorCode.CAPTURE_FAILED)
    assert controller.state == 'error'
    assert capture.buffer is None
    assert not pool.workers and stt.calls == 0


def test_pool_submission_failure_clears_unrun_job(voice):
    from companion.desktop.chat_worker import _ACTIVE_WORKERS
    before = len(_ACTIVE_WORKERS)
    controller, capture, stt, permission, pool = voice
    def fail(worker): raise RuntimeError('private path')
    pool.start = fail
    begin(voice)
    controller.release()
    assert controller.state == 'error'
    assert not capture.last_audio.pcm
    assert stt.calls == 0
    assert controller.can_record
    assert len(_ACTIVE_WORKERS) == before


def test_failed_model_preflight_happens_before_permission_or_capture(voice):
    controller, capture, stt, permission, pool = voice
    controller._preflight = lambda: (_ for _ in ()).throw(RuntimeError('private directory'))
    controller.press()
    assert controller.error_code == VoiceErrorCode.NOT_CONFIGURED
    assert permission.callbacks == [] and capture.starts == 0


def test_cancelling_as_permission_ui_opens_prevents_permission_request(voice):
    controller, capture, stt, permission, pool = voice
    controller.stateChanged.connect(lambda state: controller.cancel() if state == 'permission' else None)
    controller.press()
    assert controller.state == 'idle'
    assert permission.callbacks == [] and capture.starts == 0


def test_close_during_completion_state_change_suppresses_draft(voice, qtbot):
    controller, capture, stt, permission, pool = voice
    drafts = []
    controller.transcriptReady.connect(drafts.append)
    begin(voice)
    controller.release()
    controller.stateChanged.connect(lambda state: controller.close() if state == 'idle' else None)
    pool.workers[0].run()
    qtbot.waitUntil(lambda: controller.state == 'unavailable')
    assert drafts == []


def test_reentrant_replacement_on_transcribing_notification_preserves_new_capture(voice):
    controller, capture, stt, permission, pool = voice
    begin(voice)
    replaced = []
    def replace(state):
        if state == 'transcribing' and not replaced:
            replaced.append(True)
            controller.cancel()
            begin(voice)
    controller.stateChanged.connect(replace)
    controller.release()
    assert controller.state == 'listening'
    assert controller.session.status.state.value == 'listening'
    assert capture.buffer and capture.stops == 0
    assert pool.workers == []


def test_reentrant_new_worker_does_not_enable_old_draft_publication(voice, qtbot):
    controller, capture, stt, permission, pool = voice
    drafts, replaced = [], []
    controller.transcriptReady.connect(drafts.append)
    begin(voice)
    controller.release()
    def replace(state):
        if state == 'idle' and not replaced:
            replaced.append(True)
            begin(voice)
            controller.release()
    controller.stateChanged.connect(replace)
    pool.workers[0].run()
    qtbot.waitUntil(lambda: len(pool.workers) == 2)
    assert controller.state == 'transcribing'
    assert drafts == []


def test_real_pool_keeps_ui_responsive_and_cancelled_decode_has_no_draft(qapp, qtbot):
    capture, stt, permission = Capture(), STT(), Permission()
    entered, finish = Event(), Event()
    def decode(token):
        entered.set()
        assert finish.wait(4)
        return VoiceTranscript('late private draft')
    stt.callback = decode
    pool = QThreadPool()
    controller = VoiceController(VoiceSession(capture, stt), capture,
                                 permission_requester=permission, pool=pool)
    drafts = []
    controller.transcriptReady.connect(drafts.append)
    try:
        controller.press()
        permission.callbacks[0](True)
        controller.release()
        qtbot.waitUntil(entered.is_set)
        assert stt.threads == [stt.threads[0]] and stt.threads[0] != get_ident()
        controller.cancel()  # this runs while native work is still blocked
        assert controller.state == 'cancelling'
        assert capture.last_audio.pcm
        finish.set()
        qtbot.waitUntil(lambda: controller.state == 'idle')
        assert drafts == [] and not capture.last_audio.pcm
    finally:
        finish.set()
        controller.close()
        pool.waitForDone(5000)


def test_permission_request_uses_qobject_context_and_grant_result(qapp):
    from PySide6.QtCore import Qt
    class App:
        def checkPermission(self, permission): return Qt.PermissionStatus.Undetermined
        def requestPermission(self, permission, context, callback):
            self.context, self.callback = context, callback
    app = App()
    requester = QtMicrophonePermissionRequester(app=app)
    results = []
    requester.request(results.append)
    assert app.context is requester and results == []
    class PermissionResult:
        def status(self): return Qt.PermissionStatus.Granted
    app.callback(PermissionResult())
    assert results == [True]


@pytest.mark.parametrize('draft_state', ['empty', 'typed', 'hidden'])
def test_real_controller_and_chat_window_flow_without_hardware(qapp, qtbot, draft_state):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from companion.desktop.chat_window import ChatWindow
    capture, stt = Capture(), STT()
    class Granted:
        def request(self, callback): callback(True)
    finish = Event()
    def decode(token):
        assert finish.wait(4)
        return VoiceTranscript('语音草稿')
    stt.callback = decode
    pool = QThreadPool()
    controller = VoiceController(VoiceSession(capture, stt), capture,
                                 permission_requester=Granted(), pool=pool)
    window = ChatWindow(voice_controller=controller)
    qtbot.addWidget(window)
    window.show()
    try:
        QTest.mousePress(window.push_to_talk_button, Qt.MouseButton.LeftButton)
        assert controller.state == 'listening'
        QTest.mouseRelease(window.push_to_talk_button, Qt.MouseButton.LeftButton)
        assert controller.state == 'transcribing'
        if draft_state == 'typed':
            window.composer.setPlainText('手动输入保留')
        elif draft_state == 'hidden':
            window.hide()
        finish.set()
        qtbot.waitUntil(lambda: controller.state == 'idle')
        expected = {'empty': '语音草稿', 'typed': '手动输入保留', 'hidden': ''}[draft_state]
        assert window.composer.toPlainText() == expected
        assert not window.send_button.isEnabled()  # no chat backend in this test
        assert capture.stops == 1 and not capture.last_audio.pcm
    finally:
        finish.set()
        controller.close()
        pool.waitForDone(5000)
