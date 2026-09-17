"""TomTom Search / POI client (business phones)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from acquisition.candidates import BusinessCandidate
from acquisition.http_retry import raise_for_status_safe, request_with_retries
from sources.models import DataSource
from sources.quota import record_api_call

logger = logging.getLogger("acquisition")

GEOCODE_URL = "https://api.tomtom.com/search/2/geocode/{query}.json"
POI_SEARCH_URL = "https://api.tomtom.com/search/2/poiSearch/{query}.json"


class TomTomClient:
    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("TomTom API key is required")
        self.api_key = api_key
        self.timeout = timeout

    def search(
        self,
        *,
        city: str,
        category: str,
        source: DataSource,
        limit: int = 25,
        radius_m: int = 8000,
    ) -> list[BusinessCandidate]:
        with httpx.Client(timeout=self.timeout) as client:
            lat, lon = self._geocode_city(client, source, city)
            query = quote(category.strip() or "restaurant")
            url = POI_SEARCH_URL.format(query=query)
            params = {
                "key": self.api_key,
                "lat": lat,
                "lon": lon,
                "radius": radius_m,
                "limit": min(100, max(limit, 1)),
                "countrySet": "US",
            }
            logger.info("TomTom POI search query=%s near=%s", category, city)
            response = request_with_retries(client, "GET", url, params=params)
            record_api_call(source, decrement=1)
            if response.status_code == 401:
                raise RuntimeError(
                    "TomTom returned 401 Unauthorized. Create a Search API key at "
                    "https://developer.tomtom.com/ and set MYTOMTOM_API_KEY in .env "
                    "(Maps SDK-only keys will not work for POI search)."
                )
            raise_for_status_safe(response)
            results = (response.json() or {}).get("results") or []

            collected: list[BusinessCandidate] = []
            for item in results:
                candidate = self._to_candidate(item)
                if candidate and candidate.raw_phone:
                    collected.append(candidate)
                if len(collected) >= limit:
                    break
            return collected[:limit]

    def _geocode_city(
        self, client: httpx.Client, source: DataSource, city: str
    ) -> tuple[float, float]:
        query = quote(f"{city}, USA")
        url = GEOCODE_URL.format(query=query)
        response = request_with_retries(client, "GET", url, params={"key": self.api_key, "limit": 1, "countrySet": "US"})
        record_api_call(source, decrement=1)
        if response.status_code == 401:
            raise RuntimeError(
                "TomTom returned 401 Unauthorized. Create a Search API key at "
                "https://developer.tomtom.com/ and set MYTOMTOM_API_KEY in .env "
                "(Maps SDK-only keys will not work for geocode/POI search)."
            )
        raise_for_status_safe(response)
        results = (response.json() or {}).get("results") or []
        if not results:
            raise ValueError(f"TomTom geocode found nothing for {city!r}")
        pos = results[0]["position"]
        return float(pos["lat"]), float(pos["lon"])

    def _to_candidate(self, item: dict[str, Any]) -> BusinessCandidate | None:
        poi = item.get("poi") or {}
        addr = item.get("address") or {}
        phone = (poi.get("phone") or "").strip()
        if not phone:
            return None
        categories = poi.get("categories") or []
        category = categories[0] if categories else ""
        return BusinessCandidate(
            raw_phone=phone,
            business_name=(poi.get("name") or "Unknown")[:255],
            address=(addr.get("freeformAddress") or "")[:512],
            city=(addr.get("municipality") or addr.get("localName") or "")[:128],
            state=(addr.get("countrySubdivisionCode") or addr.get("countrySubdivision") or "")[:2],
            postal_code=(addr.get("postalCode") or "")[:16],
            category=str(category)[:128],
            source_record_id=str(item.get("id") or "")[:128],
            source_url="",
            raw_payload=item,
        )
