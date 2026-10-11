from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone

import pytest

from companion.application.cancellation import CancellationFlag
from companion.application.chat_context import DailyChatContext
from companion.application.chat_service import ChatService
from companion.domain.chat import (
    ChatContextPreferences,
    ChatMessage,
    ChatRole,
    ChatServiceError,
    ChatSettings,
    ChatResponse,
    Conversation,
    DeliveryState,
    PersonalityProfile,
    ProviderConfiguration,
    ProviderError,
    ProviderErrorCode,
)
from companion.domain.errors import ValidationError
from companion.domain.models import Memory, MemoryKind, MemoryQuery


NOW = datetime(2026, 10, 11, 12, 10, tzinfo=timezone.utc)
TODAY = date(2026, 10, 11)
CONFIG = ProviderConfiguration("https://provider.example/v1", "test-model", 30)


class FakeClock:
    def __init__(self, current=NOW, local_day=TODAY):
        self.current = current
        self.day = local_day
        self.now_calls = 0

    def now_utc(self):
        self.now_calls += 1
        return self.current

    def local_date(self):
        return self.day


class FakeConversationRepository:
    def __init__(self):
        self.conversations = {}
        self.messages = {}
        self.events = []
        self.list_result = None

    def get_latest(self):
        return max(self.conversations.values(), key=lambda c: (c.updated_at, c.id), default=None)

    def add_conversation(self, conversation):
        self.conversations[conversation.id] = conversation

    def list_messages(self, conversation_id, *, limit=None, sent_only=False):
        self.events.append(("list_messages", limit, sent_only))
        messages = [m for m in self.messages.values() if m.conversation_id == conversation_id]
        if sent_only:
            messages = [m for m in messages if m.delivery_state is DeliveryState.SENT]
        if self.list_result is not None:
            messages = list(self.list_result)
        messages.sort(key=lambda m: (m.created_at, m.id))
        return messages[-limit:] if limit is not None else messages

    def get_message(self, message_id):
        return self.messages.get(message_id)

    def append_pending(self, message):
        self.events.append(("append_pending", message.id))
        self.messages[message.id] = message

    def mark_retry_pending(self, user_message_id):
        message = self.messages[user_message_id]
        if message.role is not ChatRole.USER or message.delivery_state is not DeliveryState.FAILED:
            raise ValidationError("Only a failed user message can be retried.")
        updated = replace(message, delivery_state=DeliveryState.PENDING)
        self.messages[user_message_id] = updated
        self.events.append(("retry_pending", user_message_id))
        return updated

    def complete_turn(self, user_message_id, assistant_message, updated_at):
        self.events.append(("complete_turn", user_message_id))
        self.messages[user_message_id] = replace(
            self.messages[user_message_id], delivery_state=DeliveryState.SENT
        )
        self.messages[assistant_message.id] = assistant_message
        conversation = self.conversations[assistant_message.conversation_id]
        self.conversations[conversation.id] = replace(conversation, updated_at=updated_at)

    def mark_failed(self, user_message_id, updated_at):
        self.events.append(("mark_failed", user_message_id))
        message = replace(self.messages[user_message_id], delivery_state=DeliveryState.FAILED)
        self.messages[user_message_id] = message
        return message

    def recover_pending(self, updated_at):
        pending = [m for m in self.messages.values() if m.delivery_state is DeliveryState.PENDING]
        for message in pending:
            self.messages[message.id] = replace(message, delivery_state=DeliveryState.FAILED)
        self.events.append(("recover_pending", len(pending)))
        return len(pending)

    def clear_conversation(self, conversation_id):
        del self.conversations[conversation_id]
        self.messages = {
            key: value for key, value in self.messages.items()
            if value.conversation_id != conversation_id
        }
        self.events.append(("clear", conversation_id))


class FakeSettingsRepository:
    def __init__(self, settings=None):
        self.settings = settings or ChatSettings(provider=CONFIG)

    def get(self):
        return self.settings

    def save(self, settings, updated_at):
        self.settings = settings


class FakeMemoryRepository:
    def __init__(self, memories=()):
        self.memories = list(memories)
        self.calls = []

    def search(self, query, limit=5, *, as_of_utc=None):
        self.calls.append((query, limit, as_of_utc))
        return self.memories


class FakeContextBuilder:
    def __init__(self, value=None):
        self.value = value or DailyChatContext(TODAY, (), ())
        self.calls = []

    def build(self, day, now_utc):
        self.calls.append((day, now_utc))
        return self.value


class FakeSecretStore:
    def __init__(self, value="secret-for-test"):
        self.value = value

    def get(self):
        return self.value


