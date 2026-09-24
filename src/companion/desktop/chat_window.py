from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from companion.desktop.tasks_dialog import TodayTasksDialog


class ChatWindow(QDialog):
    """Focusable shell for the future provider-backed conversation UI."""

    def __init__(self, task_service=None, storage_error: str | None = None) -> None:
        super().__init__()
        self.task_service = task_service
        self.tasks_dialog: TodayTasksDialog | None = None
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
            self.tasks_dialog = TodayTasksDialog(self.task_service)
        self.tasks_dialog.show()
        self.tasks_dialog.raise_()
        self.tasks_dialog.activateWindow()
