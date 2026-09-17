"""Offline phone enrichment via phonenumbers (no API quota)."""

from __future__ import annotations

from dataclasses import dataclass

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat, PhoneNumberType

from phones.area_codes import AREA_CODE_TO_STATE

_LINE_TYPE_MAP = {
    PhoneNumberType.FIXED_LINE: "fixed_line",
    PhoneNumberType.MOBILE: "mobile",
    PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_line_or_mobile",
    PhoneNumberType.TOLL_FREE: "toll_free",
    PhoneNumberType.PREMIUM_RATE: "premium_rate",
    PhoneNumberType.SHARED_COST: "shared_cost",
    PhoneNumberType.VOIP: "voip",
    PhoneNumberType.PERSONAL_NUMBER: "personal_number",
    PhoneNumberType.PAGER: "pager",
    PhoneNumberType.UAN: "uan",
    PhoneNumberType.VOICEMAIL: "voicemail",
    PhoneNumberType.UNKNOWN: "unknown",
}


@dataclass(frozen=True)
class OfflineEnrichment:
    national_format: str
    line_type: str
    area_code: str
    state: str
    enrichment_geo: str


def enrich_offline(e164: str) -> OfflineEnrichment | None:
    """
    Derive format, line type, and area-code geography from E.164 offline.
    Returns None if the number cannot be parsed.
    """
    if not e164 or not str(e164).strip():
        return None
    try:
        parsed = phonenumbers.parse(str(e164).strip(), None)
    except NumberParseException:
        return None

    national = phonenumbers.format_number(parsed, PhoneNumberFormat.NATIONAL)[:32]
    nsn = phonenumbers.national_significant_number(parsed)
    area_code = nsn[:3] if len(nsn) >= 3 else ""
    state = AREA_CODE_TO_STATE.get(area_code, "")
    line_type = _LINE_TYPE_MAP.get(phonenumbers.number_type(parsed), "unknown")

    geo_parts: list[str] = []
    if area_code:
        geo_parts.append(f"area {area_code}")
    if state:
        geo_parts.append(state)
    enrichment_geo = ", ".join(geo_parts)[:255]

    return OfflineEnrichment(
        national_format=national,
        line_type=line_type,
        area_code=area_code,
        state=state,
        enrichment_geo=enrichment_geo,
    )
