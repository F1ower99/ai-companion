from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from typing import Protocol
from urllib.parse import urlsplit

from companion.domain.errors import ValidationError


def _require_aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{name} must include a timezone.")
    return value.astimezone(timezone.utc)


def _require_text(value: str, name: str, *, limit: int, allow_blank: bool = False) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{name} must be text.")
    value = value.strip()
    if not allow_blank and not value:
        raise ValidationError(f"{name} must not be blank.")
    if len(value) > limit:
        raise ValidationError(f"{name} must be at most {limit} characters.")
    return value


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class DeliveryState(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class ProviderMessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ProviderErrorCode(str, Enum):
    NOT_CONFIGURED = "not_configured"
    CONSENT_REQUIRED = "consent_required"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    AUTHENTICATION = "authentication"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    INVALID_RESPONSE = "invalid_response"
    CONFIGURATION = "configuration"
    STORAGE = "storage"


class ProviderError(RuntimeError):
    """Safe provider failure carrying only a stable code, never raw response text."""

    def __init__(self, code: ProviderErrorCode) -> None:
        self.code = ProviderErrorCode(code)
        super().__init__(self.code.value)


class ChatServiceError(RuntimeError):
    """Safe local chat failure carrying a stable code."""

    def __init__(self, code: ProviderErrorCode) -> None:
        self.code = ProviderErrorCode(code)
        super().__init__(self.code.value)


class CancellationToken(Protocol):
    def is_cancelled(self) -> bool: ...


@dataclass(frozen=True)
class Conversation:
    id: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_text(self.id, "id", limit=128))
        created = _require_aware(self.created_at, "created_at")
        updated = _require_aware(self.updated_at, "updated_at")
        if updated < created:
            raise ValidationError("updated_at cannot be earlier than created_at.")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)


@dataclass(frozen=True)
class ChatMessage:
    id: str
    conversation_id: str
    role: ChatRole
    content: str
    created_at: datetime
    delivery_state: DeliveryState = DeliveryState.SENT

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_text(self.id, "id", limit=128))
        object.__setattr__(
            self, "conversation_id", _require_text(self.conversation_id, "conversation_id", limit=128)
        )
        try:
            object.__setattr__(self, "role", ChatRole(self.role))
            object.__setattr__(self, "delivery_state", DeliveryState(self.delivery_state))
        except (TypeError, ValueError) as error:
            raise ValidationError("Chat message role or delivery state is invalid.") from error
        object.__setattr__(self, "content", _require_text(self.content, "content", limit=20_000))
        object.__setattr__(self, "created_at", _require_aware(self.created_at, "created_at"))
        if self.role is ChatRole.ASSISTANT and self.delivery_state is not DeliveryState.SENT:
            raise ValidationError("Assistant messages must have sent delivery state.")


@dataclass(frozen=True)
class ProviderConfiguration:
    base_url: str
    model: str
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        base_url = _require_text(self.base_url, "base_url", limit=2048)
        try:
            parsed = urlsplit(base_url)
            port = parsed.port
        except ValueError as error:
            raise ValidationError("Provider base URL is invalid.") from error
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValidationError("Provider base URL must be an HTTPS URL without credentials or query data.")
        if port is not None and not 1 <= port <= 65535:
            raise ValidationError("Provider base URL port is invalid.")
        model = _require_text(self.model, "model", limit=200)
        if type(self.timeout_seconds) is not int or not 5 <= self.timeout_seconds <= 120:
            raise ValidationError("Provider timeout must be between 5 and 120 seconds.")
        object.__setattr__(self, "base_url", base_url.rstrip("/"))
        object.__setattr__(self, "model", model)


@dataclass(frozen=True)
class ChatContextPreferences:
    recent_history: bool = False
    saved_memories: bool = False
    today_plan: bool = False

    def __post_init__(self) -> None:
        if any(type(value) is not bool for value in (
            self.recent_history, self.saved_memories, self.today_plan
        )):
            raise ValidationError("Chat context preferences must be booleans.")

    @property
    def enabled_categories(self) -> tuple[str, ...]:
        values = []
        if self.recent_history:
            values.append("recent conversation")
        if self.saved_memories:
            values.append("saved memories")
        if self.today_plan:
            values.append("today's plan")
        return tuple(values)


