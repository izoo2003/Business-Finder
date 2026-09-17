"""Redact secrets from URLs and exception messages before logging or DB storage."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Query / form param names that commonly carry API keys or tokens.
SENSITIVE_PARAM_NAMES = frozenset(
    {
        "apikey",
        "api_key",
        "key",
        "access_token",
        "accesstoken",
        "token",
        "password",
        "passwd",
        "secret",
        "client_secret",
        "authorization",
        "auth",
    }
)

_BEARER_RE = re.compile(r"(Bearer\s+)(\S+)", re.IGNORECASE)
_BASIC_AUTH_IN_URL_RE = re.compile(r"(://)([^/@\s]+):([^/@\s]+)(@)")


def redact_url(url: str) -> str:
    """Return URL with sensitive query params and userinfo redacted."""
    if not url:
        return url
    try:
        parsed = urlparse(url)
    except Exception:
        return "[unparseable-url]"

    # Redact user:password@host
    netloc = parsed.netloc
    if "@" in netloc:
        userinfo, _, host = netloc.rpartition("@")
        if ":" in userinfo:
            user, _, _passwd = userinfo.partition(":")
            netloc = f"{user}:REDACTED@{host}"
        else:
            netloc = f"REDACTED@{host}"

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    safe_pairs: list[tuple[str, str]] = []
    for name, value in query_pairs:
        if name.lower() in SENSITIVE_PARAM_NAMES:
            safe_pairs.append((name, "REDACTED"))
        else:
            safe_pairs.append((name, value))
    safe_query = urlencode(safe_pairs)

    return urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            safe_query,
            "",  # drop fragment
        )
    )


def safe_error_message(exc: BaseException | str, *, max_len: int = 4000) -> str:
    """
    Build a log/DB-safe error string: redact URLs and bearer tokens.
    Prefer scheme+host+path style when a full httpx URL is embedded.
    """
    text = str(exc) if not isinstance(exc, str) else exc
    # Redact any http(s) URLs found in the message.
    def _replace_url(match: re.Match[str]) -> str:
        return redact_url(match.group(0))

    text = re.sub(r"https?://[^\s\"'<>]+", _replace_url, text)
    text = _BEARER_RE.sub(r"\1REDACTED", text)
    text = _BASIC_AUTH_IN_URL_RE.sub(r"\1\2:REDACTED\4", text)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text
