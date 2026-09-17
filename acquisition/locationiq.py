"""LocationIQ nearby + lookup client (OSM-backed POIs with phones)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from acquisition.candidates import BusinessCandidate
from acquisition.http_retry import raise_for_status_safe, request_with_retries
from sources.models import DataSource
from sources.quota import record_api_call

logger = logging.getLogger("acquisition")

SEARCH_URL = "https://us1.locationiq.com/v1/search"
NEARBY_URL = "https://us1.locationiq.com/v1/nearby"
LOOKUP_URL = "https://us1.locationiq.com/v1/lookup"

TAG_MAP = {
    "restaurant": "amenity:restaurant",
    "restaurants": "amenity:restaurant",
    "cafe": "amenity:cafe",
    "fast_food": "amenity:fast_food",
    "pharmacy": "amenity:pharmacy",
    "dentist": "amenity:dentist",
    "bank": "amenity:bank",
    "hotel": "tourism:hotel",
}

OSM_TYPE_PREFIX = {"node": "N", "way": "W", "relation": "R"}


class LocationIQClient:
    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("LocationIQ API key is required")
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
        tag = TAG_MAP.get(category.lower().strip(), category.strip())
        if ":" not in tag:
            tag = f"amenity:{tag}"

        with httpx.Client(timeout=self.timeout) as client:
            lat, lon = self._geocode_city(client, source, city)
            nearby = self._nearby(client, source, lat, lon, tag, radius_m, limit=min(50, max(limit * 2, limit)))
            osm_ids = [_osm_ref(item) for item in nearby]
            osm_ids = [x for x in osm_ids if x]
            if not osm_ids:
                logger.info("LocationIQ nearby returned no OSM ids")
                return []

            looked_up: list[dict[str, Any]] = []
            # Free-tier lookup batches are small; chunk to keep requests reliable.
            chunk_size = 10
            for i in range(0, len(osm_ids), chunk_size):
                chunk = osm_ids[i : i + chunk_size]
                looked_up.extend(self._lookup(client, source, chunk))

            collected: list[BusinessCandidate] = []
            for item in looked_up:
                candidate = self._to_candidate(item, city_hint=city)
                if candidate and candidate.raw_phone:
                    collected.append(candidate)
                if len(collected) >= limit:
                    break
            return collected[:limit]

    def _geocode_city(
        self, client: httpx.Client, source: DataSource, city: str
    ) -> tuple[float, float]:
        response = request_with_retries(
            client,
            "GET",
            SEARCH_URL,
            params={
                "key": self.api_key,
                "q": f"{city}, USA",
                "format": "json",
                "limit": 1,
            },
        )
        record_api_call(source, decrement=1)
        raise_for_status_safe(response)
        rows = response.json()
        if not rows:
            raise ValueError(f"LocationIQ geocode found nothing for {city!r}")
        return float(rows[0]["lat"]), float(rows[0]["lon"])

    def _nearby(
        self,
        client: httpx.Client,
        source: DataSource,
        lat: float,
        lon: float,
        tag: str,
        radius_m: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        params = {
            "key": self.api_key,
            "lat": lat,
            "lon": lon,
            "tag": tag,
            "radius": radius_m,
            "format": "json",
            "limit": limit,
        }
        logger.info("LocationIQ nearby tag=%s", tag)
        response = request_with_retries(client, "GET", NEARBY_URL, params=params)
        record_api_call(source, decrement=1)
        raise_for_status_safe(response)
        rows = response.json()
        return rows if isinstance(rows, list) else []

    def _lookup(
        self, client: httpx.Client, source: DataSource, osm_ids: list[str]
    ) -> list[dict[str, Any]]:
        response = request_with_retries(
            client,
            "GET",
            LOOKUP_URL,
            params={
                "key": self.api_key,
                "osm_ids": ",".join(osm_ids),
                "format": "json",
                "extratags": 1,
                "addressdetails": 1,
            },
        )
        record_api_call(source, decrement=1)
        raise_for_status_safe(response)
        rows = response.json()
        return rows if isinstance(rows, list) else []

    def _to_candidate(
        self, item: dict[str, Any], *, city_hint: str
    ) -> BusinessCandidate | None:
        extratags = item.get("extratags") or {}
        phone = (
            extratags.get("phone")
            or extratags.get("contact:phone")
            or extratags.get("telephone")
            or ""
        )
        phone = str(phone).strip()
        address_obj = item.get("address") or {}
        name = (
            item.get("name")
            or address_obj.get("name")
            or address_obj.get("restaurant")
            or address_obj.get("cafe")
            or (item.get("display_name") or "Unknown").split(",")[0]
        )
        city = address_obj.get("city") or address_obj.get("town") or city_hint
        state = address_obj.get("state") or ""
        if len(state) > 2:
            # LocationIQ often returns full state name; leave blank for normalize map
            state = ""
        return BusinessCandidate(
            raw_phone=phone,
            business_name=str(name)[:255],
            address=(item.get("display_name") or "")[:512],
            city=str(city)[:128],
            state=state[:2],
            postal_code=str(address_obj.get("postcode") or "")[:16],
            category=str(item.get("type") or item.get("class") or "")[:128],
            source_record_id=str(item.get("osm_id") or item.get("place_id") or "")[:128],
            source_url="",
            raw_payload=item,
        )


def _osm_ref(item: dict[str, Any]) -> str | None:
    prefix = OSM_TYPE_PREFIX.get(str(item.get("osm_type") or "").lower())
    osm_id = item.get("osm_id")
    if not prefix or osm_id is None:
        return None
    return f"{prefix}{osm_id}"
