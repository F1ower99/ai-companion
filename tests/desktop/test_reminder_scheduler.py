import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from companion.desktop.reminder_scheduler import ReminderScheduler
from companion.domain.decisions import Decision, DecisionKind, ReasonCode
from datetime import datetime, timezone


class FakeService:
    def __init__(self):
        self.calls = 0
        self.on_evaluate = None
        self.fail = False
        self.decision = None

    def evaluate(self):
        self.calls += 1
        if self.on_evaluate is not None:
            callback, self.on_evaluate = self.on_evaluate, None
            callback()
        if self.fail:
            raise RuntimeError("private task data")
        if self.decision is not None:
            return self.decision
        return Decision(
            DecisionKind.SILENT,
            datetime(2026, 9, 26, 12, tzinfo=timezone.utc),
            (ReasonCode.NO_ELIGIBLE_TASK,),
        )


def test_scheduler_evaluates_immediately_and_never_exceeds_minute_interval(qtbot):
    service = FakeService()
    scheduler = ReminderScheduler(service, interval_ms=120_000)
    decisions = []
    scheduler.decisionReady.connect(decisions.append)
    scheduler.start()
    assert service.calls == 1
    assert scheduler.timer.interval() == 60_000
    assert scheduler.timer.isActive()
    assert len(decisions) == 1
    assert decisions[0].kind is DecisionKind.SILENT
    scheduler.stop()
    assert not scheduler.timer.isActive()


def test_scheduler_prevents_reentrant_evaluations(qtbot):
    service = FakeService()
    scheduler = ReminderScheduler(service)
    service.on_evaluate = scheduler.evaluate_now
    scheduler.evaluate_now()
    assert service.calls == 1


def test_scheduler_contains_errors_and_retries_on_next_bounded_tick(qtbot):
    service = FakeService()
    service.fail = True
    scheduler = ReminderScheduler(service)
    scheduler.evaluate_now()
    assert service.calls == 1
    assert scheduler.last_error == "reminder_evaluation_failed"
    assert scheduler.timer.interval() == 60_000


def test_scheduler_wakes_at_explicit_reevaluation_when_sooner_than_periodic_tick(qtbot):
    service = FakeService()
    now = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)
    service.decision = Decision(
        DecisionKind.WAIT,
        now,
        (ReasonCode.USER_SNOOZE,),
        next_evaluate_at=now.replace(second=15),
    )
    scheduler = ReminderScheduler(service, interval_ms=60_000)
    scheduler.evaluate_now()
    assert scheduler.timer.isSingleShot()
    assert scheduler.timer.interval() == 15_000
    scheduler.stop()