@dataclass(frozen=True)
class PersonalityProfile:
    response_language: str = "zh-CN"
    tone: str = "温和、直接、尊重用户选择"
    principles: tuple[str, ...] = (
        "先理解用户当前需要，再提供有帮助的回应。",
        "不声称执行了实际未执行的操作。",
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "response_language", _require_text(self.response_language, "response_language", limit=32)
        )
        object.__setattr__(self, "tone", _require_text(self.tone, "tone", limit=200))
        if not isinstance(self.principles, tuple) or len(self.principles) > 8:
            raise ValidationError("Personality principles must be a tuple with at most 8 items.")
        normalized = tuple(_require_text(item, "principle", limit=300) for item in self.principles)
        object.__setattr__(self, "principles", normalized)


@dataclass(frozen=True)
class ChatSettings:
    provider: ProviderConfiguration | None = None
    context_preferences: ChatContextPreferences = field(default_factory=ChatContextPreferences)
    personality: PersonalityProfile = field(default_factory=PersonalityProfile)
    consent_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if self.provider is not None and not isinstance(self.provider, ProviderConfiguration):
            raise ValidationError("provider must be a ProviderConfiguration or None.")
        if not isinstance(self.context_preferences, ChatContextPreferences):
            raise ValidationError("context_preferences must be ChatContextPreferences.")
        if not isinstance(self.personality, PersonalityProfile):
            raise ValidationError("personality must be a PersonalityProfile.")
        if self.consent_fingerprint is not None:
            fingerprint = _require_text(self.consent_fingerprint, "consent_fingerprint", limit=64)
            if len(fingerprint) != 64 or any(char not in "0123456789abcdef" for char in fingerprint):
                raise ValidationError("consent_fingerprint must be a lowercase SHA-256 value.")
            object.__setattr__(self, "consent_fingerprint", fingerprint)


@dataclass(frozen=True)
class PromptMessage:
    role: ProviderMessageRole
    content: str

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "role", ProviderMessageRole(self.role))
        except (TypeError, ValueError) as error:
            raise ValidationError("Prompt message role is invalid.") from error
        object.__setattr__(self, "content", _require_text(self.content, "prompt content", limit=48_000))


@dataclass(frozen=True)
class ChatRequest:
    model: str
    messages: tuple[PromptMessage, ...]
    timeout_seconds: int
    cancellation_token: CancellationToken | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "model", _require_text(self.model, "model", limit=200))
        if not isinstance(self.messages, tuple) or not 1 <= len(self.messages) <= 14:
            raise ValidationError("Chat request must contain between 1 and 14 messages.")
        if any(not isinstance(message, PromptMessage) for message in self.messages):
            raise ValidationError("Chat request messages must be PromptMessage values.")
        if sum(len(message.content) for message in self.messages) > 48_000:
            raise ValidationError("Chat request exceeds the 48,000 character limit.")
        if type(self.timeout_seconds) is not int or not 5 <= self.timeout_seconds <= 120:
            raise ValidationError("Chat request timeout must be between 5 and 120 seconds.")


@dataclass(frozen=True)
class ProviderCall:
    configuration: ProviderConfiguration
    request: ChatRequest
    credential: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, ProviderConfiguration):
            raise ValidationError("Provider call requires a validated configuration.")
        if not isinstance(self.request, ChatRequest):
            raise ValidationError("Provider call requires a validated chat request.")
        object.__setattr__(self, "credential", _require_text(self.credential, "credential", limit=4096))


@dataclass(frozen=True)
class ChatResponse:
    content: str
    model: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", _require_text(self.content, "response content", limit=20_000))
        if self.model is not None:
            object.__setattr__(self, "model", _require_text(self.model, "response model", limit=200))


@dataclass(frozen=True)
class ConsentDisclosure:
    provider_host: str
    enabled_categories: tuple[str, ...]
    current_message_included: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_host", _require_text(self.provider_host, "provider_host", limit=255))
        if not isinstance(self.enabled_categories, tuple):
            raise ValidationError("enabled_categories must be a tuple.")
        if not self.current_message_included:
            raise ValidationError("The current message must be included in the consent disclosure.")


@dataclass(frozen=True)
class ChatSendResult:
    conversation: Conversation
    user_message: ChatMessage
    assistant_message: ChatMessage | None
    error_code: ProviderErrorCode | None = None


def consent_fingerprint(
    configuration: ProviderConfiguration, preferences: ChatContextPreferences
) -> str:
    """Bind consent to the normalized HTTPS recipient and the optional data categories."""
    parsed = urlsplit(configuration.base_url)
    host = (parsed.hostname or "").casefold()
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    canonical = json.dumps(
        {"scheme": parsed.scheme.casefold(), "host": host,
         "categories": list(preferences.enabled_categories)},
        ensure_ascii=True, separators=(",", ":"), sort_keys=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
