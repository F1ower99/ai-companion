from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Mapping, Protocol
from urllib.parse import unquote, urlsplit, urlunsplit

from companion.domain.chat import ChatResponse, ProviderCall, ProviderError, ProviderErrorCode


MAX_REQUEST_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024


class HttpStatusError(RuntimeError):
    """HTTP status without body, URL, or provider-provided diagnostic text."""

    def __init__(self, status: int) -> None:
        if type(status) is not int or not 100 <= status <= 599:
            raise ValueError("HTTP status must be an integer from 100 to 599.")
        self.status = status
        super().__init__(str(status))


class ResponseTooLarge(RuntimeError):
    """The transport observed more than the configured maximum response bytes."""


class HttpTransport(Protocol):
    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout: int,
        max_response_bytes: int,
    ) -> bytes: ...


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UrllibTransport:
    """Bounded HTTPS POST transport which refuses all HTTP redirects."""

    def __init__(self, opener_factory=None) -> None:
        self.opener_factory = opener_factory or urllib.request.build_opener

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout: int,
        max_response_bytes: int,
    ) -> bytes:
        if type(max_response_bytes) is not int or max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive.")
        request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
        opener = self.opener_factory(_NoRedirectHandler())
        try:
            with opener.open(request, timeout=timeout) as response:
                payload = response.read(max_response_bytes + 1)
        except urllib.error.HTTPError as error:
            # Never read or retain the provider's error body.
            raise HttpStatusError(error.code) from None
        if len(payload) > max_response_bytes:
            raise ResponseTooLarge()
        return payload


def _endpoint(base_url: str) -> str:
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
        hostname = parsed.hostname
    except (TypeError, ValueError) as error:
        raise ProviderError(ProviderErrorCode.CONFIGURATION) from None
    if (
        not isinstance(base_url, str)
        or not base_url
        or any(ord(char) <= 32 or ord(char) == 127 for char in base_url)
        or parsed.scheme.casefold() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ProviderError(ProviderErrorCode.CONFIGURATION)
    if port is not None and not 1 <= port <= 65535:
        raise ProviderError(ProviderErrorCode.CONFIGURATION)
    decoded_path = unquote(parsed.path)
    if "\\" in decoded_path or any(segment in {".", ".."} for segment in decoded_path.split("/")):
        raise ProviderError(ProviderErrorCode.CONFIGURATION)
    path = parsed.path.rstrip("/") + "/chat/completions"
    return urlunsplit(("https", parsed.netloc, path, "", ""))


def _http_status_error(status: int) -> ProviderErrorCode:
    if status in (401, 403):
        return ProviderErrorCode.AUTHENTICATION
    if status == 429:
        return ProviderErrorCode.RATE_LIMITED
    if status in (300, 301, 302, 303, 304, 305, 307, 308):
        return ProviderErrorCode.UNAVAILABLE
    if 500 <= status <= 599:
        return ProviderErrorCode.UNAVAILABLE
    if 400 <= status <= 499:
        return ProviderErrorCode.CONFIGURATION
    return ProviderErrorCode.INVALID_RESPONSE


def _is_timeout(error: BaseException) -> bool:
    if isinstance(error, (TimeoutError, socket.timeout)):
        return True
    return isinstance(error, urllib.error.URLError) and isinstance(
        error.reason, (TimeoutError, socket.timeout)
    )


class OpenAICompatibleProvider:
    def __init__(self, transport: HttpTransport | None = None) -> None:
        self.transport = transport or UrllibTransport()

    def complete(self, call: ProviderCall) -> ChatResponse:
        if not isinstance(call, ProviderCall):
            raise ProviderError(ProviderErrorCode.CONFIGURATION)
        try:
            endpoint = _endpoint(call.configuration.base_url)
        except ProviderError:
            raise
        except Exception:
            raise ProviderError(ProviderErrorCode.CONFIGURATION) from None
        if call.request.model != call.configuration.model:
            raise ProviderError(ProviderErrorCode.CONFIGURATION)
        credential = call.credential
        if (
            not credential
            or any(char.isspace() or ord(char) < 33 or ord(char) > 126 for char in credential)
        ):
            raise ProviderError(ProviderErrorCode.CONFIGURATION)

        payload = {
            "model": call.request.model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in call.request.messages
            ],
            "stream": False,
        }
        try:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError, UnicodeError):
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
        if len(body) > MAX_REQUEST_BYTES:
            raise ProviderError(ProviderErrorCode.CONFIGURATION)
        if call.request.cancellation_token is not None and call.request.cancellation_token.is_cancelled():
            raise ProviderError(ProviderErrorCode.CANCELLED)
        headers = {
            "Authorization": f"Bearer {credential}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            response_body = self.transport.post(
                endpoint,
                headers,
                body,
                call.request.timeout_seconds,
                MAX_RESPONSE_BYTES,
            )
        except HttpStatusError as error:
            raise ProviderError(_http_status_error(error.status)) from None
        except ResponseTooLarge:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
        except Exception as error:
            code = ProviderErrorCode.TIMEOUT if _is_timeout(error) else ProviderErrorCode.UNAVAILABLE
            raise ProviderError(code) from None
        if not isinstance(response_body, bytes) or len(response_body) > MAX_RESPONSE_BYTES:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        try:
            result = json.loads(response_body.decode("utf-8"))
            choices = result["choices"]
            if not isinstance(choices, list) or not choices:
                raise ValueError
            message = choices[0]["message"]
            if not isinstance(message, dict) or message.get("role", "assistant") != "assistant":
                raise ValueError
            content = message["content"]
            model = result.get("model")
            if model is not None and not isinstance(model, str):
                raise ValueError
            return ChatResponse(content=content, model=model)
        except Exception:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
