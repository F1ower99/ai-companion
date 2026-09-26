import os
from dataclasses import replace
from datetime import date, datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from companion.desktop.chat_window import ChatWindow
from companion.desktop.reminder_card import ReminderCard
from companion.domain.decisions import Decision, DecisionKind, ReasonCode
from companion.domain.errors import StorageError, ValidationError
from companion.domain.models import Goal, Priority, Task
from companion.domain.reminders import ReminderAction, ReminderCategory, ReminderDisplayMode


NOW = datetime(2026, 9, 26, 12, 10, tzinfo=timezone.utc)


def make_task():
    return Task(
        id="task-1", title="Review vocabulary", goal_id="goal-1",
        due_date=date(2026, 9, 26), planned_minutes=30, priority=Priority.P1,
        planned_start_at=datetime(2026, 9, 26, 11, 30, tzinfo=timezone.utc),
        created_at=datetime(2026, 9, 26, 8, tzinfo=timezone.utc),
    )


class FakeTaskService:
    def __init__(self):
        self.task = make_task()
        self.fail_get = False

    def get_task(self, task_id):
        if self.fail_get:
            raise StorageError("private database failure")
        return self.task if task_id == self.task.id else None

    def list_active_goals(self):
        return [Goal("goal-1", "Study")]


class FakeReminderService:
    def __init__(self, result=None, error=None):
        self.result = result or Decision(
            DecisionKind.WAIT, NOW, (ReasonCode.USER_SNOOZE,),
            next_evaluate_at=NOW,
        )
        self.error = error
        self.calls = []

    def respond(self, task_id, action, minutes=None, idempotency_key=None):
        self.calls.append((task_id, action, minutes, idempotency_key))
        if self.error is not None:
            raise self.error
        return self.result


def make_decision(reason=ReasonCode.PLANNED_START_LATE, mode=ReminderDisplayMode.NORMAL):
    category = (
        ReminderCategory.DEADLINE
        if reason in (ReasonCode.DEADLINE_RISK, ReasonCode.DEADLINE_MISSED)
        else ReminderCategory.SCHEDULE
    )
    return Decision(
        DecisionKind.SHOW_REMINDER,
        NOW,
        (reason,),
        task_id="task-1",
        display_mode=mode,
        category=category,
    )


@pytest.mark.parametrize("button, action, minutes", [
    ("reminderNowButton", ReminderAction.NOW, None),
    ("reminderLaterButton", ReminderAction.LATER, None),
    ("reminderExtendButton", ReminderAction.EXTEND, 30),
    ("reminderSkipButton", ReminderAction.SKIP_TODAY, None),
    ("reminderDoneButton", ReminderAction.DONE, None),
])
def test_each_card_action_is_forwarded_once(qtbot, button, action, minutes):
    service = FakeReminderService()
    card = ReminderCard(FakeTaskService(), service, make_decision())
    qtbot.addWidget(card)
    card.extend_minutes.setValue(30)
    card.show()
    QTest.mouseClick(card.findChild(type(card.now_button), button), Qt.MouseButton.LeftButton)
    assert len(service.calls) == 1
    task_id, forwarded, forwarded_minutes, action_id = service.calls[0]
    assert task_id == "task-1"
    assert forwarded is action
    assert forwarded_minutes == minutes
    assert action_id
    assert not card.isVisible()


def test_card_is_non_modal_and_does_not_request_keyboard_focus(qtbot):
    card = ReminderCard(FakeTaskService(), FakeReminderService(), make_decision(
        ReasonCode.DEADLINE_MISSED,
        ReminderDisplayMode.SILENT_NON_MODAL,
    ))
    qtbot.addWidget(card)
    card.show()
    assert card.windowModality() is Qt.WindowModality.NonModal
    assert card.focusPolicy() is Qt.FocusPolicy.NoFocus
    assert card.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert card.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    for button in (card.now_button, card.later_button, card.extend_button,
                   card.skip_button, card.done_button):
        assert button.focusPolicy() is Qt.FocusPolicy.NoFocus
    assert "无法按时完成" in card.reason_label.text()


def test_invalid_extension_keeps_card_visible_and_shows_safe_feedback(qtbot):
    service = FakeReminderService(error=ValidationError("private hard deadline"))
    card = ReminderCard(FakeTaskService(), service, make_decision())
    qtbot.addWidget(card)
    card.show()
    QTest.mouseClick(card.extend_button, Qt.MouseButton.LeftButton)
    assert card.isVisible()
    assert "不可用" in card.error_label.text()
    assert "private hard deadline" not in card.error_label.text()
    assert len(service.calls) == 1