class FakeProvider:
    def __init__(self, response=None, error=None, on_complete=None):
        self.response = response or ChatResponse("A helpful reply.", "test-model")
        self.error = error
        self.on_complete = on_complete
        self.calls = []

    def complete(self, call):
        self.calls.append(call)
        if self.on_complete:
            self.on_complete(call)
        if self.error:
            raise self.error
        return self.response


def build_service(*, settings=None, secret="secret-for-test", provider=None, memories=(), context=None):
    conversations = FakeConversationRepository()
    settings = FakeSettingsRepository(settings or ChatSettings(provider=CONFIG))
    memory_repository = FakeMemoryRepository(memories)
    context_builder = FakeContextBuilder(context)
    secret_store = FakeSecretStore(secret)
    provider = provider or FakeProvider()
    clock = FakeClock()
    counter = iter(f"id-{i}" for i in range(100))
    service = ChatService(
        conversations=conversations,
        settings=settings,
        memories=memory_repository,
        tasks=None,
        calendar=None,
        clock=clock,
        provider=provider,
        secrets=secret_store,
        id_factory=lambda: next(counter),
        context_builder=context_builder,
    )
    conversation = service.active_conversation()
    return service, conversations, settings, memory_repository, context_builder, provider, clock, secret_store, conversation


def test_missing_secret_does_not_persist_message_or_call_provider():
    service, conversations, _, _, _, provider, _, _, conversation = build_service(secret=None)
    with pytest.raises(ChatServiceError) as error:
        service.send(conversation.id, "hello")
    assert error.value.code is ProviderErrorCode.NOT_CONFIGURED
    assert conversations.messages == {}
    assert not any(event[0] == "append_pending" for event in conversations.events)
    assert provider.calls == []


def test_missing_consent_does_not_persist_message_or_call_provider():
    service, conversations, _, _, _, provider, _, _, conversation = build_service()
    with pytest.raises(ChatServiceError) as error:
        service.send(conversation.id, "hello")
    assert error.value.code is ProviderErrorCode.CONSENT_REQUIRED
    assert conversations.messages == {}
    assert provider.calls == []


def test_successful_send_persists_pending_before_provider_and_completes_turn():
    holder = {}

    def inspect_pending(_call):
        repo = holder["repo"]
        assert [message.delivery_state for message in repo.messages.values()] == [DeliveryState.PENDING]
        repo.events.append(("provider",))

    service, conversations, settings, memories, context, provider, clock, _, conversation = build_service(
        provider=FakeProvider(on_complete=inspect_pending)
    )
    holder["repo"] = conversations
    service.grant_current_consent()
    result = service.send(conversation.id, "What should I focus on?")

    assert result.error_code is None
    assert result.user_message.delivery_state is DeliveryState.SENT
    assert result.assistant_message.content == "A helpful reply."
    assert [event[0] for event in conversations.events if event[0] in (
        "append_pending", "provider", "complete_turn",
    )] == ["append_pending", "provider", "complete_turn"]
    assert memories.calls == []
    assert context.calls == []
    assert clock.now_calls >= 2
    assert "secret-for-test" not in repr(provider.calls[0])


def test_enabled_context_is_bounded_and_uses_the_same_expiry_instant():
    preferences = ChatContextPreferences(True, True, True)
    settings = ChatSettings(provider=CONFIG, context_preferences=preferences)
    long_memories = [
        Memory(f"mem-{i}", MemoryKind.PREFERENCE, f"memory-{i}", created_at=NOW)
        for i in range(7)
    ]
    long_history = [
        ChatMessage(
            f"old-{i:02}", "history", ChatRole.USER, f"history-{i}",
            NOW.replace(minute=i), DeliveryState.SENT,
        )
        for i in range(15)
    ]
    context_data = DailyChatContext(
        TODAY,
        tuple(),
        tuple(),
    )
    service, conversations, _, memory_repo, context, provider, _, _, conversation = build_service(
        settings=settings,
        memories=long_memories,
        context=context_data,
    )
    conversations.list_result = [
        replace(message, conversation_id=conversation.id) for message in long_history
    ]
    service.grant_current_consent()
    service.send(conversation.id, "new message")

    call = provider.calls[0]
    assert len(call.request.messages) == 14  # system + 12 history + current user
    assert [m.content for m in call.request.messages[1:-1]] == [
        f"history-{i}" for i in range(3, 15)
    ]
    assert memory_repo.calls[0][1:] == (5, NOW)
    assert sum(m.content.count("memory-") for m in call.request.messages) <= 5
    assert context.calls == [(TODAY, NOW)]


