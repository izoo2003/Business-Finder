"""Shared httpx retries for transient API failures (Phase 9)."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from django.conf import settings

from acquisition.secrets_safe import redact_url, safe_error_message

logger = logging.getLogger("acquisition")

RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


class SafeHTTPError(Exception):
    """HTTP failure with a redacted message (never includes API keys in URLs)."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def http_max_retries() -> int:
    return int(getattr(settings, "HTTP_MAX_RETRIES", 3))


def http_timeout() -> float:
    return float(getattr(settings, "HTTP_TIMEOUT", 30.0))


def raise_for_status_safe(response: httpx.Response) -> None:
    """Like Response.raise_for_status but never embeds raw query-string secrets."""
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        safe_url = redact_url(str(exc.request.url))
        raise SafeHTTPError(
            f"HTTP {exc.response.status_code} for {safe_url}",
            status_code=exc.response.status_code,
        ) from None


def request_with_retries(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    max_retries: int | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """
    Perform an HTTP request with retries on timeouts, connection errors,
    and 429 / 502 / 503 / 504. Honors Retry-After when present.
    Returns the last response (caller may raise_for_status_safe).
    """
    attempts = max_retries if max_retries is not None else http_max_retries()
    attempts = max(1, attempts)
    last_response: httpx.Response | None = None
    last_error: Exception | None = None
    safe_url = redact_url(url)

    for attempt in range(1, attempts + 1):
        try:
            response = client.request(method, url, **kwargs)
            last_response = response
            if response.status_code not in RETRYABLE_STATUS:
                return response
            if attempt >= attempts:
                return response
            wait = _backoff_seconds(response, attempt)
            logger.warning(
                "HTTP %s %s status=%s; retry in %.1fs (%s/%s)",
                method,
                safe_url,
                response.status_code,
                wait,
                attempt,
                attempts,
            )
            time.sleep(wait)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            last_error = exc
            if attempt >= attempts:
                raise SafeHTTPError(
                    safe_error_message(f"HTTP {method} {safe_url} failed: {exc}")
                ) from None
            wait = 2.0 * attempt
            logger.warning(
                "HTTP %s %s error=%s; retry in %.1fs (%s/%s)",
                method,
                safe_url,
                safe_error_message(exc, max_len=500),
                wait,
                attempt,
                attempts,
            )
            time.sleep(wait)

    if last_response is not None:
        return last_response
    raise SafeHTTPError(
        safe_error_message(
            f"HTTP request failed after {attempts} attempts: {last_error}"
        )
    )


def _backoff_seconds(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After") or response.headers.get("retry-after")
    if retry_after:
        try:
            return max(1.0, float(retry_after))
        except (TypeError, ValueError):
            pass
    return float(2 * attempt)
