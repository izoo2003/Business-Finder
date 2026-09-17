"""Yelp Fusion Business Search client."""

from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone
from typing import Any

import httpx

from acquisition.candidates import BusinessCandidate
from acquisition.http_retry import raise_for_status_safe, request_with_retries
from acquisition.search_result import ClientSearchResult
from sources.models import DataSource
from sources.quota import record_api_call

logger = logging.getLogger("acquisition")

YELP_SEARCH_URL = "https://api.yelp.com/v3/businesses/search"


class YelpClient:
    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("Yelp API key is required")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    def search(
        self,
        *,
        location: str,
        categories: str,
        source: DataSource,
        limit: int = 25,
        page_size: int = 50,
        resume: dict | None = None,
    ) -> ClientSearchResult:
        page_size = min(50, max(1, page_size))
        collected: list[BusinessCandidate] = []
        offset = int((resume or {}).get("offset") or 0)
        total = 0
        exhausted = False

        with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
            while len(collected) < limit:
                params = {
                    "location": location,
                    "categories": categories,
                    "limit": min(page_size, limit - len(collected)),
                    "offset": offset,
                }
                logger.info("Yelp search location=%s categories=%s offset=%s", location, categories, offset)
                response = request_with_retries(client, "GET", YELP_SEARCH_URL, params=params)
                self._update_quota_from_headers(source, response)
                if response.status_code == 429:
                    source.quota_status = DataSource.QuotaStatus.EXHAUSTED
                    source.save(update_fields=["quota_status", "updated_at"])
                    raise_for_status_safe(response)
                raise_for_status_safe(response)
                payload = response.json()
                businesses = payload.get("businesses") or []
                if not businesses:
                    exhausted = True
                    break
                for biz in businesses:
                    candidate = self._to_candidate(biz)
                    if candidate and candidate.raw_phone:
                        collected.append(candidate)
                    if len(collected) >= limit:
                        break
                total = int(payload.get("total") or 0)
                offset += len(businesses)
                if offset >= total or len(businesses) < params["limit"]:
                    exhausted = True
                    break

        next_cursor = None if exhausted else {"offset": offset}
        return ClientSearchResult(candidates=collected[:limit], next_cursor=next_cursor)

    def _update_quota_from_headers(self, source: DataSource, response: httpx.Response) -> None:
        headers = {k.lower(): v for k, v in response.headers.items()}
        remaining = _parse_int(
            headers.get("ratelimit-remaining")
            or headers.get("rate-limit-remaining")
            or headers.get("x-ratelimit-remaining")
        )
        limit = _parse_int(
            headers.get("ratelimit-dailylimit")
            or headers.get("rate-limit-daily-limit")
            or headers.get("x-ratelimit-limit")
        )
        reset_raw = (
            headers.get("ratelimit-resettimer")
            or headers.get("rate-limit-reset")
            or headers.get("x-ratelimit-reset")
        )
        reset_at = None
        if reset_raw:
            try:
                # Yelp often returns seconds until reset or epoch
                val = int(float(reset_raw))
                if val > 1_000_000_000:
                    reset_at = datetime.fromtimestamp(val, tz=dt_timezone.utc)
            except (TypeError, ValueError):
                reset_at = None

        if remaining is None and limit is None:
            record_api_call(source, decrement=1)
        else:
            record_api_call(source, remaining=remaining, limit=limit, reset_at=reset_at)

    def _to_candidate(self, biz: dict[str, Any]) -> BusinessCandidate | None:
        phone = (biz.get("phone") or biz.get("display_phone") or "").strip()
        if not phone:
            return None
        loc = biz.get("location") or {}
        address_parts = loc.get("display_address") or []
        address = ", ".join(address_parts) if isinstance(address_parts, list) else str(address_parts)
        cats = biz.get("categories") or []
        category = ""
        if cats and isinstance(cats, list):
            category = cats[0].get("title") or cats[0].get("alias") or ""
        biz_id = str(biz.get("id") or "")
        return BusinessCandidate(
            raw_phone=phone,
            business_name=(biz.get("name") or "Unknown")[:255],
            address=address[:512],
            city=(loc.get("city") or "")[:128],
            state=(loc.get("state") or "")[:2],
            postal_code=(loc.get("zip_code") or "")[:16],
            category=category[:128],
            source_record_id=biz_id[:128],
            source_url=(biz.get("url") or "")[:1024],
            raw_payload=biz,
        )


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
