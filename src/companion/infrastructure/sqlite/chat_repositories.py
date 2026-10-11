import json
import sqlite3
from datetime import datetime, timezone

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
from companion.infrastructure.sqlite.database import SQLiteDatabase


def _encode_time(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError("Stored timestamps must include a timezone.")
    return value.astimezone(timezone.utc).isoformat()


def _decode_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise StorageError("A local chat timestamp is invalid.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StorageError("A local chat timestamp is invalid.")
    return parsed.astimezone(timezone.utc)


def _conversation_from_row(row: sqlite3.Row) -> Conversation:
    return Conversation(
        id=row["id"],
        created_at=_decode_time(row["created_at"]),
        updated_at=_decode_time(row["updated_at"]),
    )


def _message_from_row(row: sqlite3.Row) -> ChatMessage:
    try:
        return ChatMessage(
            id=row["id"],
            conversation_id=row["conversation_id"],
            role=ChatRole(row["role"]),
            content=row["content"],
            created_at=_decode_time(row["created_at"]),
            delivery_state=DeliveryState(row["delivery_state"]),
        )
    except (TypeError, ValueError, ValidationError) as error:
        raise StorageError("A local chat record is invalid.") from error


class SQLiteConversationRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get_latest(self) -> Conversation | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM conversations ORDER BY julianday(updated_at) DESC, "
                "julianday(created_at) DESC, id DESC LIMIT 1"
            ).fetchone()
        return _conversation_from_row(row) if row is not None else None

    def add_conversation(self, conversation: Conversation) -> None:
        if not isinstance(conversation, Conversation):
            raise ValidationError("A validated conversation is required.")
        with self.database.connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO conversations(id, created_at, updated_at) VALUES (?, ?, ?)",
                    (conversation.id, _encode_time(conversation.created_at),
                     _encode_time(conversation.updated_at)),
                )
            except sqlite3.IntegrityError as error:
                raise ValidationError("The conversation could not be saved.") from error

    def list_messages(
        self,
        conversation_id: str,
        *,
        limit: int | None = None,
        sent_only: bool = False,
    ) -> list[ChatMessage]:
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ValidationError("conversation_id must not be blank.")
        if limit is not None and (type(limit) is not int or limit <= 0):
            raise ValidationError("Message limit must be a positive integer.")
        if type(sent_only) is not bool:
            raise ValidationError("sent_only must be a boolean.")
        where = "conversation_id = ?"
        parameters: list[object] = [conversation_id]
        if sent_only:
            where += " AND delivery_state = 'sent'"
        if limit is None:
            order = "ORDER BY julianday(created_at), id"
        else:
            order = "ORDER BY julianday(created_at) DESC, id DESC LIMIT ?"
            parameters.append(limit)
        with self.database.connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM messages WHERE {where} {order}", parameters
            ).fetchall()
        messages = [_message_from_row(row) for row in rows]
        return list(reversed(messages)) if limit is not None else messages

    def get_message(self, message_id: str) -> ChatMessage | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM messages WHERE id = ?", (message_id,)
            ).fetchone()
        return _message_from_row(row) if row is not None else None

    def append_pending(self, message: ChatMessage) -> None:
        if (
            not isinstance(message, ChatMessage)
            or message.role is not ChatRole.USER
            or message.delivery_state is not DeliveryState.PENDING
        ):
            raise ValidationError("Only a pending user message can be appended.")
        with self.database.connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO messages(id, conversation_id, role, content, created_at, delivery_state) "
                    "VALUES (?, ?, 'user', ?, ?, 'pending')",
                    (message.id, message.conversation_id, message.content,
                     _encode_time(message.created_at)),
                )
            except sqlite3.IntegrityError as error:
                raise ValidationError("The pending message could not be saved.") from error

    def mark_retry_pending(self, user_message_id: str) -> ChatMessage:
        with self.database.connection() as connection:
            cursor = connection.execute(
                "UPDATE messages SET delivery_state = 'pending' "
                "WHERE id = ? AND role = 'user' AND delivery_state = 'failed'",
                (user_message_id,),
            )
            if cursor.rowcount == 0:
                row = connection.execute(
                    "SELECT id FROM messages WHERE id = ?", (user_message_id,)
                ).fetchone()
                if row is None:
                    raise NotFoundError("Chat message not found.")
                raise ValidationError("Only a failed user message can be retried.")
            row = connection.execute(
                "SELECT * FROM messages WHERE id = ?", (user_message_id,)
            ).fetchone()
        return _message_from_row(row)

    def complete_turn(
        self,
        user_message_id: str,
        assistant_message: ChatMessage,
        updated_at: datetime,
    ) -> None:
        if (
            not isinstance(assistant_message, ChatMessage)
            or assistant_message.role is not ChatRole.ASSISTANT
            or assistant_message.delivery_state is not DeliveryState.SENT
        ):
            raise ValidationError("A sent assistant message is required to complete a turn.")
        stamp = _encode_time(updated_at)
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT conversation_id, delivery_state, role FROM messages WHERE id = ?",
                (user_message_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError("Pending chat message not found.")
            if row["role"] != "user" or row["delivery_state"] != "pending":
                raise ValidationError("Only a pending user message can complete a turn.")
            if row["conversation_id"] != assistant_message.conversation_id:
                raise ValidationError("The assistant reply must belong to the same conversation.")
            connection.execute(
                "INSERT INTO messages(id, conversation_id, role, content, created_at, delivery_state) "
                "VALUES (?, ?, 'assistant', ?, ?, 'sent')",
                (assistant_message.id, assistant_message.conversation_id,
                 assistant_message.content, _encode_time(assistant_message.created_at)),
            )
            cursor = connection.execute(
                "UPDATE messages SET delivery_state = 'sent' "
                "WHERE id = ? AND delivery_state = 'pending'",
                (user_message_id,),
            )
            if cursor.rowcount != 1:
                raise ValidationError("The pending chat message changed before completion.")
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (stamp, assistant_message.conversation_id),
            )

    def mark_failed(self, user_message_id: str, updated_at: datetime) -> ChatMessage:
        stamp = _encode_time(updated_at)
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE messages SET delivery_state = 'failed' "
                "WHERE id = ? AND role = 'user' AND delivery_state = 'pending'",
                (user_message_id,),
            )
            if cursor.rowcount == 0:
                row = connection.execute(
                    "SELECT id FROM messages WHERE id = ?", (user_message_id,)
                ).fetchone()
                if row is None:
                    raise NotFoundError("Chat message not found.")
                raise ValidationError("Only a pending user message can be marked failed.")
            row = connection.execute(
                "SELECT conversation_id FROM messages WHERE id = ?", (user_message_id,)
            ).fetchone()
            connection.execute(
                "UPDATE conversations SET updated_at = CASE "
                "WHEN julianday(updated_at) < julianday(?) THEN ? ELSE updated_at END "
                "WHERE id = ?",
                (stamp, stamp, row["conversation_id"]),
            )
            updated = connection.execute(
                "SELECT * FROM messages WHERE id = ?", (user_message_id,)
            ).fetchone()
        return _message_from_row(updated)

    def recover_pending(self, updated_at: datetime) -> int:
        stamp = _encode_time(updated_at)
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT DISTINCT conversation_id FROM messages WHERE role = 'user' "
                "AND delivery_state = 'pending'"
            ).fetchall()
            cursor = connection.execute(
                "UPDATE messages SET delivery_state = 'failed' "
                "WHERE role = 'user' AND delivery_state = 'pending'"
            )
            for row in rows:
                connection.execute(
                    "UPDATE conversations SET updated_at = CASE "
                    "WHEN julianday(updated_at) < julianday(?) THEN ? ELSE updated_at END "
                    "WHERE id = ?",
                    (stamp, stamp, row["conversation_id"]),
                )
            return cursor.rowcount

    def clear_conversation(self, conversation_id: str) -> None:
        with self.database.connection() as connection:
            cursor = connection.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,)
            )
            if cursor.rowcount == 0:
                raise NotFoundError("Conversation not found.")


