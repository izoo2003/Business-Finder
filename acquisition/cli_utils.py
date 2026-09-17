"""Shared helpers for acquisition management commands."""

from __future__ import annotations

from django.core.management.base import CommandError

from acquisition.secrets_safe import safe_error_message
from sources.models import DataSource
from sources.quota import QuotaDenied, require_preflight


def load_active_source(slug: str) -> DataSource:
    try:
        return DataSource.objects.get(slug=slug, is_active=True)
    except DataSource.DoesNotExist as exc:
        raise CommandError(
            f"Active source '{slug}' not found. Run: python manage.py seed_sources"
        ) from exc


def require_api_key(source: DataSource) -> str:
    key = source.get_api_key()
    if not key:
        env_name = source.api_key_env_var or "API_KEY"
        raise CommandError(
            f"Missing API key for {source.name}. Paste it in the operator Keys page "
            f"or set {env_name} in your .env file."
        )
    return key


def require_source_ready(source: DataSource, min_calls: int = 1) -> None:
    try:
        require_preflight(source, min_calls=min_calls)
    except QuotaDenied as exc:
        raise CommandError(safe_error_message(exc)) from exc


def command_error_from_exc(exc: BaseException) -> CommandError:
    """Wrap any exception as CommandError with secrets redacted."""
    return CommandError(safe_error_message(exc))
