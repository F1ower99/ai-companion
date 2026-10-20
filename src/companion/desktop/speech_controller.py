"""Qt-thread speech lifecycle; workers own synthesis, never devices."""
from uuid import uuid4
from PySide6.QtCore import QObject, QThread, QThreadPool, Qt, Signal, Slot

from companion.application.voice_synthesis import SynthesisJob
from companion.application.cancellation import CancellationFlag
from companion.desktop.chat_worker import ChatWorker
from companion.domain.voice import VoiceErrorCode, VoiceOperationError


class SpeechController(QObject):
    stateChanged = Signal(str)
    errorOccurred = Signal(object)

    def __init__(self, synthesizer, playback, parent=None, *, preflight=None, pool=None):
        super().__init__(parent)
        self._synthesizer, self._playback = synthesizer, playback
        self._preflight = preflight or (lambda: None)
        self._pool = pool if pool is not None else QThreadPool.globalInstance()
        self._active = None
        self._generation = 0
        self._destroyed_token = CancellationFlag()
        self.destroyed.connect(self._destroyed_token.cancel)
        # Playback is independently parented; its lifetime can outlast this one.
        def stop_survivor():
            try:
                playback.stop()
            except Exception:
                pass  # A deleted output QObject has already lost its device.
        self.destroyed.connect(stop_survivor)
        self._closed = self._launching = self._stopping = self._stop_failed = False
        self.error_code = None
        self.state = 'idle' if getattr(synthesizer, 'local_only', None) is True else 'unavailable'
        playback.finished.connect(self._playback_finished)
        playback.failed.connect(self._playback_failed)

    def _check_thread(self):
        if QThread.currentThread() != self.thread():
            raise VoiceOperationError(VoiceErrorCode.SPEECH_FAILED)

    @property
    def _is_closed(self):
        return self._closed or self._destroyed_token.is_cancelled()

    @property
    def can_speak(self):
        return (not self._is_closed and not self._launching and not self._stopping
                and not self._stop_failed and self._active is None
                and self.state in ('idle', 'error'))

    def _state(self, state):
        if state != self.state:
            self.state = state
            self.stateChanged.emit(state)

    def _error(self, code):
        generation = self._generation
        self.error_code = code
        self._state('error')
        if not self._is_closed and generation == self._generation:
            self.errorOccurred.emit(code)

    def speak(self, text):
        self._check_thread()
        if not self.can_speak:
            return
        self._generation += 1
        generation = self._generation
        self.error_code = None
        self._launching = True
        try:
            self._preflight()
            job = SynthesisJob(self._synthesizer, text)
        except Exception:
            self._launching = False
            if not self._is_closed and generation == self._generation:
                self._error(VoiceErrorCode.NOT_CONFIGURED)
            return
        self._launching = False
        if self._is_closed or generation != self._generation:
            job.cancel()
            return
        request_id = uuid4().hex
        worker = ChatWorker(request_id, job.run)
        worker.signals.finished.connect(self._worker_finished, Qt.ConnectionType.QueuedConnection)
        self.destroyed.connect(job.cancel)
        self._active = (request_id, generation, job, worker)
        self._state('synthesizing')
        if self._is_closed or generation != self._generation:
            job.cancel()
            worker.abandon()
            self.destroyed.disconnect(job.cancel)
            self._active = None
            if not self._is_closed:
                self._state('error' if self._stop_failed else 'idle')
            return
        try:
            self._pool.start(worker)
        except Exception:
            job.cancel()
            worker.abandon()
            self.destroyed.disconnect(job.cancel)
            self._active = None
            self._error(VoiceErrorCode.SPEECH_FAILED)

    @Slot(str, object, object)
    def _worker_finished(self, request_id, unused_result, error):
        if self._active is None or request_id != self._active[0]:
            return
        _, generation, job, _ = self._active
        self.destroyed.disconnect(job.cancel)
        self._active = None
        audio = job.take_audio()
        if self._is_closed or generation != self._generation:
            if audio is not None:
                audio.clear()
            job.cancel()
            if not self._is_closed:
                self._state('error' if self._stop_failed else 'idle')
            return
        if error is not None or audio is None:
            if audio is not None:
                audio.clear()
            self._error(VoiceErrorCode.SPEECH_FAILED)
            return
        self._state('playing')
        if self._is_closed or generation != self._generation:
            audio.clear()
            return
        try:
            self._playback.play(audio)
        except Exception:
            audio.clear()
            if generation == self._generation and not self._is_closed:
                self._stop_output()
                self._error(VoiceErrorCode.SPEECH_FAILED)

    def _stop_output(self):
        self._stopping = True
        try:
            success = self._playback.stop() is True
        except Exception:
            success = False
        finally:
            self._stopping = False
        self._stop_failed = not success
        return success

    @Slot()
    def cancel(self):
        self._check_thread()
        self._generation += 1
        if self._active is not None:
            self._active[2].cancel()
        success = self._stop_output()
        if self._is_closed:
            self._state('unavailable')
        elif not success:
            self._error(VoiceErrorCode.SPEECH_FAILED)
        else:
            self._state('cancelling' if self._active is not None else 'idle')
        return success

    @Slot()
    def close(self):
        self._check_thread()
        if not self._is_closed:
            self._closed = True
            self.cancel()

    @Slot()
    def _playback_finished(self):
        if not self._is_closed and not self._stopping and self.state == 'playing':
            self._state('idle')

    @Slot(object)
    def _playback_failed(self, code):
        if not self._is_closed and not self._stopping and self.state == 'playing':
            self._stop_output()
            self._error(VoiceErrorCode.SPEECH_FAILED)
