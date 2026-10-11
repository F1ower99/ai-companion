from __future__ import annotations

from uuid import uuid4
from urllib.parse import urlsplit

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from companion.application.cancellation import CancellationFlag
from companion.desktop.chat_worker import ChatWorker
from companion.desktop.provider_settings_dialog import ProviderSettingsDialog
from companion.desktop.tasks_dialog import TodayTasksDialog
from companion.desktop.reminder_card import ReminderCard
from companion.desktop.reminder_settings_dialog import ReminderSettingsDialog
from companion.domain.chat import ChatRole, ProviderErrorCode
from companion.domain.decisions import Decision, DecisionKind, ReasonCode
from companion.domain.models import TaskStatus


class ChatWindow(QDialog):
    """Compact companion conversation window with local task/reminder controls."""

    taskStateChanged = Signal()
    reminderEvaluationRequested = Signal()

    def __init__(
        self,
        task_service=None,
        storage_error: str | None = None,
        *,
        clock=None,
        reminder_service=None,
        chat_service=None,
        settings_repository=None,
        secret_store=None,
        consent_handler=None,
        confirmation_handler=None,
    ) -> None:
        super().__init__()
        self.task_service = task_service
        self.clock = clock or getattr(task_service, "clock", None)
        self.reminder_service = reminder_service
        self.chat_service = chat_service
        self.settings_repository = settings_repository or getattr(chat_service, "settings", None)
        self.secret_store = secret_store or getattr(chat_service, "secrets", None)
        self.consent_handler = consent_handler or self._ask_for_consent
        self.confirmation_handler = confirmation_handler or self._ask_for_confirmation
        self.tasks_dialog: TodayTasksDialog | None = None
        self.reminder_settings_dialog: ReminderSettingsDialog | None = None
        self.reminder_card: ReminderCard | None = None
        self.provider_settings_dialog: ProviderSettingsDialog | None = None
        self._thread_pool: QThreadPool | None = None
        self._workers: dict[str, ChatWorker] = {}
        self._active_request_id: str | None = None
        self._closing_request_id: str | None = None
        self._active_token: CancellationFlag | None = None
        self._active_operation: str | None = None
        self._active_text: str | None = None
        self._last_failed_message_id: str | None = None
        self.is_busy = False

        self.setWindowTitle("AI Companion")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(420, 520)
        self.resize(480, 620)

        title = QLabel("和 Companion 聊聊")
        title.setObjectName("chatTitle")
        self.status_label = QLabel("对话保存在本机；只有发送时才会传给你配置的提供方。")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("chatStatus")
        self.storage_status = QLabel(
            storage_error or "本地任务存储已就绪。"
            if task_service is not None
            else storage_error or "本地任务存储尚未配置。"
        )
        self.storage_status.setWordWrap(True)
        self.storage_status.setObjectName("storageStatus")

        controls = QHBoxLayout()
        self.tasks_button = QPushButton("今日任务")
        self.tasks_button.setObjectName("tasksButton")
        self.tasks_button.setEnabled(task_service is not None)
        self.tasks_button.clicked.connect(self.open_tasks)
        self.reminder_settings_button = QPushButton("提醒设置")
        self.reminder_settings_button.setObjectName("reminderSettingsButton")
        self.reminder_settings_button.setEnabled(reminder_service is not None)
        self.reminder_settings_button.clicked.connect(self.open_reminder_settings)
        self.settings_button = QPushButton("模型与隐私设置")
        self.settings_button.setObjectName("providerSettingsButton")
        self.settings_button.setEnabled(self.settings_repository is not None)
        self.settings_button.clicked.connect(self.open_provider_settings)
        self.clear_button = QPushButton("清空对话")
        self.clear_button.setObjectName("clearConversationButton")
        self.clear_button.setEnabled(chat_service is not None)
        self.clear_button.clicked.connect(self.clear_conversation)
        controls.addWidget(self.tasks_button)
        controls.addWidget(self.reminder_settings_button)
        controls.addWidget(self.settings_button)
        controls.addWidget(self.clear_button)

        self.transcript = QPlainTextEdit()
        self.transcript.setObjectName("conversationTranscript")
        self.transcript.setReadOnly(True)
        self.transcript.setPlaceholderText("你和 Companion 的对话会显示在这里。")
        self.composer = QPlainTextEdit()
        self.composer.setObjectName("conversationComposer")
        self.composer.setPlaceholderText("写下你现在想聊的内容…")
        self.composer.setMaximumHeight(100)
        self.privacy_summary_label = QLabel()
        self.privacy_summary_label.setObjectName("privacySummary")
        self.privacy_summary_label.setWordWrap(True)
        self.send_button = QPushButton("发送")
        self.send_button.setObjectName("sendMessageButton")
        self.send_button.setEnabled(chat_service is not None)
        self.send_button.clicked.connect(self.send_message)
        self.cancel_button = QPushButton("取消发送")
        self.cancel_button.setObjectName("cancelMessageButton")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_send)
        self.retry_button = QPushButton("重试未送达消息")
        self.retry_button.setObjectName("retryMessageButton")
        self.retry_button.setEnabled(False)
        self.retry_button.clicked.connect(self.retry_message)

        composer_controls = QHBoxLayout()
        composer_controls.addWidget(self.send_button)
        composer_controls.addWidget(self.cancel_button)
        composer_controls.addWidget(self.retry_button)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(self.status_label)
        layout.addWidget(self.storage_status)
        layout.addLayout(controls)
        layout.addWidget(self.transcript, 1)
        layout.addWidget(self.composer)
        layout.addWidget(self.privacy_summary_label)
        layout.addLayout(composer_controls)

        self.setStyleSheet(
            """
            QDialog { background: #f7f5f1; color: #253c3b; }
            QLabel#chatTitle { font-size: 20px; font-weight: 650; }
            QLabel#chatStatus { color: #607270; font-size: 13px; }
            QLabel#storageStatus { color: #607270; font-size: 12px; }
            QLabel#privacySummary { color: #607270; font-size: 11px; }
            QPlainTextEdit { padding: 9px; border: 1px solid #d7dfda; border-radius: 10px; }
            QPushButton { padding: 8px; border: 0; border-radius: 9px; background: #98b9aa; }
            QPushButton:disabled { background: #d8dfdb; color: #77827e; }
            """
        )
        self._refresh_privacy_summary()
        self.refresh_transcript()

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

    def open_provider_settings(self) -> None:
        if self.settings_repository is None or self.secret_store is None or self.clock is None:
            self.status_label.setText("本地提供方设置暂时不可用。")
            return
        if self.provider_settings_dialog is None:
            self.provider_settings_dialog = ProviderSettingsDialog(
                self.settings_repository, self.secret_store, self.clock, self
            )
            self.provider_settings_dialog.saved.connect(self._on_provider_settings_saved)
        else:
            self.provider_settings_dialog._load_settings()
        self.provider_settings_dialog.show()
        self.provider_settings_dialog.raise_()
        self.provider_settings_dialog.activateWindow()

    def _on_provider_settings_saved(self, _settings) -> None:
        self.status_label.setText("提供方设置已保存在本机。发送前仍会显示隐私确认。")
        self._refresh_privacy_summary()

    def _refresh_privacy_summary(self) -> None:
        if self.chat_service is None:
            self.privacy_summary_label.setText("对话存储不可用；当前消息不会发送。")
            return
        if self.settings_repository is None:
            self.privacy_summary_label.setText("隐私设置不可用；当前消息不会发送。")
            return
        try:
            settings = self.settings_repository.get()
        except Exception:
            self.privacy_summary_label.setText("隐私设置当前无法读取；当前消息会被阻止发送。")
            return
        provider = getattr(settings, "provider", None)
        if provider is None:
            self.privacy_summary_label.setText("尚未配置提供方；当前消息只保存在本机，不会发送。")
            return
        try:
            parsed = urlsplit(provider.base_url)
            host = parsed.hostname or "已配置提供方"
            if parsed.port is not None:
                host = f"{host}:{parsed.port}"
        except (AttributeError, ValueError):
            host = "已配置提供方"
        preferences = settings.context_preferences
        categories = []
        if preferences.recent_history:
            categories.append("近期对话")
        if preferences.saved_memories:
            categories.append("保存记忆")
        if preferences.today_plan:
            categories.append("今日计划")
        extra_context = "、".join(categories) if categories else "无额外上下文"
        self.privacy_summary_label.setText(
            f"发送时会将当前消息发给 {host}；额外共享：{extra_context}。"
            "还会包含本机的回复语言、语气和行为原则设置。首次发送或共享范围变化时会请求确认。"
        )

    def send_message(self) -> None:
        if self.chat_service is None or self.is_busy:
            return
        text = self.composer.toPlainText().strip()
        if not text:
            self.status_label.setText("先写下你想聊的内容。")
            return
        if len(text) > 8_000:
            self.status_label.setText("消息最多 8,000 个字符；草稿仍保留在输入框。")
            return
        try:
            configured = self.chat_service.is_configured()
        except Exception:
            configured = False
        if not configured:
            self.status_label.setText("尚未发送。请先设置 HTTPS 提供方和本地密钥。")
            self.open_provider_settings()
            return
        try:
            consent_current = self.chat_service.consent_is_current()
            disclosure = self.chat_service.consent_disclosure()
        except Exception:
            self.status_label.setText("本地设置暂时不可用，消息尚未发送。")
            return
        if not consent_current:
            disclosure_text = self._consent_text(disclosure, text)
            if not self.consent_handler(disclosure, disclosure_text):
                self.status_label.setText("尚未发送；你可以调整隐私设置后再试。")
                return
            try:
                self.chat_service.grant_current_consent()
            except Exception:
                self.status_label.setText("隐私确认未能保存在本机，消息尚未发送。")
                return
        try:
            conversation = self.chat_service.active_conversation()
        except Exception:
            self.status_label.setText("本地对话暂时不可用，消息尚未发送。")
            return
        self._start_operation(
            "send", text, lambda token: self.chat_service.send(conversation.id, text, token)
        )

    def retry_message(self) -> None:
        if self.chat_service is None or self.is_busy or self._last_failed_message_id is None:
            return
        try:
            configured = self.chat_service.is_configured()
        except Exception:
            configured = False
        if not configured:
            self.status_label.setText("尚未发送。请先设置 HTTPS 提供方和本地密钥。")
            self.open_provider_settings()
            return

        message_id = self._last_failed_message_id
        try:
            conversation = self.chat_service.active_conversation()
            failed_message = next(
                message for message in self.chat_service.conversation_messages(conversation.id)
                if message.id == message_id
            )
            original_text = failed_message.content
        except Exception:
            self.status_label.setText("未能读取待重试消息；本机数据仍保留。")
            return

        try:
            consent_current = self.chat_service.consent_is_current()
        except Exception:
            self.status_label.setText("本地隐私设置暂时不可用，消息尚未重试。")
            return
        if not consent_current:
            try:
                disclosure = self.chat_service.consent_disclosure()
            except Exception:
                self.status_label.setText("本地隐私设置暂时不可用，消息尚未重试。")
                return
            if not self.consent_handler(disclosure, self._consent_text(disclosure, original_text)):
                self.status_label.setText("尚未重试；你可以调整隐私设置后再试。")
                return
            try:
                self.chat_service.grant_current_consent()
            except Exception:
                self.status_label.setText("隐私确认未能保存在本机，消息尚未重试。")
                return
        self._start_operation(
            "retry", original_text,
            lambda token: self.chat_service.retry(message_id, token),
        )

    def _start_operation(self, operation: str, text: str | None, call) -> None:
        request_id = uuid4().hex
        token = CancellationFlag()
        self._active_request_id = request_id
        self._active_token = token
        self._active_operation = operation
        self._active_text = text
        self.is_busy = True
        self.send_button.setEnabled(False)
        self.retry_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.clear_button.setEnabled(False)
        self.status_label.setText("正在发送…可随时取消。")
        worker = ChatWorker(request_id, lambda: call(token))
        worker.signals.finished.connect(self._on_worker_finished)
        self._workers[request_id] = worker
        if self._thread_pool is None:
            self._thread_pool = QThreadPool.globalInstance()
        self._thread_pool.start(worker)

    def cancel_send(self) -> None:
        if self._active_token is None:
            return
        self._active_token.cancel()
        self.cancel_button.setEnabled(False)
        self.status_label.setText("正在取消…等待当前网络操作结束。")

    def _on_worker_finished(self, request_id: str, result, error) -> None:
        self._workers.pop(request_id, None)
        if request_id != self._active_request_id:
            if request_id == self._closing_request_id:
                self._finish_closed_request(result, error)
            return
        operation = self._active_operation
        sent_text = self._active_text
        self._active_request_id = None
        self._active_token = None
        self._active_operation = None
        self._active_text = None
        self.is_busy = False
        self.send_button.setEnabled(self.chat_service is not None)
        self.cancel_button.setEnabled(False)
        self.clear_button.setEnabled(self.chat_service is not None)

        if error is not None:
            code = getattr(error, "code", None)
            self._last_failed_message_id = None
            self.retry_button.setEnabled(False)
            self._set_failure_status(code)
            self.refresh_transcript()
            return
        error_code = getattr(result, "error_code", None)
        if error_code is not None:
            self._last_failed_message_id = getattr(
                getattr(result, "user_message", None), "id", None
            )
            self.retry_button.setEnabled(self._last_failed_message_id is not None)
            self._set_failure_status(error_code)
            self.refresh_transcript()
            return

        self._last_failed_message_id = None
        self.retry_button.setEnabled(False)
        if operation in ("send", "retry") and sent_text is not None and self.composer.toPlainText().strip() == sent_text:
            self.composer.clear()
        self.status_label.setText("Companion 已回复。")
        self.refresh_transcript()

    def _finish_closed_request(self, result, error) -> None:
        self._closing_request_id = None
        operation = self._active_operation
        active_text = self._active_text
        self._active_operation = None
        self._active_text = None
        self._active_token = None
        self.is_busy = False
        self.send_button.setEnabled(self.chat_service is not None)
        self.cancel_button.setEnabled(False)
        self.clear_button.setEnabled(self.chat_service is not None)
        self._last_failed_message_id = None
        retry_user = getattr(result, "user_message", None)
        if (
            error is None
            and retry_user is not None
            and getattr(retry_user.delivery_state, "value", "") == "failed"
        ):
            self._last_failed_message_id = retry_user.id
            self.retry_button.setEnabled(True)
        else:
            self.retry_button.setEnabled(False)
        if (
            error is None
            and getattr(result, "error_code", None) is None
            and operation in ("send", "retry")
            and active_text is not None
            and self.composer.toPlainText().strip() == active_text
        ):
            self.composer.clear()
        self.refresh_transcript()
        self.status_label.setText("上次请求已结束；本机对话已刷新。")

    def _set_failure_status(self, code) -> None:
        if code is ProviderErrorCode.CANCELLED or getattr(code, "value", None) == "cancelled":
            self.status_label.setText("发送已取消；原消息保留在本机，可重试。")
        elif code is ProviderErrorCode.CONSENT_REQUIRED:
            self.status_label.setText("隐私确认已失效，消息尚未发送。")
        elif code is ProviderErrorCode.NOT_CONFIGURED:
            self.status_label.setText("尚未发送。请先设置提供方和本地密钥。")
        elif code is ProviderErrorCode.TIMEOUT:
            self.status_label.setText("提供方响应超时；消息可能尚未送达，可重试原消息。")
        elif code is ProviderErrorCode.AUTHENTICATION:
            self.status_label.setText("提供方拒绝了身份验证；请检查密钥设置，消息可能尚未送达。")
        elif code is ProviderErrorCode.RATE_LIMITED:
            self.status_label.setText("提供方暂时限流；稍后可以重试原消息。")
        elif code is ProviderErrorCode.UNAVAILABLE:
            self.status_label.setText("提供方暂时不可用；消息可能尚未送达，可重试原消息。")
        elif code is ProviderErrorCode.INVALID_RESPONSE:
            self.status_label.setText("提供方回复无法识别；消息可能已送达，可重试原消息。")
        elif code is ProviderErrorCode.CONFIGURATION:
            self.status_label.setText("提供方设置无效；请检查 HTTPS 地址、模型和请求设置。")
        elif code is ProviderErrorCode.STORAGE:
            self.status_label.setText("本地对话存储失败；草稿仍保留，请检查后再试。")
        else:
            self.status_label.setText("发送未能完成；草稿仍保留在本机。")

    def refresh_transcript(self) -> None:
        if self.chat_service is None:
            self.transcript.clear()
            self._last_failed_message_id = None
            self.retry_button.setEnabled(False)
            return
        try:
            conversation = self.chat_service.active_conversation()
            messages = self.chat_service.conversation_messages(conversation.id)
        except Exception:
            self.transcript.setPlainText("本地对话暂时无法读取。")
            self._last_failed_message_id = None
            self.retry_button.setEnabled(False)
            return
        failed_messages = [
            message for message in messages
            if message.role is ChatRole.USER
            and getattr(message.delivery_state, "value", "") == "failed"
        ]
        self._last_failed_message_id = failed_messages[-1].id if failed_messages else None
        self.retry_button.setEnabled(not self.is_busy and self._last_failed_message_id is not None)
        rows = []
        for message in messages:
            role = "你" if message.role is ChatRole.USER else "Companion"
            state = "（发送状态待确认）" if getattr(message.delivery_state, "value", "") == "failed" else ""
            rows.append(f"{role}{state}：\n{message.content}")
        self.transcript.setPlainText("\n\n".join(rows))
        cursor = self.transcript.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.transcript.setTextCursor(cursor)

    @staticmethod
    def _consent_text(disclosure, current_message: str) -> str:
        categories = "、".join(disclosure.enabled_categories) or "无额外上下文"
        return (
            f"将把本条消息发送给 {disclosure.provider_host}。\n\n"
            f"本条内容：\n{current_message}\n\n"
            "此外会包含本机的回复语言、语气和行为原则设置。\n\n"
            f"可选上下文类别：{categories}。最多 12 条近期对话、5 条记忆、"
            "12 项任务和 8 门课程；单次请求最多 48,000 字符。"
        )

    @staticmethod
    def _ask_for_consent(disclosure, disclosure_text: str) -> bool:
        return QMessageBox.question(
            None, "确认发送到模型提供方", disclosure_text + "\n\n是否允许发送？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    @staticmethod
    def _ask_for_confirmation(purpose: str) -> bool:
        if purpose != "clear_conversation":
            return False
        return QMessageBox.question(
            None, "清空本地对话", "这会删除本机保存的当前对话。此操作无法恢复，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def clear_conversation(self) -> None:
        if self.chat_service is None or self.is_busy:
            return
        if not self.confirmation_handler("clear_conversation"):
            return
        try:
            conversation = self.chat_service.active_conversation()
            self.chat_service.clear(conversation.id)
        except Exception:
            self.status_label.setText("本地对话未能清空。")
            return
        self.composer.clear()
        self._last_failed_message_id = None
        self.retry_button.setEnabled(False)
        self.refresh_transcript()
        self.status_label.setText("本机保存的对话已清空。")

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

    def closeEvent(self, event) -> None:
        if self._active_request_id is not None:
            self._closing_request_id = self._active_request_id
            if self._active_token is not None:
                self._active_token.cancel()
            self._active_request_id = None
            self.cancel_button.setEnabled(False)
        super().closeEvent(event)
