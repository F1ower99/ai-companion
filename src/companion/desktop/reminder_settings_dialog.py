from PySide6.QtCore import QSignalBlocker, QTime, Signal
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
    activityAwarenessChanged = Signal(bool)

    def __init__(self, reminder_service, parent=None, *, activity_awareness_service=None) -> None:
        super().__init__(parent)
        self.reminder_service = reminder_service
        self.activity_awareness_service = activity_awareness_service
        self._activity_preference = None
        self.setWindowTitle("提醒设置")
        self.setMinimumWidth(320)
        self.enabled_checkbox = QCheckBox("启用主动提醒")
        self.enabled_checkbox.setObjectName("remindersEnabled")
        self.activity_awareness_checkbox = QCheckBox("允许活动状态感知")
        self.activity_awareness_checkbox.setObjectName("activityAwarenessEnabled")
        self.activity_privacy_label = QLabel(
            "可选：仅判断当前 Windows 会话最近 5 分钟是否有操作；"
            "不读取应用名称或输入内容，活动状态只保存在内存中。"
        )
        self.activity_privacy_label.setObjectName("activityAwarenessPrivacy")
        self.activity_privacy_label.setWordWrap(True)
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
        form.addRow(self.activity_awareness_checkbox)
        form.addRow("", self.activity_privacy_label)
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
        self.activity_awareness_checkbox.toggled.connect(self._set_activity_awareness)
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
        else:
            self.enabled_checkbox.setChecked(preferences.enabled)
            self.quiet_start_input.setTime(QTime(
                preferences.quiet_start.hour, preferences.quiet_start.minute,
                preferences.quiet_start.second,
            ))
            self.quiet_end_input.setTime(QTime(
                preferences.quiet_end.hour, preferences.quiet_end.minute,
                preferences.quiet_end.second,
            ))

        service = self.activity_awareness_service
        if service is None:
            self.activity_awareness_checkbox.setEnabled(False)
            self.activity_privacy_label.setText(
                self.activity_privacy_label.text() + " 当前设备未提供此功能。"
            )
            return
        try:
            self._activity_preference = service.get_preferences()
        except StorageError:
            self.activity_awareness_checkbox.setEnabled(False)
            self.status_label.setText("活动状态设置暂时不可用。")
            return
        blocker = QSignalBlocker(self.activity_awareness_checkbox)
        self.activity_awareness_checkbox.setChecked(self._activity_preference.enabled)
        del blocker
        if not service.available:
            self.activity_awareness_checkbox.setEnabled(False)
            self.activity_privacy_label.setText(
                self.activity_privacy_label.text() + " 当前设备不支持活动状态检测。"
            )

    def _set_activity_awareness(self, enabled: bool) -> None:
        service = self.activity_awareness_service
        if service is None:
            return
        try:
            updated = service.set_enabled(enabled)
        except (StorageError, ValidationError):
            blocker = QSignalBlocker(self.activity_awareness_checkbox)
            self.activity_awareness_checkbox.setChecked(
                bool(self._activity_preference and self._activity_preference.enabled)
            )
            del blocker
            self.status_label.setText("活动状态设置暂时不可用，尚未更改。")
            return
        self._activity_preference = updated
        self.status_label.setText(
            "活动状态感知已启用。" if updated.enabled else "活动状态感知已暂停。"
        )
        self.activityAwarenessChanged.emit(updated.enabled)

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
