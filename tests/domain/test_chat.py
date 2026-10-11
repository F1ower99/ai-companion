from datetime import datetime, timezone

import pytest

from companion.domain.errors import ValidationError
from companion.domain.chat import (
    ChatContextPreferences,
    ChatMessage,
    ChatResponse,
    ChatRole,
    ChatSettings,
    Conversation,
    DeliveryState,
    PersonalityProfile,
    PromptMessage,
    ProviderCall,
    ProviderConfiguration,
    ProviderMessageRole,
    ChatRequest,
    consent_fingerprint,
)


NOW = datetime(2026, 10, 11, 4, 0, tzinfo=timezone.utc)


def test_user_message_can_be_pending_but_assistant_message_must_be_sent():
    pending_user = ChatMessage(
        id="u1", conversation_id="c1", role=ChatRole.USER, content="hello",
        created_at=NOW, delivery_state=DeliveryState.PENDING,
    )
    assert pending_user.delivery_state is DeliveryState.PENDING

    with pytest.raises(ValidationError, match="(?i)assistant"):
        ChatMessage(
            id="a1", conversation_id="c1", role=ChatRole.ASSISTANT, content="hello",
            created_at=NOW, delivery_state=DeliveryState.PENDING,
        )


def test_chat_records_require_aware_times_and_nonblank_content():
    with pytest.raises(ValidationError, match="timezone"):
        Conversation("c1", datetime(2026, 10, 11), NOW)
    with pytest.raises(ValidationError, match="content"):
        ChatMessage(
            "u1", "c1", ChatRole.USER, "  ", NOW, DeliveryState.SENT,
        )


def test_provider_configuration_bounds_timeout_and_model():
    with pytest.raises(ValidationError, match="timeout"):
        ProviderConfiguration("https://api.example.test/v1", "model", 0)
    with pytest.raises(ValidationError, match="model"):
        ProviderConfiguration("https://api.example.test/v1", " ", 30)


def test_context_preferences_default_to_private_and_settings_are_validated():
    preferences = ChatContextPreferences()
    assert not preferences.recent_history
    assert not preferences.saved_memories
    assert not preferences.today_plan
    settings = ChatSettings(
        provider=ProviderConfiguration("https://api.example.test/v1", "model", 30),
        context_preferences=preferences,
        personality=PersonalityProfile(),
    )
    assert settings.consent_fingerprint is None


def test_consent_fingerprint_changes_with_host_or_shared_context():
    config = ProviderConfiguration("https://one.example/v1", "model", 30)
    same_config = ProviderConfiguration("https://one.example/v1", "other-model", 30)
    base = ChatContextPreferences()
    with_history = ChatContextPreferences(recent_history=True)

    assert consent_fingerprint(config, base) == consent_fingerprint(same_config, base)
    assert consent_fingerprint(config, base) != consent_fingerprint(
        ProviderConfiguration("https://two.example/v1", "model", 30), base
    )
    assert consent_fingerprint(config, base) != consent_fingerprint(config, with_history)


def test_provider_call_never_exposes_credential_in_repr():
    request = ChatRequest(
        model="model", messages=(PromptMessage(ProviderMessageRole.USER, "hello"),),
        timeout_seconds=30,
    )
    call = ProviderCall(
        configuration=ProviderConfiguration("https://api.example.test/v1", "model", 30),
        request=request,
        credential="secret-value-that-must-not-appear",
    )
    assert "secret-value-that-must-not-appear" not in repr(call)


def test_provider_response_rejects_blank_content():
    with pytest.raises(ValidationError, match="content"):
        ChatResponse("   ")