class SQLiteChatSettingsRepository:
    KEY = "chat.settings"

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get(self) -> ChatSettings:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?", (self.KEY,)
            ).fetchone()
        if row is None:
            return ChatSettings()
        try:
            value = json.loads(row["value"])
            provider_value = value.get("provider")
            provider = (
                ProviderConfiguration(
                    provider_value["base_url"], provider_value["model"],
                    provider_value["timeout_seconds"],
                )
                if provider_value is not None else None
            )
            context = value.get("context_preferences", {})
            personality = value.get("personality", {})
            return ChatSettings(
                provider=provider,
                context_preferences=ChatContextPreferences(
                    recent_history=context.get("recent_history", False),
                    saved_memories=context.get("saved_memories", False),
                    today_plan=context.get("today_plan", False),
                ),
                personality=PersonalityProfile(
                    response_language=personality.get("response_language", "zh-CN"),
                    tone=personality.get("tone", "温和、直接、尊重用户选择"),
                    principles=tuple(personality.get("principles", (
                        "先理解用户当前需要，再提供有帮助的回应。",
                        "不声称执行了实际未执行的操作。",
                    ))),
                ),
                consent_fingerprint=value.get("consent_fingerprint"),
            )
        except (AttributeError, KeyError, TypeError, ValueError, ValidationError) as error:
            raise StorageError("Stored chat settings are invalid.") from error

    def save(self, settings: ChatSettings, updated_at: datetime) -> None:
        if not isinstance(settings, ChatSettings):
            raise ValidationError("Validated chat settings are required.")
        stamp = _encode_time(updated_at)
        provider = settings.provider
        data = {
            "provider": (
                {
                    "base_url": provider.base_url,
                    "model": provider.model,
                    "timeout_seconds": provider.timeout_seconds,
                }
                if provider is not None else None
            ),
            "context_preferences": {
                "recent_history": settings.context_preferences.recent_history,
                "saved_memories": settings.context_preferences.saved_memories,
                "today_plan": settings.context_preferences.today_plan,
            },
            "personality": {
                "response_language": settings.personality.response_language,
                "tone": settings.personality.tone,
                "principles": list(settings.personality.principles),
            },
            "consent_fingerprint": settings.consent_fingerprint,
        }
        serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (self.KEY, serialized, stamp),
            )
