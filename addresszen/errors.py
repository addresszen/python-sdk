"""Public exceptions. Messages omit request URLs, credentials and response payloads."""

from __future__ import annotations

from typing import Any, cast


class ClientError(Exception):
    """Base for API responses, network failures and malformed responses."""


class TransportError(ClientError):
    """The request failed before an HTTP response was available. Not retried."""


class ProtocolError(ClientError):
    """The server returned an unexpected status, a malformed envelope or a result of the wrong JSON type.

    result is always None. Result fields that break the spec warn with ResponseValidationWarning instead.
    """

    def __init__(self, message: str, result: object = None) -> None:
        self.result = result
        super().__init__(message)


class ResponseValidationWarning(UserWarning):
    """A result did not match the API spec and was returned unvalidated. Names field paths, never values."""


class APIError(ClientError):
    """An unsuccessful HTTP response, with API code and retry metadata."""

    def __init__(self, status: int, body: dict[str, Any], retry_after: str | None = None) -> None:
        code = body.get("code")
        message = body.get("message")
        self.status = status
        self.code = code if isinstance(code, int) else 0
        self.message = message if isinstance(message, str) else "API request failed"
        self.body = body
        self.retry_after = retry_after
        summary = f"API request failed (HTTP {status}, code {self.code})"
        super().__init__(f"{summary}: {message}" if isinstance(message, str) and message else summary)


class AuthenticationError(APIError):
    """HTTP 401 or 403. Check credentials and permissions."""


class PaymentRequiredError(APIError):
    """HTTP 402. Check the balance and account limits."""


class NotFoundError(APIError):
    """HTTP 404. The requested resource was not found."""

    @property
    def suggestions(self) -> list[str]:
        value = self.body.get("suggestions")
        if not isinstance(value, list):
            return []
        return [item for item in cast("list[object]", value) if isinstance(item, str)]


class RateLimitError(APIError):
    """HTTP 429 or API throttling code 5030. Retry-After is preserved verbatim."""


class ServerError(APIError):
    """HTTP 5xx without a recognised throttling code."""


def error_for(status: int, body: dict[str, Any], retry_after: str | None) -> APIError:
    if status == 429 or (status == 503 and body.get("code") == 5030):
        cls = RateLimitError
    elif status >= 500:
        cls = ServerError
    else:
        cls = {
            401: AuthenticationError,
            403: AuthenticationError,
            402: PaymentRequiredError,
            404: NotFoundError,
        }.get(status, APIError)
    return cls(status, body, retry_after)