def test_provider_timeout_returns_safe_failure_and_marks_user_failed():
    service, conversations, _, _, _, provider, _, _, conversation = build_service(
        provider=FakeProvider(error=ProviderError(ProviderErrorCode.TIMEOUT))
    )
    service.grant_current_consent()
    result = service.send(conversation.id, "hello")
    assert result.error_code is ProviderErrorCode.TIMEOUT
    assert result.assistant_message is None
    assert result.user_message.delivery_state is DeliveryState.FAILED
    assert "secret-for-test" not in str(result)
    assert len(provider.calls) == 1


def test_retry_reuses_failed_user_message_row():
    provider = FakeProvider(error=ProviderError(ProviderErrorCode.UNAVAILABLE))
    service, conversations, _, _, _, _, _, _, conversation = build_service(provider=provider)
    service.grant_current_consent()
    first = service.send(conversation.id, "hello")
    assert first.user_message.delivery_state is DeliveryState.FAILED
    provider.error = None
    retried = service.retry(first.user_message.id)
    assert retried.user_message.id == first.user_message.id
    assert retried.user_message.delivery_state is DeliveryState.SENT
    assert len([m for m in conversations.messages.values() if m.role is ChatRole.USER]) == 1
    assert len(provider.calls) == 2


def test_cancel_after_provider_returns_suppresses_assistant_turn():
    token = CancellationFlag()
    provider = FakeProvider(on_complete=lambda _call: token.cancel())
    service, conversations, _, _, _, _, _, _, conversation = build_service(provider=provider)
    service.grant_current_consent()
    result = service.send(conversation.id, "hello", token)
    assert result.error_code is ProviderErrorCode.CANCELLED
    assert result.assistant_message is None
    assert result.user_message.delivery_state is DeliveryState.FAILED
    assert [message.role for message in conversations.messages.values()] == [ChatRole.USER]


def test_cancel_after_pending_insert_but_before_provider_skips_network_call():
    token = CancellationFlag()
    provider = FakeProvider()
    service, conversations, _, _, _, _, _, _, conversation = build_service(provider=provider)
    service.grant_current_consent()
    append_pending = conversations.append_pending

    def append_then_cancel(message):
        append_pending(message)
        token.cancel()

    conversations.append_pending = append_then_cancel
    result = service.send(conversation.id, "hello", token)

    assert result.error_code is ProviderErrorCode.CANCELLED
    assert provider.calls == []
    assert result.user_message.delivery_state is DeliveryState.FAILED


def test_pending_recovery_and_clear_create_a_fresh_local_conversation():
    service, conversations, _, _, _, _, _, _, conversation = build_service()
    older_conversation = Conversation(
        "z-existing-conversation", NOW, NOW
    )
    conversations.add_conversation(older_conversation)
    pending = ChatMessage(
        "pending", conversation.id, ChatRole.USER, "uncertain", NOW,
        DeliveryState.PENDING,
    )
    conversations.append_pending(pending)
    assert service.recover_pending() == 1
    assert conversations.get_message("pending").delivery_state is DeliveryState.FAILED
    new_conversation = service.clear(conversation.id)
    assert new_conversation.id != conversation.id
    assert new_conversation.id != older_conversation.id
    assert conversations.get_message("pending") is None
    assert conversations.conversations[older_conversation.id] == older_conversation
    assert conversations.get_latest() == new_conversation
    assert service.active_conversation() == new_conversation


def test_user_message_length_is_checked_before_persistence():
    service, conversations, _, _, _, provider, _, _, conversation = build_service()
    service.grant_current_consent()
    with pytest.raises(ValidationError, match="8,000"):
        service.send(conversation.id, "x" * 8_001)
    assert conversations.messages == {}
    assert provider.calls == []


def test_ui_preflight_exposes_configuration_consent_and_local_history():
    service, conversations, settings, _, _, _, _, secret_store, conversation = build_service(secret=None)
    assert not service.is_configured()
    assert not service.consent_is_current()
    secret_store.value = "configured-key"
    assert service.is_configured()
    service.grant_current_consent()
    assert service.consent_is_current()
    old = ChatMessage(
        "old", conversation.id, ChatRole.USER, "local history", NOW,
        DeliveryState.SENT,
    )
    conversations.messages[old.id] = old
    assert service.conversation_messages(conversation.id) == [old]
    settings.save(
        replace(settings.settings, context_preferences=ChatContextPreferences(today_plan=True)),
        NOW,
    )
    assert not service.consent_is_current()
