import os
from datetime import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

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
