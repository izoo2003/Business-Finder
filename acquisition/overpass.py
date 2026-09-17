"""OpenStreetMap Nominatim + Overpass API client."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx
from django.conf import settings

from acquisition.http_retry import raise_for_status_safe, request_with_retries

logger = logging.getLogger("acquisition")

CATEGORY_TAG_MAP: dict[str, tuple[str, str]] = {
    "restaurant": ("amenity", "restaurant"),
    "cafe": ("amenity", "cafe"),
    "fast_food": ("amenity", "fast_food"),
    "pharmacy": ("amenity", "pharmacy"),
    "dentist": ("amenity", "dentist"),
    "bank": ("amenity", "bank"),
    "fuel": ("amenity", "fuel"),
}


@dataclass(frozen=True)
class BoundingBox:
    south: float
    west: float
    north: float
    east: float


@dataclass
class OverpassPOI:
    osm_type: str
    osm_id: int
    tags: dict[str, str]
    lat: float | None = None
    lon: float | None = None

    @property
    def phone_raw(self) -> str:
        return (self.tags.get("phone") or self.tags.get("contact:phone") or "").strip()

    @property
    def name(self) -> str:
        return (self.tags.get("name") or self.tags.get("brand") or "").strip()

    @property
    def category(self) -> str:
        for key in ("amenity", "shop", "craft", "office"):
            if key in self.tags:
                return f"{key}={self.tags[key]}"
        return ""

    @property
    def address(self) -> str:
        parts = [
            self.tags.get("addr:housenumber", ""),
            self.tags.get("addr:street", ""),
        ]
        return " ".join(p for p in parts if p).strip()

    @property
    def city(self) -> str:
        return (
            self.tags.get("addr:city")
            or self.tags.get("addr:suburb")
            or ""
        ).strip()

    @property
    def postal_code(self) -> str:
        return (self.tags.get("addr:postcode") or "").strip()

    @property
    def state(self) -> str:
        return (self.tags.get("addr:state") or "").strip()[:2].upper()

    @property
    def source_record_id(self) -> str:
        return f"{self.osm_type}/{self.osm_id}"

    @property
    def source_url(self) -> str:
        return f"https://www.openstreetmap.org/{self.osm_type}/{self.osm_id}"


class OverpassClient:
    def __init__(
        self,
        overpass_url: str | None = None,
        nominatim_url: str | None = None,
        user_agent: str | None = None,
        timeout: float = 90.0,
    ) -> None:
        self.overpass_url = overpass_url or getattr(
            settings, "OVERPASS_URL", "https://overpass-api.de/api/interpreter"
        )
        self.nominatim_url = nominatim_url or getattr(
            settings, "NOMINATIM_URL", "https://nominatim.openstreetmap.org"
        )
        self.user_agent = user_agent or getattr(
            settings,
            "OVERPASS_USER_AGENT",
            "PhoneCollectionAgent/0.1 (phase3; local-dev)",
        )
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": self.user_agent, "Accept": "application/json"}

    def resolve_city_bbox(self, city: str, country: str = "USA") -> BoundingBox:
        query = f"{city}, {country}"
        url = f"{self.nominatim_url.rstrip('/')}/search"
        params = {
            "q": query,
            "format": "json",
            "limit": 1,
            "addressdetails": 0,
        }
        logger.info("Nominatim lookup: %s", query)
        with httpx.Client(timeout=30.0, headers=self._headers()) as client:
            response = request_with_retries(client, "GET", url, params=params)
            raise_for_status_safe(response)
            results = response.json()

        if not results:
            raise ValueError(f"No Nominatim result for city={city!r}")

        bbox = results[0].get("boundingbox")
        if not bbox or len(bbox) != 4:
            raise ValueError(f"Nominatim result missing boundingbox for city={city!r}")

        # Nominatim boundingbox: [south, north, west, east]
        south, north, west, east = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        box = BoundingBox(south=south, west=west, north=north, east=east)
        logger.info("Resolved bbox for %s: %s", city, box)
        return box

    def build_query(self, bbox: BoundingBox, tag_key: str, tag_value: str) -> str:
        # south,west,north,east for Overpass bbox filter
        bbox_str = f"{bbox.south},{bbox.west},{bbox.north},{bbox.east}"
        return f"""
[out:json][timeout:60];
(
  node["{tag_key}"="{tag_value}"]["phone"]({bbox_str});
  node["{tag_key}"="{tag_value}"]["contact:phone"]({bbox_str});
  way["{tag_key}"="{tag_value}"]["phone"]({bbox_str});
  way["{tag_key}"="{tag_value}"]["contact:phone"]({bbox_str});
);
out center tags;
""".strip()

    def fetch_pois(
        self,
        bbox: BoundingBox,
        tag_key: str,
        tag_value: str,
        *,
        max_retries: int | None = None,
    ) -> list[OverpassPOI]:
        query = self.build_query(bbox, tag_key, tag_value)
        logger.info("Overpass query tag=%s=%s", tag_key, tag_value)
        with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
            response = request_with_retries(
                client,
                "POST",
                self.overpass_url,
                max_retries=max_retries,
                data={"data": query},
            )
            raise_for_status_safe(response)
            return self._parse_elements(response.json())

    def _parse_elements(self, payload: dict[str, Any]) -> list[OverpassPOI]:
        pois: list[OverpassPOI] = []
        for element in payload.get("elements", []):
            osm_type = element.get("type")
            osm_id = element.get("id")
            tags = element.get("tags") or {}
            if not osm_type or osm_id is None:
                continue
            lat = element.get("lat")
            lon = element.get("lon")
            if lat is None and "center" in element:
                lat = element["center"].get("lat")
                lon = element["center"].get("lon")
            pois.append(
                OverpassPOI(
                    osm_type=osm_type,
                    osm_id=int(osm_id),
                    tags={str(k): str(v) for k, v in tags.items()},
                    lat=float(lat) if lat is not None else None,
                    lon=float(lon) if lon is not None else None,
                )
            )
        logger.info("Overpass returned %s elements with tags", len(pois))
        return pois


def resolve_category_tag(category: str, osm_tag: str | None = None) -> tuple[str, str]:
    if osm_tag:
        if "=" not in osm_tag:
            raise ValueError("--osm-tag must look like key=value")
        key, value = osm_tag.split("=", 1)
        return key.strip(), value.strip()

    key = category.strip().lower()
    if key not in CATEGORY_TAG_MAP:
        supported = ", ".join(sorted(CATEGORY_TAG_MAP))
        raise ValueError(f"Unknown category {category!r}. Use one of: {supported} or --osm-tag key=value")
    return CATEGORY_TAG_MAP[key]