def test_storage_failure_keeps_card_visible_and_does_not_show_private_error(qtbot):
    service = FakeReminderService(error=StorageError("private database path"))
    card = ReminderCard(FakeTaskService(), service, make_decision())
    qtbot.addWidget(card)
    card.show()
    QTest.mouseClick(card.now_button, Qt.MouseButton.LeftButton)
    assert card.isVisible()
    assert "本地数据暂时不可用" in card.error_label.text()
    assert "private database path" not in card.error_label.text()


def test_close_records_close_action_once(qtbot):
    service = FakeReminderService()
    card = ReminderCard(FakeTaskService(), service, make_decision())
    qtbot.addWidget(card)
    card.show()
    card.close()
    assert len(service.calls) == 1
    assert service.calls[0][1] is ReminderAction.CLOSE


def test_chat_shell_only_renders_show_decisions(qtbot):
    reminder_service = FakeReminderService()
    window = ChatWindow(FakeTaskService(), reminder_service=reminder_service)
    qtbot.addWidget(window)
    window.show_decision(Decision(DecisionKind.WAIT, NOW, (ReasonCode.FOCUS_GRACE,)))
    window.show_decision(Decision(DecisionKind.SILENT, NOW, (ReasonCode.QUIET_HOURS,)))
    assert window.reminder_card is None
    window.show_decision(make_decision())
    assert window.reminder_card is not None
    assert window.reminder_card.isVisible()


def test_silent_decision_dismisses_an_existing_card(qtbot):
    window = ChatWindow(FakeTaskService(), reminder_service=FakeReminderService())
    qtbot.addWidget(window)
    window.show_decision(make_decision())
    card = window.reminder_card
    assert card is not None and card.isVisible()
    window.show_decision(Decision(
        DecisionKind.SILENT, NOW, (ReasonCode.REMINDERS_DISABLED,),
    ))
    assert not card.isVisible()


def test_completed_task_decision_dismisses_its_existing_card(qtbot):
    from companion.domain.models import TaskStatus

    window = ChatWindow(FakeTaskService(), reminder_service=FakeReminderService())
    qtbot.addWidget(window)
    window.show_decision(make_decision())
    card = window.reminder_card
    window.task_service.task = replace(window.task_service.task, status=TaskStatus.COMPLETED)
    window.show_decision(Decision(DecisionKind.WAIT, NOW, (ReasonCode.NO_ELIGIBLE_TASK,)))
    assert card is not None and not card.isVisible()


def test_storage_failure_silent_decision_dismisses_without_task_lookup(qtbot):
    tasks = FakeTaskService()
    window = ChatWindow(tasks, reminder_service=FakeReminderService())
    qtbot.addWidget(window)
    window.show_decision(make_decision())
    card = window.reminder_card
    tasks.fail_get = True
    window.show_decision(Decision(DecisionKind.SILENT, NOW, (ReasonCode.STORAGE_UNAVAILABLE,)))
    assert card is not None and not card.isVisible()


def test_repeated_show_for_same_task_refreshes_visible_card(qtbot):
    window = ChatWindow(FakeTaskService(), reminder_service=FakeReminderService())
    qtbot.addWidget(window)
    first_decision = make_decision()
    window.show_decision(first_decision)
    old_card = window.reminder_card
    refreshed = Decision(
        DecisionKind.SHOW_REMINDER,
        NOW.replace(minute=40),
        (ReasonCode.DEADLINE_RISK,),
        task_id="task-1",
        category=ReminderCategory.DEADLINE,
    )
    window.show_decision(refreshed)
    assert old_card is not None and not old_card.isVisible()
    assert window.reminder_card is not old_card
    assert window.reminder_card is not None and window.reminder_card.isVisible()
    assert window.reminder_card.decision == refreshed


def test_extension_validation_displays_the_specific_boundary_reason(qtbot):
    service = FakeReminderService(error=ValidationError("The extension would reach quiet hours."))
    card = ReminderCard(FakeTaskService(), service, make_decision())
    qtbot.addWidget(card)
    card.show()
    QTest.mouseClick(card.extend_button, Qt.MouseButton.LeftButton)
    assert "安静时段" in card.error_label.text()
    assert "不可用" not in card.error_label.text()


def test_extension_validation_distinguishes_quiet_hours_capacity(qtbot):
    service = FakeReminderService(
        error=ValidationError("The extension leaves too little time before quiet hours.")
    )
    card = ReminderCard(FakeTaskService(), service, make_decision())
    qtbot.addWidget(card)
    card.show()
    QTest.mouseClick(card.extend_button, Qt.MouseButton.LeftButton)
    assert "安静时段" in card.error_label.text()
    assert "硬截止" not in card.error_label.text()
