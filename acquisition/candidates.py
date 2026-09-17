"""Shared business candidate shape for all acquisition sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BusinessCandidate:
    raw_phone: str
    business_name: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    category: str = ""
    source_record_id: str = ""
    source_url: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)
