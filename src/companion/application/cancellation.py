from threading import Event


class CancellationFlag:
    """Thread-safe cancellation state shared by the UI and synchronous service."""

    def __init__(self) -> None:
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()
