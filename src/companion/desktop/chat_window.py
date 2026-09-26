from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from companion.desktop.tasks_dialog import TodayTasksDialog
from companion.desktop.reminder_card import ReminderCard
from companion.desktop.reminder_settings_dialog import ReminderSettingsDialog
from companion.domain.decisions import Decision, DecisionKind, ReasonCode
from companion.domain.models import TaskStatus


class ChatWindow(QDialog):
    """Focusable shell for the future provider-backed conversation UI."""

    taskStateChanged = Signal()
    reminderEvaluationRequested = Signal()

    def __init__(
        self,
        task_service=None,
        storage_error: str | None = None,
        *,
        clock=None,
        reminder_service=None,
    ) -> None:
        super().__init__()
        self.task_service = task_service
        self.clock = clock or getattr(task_service, "clock", None)
        self.reminder_service = reminder_service
        self.tasks_dialog: TodayTasksDialog | None = None
        self.reminder_settings_dialog: ReminderSettingsDialog | None = None
        self.reminder_card: ReminderCard | None = None
        self.setWindowTitle("AI Companion")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(360, 260)
        self.resize(390, 300)

        title = QLabel("和 Companion 聊聊")
        title.setObjectName("chatTitle")
        status = QLabel("文字对话会在下一阶段接入。当前版本不会发送或保存聊天内容。")
        status.setWordWrap(True)
        status.setObjectName("chatStatus")

        self.storage_status = QLabel(
            storage_error or "本地任务存储已就绪。"
            if task_service is not None
            else storage_error or "本地任务存储尚未配置。"
        )
        self.storage_status.setWordWrap(True)
        self.storage_status.setObjectName("storageStatus")
        self.tasks_button = QPushButton("今日任务")
        self.tasks_button.setObjectName("tasksButton")
        self.tasks_button.setEnabled(task_service is not None)
        self.tasks_button.clicked.connect(self.open_tasks)
        self.reminder_settings_button = QPushButton("提醒设置")
        self.reminder_settings_button.setObjectName("reminderSettingsButton")
        self.reminder_settings_button.setEnabled(reminder_service is not None)
        self.reminder_settings_button.clicked.connect(self.open_reminder_settings)

        self.input = QLineEdit()
        self.input.setPlaceholderText("模型接入后可在这里输入")
        self.input.setEnabled(False)
        self.send_button = QPushButton("发送")
        self.send_button.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(status)
        layout.addWidget(self.storage_status)
        layout.addWidget(self.tasks_button)
        layout.addWidget(self.reminder_settings_button)
        layout.addStretch(1)
        layout.addWidget(self.input)
        layout.addWidget(self.send_button)

        self.setStyleSheet(
            """
            QDialog { background: #f7f5f1; color: #253c3b; }
            QLabel#chatTitle { font-size: 20px; font-weight: 650; }
            QLabel#chatStatus { color: #607270; font-size: 13px; }
            QLabel#storageStatus { color: #607270; font-size: 12px; }
            QLineEdit { padding: 10px; border: 1px solid #d7dfda; border-radius: 10px; }
            QPushButton { padding: 9px; border: 0; border-radius: 9px; background: #98b9aa; }
            """
        )

    def open_tasks(self) -> None:
        if self.task_service is None:
            return
        if self.tasks_dialog is None:
            self.tasks_dialog = TodayTasksDialog(self.task_service, clock=self.clock)
            self.tasks_dialog.tasksChanged.connect(self.taskStateChanged.emit)
        else:
            self.tasks_dialog.refresh()
        self.tasks_dialog.show()
        self.tasks_dialog.raise_()
        self.tasks_dialog.activateWindow()

    def open_reminder_settings(self) -> None:
        if self.reminder_service is None:
            return
        if self.reminder_settings_dialog is None:
            self.reminder_settings_dialog = ReminderSettingsDialog(self.reminder_service, self)
            self.reminder_settings_dialog.preferencesSaved.connect(
                lambda _preferences: self.reminderEvaluationRequested.emit()
            )
        self.reminder_settings_dialog.show()
        self.reminder_settings_dialog.raise_()
        self.reminder_settings_dialog.activateWindow()

    def show_decision(self, decision: Decision) -> None:
        if self.reminder_service is None:
            return
        if decision.kind is not DecisionKind.SHOW_REMINDER:
            card = self.reminder_card
            if card is None or not card.isVisible():
                return
            only_cooldown_wait = (
                decision.kind is DecisionKind.WAIT
                and bool(decision.reason_codes)
                and all(code in (ReasonCode.GLOBAL_COOLDOWN, ReasonCode.TASK_COOLDOWN)
                        for code in decision.reason_codes)
            )
            if (
                decision.kind is DecisionKind.SILENT
                or ReasonCode.IDLE_USER in decision.reason_codes
                or not only_cooldown_wait
            ):
                card.dismiss()
                return
            try:
                task = self.task_service.get_task(card.task.id) if self.task_service is not None else None
            except Exception:
                task = None
            if task is None or task.status is not TaskStatus.OPEN:
                card.dismiss()
            return
        if self.reminder_card is not None and self.reminder_card.isVisible():
            self.reminder_card.dismiss()
        try:
            card = ReminderCard(self.task_service, self.reminder_service, decision)
        except Exception:
            return
        self.reminder_card = card
        card.decisionReady.connect(self.show_decision)
        card.show()
