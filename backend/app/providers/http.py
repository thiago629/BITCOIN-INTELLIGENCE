"""Thin HTTP helper with retries and error classification for providers."""

import asyncio
import logging
from typing import Any

import httpx

from app.providers.errors import (
    ProviderError,
    ProviderNotFound,
    ProviderRateLimited,
    ProviderUnavailable,
)

logger = logging.getLogger(__name__)


class ProviderHttpClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        provider: str,
        base_url: str,
        max_retries: int = 2,
        backoff_base_s: float = 0.3,
    ) -> None:
        self._client = client
        self._provider = provider
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._backoff_base_s = backoff_base_s

    async def get_json(self, path: str) -> Any:
        resp = await self._get(path)
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderUnavailable(self._provider, f"invalid JSON from {path}") from exc

    async def get_text(self, path: str) -> str:
        resp = await self._get(path)
        return resp.text.strip()

    async def _get(self, path: str) -> httpx.Response:
        url = f"{self._base_url}{path}"
        last_error: ProviderError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = await self._client.get(url)
            except httpx.TimeoutException:
                last_error = ProviderUnavailable(self._provider, f"timeout on {path}")
            except httpx.TransportError as exc:
                last_error = ProviderUnavailable(
                    self._provider, f"connection error on {path}: {type(exc).__name__}"
                )
            else:
                status = resp.status_code
                if status == 200:
                    return resp
                if status in (400, 404):
                    # Esplora answers 400 for malformed ids and 404 for unknown ones.
                    raise ProviderNotFound(self._provider, f"not found or invalid: {path}", status)
                if status == 429:
                    raise ProviderRateLimited(
                        self._provider,
                        "rate limited",
                        retry_after_s=_parse_retry_after(resp.headers.get("Retry-After")),
                    )
                if status >= 500:
                    last_error = ProviderUnavailable(
                        self._provider, f"HTTP {status} on {path}", status
                    )
                else:
                    raise ProviderError(
                        self._provider, f"unexpected HTTP {status} on {path}", status
                    )

            if attempt < self._max_retries:
                await asyncio.sleep(self._backoff_base_s * (2**attempt))

        assert last_error is not None
        raise last_error


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
