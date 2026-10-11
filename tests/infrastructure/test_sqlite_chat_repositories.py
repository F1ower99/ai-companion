from datetime import datetime, timezone

import pytest

from companion.domain.chat import (
    ChatContextPreferences,
    ChatMessage,
    ChatRole,
    ChatSettings,
    Conversation,
    DeliveryState,
    PersonalityProfile,
    ProviderConfiguration,
)
from companion.domain.errors import NotFoundError, StorageError, ValidationError
from companion.application.chat_service import ChatService
from companion.infrastructure.sqlite.chat_repositories import (
    SQLiteChatSettingsRepository,
    SQLiteConversationRepository,
)
from companion.infrastructure.sqlite.database import SQLiteDatabase


BASE = datetime(2026, 10, 11, 4, 0, tzinfo=timezone.utc)


@pytest.fixture
def chat_repositories(tmp_path):
    database = SQLiteDatabase(tmp_path / "companion.sqlite3")
    database.initialize()
    return (
        database,
        SQLiteConversationRepository(database),
        SQLiteChatSettingsRepository(database),
    )


def make_conversation(conversation_id, minute=0):
    created = BASE.replace(minute=minute)
    return Conversation(conversation_id, created, created)


def make_message(message_id, conversation_id, role, content, minute, state=DeliveryState.SENT):
    return ChatMessage(
        message_id, conversation_id, role, content,
        BASE.replace(minute=minute), state,
    )


def test_latest_conversation_and_messages_have_stable_chronological_order(chat_repositories):
    database, conversations, _ = chat_repositories
    older = make_conversation("older", 0)
    newer = make_conversation("newer", 1)
    conversations.add_conversation(older)
    conversations.add_conversation(newer)
    assert conversations.get_latest() == newer

    with database.connection() as connection:
        connection.execute(
            "INSERT INTO messages(id, conversation_id, role, content, created_at, delivery_state) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("m-a", "newer", "user", "first", BASE.replace(minute=2).isoformat(), "sent"),
        )
        connection.execute(
            "INSERT INTO messages(id, conversation_id, role, content, created_at, delivery_state) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("m-b", "newer", "assistant", "second", BASE.replace(minute=2).isoformat(), "sent"),
        )
    conversations.append_pending(
        make_message("m-c", "newer", ChatRole.USER, "pending", 3, DeliveryState.PENDING)
    )
    conversations.complete_turn(
        "m-c", make_message("m-d", "newer", ChatRole.ASSISTANT, "done", 3),
        BASE.replace(minute=4),
    )
    conversations.append_pending(
        make_message("m-e", "newer", ChatRole.USER, "still pending", 5, DeliveryState.PENDING)
    )
    # Stable (created_at, id) order is visible for tied timestamps.
    assert [m.id for m in conversations.list_messages("newer")] == [
        "m-a", "m-b", "m-c", "m-d", "m-e",
    ]
    assert [m.id for m in conversations.list_messages("newer", limit=2)] == ["m-d", "m-e"]
    assert [m.id for m in conversations.list_messages("newer", sent_only=True)] == [
        "m-a", "m-b", "m-c", "m-d",
    ]


def test_successful_turn_is_atomic_and_updates_conversation(chat_repositories):
    _, conversations, _ = chat_repositories
    conversation = make_conversation("c1")
    conversations.add_conversation(conversation)
    user = make_message("u1", "c1", ChatRole.USER, "hello", 1, DeliveryState.PENDING)
    assistant = make_message("a1", "c1", ChatRole.ASSISTANT, "hi", 2)
    conversations.append_pending(user)
    updated_at = BASE.replace(minute=3)
    conversations.complete_turn(user.id, assistant, updated_at)

    assert conversations.get_message("u1").delivery_state is DeliveryState.SENT
    assert conversations.get_message("a1") == assistant
    assert conversations.get_latest().updated_at == updated_at


def test_failed_turn_can_be_retried_on_the_same_user_row(chat_repositories):
    _, conversations, _ = chat_repositories
    conversations.add_conversation(make_conversation("c1"))
    user = make_message("u1", "c1", ChatRole.USER, "hello", 1, DeliveryState.PENDING)
    conversations.append_pending(user)
    failed = conversations.mark_failed(user.id, BASE.replace(minute=2))
    retried = conversations.mark_retry_pending(user.id)
    assert failed.delivery_state is DeliveryState.FAILED
    assert retried.id == user.id
    assert retried.delivery_state is DeliveryState.PENDING
    assert [m.id for m in conversations.list_messages("c1")] == ["u1"]
    with pytest.raises(ValidationError):
        conversations.mark_retry_pending(user.id)


def test_pending_recovery_marks_uncertain_messages_failed(chat_repositories):
    _, conversations, _ = chat_repositories
    conversations.add_conversation(make_conversation("c1"))
    conversations.append_pending(
        make_message("u1", "c1", ChatRole.USER, "maybe sent", 1, DeliveryState.PENDING)
    )
    recovered = conversations.recover_pending(BASE.replace(minute=2))
    assert recovered == 1
    assert conversations.get_message("u1").delivery_state is DeliveryState.FAILED
    assert conversations.recover_pending(BASE.replace(minute=3)) == 0


def test_clear_removes_only_selected_conversation_and_cascades_messages(chat_repositories):
    _, conversations, _ = chat_repositories
    conversations.add_conversation(make_conversation("keep"))
    conversations.add_conversation(make_conversation("clear", 1))
    conversations.append_pending(
        make_message("m1", "keep", ChatRole.USER, "keep", 1, DeliveryState.PENDING)
    )
    conversations.append_pending(
        make_message("m2", "clear", ChatRole.USER, "clear", 1, DeliveryState.PENDING)
    )
    conversations.clear_conversation("clear")
    assert conversations.get_message("m2") is None
    assert conversations.get_message("m1") is not None
    assert conversations.get_latest().id == "keep"
    with pytest.raises(NotFoundError):
        conversations.clear_conversation("clear")


def test_service_clear_keeps_new_conversation_latest_under_sqlite_time_precision(chat_repositories):
    _, conversations, settings = chat_repositories
    cleared = make_conversation("a-cleared")
    remaining = make_conversation("z-remaining")
    conversations.add_conversation(cleared)
    conversations.add_conversation(remaining)

    class FixedClock:
        def now_utc(self):
            return BASE

    service = ChatService(
        conversations=conversations,
        settings=settings,
        memories=None,
        tasks=None,
        calendar=None,
        clock=FixedClock(),
        provider=None,
        secrets=None,
        id_factory=lambda: "a-fresh",
        context_builder=None,
    )

    fresh = service.clear(cleared.id)

    assert fresh.updated_at > remaining.updated_at
    assert conversations.get_latest() == fresh


def test_settings_round_trip_without_a_secret_field(chat_repositories):
    database, _, settings_repository = chat_repositories
    settings = ChatSettings(
        provider=ProviderConfiguration("https://api.example.test/v1", "local-model", 45),
        context_preferences=ChatContextPreferences(saved_memories=True),
        personality=PersonalityProfile("zh-CN", "calm", ("Be clear.",)),
        consent_fingerprint="a" * 64,
    )
    settings_repository.save(settings, BASE)
    assert settings_repository.get() == settings
    with database.connection() as connection:
        stored = connection.execute("SELECT key, value FROM settings").fetchall()
    assert len(stored) == 1
    assert stored[0]["key"] == "chat.settings"
    assert "credential" not in stored[0]["value"].lower()
    assert "api_key" not in stored[0]["value"].lower()
