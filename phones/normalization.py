"""US phone normalization and basic validation (Phase 4)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat

from phones.area_codes import AREA_CODE_TO_STATE

logger = logging.getLogger("phones")

US_REGIONS = frozenset({"US", "PR", "VI", "GU", "AS", "MP"})


@dataclass(frozen=True)
class NormalizeResult:
    e164: str
    national_format: str
    area_code: str
    state: str


def normalize_us_phone(raw: str) -> NormalizeResult | None:
    """
    Parse raw phone text as a US (+1) number.

    Returns NormalizeResult on success, or None if the number is missing,
    unparseable, invalid, or not a US / US-territory line.
    Extensions are ignored for the stored E.164 key.
    """
    if not raw or not str(raw).strip():
        return None

    cleaned = _strip_extension_noise(str(raw).strip())
    try:
        parsed = phonenumbers.parse(cleaned, "US")
    except NumberParseException:
        logger.debug("Parse failed for %r", raw)
        return None

    if parsed.country_code != 1:
        logger.debug("Reject non-+1 country_code=%s for %r", parsed.country_code, raw)
        return None

    if not phonenumbers.is_possible_number(parsed):
        logger.debug("Not possible number: %r", raw)
        return None

    if not phonenumbers.is_valid_number(parsed):
        logger.debug("Not valid number: %r", raw)
        return None

    region = phonenumbers.region_code_for_number(parsed)
    if region not in US_REGIONS:
        logger.debug("Reject non-US region %s for %r", region, raw)
        return None

    e164 = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    national = phonenumbers.format_number(parsed, PhoneNumberFormat.NATIONAL)
    nsn = phonenumbers.national_significant_number(parsed)
    area_code = nsn[:3] if len(nsn) >= 3 else ""
    state = AREA_CODE_TO_STATE.get(area_code, "")

    return NormalizeResult(
        e164=e164,
        national_format=national[:32],
        area_code=area_code,
        state=state,
    )


def _strip_extension_noise(raw: str) -> str:
    """Remove common extension suffixes so the main line can be parsed."""
    parts = re.split(
        r"(?i)\s*(?:ext\.?|extension|x|#)\s*\d+\s*$",
        raw,
        maxsplit=1,
    )
    return parts[0].strip() if parts else raw
