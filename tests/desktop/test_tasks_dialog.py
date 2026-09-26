import os
from datetime import date, datetime, time, timedelta, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from companion.domain.errors import StorageError, ValidationError
from companion.domain.models import Goal, Priority, Task
import companion.desktop.tasks_dialog as tasks_dialog_module
from companion.desktop.chat_window import ChatWindow
from companion.desktop.pet_window import PetWindow
from companion.desktop.tasks_dialog import TodayTasksDialog


def make_goal(goal_id="goal-1", name="Study"):
    return Goal(id=goal_id, name=name, priority=Priority.P1)


def make_task(task_id="task-1", target_units=None):
    return Task(
        id=task_id,
        title="Read",
        goal_id="goal-1",
        due_date=date(2026, 9, 24),
        planned_minutes=30,
        priority=Priority.P1,
        target_units=target_units,
        created_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
    )


class FakeTaskService:
    def __init__(self, goals=(), tasks=(), fail_on=None):
        self.goals = list(goals)
        self.tasks = list(tasks)
        self.calls = []
        self.days_requested = []
        self.goal_reads = 0
        self.fail_on = fail_on

    def _fail(self, name):
        if self.fail_on == f"validation:{name}":
            raise ValidationError("private validation detail")
        if self.fail_on == name:
            raise StorageError("private database path must not be shown")

    def list_active_goals(self):
        self.goal_reads += 1
        self._fail("list_active_goals")
        return self.goals

    def list_for_day(self, day):
        self.days_requested.append(day)
        self._fail("list_for_day")
        return [task for task in self.tasks if task.due_date == day]

    def add_goal(self, name, target=None, priority=Priority.P1):
        self._fail("add_goal")
        self.calls.append(("add_goal", name, target, priority))
        goal = make_goal(f"goal-{len(self.goals) + 1}", name)
        self.goals.append(goal)
        return goal

    def add_task(self, **values):
        self._fail("add_task")
        self.calls.append(("add_task", values))

    def mark_completed(self, task_id):
        self._fail("mark_completed")
        self.calls.append(("mark_completed", task_id))

    def complete_units(self, task_id, count):
        self._fail("complete_units")
        self.calls.append(("complete_units", task_id, count))


@pytest.fixture
def task_service():
    return FakeTaskService()


def test_today_tasks_button_opens_single_reused_dialog(qtbot, task_service):
    window = ChatWindow(task_service=task_service)
    qtbot.addWidget(window)
    window.show()
    QTest.mouseClick(window.tasks_button, Qt.MouseButton.LeftButton)
    dialog = window.tasks_dialog
    assert dialog.isVisible()
    QTest.mouseClick(window.tasks_button, Qt.MouseButton.LeftButton)
    assert window.tasks_dialog is dialog


def test_reopening_tasks_refreshes_date_and_new_tasks_use_that_date(qtbot, monkeypatch):
    class MutableDate:
        current = date(2026, 9, 24)

        @classmethod
        def today(cls):
            return cls.current

    monkeypatch.setattr(tasks_dialog_module, "date", MutableDate)
    service = FakeTaskService(goals=[make_goal()])
    window = ChatWindow(task_service=service)
    qtbot.addWidget(window)

    window.open_tasks()
    dialog = window.tasks_dialog
    assert dialog.today == date(2026, 9, 24)

    MutableDate.current = date(2026, 9, 25)
    window.open_tasks()
    assert window.tasks_dialog is dialog
    assert dialog.today == date(2026, 9, 25)
    assert dialog.storage_hint.text() == "2026年09月25日"
    assert service.days_requested[-1] == date(2026, 9, 25)

    dialog.title_input.setText("New day task")
    QTest.mouseClick(dialog.add_task_button, Qt.MouseButton.LeftButton)
    assert service.calls[-1][1]["due_date"] == date(2026, 9, 25)


def test_open_dialog_refreshes_after_midnight_without_reopening(qtbot, monkeypatch):
    class MutableDate:
        current = date(2026, 9, 24)

        @classmethod
        def today(cls):
            return cls.current

    monkeypatch.setattr(tasks_dialog_module, "date", MutableDate)
    second_goal = make_goal("goal-2", "Work")
    service = FakeTaskService(goals=[make_goal(), second_goal])
    dialog = TodayTasksDialog(service)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.goal_combo.setCurrentIndex(1)
    assert dialog.goal_combo.currentData() == "goal-2"

    MutableDate.current = date(2026, 9, 25)
    dialog._day_timer.timeout.emit()

    assert dialog.today == date(2026, 9, 25)
    assert dialog.storage_hint.text() == "2026年09月25日"
    assert service.days_requested[-1] == date(2026, 9, 25)
    assert dialog._day_timer.isActive()
    assert dialog.goal_combo.currentData() == "goal-2"

    dialog.title_input.setText("Just after midnight")
    QTest.mouseClick(dialog.add_task_button, Qt.MouseButton.LeftButton)

    assert service.calls[-1][1]["due_date"] == date(2026, 9, 25)
    assert service.calls[-1][1]["goal_id"] == "goal-2"


