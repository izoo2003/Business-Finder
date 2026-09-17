"""Foursquare Places API search client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from acquisition.candidates import BusinessCandidate
from acquisition.http_retry import raise_for_status_safe, request_with_retries
from acquisition.search_result import ClientSearchResult
from sources.models import DataSource
from sources.quota import record_api_call

logger = logging.getLogger("acquisition")

FSQ_SEARCH_URL = "https://api.foursquare.com/v3/places/search"


class FoursquareClient:
    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("Foursquare API key is required")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.api_key,
            "Accept": "application/json",
        }

    def search(
        self,
        *,
        city: str,
        category: str,
        source: DataSource,
        limit: int = 25,
        resume: dict | None = None,
    ) -> ClientSearchResult:
        collected: list[BusinessCandidate] = []
        offset = int((resume or {}).get("offset") or 0)
        page_size = min(50, limit)
        exhausted = False

        with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
            while len(collected) < limit:
                params = {
                    "near": f"{city}, USA",
                    "query": category,
                    "limit": min(page_size, limit - len(collected)),
                    "offset": offset,
                    "fields": "fsq_id,name,tel,location,categories,website,link",
                }
                logger.info("Foursquare search near=%s query=%s offset=%s", city, category, offset)
                response = request_with_retries(client, "GET", FSQ_SEARCH_URL, params=params)
                record_api_call(source, decrement=1)
                if response.status_code == 429:
                    source.quota_status = DataSource.QuotaStatus.EXHAUSTED
                    source.save(update_fields=["quota_status", "updated_at"])
                raise_for_status_safe(response)
                payload = response.json()
                results = payload.get("results") or []
                if not results:
                    exhausted = True
                    break
                for item in results:
                    candidate = self._to_candidate(item)
                    if candidate and candidate.raw_phone:
                        collected.append(candidate)
                    if len(collected) >= limit:
                        break
                offset += len(results)
                if len(results) < params["limit"]:
                    exhausted = True
                    break

        next_cursor = None if exhausted else {"offset": offset}
        return ClientSearchResult(candidates=collected[:limit], next_cursor=next_cursor)

    def _to_candidate(self, item: dict[str, Any]) -> BusinessCandidate | None:
        phone = (item.get("tel") or "").strip()
        if not phone:
            return None
        loc = item.get("location") or {}
        cats = item.get("categories") or []
        category = ""
        if cats and isinstance(cats, list):
            category = cats[0].get("name") or ""
        fsq_id = str(item.get("fsq_id") or "")
        address = loc.get("formatted_address") or loc.get("address") or ""
        return BusinessCandidate(
            raw_phone=phone,
            business_name=(item.get("name") or "Unknown")[:255],
            address=str(address)[:512],
            city=(loc.get("locality") or loc.get("city") or "")[:128],
            state=(loc.get("region") or "")[:2],
            postal_code=(loc.get("postcode") or "")[:16],
            category=category[:128],
            source_record_id=fsq_id[:128],
            source_url=(item.get("website") or item.get("link") or "")[:1024],
            raw_payload=item,
        )
