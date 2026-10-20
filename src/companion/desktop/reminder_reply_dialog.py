"""Explicitly opened, transient reminder command preview; never general chat."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from companion.application.reminder_reply import parse_reminder_reply
from companion.domain.errors import ValidationError
from companion.domain.reminders import ReminderAction

_SUMMARIES = {
    ReminderAction.NOW: '现在开始这项任务。',
    ReminderAction.LATER: '按现有设置稍后再评估这条提醒。',
    ReminderAction.SKIP_TODAY: '今天跳过这项任务的提醒。',
    ReminderAction.DONE: '将这项任务标记为已完成。',
}


class ReminderReplyDialog(QDialog):
    def __init__(self, task_title, apply_proposal, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.apply_proposal = apply_proposal
        self._proposal, self._active, self._busy = None, False, False
        self.setWindowTitle('回复这条提醒')
        self.setFixedWidth(360)
        title = QLabel(task_title[:120])
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        self.reply_input = QLineEdit()
        # One overflow sentinel prevents a pasted long command being silently
        # truncated to a valid 128-character command before parser validation.
        self.reply_input.setMaxLength(129)
        self.reply_input.setPlaceholderText('例如：再给我半小时')
        self.preview_button = QPushButton('预览')
        self.confirm_button = QPushButton('确认操作')
        self.cancel_button = QPushButton('取消')
        for button in (self.preview_button, self.confirm_button, self.cancel_button):
            button.setAutoDefault(False)
            button.setDefault(False)
        self.confirm_button.setEnabled(False)
        self.preview_label = QLabel()
        self.preview_label.setTextFormat(Qt.TextFormat.PlainText)
        self.preview_label.setWordWrap(True)
        self.status_label = QLabel()
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        entry = QHBoxLayout()
        entry.addWidget(self.reply_input, 1)
        entry.addWidget(self.preview_button)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.confirm_button)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addLayout(entry)
        layout.addWidget(self.preview_label)
        layout.addWidget(self.status_label)
        layout.addLayout(actions)
        self.reply_input.textChanged.connect(self._changed)
        self.reply_input.returnPressed.connect(self._preview)
        self.preview_button.clicked.connect(self._preview)
        self.confirm_button.clicked.connect(self._confirm)
        self.cancel_button.clicked.connect(self.reject)

    def begin(self):
        self._active, self._busy = True, False
        self._clear()
        self.show()
        self.raise_()
        self.activateWindow()
        self.reply_input.setFocus()

    def _changed(self, *_args):
        self._proposal = None
        self.confirm_button.setEnabled(False)
        self.preview_label.clear()
        self.status_label.clear()

    def _clear(self):
        # clear() is undoable; setText resets undo history as well as contents.
        self.reply_input.setText('')
        self._changed()

    def _preview(self):
        if not self._active or not self.isVisible() or self._busy:
            return
        self._changed()
        try:
            proposal = parse_reminder_reply(self.reply_input.text())
        except ValidationError:
            self.status_label.setText('支持“现在做”“稍后”“延长30分钟”“今天跳过”“已完成”等明确回复。')
            return
        self._proposal = proposal
        if proposal.action is ReminderAction.EXTEND:
            self.preview_label.setText(f'申请延长 {proposal.minutes} 分钟；确认后会按剩余安排校验，硬截止不变。')
        else:
            self.preview_label.setText(_SUMMARIES[proposal.action])
        self.confirm_button.setEnabled(True)

    def _confirm(self):
        if not self._active or not self.isVisible() or self._busy or self._proposal is None:
            return
        proposal = self._proposal
        self._busy = True
        self.confirm_button.setEnabled(False)
        try:
            try:
                error = self.apply_proposal(proposal)
            except Exception:
                error = '这条提醒暂时不可用，请稍后重试。'
            if error is None:
                self.accept()
            elif self._active and self.isVisible():
                self.status_label.setText(error)
        finally:
            self._busy = False
            self.confirm_button.setEnabled(self._active and self.isVisible() and self._proposal is not None)

    def invalidate(self):
        self._active = False
        self._clear()
        self.hide()

    def hideEvent(self, event):
        self._active = False
        self._clear()
        super().hideEvent(event)
