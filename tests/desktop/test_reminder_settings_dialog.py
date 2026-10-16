import os
from datetime import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QCheckBox, QLabel

from companion.desktop.reminder_settings_dialog import ReminderSettingsDialog
from companion.domain.errors import StorageError
from companion.domain.reminders import ReminderPreferences


class FakeReminderService:
    def __init__(self, preferences=None, fail=False):
        self.preferences = preferences or ReminderPreferences()
        self.fail = fail
        self.saved = []

    def get_preferences(self):
        if self.fail:
            raise StorageError("private settings file")
        return self.preferences

    def update_preferences(self, preferences):
        if self.fail:
            raise StorageError("private settings file")
        self.preferences = preferences
        self.saved.append(preferences)


def test_settings_dialog_persists_enabled_and_quiet_hours(qtbot):
    original = ReminderPreferences()
    service = FakeReminderService(original)
    dialog = ReminderSettingsDialog(service)
    qtbot.addWidget(dialog)
    dialog.enabled_checkbox.setChecked(False)
    dialog.quiet_start_input.setTime(time(21, 30))
    dialog.quiet_end_input.setTime(time(7, 30))
    QTest.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
    assert service.preferences.enabled is False
    assert service.preferences.quiet_start == time(21, 30)
    assert service.preferences.quiet_end == time(7, 30)
    assert service.preferences.global_cooldown_minutes == original.global_cooldown_minutes
    assert service.preferences.task_cooldown_minutes == original.task_cooldown_minutes
    assert service.preferences.later_minutes == original.later_minutes
    assert len(service.saved) == 1


def test_equal_quiet_boundaries_are_rejected_without_closing(qtbot):
    dialog = ReminderSettingsDialog(FakeReminderService())
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.quiet_end_input.setTime(dialog.quiet_start_input.time())
    QTest.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
    assert dialog.isVisible()
    assert "两个不同" in dialog.status_label.text()


def test_settings_storage_failure_is_displayed_safely(qtbot):
    dialog = ReminderSettingsDialog(FakeReminderService(fail=True))
    qtbot.addWidget(dialog)
    assert not dialog.save_button.isEnabled()
    assert "本地提醒设置暂时不可用" in dialog.status_label.text()
    assert "private settings file" not in dialog.status_label.text()

class FakeActivityAwarenessService:
    def __init__(self, enabled=False, available=True, fail=False):
        from companion.domain.activity import ActivityAwarenessPreferences
        self.preferences = ActivityAwarenessPreferences(enabled=enabled)
        self.available = available
        self.fail = fail
        self.saved = []

    def get_preferences(self):
        if self.fail:
            raise StorageError("private activity setting")
        return self.preferences

    def set_enabled(self, enabled):
        from companion.domain.activity import ActivityAwarenessPreferences
        if self.fail:
            raise StorageError("private activity setting")
        self.preferences = ActivityAwarenessPreferences(enabled=enabled)
        self.saved.append(enabled)
        return self.preferences


def test_activity_awareness_control_is_opt_in_and_explains_what_it_reads(qtbot):
    activity = FakeActivityAwarenessService()
    dialog = ReminderSettingsDialog(FakeReminderService(), activity_awareness_service=activity)
    qtbot.addWidget(dialog)

    control = dialog.findChild(QCheckBox, "activityAwarenessEnabled")
    privacy_copy = dialog.findChild(QLabel, "activityAwarenessPrivacy").text()

    assert control is not None
    assert control.isChecked() is False
    assert control.isEnabled() is True
    assert "5 分钟" in privacy_copy
    assert "不读取应用名称或输入内容" in privacy_copy


def test_activity_toggle_persists_immediately_and_emits_only_after_success(qtbot):
    from PySide6.QtTest import QSignalSpy

    activity = FakeActivityAwarenessService()
    dialog = ReminderSettingsDialog(FakeReminderService(), activity_awareness_service=activity)
    qtbot.addWidget(dialog)
    changed = QSignalSpy(dialog.activityAwarenessChanged)
    control = dialog.findChild(QCheckBox, "activityAwarenessEnabled")

    control.setChecked(True)

    assert activity.preferences.enabled is True
    assert activity.saved == [True]
    assert changed.count() == 1
    assert changed.at(0)[0] is True


def test_activity_toggle_reverts_on_storage_error(qtbot):
    activity = FakeActivityAwarenessService(fail=True)
    dialog = ReminderSettingsDialog(FakeReminderService(), activity_awareness_service=activity)
    qtbot.addWidget(dialog)
    control = dialog.findChild(QCheckBox, "activityAwarenessEnabled")

    control.setChecked(True)

    assert control.isChecked() is False
    assert "活动状态设置暂时不可用" in dialog.status_label.text()


def test_activity_toggle_is_disabled_when_platform_source_is_unsupported(qtbot):
    activity = FakeActivityAwarenessService(available=False)
    dialog = ReminderSettingsDialog(FakeReminderService(), activity_awareness_service=activity)
    qtbot.addWidget(dialog)
    control = dialog.findChild(QCheckBox, "activityAwarenessEnabled")

    assert control.isChecked() is False
    assert control.isEnabled() is False

def test_chat_window_requests_one_reminder_evaluation_after_activity_toggle(qtbot):
    from PySide6.QtTest import QSignalSpy
    from companion.desktop.chat_window import ChatWindow

    activity = FakeActivityAwarenessService()
    chat = ChatWindow(
        reminder_service=FakeReminderService(),
        activity_awareness_service=activity,
    )
    qtbot.addWidget(chat)
    chat.open_reminder_settings()
    evaluations = QSignalSpy(chat.reminderEvaluationRequested)
    control = chat.reminder_settings_dialog.findChild(
        QCheckBox,
        "activityAwarenessEnabled",
    )

    control.setChecked(True)

    assert evaluations.count() == 1
