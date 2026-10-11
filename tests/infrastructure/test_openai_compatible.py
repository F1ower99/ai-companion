import json
import urllib.request

import pytest

from companion.domain.chat import (
    ChatRequest,
    ChatResponse,
    PromptMessage,
    ProviderCall,
    ProviderConfiguration,
    ProviderError,
    ProviderErrorCode,
    ProviderMessageRole,
)
from companion.domain.errors import ValidationError
from companion.infrastructure.openai_compatible import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    HttpStatusError,
    OpenAICompatibleProvider,
    UrllibTransport,
    _NoRedirectHandler,
)


SECRET = "test-secret-that-must-not-escape"


class FakeTransport:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def post(self, url, headers, body, timeout, max_response_bytes):
        self.calls.append((url, headers, body, timeout, max_response_bytes))
        if self.error:
            raise self.error
        return self.response


def make_call(base_url="https://provider.example/v1", *, credential=SECRET, content="hello"):
    config = ProviderConfiguration(base_url, "test-model", 17)
    request = ChatRequest(
        model="test-model",
        messages=(
            PromptMessage(ProviderMessageRole.SYSTEM, "Be helpful."),
            PromptMessage(ProviderMessageRole.USER, content),
        ),
        timeout_seconds=17,
    )
    return ProviderCall(config, request, credential)


def valid_response(text="hello from model"):
    return json.dumps({
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "model": "test-model",
    }).encode("utf-8")


def test_provider_posts_nonstreaming_chat_completion_and_parses_text():
    transport = FakeTransport(valid_response())
    response = OpenAICompatibleProvider(transport).complete(make_call())

    assert response == ChatResponse("hello from model", "test-model")
    assert len(transport.calls) == 1
    url, headers, body, timeout, max_bytes = transport.calls[0]
    assert url == "https://provider.example/v1/chat/completions"
    assert headers["Authorization"] == f"Bearer {SECRET}"
    assert headers["Content-Type"] == "application/json"
    payload = json.loads(body.decode("utf-8"))
    assert payload == {
        "model": "test-model",
        "messages": [
            {"role": "system", "content": "Be helpful."},
            {"role": "user", "content": "hello"},
        ],
        "stream": False,
    }
    assert timeout == 17
    assert max_bytes == MAX_RESPONSE_BYTES
    assert len(body) <= MAX_REQUEST_BYTES


@pytest.mark.parametrize(
    "base_url",
    [
        "http://provider.example/v1",
        "https://user:pass@provider.example/v1",
        "https://provider.example/v1?key=value",
        "https://provider.example/v1#fragment",
    ],
)
def test_configuration_rejects_non_https_or_credential_bearing_urls(base_url):
    with pytest.raises(ValidationError):
        ProviderConfiguration(base_url, "model", 30)


def test_malformed_base_path_is_rejected_before_transport_call():
    transport = FakeTransport(valid_response())
    with pytest.raises(ProviderError) as error:
        OpenAICompatibleProvider(transport).complete(
            make_call("https://provider.example/v1/../admin")
        )
    assert error.value.code is ProviderErrorCode.CONFIGURATION
    assert transport.calls == []


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ProviderErrorCode.AUTHENTICATION),
        (403, ProviderErrorCode.AUTHENTICATION),
        (429, ProviderErrorCode.RATE_LIMITED),
        (503, ProviderErrorCode.UNAVAILABLE),
        (302, ProviderErrorCode.UNAVAILABLE),
        (400, ProviderErrorCode.CONFIGURATION),
    ],
)
def test_http_statuses_map_to_safe_error_codes(status, expected):
    transport = FakeTransport(error=HttpStatusError(status))
    with pytest.raises(ProviderError) as error:
        OpenAICompatibleProvider(transport).complete(make_call())
    assert error.value.code is expected
    assert SECRET not in str(error.value)


def test_timeout_is_sanitized_and_not_retried():
    transport = FakeTransport(error=TimeoutError(f"{SECRET} timeout detail"))
    with pytest.raises(ProviderError) as error:
        OpenAICompatibleProvider(transport).complete(make_call())
    assert error.value.code is ProviderErrorCode.TIMEOUT
    assert SECRET not in str(error.value)
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"{}",
        b'{"choices": []}',
        b'{"choices": [{"message": {"role": "assistant", "content": "  "}}]}',
        b'{"choices": [{"message": {"role": "assistant", "content": ["not text"]}}]}',
    ],
)
def test_malformed_or_empty_responses_are_rejected(body):
    with pytest.raises(ProviderError) as error:
        OpenAICompatibleProvider(FakeTransport(body)).complete(make_call())
    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE
    assert SECRET not in str(error.value)


def test_oversized_response_is_rejected_without_parsing():
    body = b"x" * (MAX_RESPONSE_BYTES + 1)
    with pytest.raises(ProviderError) as error:
        OpenAICompatibleProvider(FakeTransport(body)).complete(make_call())
    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE


def test_redirect_handler_refuses_redirects_and_provider_never_retries():
    request = urllib.request.Request("https://provider.example/start")
    handler = _NoRedirectHandler()
    assert handler.redirect_request(request, None, 302, "Found", {}, "https://other.example/") is None
    transport = FakeTransport(error=HttpStatusError(302))
    with pytest.raises(ProviderError):
        OpenAICompatibleProvider(transport).complete(make_call())
    assert len(transport.calls) == 1


def test_credential_and_request_content_are_not_in_repr_or_safe_errors():
    call = make_call(content="private message")
    assert SECRET not in repr(call)
    transport = FakeTransport(error=OSError("connection detail"))
    with pytest.raises(ProviderError) as error:
        OpenAICompatibleProvider(transport).complete(call)
    assert SECRET not in repr(error.value)
    assert SECRET not in str(error.value)
    assert "private message" not in str(error.value)


@pytest.mark.parametrize("credential", ["bad\r\nInjected: yes", "non-ascii-密钥"])
def test_invalid_bearer_header_values_are_rejected_before_transport(credential):
    transport = FakeTransport(valid_response())
    with pytest.raises(ProviderError) as error:
        OpenAICompatibleProvider(transport).complete(make_call(credential=credential))
    assert error.value.code is ProviderErrorCode.CONFIGURATION
    assert transport.calls == []


def test_urllib_transport_reads_at_most_the_configured_response_limit(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, size):
            assert size == MAX_RESPONSE_BYTES + 1
            return b"{}"

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == "https://provider.example/v1/chat/completions"
            assert timeout == 17
            return Response()

    transport = UrllibTransport(opener_factory=lambda _handler: Opener())
    body = transport.post(
        "https://provider.example/v1/chat/completions",
        {"Authorization": f"Bearer {SECRET}"},
        b"{}",
        17,
        MAX_RESPONSE_BYTES,
    )
    assert body == b"{}"
