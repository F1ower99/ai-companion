from PySide6.QtCore import QObject, QTimer, Signal


class ReminderScheduler(QObject):
    """Qt wake-up adapter; all eligibility decisions stay in the application/domain."""

    decisionReady = Signal(object)

    def __init__(self, service, parent=None, interval_ms: int = 60_000) -> None:
        super().__init__(parent)
        self.service = service
        self.interval_ms = min(max(int(interval_ms), 1), 60_000)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(self.interval_ms)
        self.timer.timeout.connect(self.evaluate_now)
        self.last_error: str | None = None
        self._evaluating = False

    def start(self) -> None:
        self.evaluate_now()

    def stop(self) -> None:
        self.timer.stop()

    def evaluate_now(self) -> None:
        if self._evaluating:
            return
        self._evaluating = True
        try:
            decision = self.service.evaluate()
            self.last_error = None
            self.decisionReady.emit(decision)
            delay = self.interval_ms
            if decision.next_evaluate_at is not None:
                seconds = (decision.next_evaluate_at - decision.generated_at).total_seconds()
                if seconds > 0:
                    delay = min(delay, max(1_000, int(seconds * 1_000)))
            self.timer.start(delay)
        except Exception:
            # The next bounded timer tick retries; task/pet UI remains available.
            self.last_error = "reminder_evaluation_failed"
            self.timer.start(self.interval_ms)
        finally:
            self._evaluating = False
