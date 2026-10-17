from dataclasses import replace
from datetime import date, datetime, timezone
from threading import Event

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLineEdit

from companion.application.cancellation import CancellationFlag
from companion.desktop.chat_window import ChatWindow
from companion.desktop.provider_settings_dialog import ProviderSettingsDialog
from companion.domain.chat import (
    ChatContextPreferences,
    ChatMessage,
    ChatResponse,
    ChatRole,
    ChatSendResult,
    ChatSettings,
    ConsentDisclosure,
    Conversation,
    DeliveryState,
    PersonalityProfile,
    ProviderConfiguration,
    ProviderErrorCode,
)


NOW = datetime(2026, 10, 11, 12, 10, tzinfo=timezone.utc)
CONFIG = ProviderConfiguration("https://provider.example/v1", "demo-model", 30)


class FakeClock:
    def now_utc(self):
        return NOW

    def local_date(self):
        return date(2026, 10, 11)


class FakeSettingsRepository:
    def __init__(self):
        self.value = ChatSettings(
            provider=CONFIG,
            context_preferences=ChatContextPreferences(saved_memories=True),
            personality=PersonalityProfile(),
        )

    def get(self):
        return self.value

    def save(self, settings, updated_at):
        self.value = settings


class FakeSecretStore:
    def __init__(self, value=None):
        self.value = value
        self.deleted = False

    def get(self):
        return self.value

    def set(self, secret):
        self.value = secret
        self.deleted = False

    def delete(self):
        self.value = None
        self.deleted = True


class FakeChatService:
    def __init__(self, *, configured=True, consent=True):
        self.settings = FakeSettingsRepository()
        self.secrets = FakeSecretStore("fixture-secret" if configured else None)
        self.clock = FakeClock()
        self.conversation = Conversation("conversation-1", NOW, NOW)
        self.messages = []
        self.send_calls = []
        self.retry_calls = []
        self.clear_calls = []
        self.configured = configured
        self.consent = consent
        self.grant_count = 0
        self.fail_next = None
        self.block_send = False
        self.started = Event()
        self.release = Event()
        self.last_token = None
        self.sequence = 0

    def active_conversation(self):
        return self.conversation

    def conversation_messages(self, conversation_id):
        assert conversation_id == self.conversation.id
        return list(self.messages)

    def is_configured(self):
        return self.configured and bool(self.secrets.value)

    def consent_is_current(self):
        return self.consent

    def consent_disclosure(self):
        return ConsentDisclosure("provider.example", ("saved memories",))

    def grant_current_consent(self):
        self.grant_count += 1
        self.consent = True

    def _send_result(self, text, token):
        self.sequence += 1
        user_id = f"user-{self.sequence}"
        if self.block_send:
            self.last_token = token
            self.started.set()
            self.release.wait(4)
        if token is not None and token.is_cancelled():
            user = ChatMessage(
                user_id, self.conversation.id, ChatRole.USER, text, NOW,
                DeliveryState.FAILED,
            )
            self.messages.append(user)
            return ChatSendResult(
                self.conversation, user, None, ProviderErrorCode.CANCELLED
            )
        if self.fail_next is not None:
            code, self.fail_next = self.fail_next, None
            user = ChatMessage(
                user_id, self.conversation.id, ChatRole.USER, text, NOW,
                DeliveryState.FAILED,
            )
            self.messages.append(user)
            return ChatSendResult(self.conversation, user, None, code)
        user = ChatMessage(
            user_id, self.conversation.id, ChatRole.USER, text, NOW,
            DeliveryState.SENT,
        )
        assistant = ChatMessage(
            f"assistant-{self.sequence}", self.conversation.id,
            ChatRole.ASSISTANT, "我在。", NOW, DeliveryState.SENT,
        )
        self.messages.extend((user, assistant))
        return ChatSendResult(self.conversation, user, assistant)

    def send(self, conversation_id, text, cancellation_token=None):
        self.send_calls.append((conversation_id, text))
        return self._send_result(text, cancellation_token)

    def retry(self, user_message_id, cancellation_token=None):
        self.retry_calls.append(user_message_id)
        previous = next(message for message in self.messages if message.id == user_message_id)
        self.messages.remove(previous)
        result = self._send_result(previous.content, cancellation_token)
        if result.user_message.id != user_message_id:
            self.messages.remove(result.user_message)
            user = replace(result.user_message, id=user_message_id)
            self.messages.append(user)
            result = replace(result, user_message=user)
        return result

    def clear(self, conversation_id):
        self.clear_calls.append(conversation_id)
        self.messages.clear()
        self.sequence += 1
        self.conversation = Conversation(f"conversation-{self.sequence + 1}", NOW, NOW)
        return self.conversation


