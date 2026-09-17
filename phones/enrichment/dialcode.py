"""DialCode phone validation / risk API client (Phase 6)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_timezone
from typing import Any
from urllib.parse import quote

import httpx

from acquisition.http_retry import raise_for_status_safe, request_with_retries
from sources.models import DataSource
from sources.quota import record_api_call

logger = logging.getLogger("phones")

DIALCODE_BASE_URL = "https://dialcode.app/v1/phone"


@dataclass
class DialCodeResult:
    valid: bool | None
    line_type: str
    carrier: str
    risk_level: str
    risk_signals: list[Any] = field(default_factory=list)
    enrichment_geo: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class DialCodeClient:
    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("DialCode API key is required")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "X-Api-Key": self.api_key,
            "Accept": "application/json",
        }

    def lookup(self, e164: str, *, source: DataSource) -> DialCodeResult:
        # Path-safe E.164 (+ must be encoded)
        path_number = quote(e164, safe="")
        url = f"{DIALCODE_BASE_URL}/{path_number}"
        logger.info("DialCode lookup %s", e164)

        with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
            response = request_with_retries(client, "GET", url)
            self._update_quota_from_headers(source, response)
            if response.status_code == 429:
                source.quota_status = DataSource.QuotaStatus.EXHAUSTED
                source.save(update_fields=["quota_status", "updated_at"])
                raise_for_status_safe(response)
            raise_for_status_safe(response)
            payload = response.json()

        return self._parse(payload)

    def _update_quota_from_headers(self, source: DataSource, response: httpx.Response) -> None:
        headers = {k.lower(): v for k, v in response.headers.items()}
        remaining = _parse_int(headers.get("x-ratelimit-remaining"))
        limit = _parse_int(headers.get("x-ratelimit-limit"))
        reset_raw = headers.get("x-ratelimit-reset")
        reset_at = None
        if reset_raw:
            try:
                val = int(float(reset_raw))
                if val > 1_000_000_000:
                    reset_at = datetime.fromtimestamp(val, tz=dt_timezone.utc)
            except (TypeError, ValueError):
                reset_at = None

        if remaining is None and limit is None:
            record_api_call(source, decrement=1)
        else:
            record_api_call(source, remaining=remaining, limit=limit, reset_at=reset_at)

    def _parse(self, payload: dict[str, Any]) -> DialCodeResult:
        risk = payload.get("risk") or {}
        signals = risk.get("signals")
        if not isinstance(signals, list):
            signals = []

        area = payload.get("area") or {}
        country = payload.get("country") or {}
        geo_parts: list[str] = []
        area_name = (area.get("name") or "").strip()
        area_code = str(area.get("code") or "").strip()
        if area_name:
            geo_parts.append(area_name)
        elif area_code:
            geo_parts.append(f"area {area_code}")
        tz = (country.get("timezone") or "").strip()
        if tz:
            geo_parts.append(tz)
        country_code = (country.get("code") or "").strip()
        if country_code:
            geo_parts.append(country_code)

        carrier = payload.get("carrier")
        line_type = payload.get("line_type")
        scam_risk = risk.get("scam_risk")

        return DialCodeResult(
            valid=payload.get("valid") if isinstance(payload.get("valid"), bool) else None,
            line_type=(str(line_type) if line_type else "")[:32],
            carrier=(str(carrier) if carrier else "")[:128],
            risk_level=(str(scam_risk) if scam_risk else "")[:32],
            risk_signals=signals,
            enrichment_geo=", ".join(geo_parts)[:255],
            raw=payload if isinstance(payload, dict) else {},
        )


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
