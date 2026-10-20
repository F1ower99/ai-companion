from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


_ACTIVE_WORKERS: set["ChatWorker"] = set()


class ChatWorkerSignals(QObject):
    finished = Signal(str, object, object)


class ChatWorker(QRunnable):
    """Run one synchronous application-service operation away from Qt's UI thread."""

    def __init__(self, request_id: str, operation: Callable[[], object]) -> None:
        super().__init__()
        self.request_id = request_id
        self.operation = operation
        self.signals = ChatWorkerSignals()
        _ACTIVE_WORKERS.add(self)

    def abandon(self) -> None:
        """Release the keepalive after a caller's pool submission fails."""
        _ACTIVE_WORKERS.discard(self)

    @Slot()
    def run(self) -> None:
        try:
            try:
                result = self.operation()
            except Exception as error:
                self.signals.finished.emit(self.request_id, None, error)
            else:
                self.signals.finished.emit(self.request_id, result, None)
        finally:
            _ACTIVE_WORKERS.discard(self)