def make_window(qtbot, service=None, **kwargs):
    service = service or FakeChatService()
    window = ChatWindow(
        chat_service=service,
        settings_repository=service.settings,
        secret_store=service.secrets,
        clock=service.clock,
        **kwargs,
    )
    qtbot.addWidget(window)
    window.show()
    return window, service


def test_unconfigured_local_voice_controls_are_disabled(qtbot):
    window, service = make_window(qtbot)
    assert not window.push_to_talk_button.isEnabled()
    assert not window.speak_reply_button.isEnabled()
    assert '本地' in window.push_to_talk_button.toolTip()
    assert '本地' in window.speak_reply_button.toolTip()
    assert service.send_calls == []


def test_voice_transcript_only_becomes_editable_draft_until_send(qtbot):
    from companion.domain.voice import VoiceTranscript

    window, service = make_window(qtbot)
    assert window.accept_voice_transcript(VoiceTranscript('先背单词'))
    assert window.composer.toPlainText() == '先背单词'
    assert not window.composer.isReadOnly()
    assert service.messages == []
    assert service.send_calls == []
    window.composer.setPlainText('先背单词，然后休息')
    QTest.mouseClick(window.send_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.is_busy)
    assert service.send_calls == [('conversation-1', '先背单词，然后休息')]


def test_voice_transcript_cannot_overwrite_existing_draft(qtbot):
    from companion.domain.voice import VoiceTranscript

    window, service = make_window(qtbot)
    window.composer.setPlainText('尚未发送的手写内容')
    assert not window.accept_voice_transcript(VoiceTranscript('新的识别内容'))
    assert window.composer.toPlainText() == '尚未发送的手写内容'
    assert service.messages == []


def test_missing_secret_keeps_draft_and_opens_provider_settings(qtbot):
    service = FakeChatService(configured=False)
    window, _ = make_window(qtbot, service)
    window.composer.setPlainText("这句话先留在本地")

    QTest.mouseClick(window.send_button, Qt.MouseButton.LeftButton)

    assert window.composer.toPlainText() == "这句话先留在本地"
    assert window.provider_settings_dialog is not None
    assert window.provider_settings_dialog.isVisible()
    assert service.send_calls == []
    assert "尚未发送" in window.status_label.text()


def test_consent_disclosure_shows_recipient_message_and_context_limits(qtbot):
    captured = []
    service = FakeChatService(consent=False)
    window, service = make_window(
        qtbot, service,
        consent_handler=lambda disclosure, text: captured.append((disclosure, text)) or False,
    )
    window.composer.setPlainText("私人草稿")

    QTest.mouseClick(window.send_button, Qt.MouseButton.LeftButton)

    assert service.send_calls == []
    assert service.grant_count == 0
    assert window.composer.toPlainText() == "私人草稿"
    assert captured[0][0].provider_host == "provider.example"
    assert "私人草稿" in captured[0][1]
    assert "最多 12" in captured[0][1]
    assert "48,000" in captured[0][1]
    assert "回复语言、语气和行为原则" in captured[0][1]


def test_privacy_summary_keeps_provider_and_enabled_categories_visible(qtbot):
    window, service = make_window(qtbot)

    summary = window.privacy_summary_label.text()
    assert "provider.example" in summary
    assert "保存记忆" in summary
    assert "近期对话" not in summary
    assert "今日计划" not in summary
    assert "回复语言、语气和行为原则" in summary

    updated = replace(
        service.settings.value,
        context_preferences=ChatContextPreferences(
            recent_history=True, saved_memories=False, today_plan=True
        ),
    )
    service.settings.save(updated, NOW)
    window._on_provider_settings_saved(updated)

    summary = window.privacy_summary_label.text()
    assert "近期对话" in summary
    assert "今日计划" in summary
    assert "保存记忆" not in summary