def test_add_task_checks_day_before_periodic_refresh(qtbot, monkeypatch):
    class MutableDate:
        current = date(2026, 9, 24)

        @classmethod
        def today(cls):
            return cls.current

    monkeypatch.setattr(tasks_dialog_module, "date", MutableDate)
    service = FakeTaskService(goals=[make_goal()])
    dialog = TodayTasksDialog(service)
    qtbot.addWidget(dialog)
    dialog.title_input.setText("Just after midnight")

    MutableDate.current = date(2026, 9, 25)
    QTest.mouseClick(dialog.add_task_button, Qt.MouseButton.LeftButton)

    assert dialog.today == date(2026, 9, 25)
    assert service.calls[-1][1]["due_date"] == date(2026, 9, 25)


def test_explicitly_injected_date_stays_fixed_when_live_clock_is_later(qtbot, monkeypatch):
    class LaterDate:
        @classmethod
        def today(cls):
            return date(2026, 9, 25)

    monkeypatch.setattr(tasks_dialog_module, "date", LaterDate)
    service = FakeTaskService(goals=[make_goal()])
    fixed_day = date(2026, 9, 24)
    dialog = TodayTasksDialog(service, today=fixed_day)
    qtbot.addWidget(dialog)
    dialog.title_input.setText("Fixed date task")

    dialog.refresh()
    QTest.mouseClick(dialog.add_task_button, Qt.MouseButton.LeftButton)

    assert dialog.today == fixed_day
    assert service.calls[-1][1]["due_date"] == fixed_day
    assert not dialog._day_timer.isActive()


def test_empty_day_shows_explanation(qtbot, task_service):
    dialog = TodayTasksDialog(task_service, today=date(2026, 9, 24))
    qtbot.addWidget(dialog)
    dialog.show()
    assert dialog.empty_label.isVisible()
    assert "还没有任务" in dialog.empty_label.text()


def test_enabled_goal_is_available_for_task_creation(qtbot):
    service = FakeTaskService(goals=[make_goal()])
    dialog = TodayTasksDialog(service, today=date(2026, 9, 24))
    qtbot.addWidget(dialog)
    assert dialog.goal_combo.count() == 1
    assert dialog.goal_combo.currentData() == "goal-1"


def test_add_task_passes_selected_values_and_injected_day(qtbot):
    today = date(2026, 9, 24)
    service = FakeTaskService(goals=[make_goal()])
    dialog = TodayTasksDialog(service, today=today)
    qtbot.addWidget(dialog)
    dialog.title_input.setText("Review notes")
    dialog.minutes_input.setValue(45)
    dialog.priority_combo.setCurrentIndex(dialog.priority_combo.findData(Priority.P0))
    dialog.target_input.setValue(6)
    QTest.mouseClick(dialog.add_task_button, Qt.MouseButton.LeftButton)
    assert service.calls == [(
        "add_task",
        {
            "title": "Review notes",
            "goal_id": "goal-1",
            "due_date": today,
            "planned_minutes": 45,
            "priority": Priority.P0,
            "planned_start_at": None,
            "target_units": 6,
        },
    )]


def test_blank_planned_time_is_passed_as_none(qtbot):
    service = FakeTaskService(goals=[make_goal()])
    dialog = TodayTasksDialog(service, today=date(2026, 9, 26))
    qtbot.addWidget(dialog)
    dialog.title_input.setText("Vocabulary")
    QTest.mouseClick(dialog.add_task_button, Qt.MouseButton.LeftButton)
    assert service.calls[-1][1]["planned_start_at"] is None


