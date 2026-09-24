from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class ChatWindow(QDialog):
    """Focusable shell for the future provider-backed conversation UI."""

    def __init__(self) -> None:
        super().__init__()
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

        self.input = QLineEdit()
        self.input.setPlaceholderText("模型接入后可在这里输入")
        self.input.setEnabled(False)
        self.send_button = QPushButton("发送")
        self.send_button.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(status)
        layout.addStretch(1)
        layout.addWidget(self.input)
        layout.addWidget(self.send_button)

        self.setStyleSheet(
            """
            QDialog { background: #f7f5f1; color: #253c3b; }
            QLabel#chatTitle { font-size: 20px; font-weight: 650; }
            QLabel#chatStatus { color: #607270; font-size: 13px; }
            QLineEdit { padding: 10px; border: 1px solid #d7dfda; border-radius: 10px; }
            QPushButton { padding: 9px; border: 0; border-radius: 9px; background: #98b9aa; }
            """
        )