def test_successful_send_runs_off_ui_thread_and_renders_persisted_turn(qtbot):
    consent_calls = []
    service = FakeChatService(consent=False)
    window, service = make_window(
        qtbot, service,
        consent_handler=lambda disclosure, text: consent_calls.append(text) or True,
    )
    window.composer.setPlainText("你好，Companion")

    QTest.mouseClick(window.send_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.is_busy, timeout=2000)

    assert service.grant_count == 1
    assert service.send_calls == [(service.conversation.id, "你好，Companion")]
    assert window.composer.toPlainText() == ""
    assert "你好，Companion" in window.transcript.toPlainText()
    assert "我在。" in window.transcript.toPlainText()
    assert window.status_label.text() == "Companion 已回复。"
    assert len(consent_calls) == 1
    assert "你好，Companion" in consent_calls[0]
    assert "48,000" in consent_calls[0]


def test_provider_failure_keeps_draft_and_offers_same_message_retry(qtbot):
    service = FakeChatService()
    service.fail_next = ProviderErrorCode.UNAVAILABLE
    window, _ = make_window(qtbot, service)
    window.composer.setPlainText("请继续")

    QTest.mouseClick(window.send_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.is_busy, timeout=2000)

    failed_id = service.messages[0].id
    assert window.composer.toPlainText() == "请继续"
    assert window.retry_button.isEnabled()
    assert "可能尚未送达" in window.status_label.text()

    QTest.mouseClick(window.retry_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.is_busy, timeout=2000)
    assert service.retry_calls == [failed_id]
    assert sum(message.role is ChatRole.USER for message in service.messages) == 1
    assert window.composer.toPlainText() == ""
    assert "我在。" in window.transcript.toPlainText()


def test_recovered_failed_message_is_retryable_after_window_start(qtbot):
    service = FakeChatService()
    failed = ChatMessage(
        "recovered-failed", service.conversation.id, ChatRole.USER,
        "上次请求送达状态未知", NOW, DeliveryState.FAILED,
    )
    service.messages.append(failed)

    window, _ = make_window(qtbot, service)

    assert "上次请求送达状态未知" in window.transcript.toPlainText()
    assert window.retry_button.isEnabled()
    assert window._last_failed_message_id == failed.id


