"""Shared search result shape for paginated acquisition clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from acquisition.candidates import BusinessCandidate


@dataclass
class ClientSearchResult:
    candidates: list[BusinessCandidate] = field(default_factory=list)
    next_cursor: dict[str, Any] | None = None
