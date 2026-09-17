"""Save a rotated API key, reset quota, and optionally ping the provider."""

from __future__ import annotations

import logging

import httpx
from django.utils import timezone

from sources.crypto import encrypt_api_key, last4
from sources.models import DataSource
from sources.quota import mark_from_remaining

logger = logging.getLogger("sources")


class KeyRotationError(Exception):
    """Raised when a pasted key cannot be saved."""


def rotate_api_key(source: DataSource, raw_key: str, *, verify: bool = True) -> dict:
    """
    Encrypt and store a new key. Resets quota to Healthy so collection can resume.
    Returns {verified, message}. Never returns the key.
    """
    if not source.api_key_env_var and source.slug != "openstreetmap":
        # Still allow storing a key for unknown keyed sources.
        pass
    if source.slug == "openstreetmap" or not guide_needs_key(source):
        raise KeyRotationError("This source does not use an API key.")

    key = (raw_key or "").strip()
    if len(key) < 8:
        raise KeyRotationError("That does not look like a full API key. Paste the whole key.")

    verified = True
    message = "New key saved. This source is ready to use."
    if verify:
        ok, verify_message = verify_api_key(source.slug, key)
        if ok is False:
            raise KeyRotationError(verify_message)
        if ok is None:
            verified = False
            message = verify_message

    source.api_key_ciphertext = encrypt_api_key(key)
    source.api_key_hint = last4(key)
    source.is_active = True
    if source.quota_max is not None:
        source.quota_remaining = source.quota_max
    source.quota_status = DataSource.QuotaStatus.HEALTHY
    source.quota_refreshed_at = timezone.now()
    mark_from_remaining(source)
    source.save(
        update_fields=[
            "api_key_ciphertext",
            "api_key_hint",
            "is_active",
            "quota_remaining",
            "quota_status",
            "quota_refreshed_at",
            "updated_at",
        ]
    )
    logger.info("Rotated API key for %s (hint=%s)", source.slug, source.api_key_hint)
    return {"verified": verified, "message": message}


def guide_needs_key(source: DataSource) -> bool:
    from sources.provider_guides import guide_for

    return bool(guide_for(source.slug)["needs_key"] or source.api_key_env_var)


def verify_api_key(slug: str, key: str) -> tuple[bool | None, str]:
    """
    Cheap provider ping.
    True = accepted, False = rejected, None = could not verify (save anyway).
    """
    try:
        status = _ping_provider(slug, key)
    except httpx.HTTPError:
        return None, "Key saved, but we could not reach the provider to double-check it."
    except Exception:
        logger.exception("Key verify failed for %s", slug)
        return None, "Key saved. We could not double-check it with the provider."

    if status is None:
        return True, "New key saved. This source is ready to use."
    if status in (401, 403):
        return False, "The provider rejected this key. Check you copied the whole key."
    if status >= 500:
        return None, "Key saved. The provider was busy, so we could not double-check it."
    return True, "New key saved. This source is ready to use."


def _ping_provider(slug: str, key: str) -> int | None:
    timeout = httpx.Timeout(8.0)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        if slug == "geoapify":
            response = client.get(
                "https://api.geoapify.com/v1/geocode/search",
                params={"text": "Austin, USA", "limit": 1, "apiKey": key},
            )
            return response.status_code
        if slug == "locationiq":
            response = client.get(
                "https://us1.locationiq.com/v1/search",
                params={"q": "Austin, USA", "format": "json", "limit": 1, "key": key},
            )
            return response.status_code
        if slug == "tomtom":
            response = client.get(
                "https://api.tomtom.com/search/2/geocode/Austin,USA.json",
                params={"key": key, "limit": 1, "countrySet": "US"},
            )
            return response.status_code
        if slug == "yelp":
            response = client.get(
                "https://api.yelp.com/v3/businesses/search",
                headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
                params={"location": "Austin", "limit": 1},
            )
            return response.status_code
        if slug == "foursquare":
            response = client.get(
                "https://api.foursquare.com/v3/places/search",
                headers={"Authorization": key, "Accept": "application/json"},
                params={"near": "Austin, TX", "limit": 1},
            )
            return response.status_code
        if slug == "google-places":
            response = client.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": key,
                    "X-Goog-FieldMask": "places.id",
                },
                json={"textQuery": "cafe in Austin, USA", "pageSize": 1, "regionCode": "US"},
            )
            return response.status_code
        if slug == "dialcode":
            response = client.get(
                "https://dialcode.app/v1/phone/%2B15125551234",
                headers={"X-Api-Key": key, "Accept": "application/json"},
            )
            return response.status_code
    return None