def test_cancel_keeps_event_loop_responsive_and_draft(qtbot):
    service = FakeChatService()
    service.block_send = True
    window, _ = make_window(
        qtbot, service, task_service=object(), reminder_service=object()
    )
    window.composer.setPlainText("先等等")

    QTest.mouseClick(window.send_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(service.started.is_set, timeout=1000)
    assert window.is_busy
    assert window.cancel_button.isEnabled()
    assert window.tasks_button.isEnabled()
    assert window.settings_button.isEnabled()
    QTest.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
    service.release.set()
    qtbot.waitUntil(lambda: not window.is_busy, timeout=2000)

    assert service.last_token.is_cancelled()
    assert window.composer.toPlainText() == "先等等"
    assert window.retry_button.isEnabled()
    assert "已取消" in window.status_label.text()


def test_clear_requires_local_confirmation_and_preserves_other_controls(qtbot):
    accepted = []
    window, service = make_window(
        qtbot,
        confirmation_handler=lambda purpose: accepted.append(purpose) or True,
        task_service=object(),
        reminder_service=object(),
    )
    service.messages.append(ChatMessage(
        "u1", service.conversation.id, ChatRole.USER, "local only", NOW, DeliveryState.SENT
    ))
    window.refresh_transcript()
    old_id = service.conversation.id

    QTest.mouseClick(window.clear_button, Qt.MouseButton.LeftButton)

    assert accepted == ["clear_conversation"]
    assert service.clear_calls == [old_id]
    assert service.conversation.id != old_id
    assert window.transcript.toPlainText() == ""
    assert window.tasks_button.isEnabled()
    assert window.reminder_settings_button.isEnabled()


def test_older_failed_message_remains_retryable_after_new_send_succeeds(qtbot):
    service = FakeChatService()
    service.fail_next = ProviderErrorCode.UNAVAILABLE
    window, _ = make_window(qtbot, service)
    window.composer.setPlainText("第一个请求")

    QTest.mouseClick(window.send_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.is_busy, timeout=2000)
    failed_id = service.messages[0].id
    assert window.retry_button.isEnabled()

    window.composer.setPlainText("新的独立请求")
    QTest.mouseClick(window.send_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.is_busy, timeout=2000)

    assert window.retry_button.isEnabled()
    assert window._last_failed_message_id == failed_id
    QTest.mouseClick(window.retry_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.is_busy, timeout=2000)

    assert service.retry_calls == [failed_id]
    assert all(message.delivery_state is not DeliveryState.FAILED for message in service.messages)


def test_settings_masks_and_clears_key_after_successful_save(qtbot):
    service = FakeChatService(configured=False)
    dialog = ProviderSettingsDialog(
        service.settings, service.secrets, service.clock,
    )
    qtbot.addWidget(dialog)
    dialog.api_key_input.setText("new-local-secret")
    dialog.show()

    assert dialog.api_key_input.echoMode() is QLineEdit.EchoMode.Password
    QTest.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert service.secrets.value == "new-local-secret"
    assert dialog.api_key_input.text() == ""


def test_late_worker_result_for_old_request_is_ignored(qtbot):
    window, service = make_window(qtbot)
    window._active_request_id = "current-request"
    before = window.transcript.toPlainText()
    stale_message = ChatMessage(
        "stale", service.conversation.id, ChatRole.USER, "stale reply", NOW, DeliveryState.SENT
    )
    stale_result = ChatSendResult(service.conversation, stale_message, None)

    window._on_worker_finished("old-request", stale_result, None)

    assert window.transcript.toPlainText() == before
    assert window._active_request_id == "current-request"

def test_retry_after_context_change_reconfirms_before_reusing_failed_message(qtbot):
    service = FakeChatService(consent=False)
    failed = ChatMessage(
        "failed-original", service.conversation.id, ChatRole.USER,
        "retry only after renewed consent", NOW, DeliveryState.FAILED,
    )
    service.messages.append(failed)
    disclosures = []
    window, _ = make_window(
        qtbot,
        service,
        consent_handler=lambda disclosure, text: disclosures.append((disclosure, text)) or True,
    )
    window._last_failed_message_id = failed.id
    window.retry_button.setEnabled(True)
    window.composer.setPlainText(failed.content)

    QTest.mouseClick(window.retry_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.is_busy, timeout=2000)

    assert service.grant_count == 1
    assert service.retry_calls == [failed.id]
    assert len(disclosures) == 1
    assert failed.content in disclosures[0][1]
    assert "provider.example" == disclosures[0][0].provider_host
    assert window.composer.toPlainText() == ""

def test_closed_inflight_request_cleans_busy_state_when_window_is_reopened(qtbot):
    service = FakeChatService()
    service.block_send = True
    window, _ = make_window(qtbot, service)
    window.composer.setPlainText("close while waiting")

    QTest.mouseClick(window.send_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(service.started.is_set, timeout=1000)
    request_id = window._active_request_id
    QTest.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
    window.close()
    assert service.last_token.is_cancelled()

    window.show()
    assert not window.send_button.isEnabled()
    service.release.set()
    qtbot.waitUntil(lambda: not window.is_busy, timeout=2000)

    assert window.send_button.isEnabled()
    assert request_id != window._active_request_id
    assert "我在。" not in window.transcript.toPlainText()


def test_oversized_draft_is_rejected_locally_without_retrying_an_old_row(qtbot):
    service = FakeChatService()
    stale = ChatMessage(
        "old-failed", service.conversation.id, ChatRole.USER,
        "previous failed turn", NOW, DeliveryState.FAILED,
    )
    service.messages.append(stale)
    window, _ = make_window(qtbot, service)
    window._last_failed_message_id = stale.id
    window.retry_button.setEnabled(True)
    oversized = "x" * 8001
    window.composer.setPlainText(oversized)

    QTest.mouseClick(window.send_button, Qt.MouseButton.LeftButton)

    assert not window.is_busy
    assert service.send_calls == []
    assert window.composer.toPlainText() == oversized
    assert window.retry_button.isEnabled()
    assert window._last_failed_message_id == stale.id
    assert "8,000" in window.status_label.text()


def test_provider_error_statuses_are_distinct_and_do_not_echo_details(qtbot):
    window, _ = make_window(qtbot)
    codes = (
        ProviderErrorCode.TIMEOUT,
        ProviderErrorCode.AUTHENTICATION,
        ProviderErrorCode.RATE_LIMITED,
        ProviderErrorCode.UNAVAILABLE,
        ProviderErrorCode.INVALID_RESPONSE,
        ProviderErrorCode.CONFIGURATION,
        ProviderErrorCode.STORAGE,
    )
    messages = []
    for code in codes:
        window._set_failure_status(code)
        messages.append(window.status_label.text())

    assert len(set(messages)) == len(codes)
    assert all(message for message in messages)
    assert "fixture-secret" not in " ".join(messages)
