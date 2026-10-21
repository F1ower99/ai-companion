from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from companion.domain.decisions import Decision, DecisionKind, ReasonCode
from companion.domain.errors import StorageError, ValidationError
from companion.domain.reminders import ReminderAction, ReminderDisplayMode, remaining_minutes
from companion.application.reminder_reply import ParsedReminderReply
from companion.desktop.reminder_reply_dialog import ReminderReplyDialog


_REASON_TEXT = {
    ReasonCode.PLANNED_START_LATE: "已经晚于原计划开始时间。",
    ReasonCode.DEADLINE_RISK: "硬截止时间临近；请按当前估算安排剩余工作。",
    ReasonCode.DEADLINE_MISSED: "原硬截止时间已过，当前估算无法按时完成。",
    ReasonCode.PLAN_OVER_CAPACITY: "今晚剩余任务的估算总时长超过可用时间。",
    ReasonCode.REMAINING_TIME_LOW: "今晚剩余时间已接近这项任务的估算时长。",
    ReasonCode.EXTENSION_DUE: "你请求的延长时间已到，现在重新评估当前计划。",
}

_VALIDATION_TEXT = {
    "Extension must be a whole number from 1 to 120 minutes.": "延期时长需为 1 到 120 分钟。",
    "Only one extension is allowed for this task today.": "这项任务今天已经延期过一次。",
    "An extension cannot be accepted during quiet hours.": "安静时段内不能接受延期。",
    "The hard deadline has already passed.": "任务硬截止时间已过，不能再延期。",
    "The extension would reach quiet hours.": "延长后的时间会进入安静时段。",
    "The extension leaves too little time before quiet hours.": "延长后剩余时间不足以在安静时段开始前完成。",
    "The extension leaves too little time before the hard deadline.": "延长后剩余时间不足以在硬截止前完成。",
    "This task is no longer open.": "这项任务已关闭，提醒操作已失效。",
}


