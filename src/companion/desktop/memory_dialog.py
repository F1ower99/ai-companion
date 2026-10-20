"""Temporary, explicit local-memory inspection; no automatic memory writes."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from companion.application.memory_management import PAGE_SIZE
from companion.domain.models import MemoryKind

KIND_LABELS = {
    MemoryKind.PROFILE: '个人资料', MemoryKind.PREFERENCE: '偏好',
    MemoryKind.BEHAVIORAL: '行为', MemoryKind.EPISODIC: '经历', MemoryKind.CONVERSATION: '对话记忆',
}


class MemoryDialog(QDialog):
    def __init__(self, service, parent=None, *, confirmation_handler=None):
        super().__init__(parent)
        self.service = service
        self.confirmation_handler = confirmation_handler or self._confirm_delete
        self._records, self._offset, self._observed_at = (), 0, None
        self._view_generation = 0
        self.setWindowTitle('本地记忆')
        self.resize(460, 540)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('搜索记忆内容')
        self.search_input.setMaxLength(2000)
        self.search_button = QPushButton('搜索 / 刷新')
        self.kind_combo = QComboBox()
        self.kind_combo.addItem('全部类别', None)
        for kind, label in KIND_LABELS.items():
            self.kind_combo.addItem(label, kind)
        self.include_expired = QCheckBox('显示已过期记忆')
        self.include_expired.setChecked(True)
        self.list_widget = QListWidget()
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(120)
        self.metadata = QLabel()
        self.metadata.setTextFormat(Qt.TextFormat.PlainText)
        self.metadata.setWordWrap(True)
        self.previous_button = QPushButton('上一页')
        self.next_button = QPushButton('下一页')
        self.delete_button = QPushButton('删除选中记忆')
        self.delete_button.setEnabled(False)
        self.status_label = QLabel('只管理本地记忆；删除不影响已发送的请求或对话中的既有内容。')
        self.status_label.setWordWrap(True)
        close_button = QPushButton('关闭')
        search_row = QHBoxLayout()
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.search_button)
        filter_row = QHBoxLayout()
        filter_row.addWidget(self.kind_combo)
        filter_row.addWidget(self.include_expired)
        pages = QHBoxLayout()
        pages.addWidget(self.previous_button)
        pages.addWidget(self.next_button)
        pages.addStretch(1)
        pages.addWidget(self.delete_button)
        layout = QVBoxLayout(self)
        layout.addLayout(search_row)
        layout.addLayout(filter_row)
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(self.metadata)
        layout.addWidget(self.detail)
        layout.addLayout(pages)
        layout.addWidget(self.status_label)
        layout.addWidget(close_button)
        self.search_button.clicked.connect(self._filters_changed)
        self.search_input.returnPressed.connect(self._filters_changed)
        self.kind_combo.currentIndexChanged.connect(self._filters_changed)
        self.include_expired.toggled.connect(self._filters_changed)
        self.previous_button.clicked.connect(lambda: self._move_page(-PAGE_SIZE))
        self.next_button.clicked.connect(lambda: self._move_page(PAGE_SIZE))
        self.list_widget.currentRowChanged.connect(self._select)
        self.delete_button.clicked.connect(self._delete_selected)
        close_button.clicked.connect(self.close)

    def _clear_view(self):
        self._view_generation += 1
        self._records = ()
        self.list_widget.clear()
        self.detail.clear()
        self.metadata.clear()
        self.delete_button.setEnabled(False)
        self.previous_button.setEnabled(False)
        self.next_button.setEnabled(False)

    def _filters_changed(self, *_args):
        self._offset = 0
        self.reload()

    def _move_page(self, delta):
        self._offset = max(0, self._offset + delta)
        self.reload()

    def reload(self):
        self._clear_view()
        try:
            page = self.service.list_page(
                text=self.search_input.text(), kind=self.kind_combo.currentData(),
                include_expired=self.include_expired.isChecked(), offset=self._offset,
            )
            if not page.records and self._offset:
                self._offset = 0
                page = self.service.list_page(
                    text=self.search_input.text(), kind=self.kind_combo.currentData(),
                    include_expired=self.include_expired.isChecked(), offset=0,
                )
        except Exception:
            self.status_label.setText('本地记忆暂时不可用，请稍后刷新。')
            return
        self._records, self._observed_at = page.records, page.observed_at
        for memory in self._records:
            expired = memory.expires_at is not None and memory.expires_at <= self._observed_at
            prefix = '已过期 · ' if expired else ''
            self.list_widget.addItem(f'{prefix}{KIND_LABELS[memory.kind]} · {" ".join(memory.content.split())[:80]}')
        self.previous_button.setEnabled(self._offset > 0)
        self.next_button.setEnabled(page.has_next)
        self.status_label.setText(f'本页 {len(page.records)} 条；删除仅影响之后的记忆检索，不会清除既有对话。')

    def _select(self, index):
        self.detail.clear()
        self.metadata.clear()
        self.delete_button.setEnabled(0 <= index < len(self._records))
        if 0 <= index < len(self._records):
            memory = self._records[index]
            self.detail.setPlainText(memory.content)
            expiration = memory.expires_at.isoformat(timespec='minutes') if memory.expires_at else '不过期'
            self.metadata.setText(f'{KIND_LABELS[memory.kind]} · 重要性 {memory.importance}/5\n'
                                  f'来源：{memory.source or "未填写"}\n到期（UTC）：{expiration}')

    def _confirm_delete(self):
        return QMessageBox.question(
            self, '删除本地记忆', '删除选中的这条本地记忆？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def _delete_selected(self):
        index = self.list_widget.currentRow()
        if not 0 <= index < len(self._records):
            return
        selected_id = self._records[index].id
        generation = self._view_generation
        if not self.confirmation_handler():
            return
        if not self.isVisible() or generation != self._view_generation:
            return
        try:
            self.service.delete(selected_id)
        except Exception:
            self.status_label.setText('删除未完成，本地记忆暂时不可用。')
            return
        self.reload()

    def showEvent(self, event):
        self.reload()
        super().showEvent(event)

    def hideEvent(self, event):
        self._clear_view()
        self._observed_at = None
        super().hideEvent(event)
