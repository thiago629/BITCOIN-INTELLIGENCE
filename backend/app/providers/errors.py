"""Error hierarchy for the data-provider layer.

The service layer relies on these types to decide whether to fall back to
another provider (transient errors) or to stop (authoritative answers such as
"not found").
"""


class ProviderError(Exception):
    """Base error raised by a data provider."""

    def __init__(self, provider: str, message: str, status_code: int | None = None) -> None:
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.message = message
        self.status_code = status_code


class ProviderNotFound(ProviderError):
    """The requested object does not exist (or the identifier is invalid)."""


class ProviderRateLimited(ProviderError):
    """The provider asked us to slow down (HTTP 429)."""

    def __init__(self, provider: str, message: str, retry_after_s: float | None = None) -> None:
        super().__init__(provider, message, 429)
        self.retry_after_s = retry_after_s


class ProviderUnavailable(ProviderError):
    """Timeouts, connection failures, 5xx answers or malformed payloads."""


class CapabilityNotSupported(ProviderError):
    """The provider does not implement the requested operation."""


class AllProvidersFailed(Exception):
    """No configured provider could answer the request."""

    def __init__(self, operation: str, errors: list[ProviderError]) -> None:
        detail = "; ".join(str(e) for e in errors) or "no provider available"
        super().__init__(f"All providers failed for '{operation}': {detail}")
        self.operation = operation
        self.errors = errors
