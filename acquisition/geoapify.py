"""Geoapify Places client (Yelp alternative for business phones)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from acquisition.http_retry import raise_for_status_safe, request_with_retries
from acquisition.candidates import BusinessCandidate
from sources.models import DataSource
from sources.quota import record_api_call

logger = logging.getLogger("acquisition")

GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"
PLACES_URL = "https://api.geoapify.com/v2/places"
DETAILS_URL = "https://api.geoapify.com/v2/place-details"

CATEGORY_MAP = {
    "restaurant": "catering.restaurant",
    "restaurants": "catering.restaurant",
    "cafe": "catering.cafe",
    "fast_food": "catering.fast_food",
    "pharmacy": "healthcare.pharmacy",
    "dentist": "healthcare.dentist",
    "bank": "service.financial.bank",
    "hotel": "accommodation.hotel",
}


class GeoapifyClient:
    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("Geoapify API key is required")
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
        cat = CATEGORY_MAP.get(category.lower().strip(), category.strip())
        with httpx.Client(timeout=self.timeout) as client:
            lon, lat = self._geocode_city(client, source, city)
            params = {
                "categories": cat,
                "filter": f"circle:{lon},{lat},{radius_m}",
                "limit": min(50, max(limit, 1)),
                "apiKey": self.api_key,
            }
            logger.info("Geoapify places categories=%s near=%s", cat, city)
            response = request_with_retries(client, "GET", PLACES_URL, params=params)
            record_api_call(source, decrement=1)
            raise_for_status_safe(response)
            features = (response.json() or {}).get("features") or []

            collected: list[BusinessCandidate] = []
            for feature in features:
                candidate = self._from_feature(feature)
                if candidate and not candidate.raw_phone:
                    place_id = (feature.get("properties") or {}).get("place_id")
                    if place_id:
                        candidate = self._enrich_phone(client, source, place_id, candidate)
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
            GEOCODE_URL,
            params={"text": f"{city}, USA", "limit": 1, "apiKey": self.api_key},
        )
        record_api_call(source, decrement=1)
        raise_for_status_safe(response)
        features = (response.json() or {}).get("features") or []
        if not features:
            raise ValueError(f"Geoapify geocode found nothing for {city!r}")
        coords = features[0]["geometry"]["coordinates"]
        return float(coords[0]), float(coords[1])

    def _enrich_phone(
        self,
        client: httpx.Client,
        source: DataSource,
        place_id: str,
        candidate: BusinessCandidate,
    ) -> BusinessCandidate:
        response = request_with_retries(
            client,
            "GET",
            DETAILS_URL,
            params={"id": place_id, "features": "details", "apiKey": self.api_key},
        )
        record_api_call(source, decrement=1)
        if response.status_code >= 400:
            return candidate
        props = ((response.json() or {}).get("features") or [{}])[0].get("properties") or {}
        phone = _extract_phone(props)
        if phone:
            candidate.raw_phone = phone
            candidate.raw_payload = {**candidate.raw_payload, "details": props}
        return candidate

    def _from_feature(self, feature: dict[str, Any]) -> BusinessCandidate | None:
        props = feature.get("properties") or {}
        phone = _extract_phone(props)
        name = props.get("name") or props.get("address_line1") or "Unknown"
        return BusinessCandidate(
            raw_phone=phone or "",
            business_name=str(name)[:255],
            address=(props.get("address_line1") or props.get("formatted") or "")[:512],
            city=(props.get("city") or "")[:128],
            state=(props.get("state_code") or props.get("state") or "")[:2],
            postal_code=(props.get("postcode") or "")[:16],
            category=(props.get("categories") or [""])[0][:128]
            if isinstance(props.get("categories"), list)
            else str(props.get("category") or "")[:128],
            source_record_id=str(props.get("place_id") or "")[:128],
            source_url="",
            raw_payload=props,
        )


def _extract_phone(props: dict[str, Any]) -> str:
    contact = props.get("contact") or {}
    if isinstance(contact, dict) and contact.get("phone"):
        return str(contact["phone"]).strip()
    datasource = props.get("datasource") or {}
    raw = datasource.get("raw") if isinstance(datasource, dict) else {}
    if isinstance(raw, dict):
        for key in ("phone", "contact:phone", "telephone"):
            if raw.get(key):
                return str(raw[key]).strip()
    return ""
