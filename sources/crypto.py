"""Encrypt operator-pasted API keys at rest (Fernet derived from SECRET_KEY)."""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger("sources")


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_api_key(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        raise ValueError("API key is empty")
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_api_key(ciphertext: str) -> str | None:
    token = (ciphertext or "").strip()
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        logger.warning("Could not decrypt stored API key: %s", type(exc).__name__)
        return None


def last4(raw: str | None) -> str:
    value = (raw or "").strip()
    if len(value) < 4:
        return value
    return value[-4:]
