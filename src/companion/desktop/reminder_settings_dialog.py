from PySide6.QtCore import QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
)

from companion.domain.errors import StorageError, ValidationError
from companion.domain.reminders import ReminderPreferences


class ReminderSettingsDialog(QDialog):
    preferencesSaved = Signal(object)

    def __init__(self, reminder_service, parent=None) -> None:
        super().__init__(parent)
        self.reminder_service = reminder_service
        self.setWindowTitle("提醒设置")
        self.setMinimumWidth(320)
        self.enabled_checkbox = QCheckBox("启用主动提醒")
        self.enabled_checkbox.setObjectName("remindersEnabled")
        self.quiet_start_input = QTimeEdit()
        self.quiet_start_input.setObjectName("quietStartInput")
        self.quiet_start_input.setDisplayFormat("HH:mm")
        self.quiet_end_input = QTimeEdit()
        self.quiet_end_input.setObjectName("quietEndInput")
        self.quiet_end_input.setDisplayFormat("HH:mm")
        self.status_label = QLabel()
        self.status_label.setObjectName("reminderSettingsStatus")
        self.status_label.setWordWrap(True)
        self.save_button = QPushButton("保存")
        self.save_button.setObjectName("saveReminderSettingsButton")
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("cancelReminderSettingsButton")
        form = QFormLayout()
        form.addRow(self.enabled_checkbox)
        form.addRow("安静时段开始", self.quiet_start_input)
        form.addRow("安静时段结束", self.quiet_end_input)
        buttons = QHBoxLayout()
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        layout.addLayout(buttons)
        self.save_button.clicked.connect(self.save)
        self.cancel_button.clicked.connect(self.reject)
        self._load()
        self.setStyleSheet(
            "QDialog { background: #f7f5f1; color: #253c3b; }"
            "QTimeEdit { padding: 7px; border: 1px solid #d7dfda; border-radius: 6px; background: white; }"
            "QPushButton { padding: 8px 10px; border: 0; border-radius: 7px; background: #98b9aa; }"
        )

    def _load(self) -> None:
        try:
            preferences = self.reminder_service.get_preferences()
        except StorageError:
            self.status_label.setText("本地提醒设置暂时不可用。")
            self.save_button.setEnabled(False)
            return
        self.enabled_checkbox.setChecked(preferences.enabled)
        self.quiet_start_input.setTime(QTime(
            preferences.quiet_start.hour, preferences.quiet_start.minute,
            preferences.quiet_start.second,
        ))
        self.quiet_end_input.setTime(QTime(
            preferences.quiet_end.hour, preferences.quiet_end.minute,
            preferences.quiet_end.second,
        ))

    def save(self) -> None:
        try:
            current = self.reminder_service.get_preferences()
            preferences = ReminderPreferences(
                enabled=self.enabled_checkbox.isChecked(),
                quiet_start=self.quiet_start_input.time().toPython(),
                quiet_end=self.quiet_end_input.time().toPython(),
                global_cooldown_minutes=current.global_cooldown_minutes,
                task_cooldown_minutes=current.task_cooldown_minutes,
                later_minutes=current.later_minutes,
            )
            self.reminder_service.update_preferences(preferences)
        except ValidationError:
            self.status_label.setText("安静时段需要设置为两个不同的本地时间。")
            return
        except StorageError:
            self.status_label.setText("本地提醒设置暂时不可用，尚未保存。")
            return
        self.status_label.setText("提醒设置已保存。")
        self.preferencesSaved.emit(preferences)
        self.accept()
