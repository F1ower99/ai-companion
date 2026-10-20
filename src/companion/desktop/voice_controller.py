from __future__ import annotations

from uuid import uuid4
from weakref import ref

from PySide6.QtCore import QCoreApplication, QMicrophonePermission, QObject, QThread, QThreadPool, Qt, Signal, Slot

from companion.desktop.chat_worker import ChatWorker
from companion.domain.voice import VoiceErrorCode, VoiceOperationError, VoiceState, VoiceTranscript


class QtMicrophonePermissionRequester(QObject):
    def __init__(self, parent=None, *, app=None):
        super().__init__(parent)
        self._app = app

    def request(self, callback):
        app = self._app if self._app is not None else QCoreApplication.instance()
        if app is None:
            callback(False)
            return
        permission = QMicrophonePermission()
        status = app.checkPermission(permission)
        if status == Qt.PermissionStatus.Undetermined:
            app.requestPermission(permission, self,
                                  lambda result: callback(result.status() == Qt.PermissionStatus.Granted))
        else:
            callback(status == Qt.PermissionStatus.Granted)


class VoiceController(QObject):
    """UI-thread capture/permission lifecycle; workers receive PCM jobs only."""

    stateChanged = Signal(str)
    transcriptReady = Signal(object)
    errorOccurred = Signal(object)

    def __init__(self, session, capture, parent=None, *, permission_requester=None,
                 preflight=None, pool=None):
        super().__init__(parent)
        self.session = session
        self._capture = capture
        self._permission = permission_requester or QtMicrophonePermissionRequester(self)
        self._preflight = preflight or (lambda: None)
        self._pool = pool if pool is not None else QThreadPool.globalInstance()
        self._generation = 0
        self._held = False
        self._waiting = False
        self._closed = False
        self._starting = False
        self._limit_pending = False
        self._startup_error = None
        self._workers = {}
        self._active_worker = None
        self._worker_generation = None
        self.error_code = None
        self.state = 'idle' if session.can_capture else 'unavailable'
        capture.captureFinished.connect(self._capture_finished)
        capture.captureFailed.connect(self._capture_failed)

    def _check_thread(self):
        if QThread.currentThread() != self.thread():
            raise VoiceOperationError(VoiceErrorCode.CAPTURE_FAILED)

    @property
    def can_record(self):
        return (not self._closed and self.session.can_capture and self._active_worker is None
                and self.state in ('idle', 'error'))

    def _state(self, state):
        if state == self.state:
            return
        self.state = state
        self.stateChanged.emit(state)

    def _error(self, code):
        self.error_code = code
        self._state('error')
        self.errorOccurred.emit(code)

    @Slot()
    def press(self):
        self._check_thread()
        if not self.can_record:
            return
        self._held = True
        self.error_code = None
        self._generation += 1
        generation = self._generation
        try:
            self._preflight()
        except Exception:
            self._held = False
            self._error(VoiceErrorCode.NOT_CONFIGURED)
            return
        self._waiting = True
        self._state('permission')
        if self._closed or generation != self._generation or not self._waiting or not self._held:
            return
        owner = ref(self)
        def permission_result(granted):
            controller = owner()
            if controller is not None and not controller._closed:
                controller._permission_result(generation, granted)
        try:
            self._permission.request(permission_result)
        except Exception:
            if generation == self._generation and self._waiting:
                self._waiting = False
                self._held = False
                self._error(VoiceErrorCode.PERMISSION_DENIED)

    def _permission_result(self, generation, granted):
        self._check_thread()
        if self._closed or generation != self._generation or not self._waiting or not self._held:
            return
        self._waiting = False
        if granted is not True:
            self._held = False
            self._error(VoiceErrorCode.PERMISSION_DENIED)
            return
        self._starting = True
        self._limit_pending = False
        self._startup_error = None
        try:
            status = self.session.start_push_to_talk()
        finally:
            self._starting = False
        if self._closed or generation != self._generation:
            return
        if status.state is not VoiceState.LISTENING or status.error_code or self._startup_error:
            self._held = False
            self.session.cancel_capture()
            self._error(self._startup_error or status.error_code or VoiceErrorCode.CAPTURE_FAILED)
            return
        self._state('listening')
        if self._limit_pending:
            self.release()

    @Slot()
    def release(self):
        self._check_thread()
        self._held = False
        if self.state == 'permission':
            self.cancel()
            return
        if self._closed or self.state != 'listening':
            return
        generation = self._generation
        self._state('transcribing')
        if generation != self._generation or self._closed:
            return
        job = self.session.prepare_transcription()
        if generation != self._generation or self._closed:
            if job is not None:
                job.cancel()
            return
        if job is None:
            self._error(self.session.status.error_code or VoiceErrorCode.CAPTURE_FAILED)
            return
        request_id = uuid4().hex
        worker = ChatWorker(request_id, job.run)
        worker.signals.finished.connect(self._worker_finished, Qt.ConnectionType.QueuedConnection)
        self._workers[request_id] = worker
        self._active_worker, self._worker_generation = request_id, generation
        try:
            self._pool.start(worker)
        except Exception:
            self.session.cancel_capture()
            worker.abandon()
            self._workers.pop(request_id, None)
            self._active_worker = None
            self._error(VoiceErrorCode.TRANSCRIPTION_FAILED)

    @Slot(str, object, object)
    def _worker_finished(self, request_id, transcript, error):
        self._workers.pop(request_id, None)
        if request_id != self._active_worker:
            return
        self._active_worker = None
        generation = self._worker_generation
        if self._closed:
            return
        if generation != self._generation:
            self._state('idle')
            return
        if error is not None or not isinstance(transcript, VoiceTranscript):
            self._error(self.session.status.error_code or VoiceErrorCode.TRANSCRIPTION_FAILED)
            return
        self._state('idle')
        if not self._closed and generation == self._generation:
            self.transcriptReady.emit(transcript)

    @Slot()
    def _capture_finished(self):
        if self._starting:
            self._limit_pending = True
        elif self.state == 'listening':
            self.release()

    @Slot(object)
    def _capture_failed(self, code):
        if self._starting:
            self._startup_error = VoiceErrorCode.CAPTURE_FAILED
        elif not self._closed and self.state == 'listening':
            self.cancel()
            self._error(VoiceErrorCode.CAPTURE_FAILED)

    @Slot()
    def cancel(self):
        self._check_thread()
        if self._closed:
            return
        self._generation += 1
        self._held = self._waiting = False
        self.session.cancel_capture()
        self._state('cancelling' if self._active_worker is not None else 'idle')

    @Slot()
    def close(self):
        self._check_thread()
        if self._closed:
            return
        self._closed = True
        self._generation += 1
        self._held = self._waiting = False
        self.session.close()
        self._capture.captureFinished.disconnect(self._capture_finished)
        self._capture.captureFailed.disconnect(self._capture_failed)
        self._state('unavailable')