def test_planned_local_time_is_resolved_before_task_service_write(qtbot):
    local_tz = timezone(timedelta(hours=8))

    class FixedResolver:
        def resolve_local(self, day, local_time):
            return datetime.combine(day, local_time).replace(tzinfo=local_tz).astimezone(timezone.utc)

    service = FakeTaskService(goals=[make_goal()])
    dialog = TodayTasksDialog(
        service, today=date(2026, 9, 26), clock=FixedResolver()
    )
    qtbot.addWidget(dialog)
    dialog.title_input.setText("Vocabulary")
    dialog.planned_start_enabled.setChecked(True)
    dialog.planned_start_date_input.setDate(
        dialog.planned_start_date_input.date().fromString("2026-09-26", "yyyy-MM-dd")
    )
    dialog.planned_start_time_input.setTime(
        dialog.planned_start_time_input.time().fromString("19:30", "HH:mm")
    )
    QTest.mouseClick(dialog.add_task_button, Qt.MouseButton.LeftButton)
    assert service.calls[-1][1]["planned_start_at"] == datetime(
        2026, 9, 26, 11, 30, tzinfo=timezone.utc
    )


def test_create_goal_calls_task_service_and_selects_new_goal(qtbot):
    service = FakeTaskService()
    dialog = TodayTasksDialog(service, today=date(2026, 9, 24))
    qtbot.addWidget(dialog)
    dialog.goal_name_input.setText("Language")
    dialog.goal_target_input.setText("Practice weekly")
    QTest.mouseClick(dialog.add_goal_button, Qt.MouseButton.LeftButton)
    assert service.calls[0] == ("add_goal", "Language", "Practice weekly", Priority.P1)
    assert dialog.goal_combo.currentText() == "Language"


def test_selected_task_actions_call_service(qtbot):
    service = FakeTaskService(
        goals=[make_goal()],
        tasks=[make_task("ordinary"), make_task("counted", target_units=10)],
    )
    dialog = TodayTasksDialog(service, today=date(2026, 9, 24))
    qtbot.addWidget(dialog)
    dialog.task_list.setCurrentRow(0)
    QTest.mouseClick(dialog.complete_button, Qt.MouseButton.LeftButton)
    dialog.task_list.setCurrentRow(1)
    dialog.progress_input.setValue(3)
    QTest.mouseClick(dialog.progress_button, Qt.MouseButton.LeftButton)
    assert ("mark_completed", "ordinary") in service.calls
    assert ("complete_units", "counted", 3) in service.calls


def test_storage_error_is_safe_and_keeps_chat_and_pet_open(qtbot):
    service = FakeTaskService(goals=[make_goal()], fail_on="add_task")
    chat = ChatWindow(task_service=service)
    pet = PetWindow(chat)
    qtbot.addWidget(chat)
    qtbot.addWidget(pet)
    chat.show()
    pet.show()
    QTest.mouseClick(chat.tasks_button, Qt.MouseButton.LeftButton)
    dialog = chat.tasks_dialog
    dialog.title_input.setText("Read")
    QTest.mouseClick(dialog.add_task_button, Qt.MouseButton.LeftButton)
    assert "暂时不可用" in dialog.status_label.text()
    assert "private database path" not in dialog.status_label.text()
    assert dialog.isVisible() and chat.isVisible() and pet.isVisible()


def test_validation_error_is_distinct_from_storage_failure(qtbot):
    service = FakeTaskService(goals=[make_goal()], fail_on="validation:add_task")
    dialog = TodayTasksDialog(service, today=date(2026, 9, 24))
    qtbot.addWidget(dialog)
    dialog.title_input.setText("Read")

    QTest.mouseClick(dialog.add_task_button, Qt.MouseButton.LeftButton)

    assert dialog.status_label.text() == "请检查填写内容后重试。"
    assert "本地任务暂时不可用" not in dialog.status_label.text()
    assert "private validation detail" not in dialog.status_label.text()


def test_reopening_tasks_recovers_after_temporary_goal_read_failure(qtbot):
    service = FakeTaskService(goals=[make_goal()], fail_on="list_active_goals")
    window = ChatWindow(task_service=service)
    qtbot.addWidget(window)

    window.open_tasks()
    assert not window.tasks_dialog.add_task_button.isEnabled()

    service.fail_on = None
    window.open_tasks()

    assert window.tasks_dialog.add_task_button.isEnabled()
    assert window.tasks_dialog.goal_combo.currentData() == "goal-1"


def test_missing_storage_disables_tasks_and_shows_status(qtbot):
    window = ChatWindow(storage_error="本地数据暂时不可用，任务功能已停用。")
    qtbot.addWidget(window)
    assert not window.tasks_button.isEnabled()
    assert "本地数据暂时不可用" in window.storage_status.text()