class ReminderCard(QDialog):
    """Small, non-modal renderer for one persisted structured reminder."""

    decisionReady = Signal(object)
    actionFailed = Signal(str)

    def __init__(self, task_service, reminder_service, decision: Decision, parent=None, *, draft_source=None) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        if decision.kind is not DecisionKind.SHOW_REMINDER:
            raise ValueError("ReminderCard requires a SHOW_REMINDER decision.")
        self.task_service = task_service
        self.reminder_service = reminder_service
        self._draft_source = draft_source
        self.decision = decision
        self._close_without_action = False
        self._busy = False
        self.reply_dialog = None
        self.setObjectName("reminderCard")
        self.setWindowTitle("Companion 提醒")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedWidth(370)

        task = self.task_service.get_task(decision.task_id)
        if task is None:
            raise ValueError("The reminder task is no longer available.")
        self.task = task
        goals = {goal.id: goal for goal in self.task_service.list_active_goals()}
        goal = goals.get(task.goal_id)

        self.title_label = QLabel(task.title)
        self.title_label.setObjectName("reminderTitle")
        self.title_label.setWordWrap(True)
        self.priority_label = QLabel(f"P{int(task.priority)} · {goal.name if goal else '目标不可用'}")
        self.priority_label.setObjectName("reminderMetadata")
        detail_parts = [f"预计剩余 {remaining_minutes(task)} 分钟"]
        if task.planned_start_at is not None:
            local_start = task.planned_start_at.astimezone()
            detail_parts.insert(0, "原计划 " + local_start.strftime("%H:%M"))
            delay = max(0, int((decision.generated_at - task.planned_start_at).total_seconds() // 60))
            if delay:
                detail_parts.append(f"已晚 {delay} 分钟")
        self.detail_label = QLabel(" · ".join(detail_parts))
        self.detail_label.setObjectName("reminderDetails")
        reason = (
            ReasonCode.DEADLINE_MISSED
            if ReasonCode.DEADLINE_MISSED in decision.reason_codes
            else next((code for code in decision.reason_codes if code in _REASON_TEXT), None)
        )
        self.reason_label = QLabel(_REASON_TEXT.get(reason, "根据今天的计划重新评估后，建议处理这项任务。"))
        self.reason_label.setObjectName("reminderReason")
        self.reason_label.setWordWrap(True)
        self.error_label = QLabel()
        self.error_label.setObjectName("reminderError")
        self.error_label.setWordWrap(True)

        self.now_button = self._button("现在做", "reminderNowButton")
        self.later_button = self._button("稍后", "reminderLaterButton")
        self.extend_minutes = QSpinBox()
        self.extend_minutes.setObjectName("reminderExtensionMinutes")
        self.extend_minutes.setRange(1, 120)
        self.extend_minutes.setValue(30)
        self.extend_button = self._button("延长 X 分钟", "reminderExtendButton")
        self.skip_button = self._button("今天跳过", "reminderSkipButton")
        self.done_button = self._button("已完成", "reminderDoneButton")
        self.reply_button = self._button('回复提醒…', 'reminderReplyButton')

        row_one = QHBoxLayout()
        row_one.addWidget(self.now_button)
        row_one.addWidget(self.later_button)
        row_two = QHBoxLayout()
        row_two.addWidget(self.extend_minutes)
        row_two.addWidget(self.extend_button)
        row_three = QHBoxLayout()
        row_three.addWidget(self.skip_button)
        row_three.addWidget(self.done_button)
        row_three.addWidget(self.reply_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.title_label)
        layout.addWidget(self.priority_label)
        layout.addWidget(self.detail_label)
        layout.addWidget(self.reason_label)
        layout.addLayout(row_one)
        layout.addLayout(row_two)
        layout.addLayout(row_three)
        layout.addWidget(self.error_label)
        self.now_button.clicked.connect(lambda: self._submit(ReminderAction.NOW))
        self.later_button.clicked.connect(lambda: self._submit(ReminderAction.LATER))
        self.extend_button.clicked.connect(
            lambda: self._submit(ReminderAction.EXTEND, self.extend_minutes.value())
        )
        self.skip_button.clicked.connect(lambda: self._submit(ReminderAction.SKIP_TODAY))
        self.done_button.clicked.connect(lambda: self._submit(ReminderAction.DONE))
        self.reply_button.clicked.connect(self.open_reply)
        if decision.display_mode is ReminderDisplayMode.SILENT_NON_MODAL:
            self.setProperty("silentNonModal", True)
        self.setStyleSheet(
            "QDialog#reminderCard { background: #f7f5f1; color: #253c3b; border: 1px solid #b9c8c0; border-radius: 12px; }"
            "QLabel#reminderTitle { color: #253c3b; font-size: 16px; font-weight: 650; }"
            "QLabel#reminderMetadata, QLabel#reminderDetails { color: #607270; font-size: 12px; }"
            "QLabel#reminderReason { color: #354b49; }"
            "QLabel#reminderError { color: #a14343; }"
            "QPushButton { color: #253c3b; padding: 7px 8px; border: 0; border-radius: 7px; background: #dfe9e3; }"
            "QPushButton:disabled { color: #607270; background: #e5e5e1; }"
            "QSpinBox { color: #253c3b; background: #ffffff; }"
        )

    @staticmethod
    def _button(label: str, object_name: str) -> QPushButton:
        button = QPushButton(label)
        button.setObjectName(object_name)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    def open_reply(self):
        if self._busy or self._close_without_action or not self.isVisible():
            return
        if self.reply_dialog is None:
            self.reply_dialog = ReminderReplyDialog(self.task.title, self._apply_reply, self,
                                                    draft_source=self._draft_source)
        if self.reply_dialog.isVisible():
            self.reply_dialog.raise_()
            self.reply_dialog.activateWindow()
        else:
            self.reply_dialog.begin()

    def _apply_reply(self, proposal):
        if (not isinstance(proposal, ParsedReminderReply) or self._busy
                or self._close_without_action or not self.isVisible()):
            return '这条提醒已失效，请使用当前提醒。'
        if self._submit(proposal.action, proposal.minutes):
            return None
        return self.error_label.text() or '这条提醒暂时不可用。'

    def _submit(self, action: ReminderAction, minutes: int | None = None) -> bool:
        if self._busy:
            return False
        self._busy = True
        self._set_buttons_enabled(False)
        self.error_label.clear()
        try:
            result = self.reminder_service.respond(
                self.task.id,
                action,
                minutes=minutes,
                idempotency_key=str(uuid4()),
            )
        except ValidationError as error:
            self.error_label.setText(
                _VALIDATION_TEXT.get(str(error), "这个时间安排不可用，请调整后重试。")
            )
            self._set_buttons_enabled(True)
            self._busy = False
            self.actionFailed.emit("validation")
            return False
        except StorageError:
            self.error_label.setText("本地数据暂时不可用，提醒仍保留。")
            self._set_buttons_enabled(True)
            self._busy = False
            self.actionFailed.emit("storage")
            return False
        except Exception:
            self.error_label.setText("操作未能完成，提醒仍保留。")
            self._set_buttons_enabled(True)
            self._busy = False
            self.actionFailed.emit("operation")
            return False
        self._close_without_action = True
        self.decisionReady.emit(result)
        self.close()
        return True

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for button in (self.now_button, self.later_button, self.extend_button,
                       self.skip_button, self.done_button, self.reply_button):
            button.setEnabled(enabled)
        self.extend_minutes.setEnabled(enabled)

    def dismiss(self) -> None:
        self._close_without_action = True
        self.close()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self.screen() is not None:
            area = self.screen().availableGeometry()
            self.move(area.right() - self.width() - 24, area.bottom() - self.height() - 24)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self.reply_dialog is not None:
            self.reply_dialog.invalidate()
        if self._close_without_action:
            event.accept()
            return
        event.ignore()
        self._submit(ReminderAction.CLOSE)

    def hideEvent(self, event):
        if self.reply_dialog is not None:
            self.reply_dialog.invalidate()
        super().hideEvent(event)
