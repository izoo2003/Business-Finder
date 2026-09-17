"""Google Places API (New) text search + details for phone numbers."""

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

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACE_DETAIL_URL = "https://places.googleapis.com/v1/places/{place_id}"


class GooglePlacesClient:
    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("Google Places API key is required")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self, field_mask: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": field_mask,
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
        text_query = f"{category} in {city}, USA"
        collected: list[BusinessCandidate] = []
        page_token: str | None = (resume or {}).get("page_token") or None

        with httpx.Client(timeout=self.timeout) as client:
            while len(collected) < limit:
                body: dict[str, Any] = {
                    "textQuery": text_query,
                    "regionCode": "US",
                    "pageSize": min(20, limit - len(collected)),
                }
                if page_token:
                    body["pageToken"] = page_token

                logger.info("Google Places text search: %s", text_query)
                response = request_with_retries(
                    client,
                    "POST",
                    TEXT_SEARCH_URL,
                    headers=self._headers(
                        "places.id,places.displayName,places.formattedAddress,"
                        "places.nationalPhoneNumber,places.internationalPhoneNumber,"
                        "places.types,nextPageToken"
                    ),
                    json=body,
                )
                record_api_call(source, decrement=1)
                if response.status_code == 429:
                    source.quota_status = DataSource.QuotaStatus.EXHAUSTED
                    source.save(update_fields=["quota_status", "updated_at"])
                raise_for_status_safe(response)
                payload = response.json()
                places = payload.get("places") or []
                if not places:
                    page_token = None
                    break

                for place in places:
                    candidate = self._from_place(place)
                    if candidate is None:
                        # Details call only when search omitted phone
                        place_id = (place.get("id") or "").replace("places/", "")
                        if place_id:
                            candidate = self._fetch_details(client, source, place_id)
                    if candidate and candidate.raw_phone:
                        collected.append(candidate)
                    if len(collected) >= limit:
                        break

                page_token = payload.get("nextPageToken")
                if not page_token:
                    break

        next_cursor = {"page_token": page_token} if page_token else None
        return ClientSearchResult(candidates=collected[:limit], next_cursor=next_cursor)

    def _fetch_details(
        self, client: httpx.Client, source: DataSource, place_id: str
    ) -> BusinessCandidate | None:
        url = PLACE_DETAIL_URL.format(place_id=place_id)
        response = request_with_retries(
            client,
            "GET",
            url,
            headers=self._headers(
                "id,displayName,formattedAddress,nationalPhoneNumber,"
                "internationalPhoneNumber,types"
            ),
        )
        record_api_call(source, decrement=1)
        if response.status_code >= 400:
            logger.warning("Google Place Details failed %s: %s", place_id, response.status_code)
            return None
        return self._from_place(response.json())

    def _from_place(self, place: dict[str, Any]) -> BusinessCandidate | None:
        phone = (
            place.get("nationalPhoneNumber")
            or place.get("internationalPhoneNumber")
            or ""
        ).strip()
        if not phone:
            return None
        name_obj = place.get("displayName") or {}
        name = name_obj.get("text") if isinstance(name_obj, dict) else str(name_obj or "")
        place_id = str(place.get("id") or "").replace("places/", "")
        types = place.get("types") or []
        category = types[0] if types else ""
        address = place.get("formattedAddress") or ""
        # Best-effort city/state from address trailing parts
        city, state, postal = _parse_us_address_tail(address)
        return BusinessCandidate(
            raw_phone=phone,
            business_name=(name or "Unknown")[:255],
            address=address[:512],
            city=city[:128],
            state=state[:2],
            postal_code=postal[:16],
            category=str(category)[:128],
            source_record_id=place_id[:128],
            source_url=f"https://www.google.com/maps/place/?q=place_id:{place_id}"[:1024]
            if place_id
            else "",
            raw_payload=place,
        )


def _parse_us_address_tail(address: str) -> tuple[str, str, str]:
    """Very light parse: '... City, ST 12345, USA'."""
    city = state = postal = ""
    parts = [p.strip() for p in address.split(",") if p.strip()]
    if len(parts) >= 2:
        # often last is country
        if parts[-1].upper() in {"USA", "US", "UNITED STATES"}:
            parts = parts[:-1]
        if parts:
            tail = parts[-1]
            tokens = tail.split()
            if tokens and tokens[0].isalpha() and len(tokens[0]) == 2:
                state = tokens[0].upper()
                if len(tokens) > 1:
                    postal = tokens[1]
            if len(parts) >= 2:
                city = parts[-2]
    return city, state, postal
