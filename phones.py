"""International phone handling built on Google's libphonenumber data (the `phonenumbers` package).

Every country has its own length and numbering rules (India: exactly 10 digits starting 6-9,
UAE: 9 digits, UK: 10 digits, ...). Those rules come from libphonenumber, so they stay accurate.
"""
from __future__ import annotations

import re
from functools import lru_cache

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberType

try:  # country names
    import pycountry
except Exception:  # pragma: no cover
    pycountry = None

SMS_TYPES = {PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE}
DEFAULT_REGION = "IN"


def flag(iso: str) -> str:
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in iso.upper()) if re.fullmatch(r"[A-Za-z]{2}", iso or "") else ""


def _name(iso: str) -> str:
    if pycountry:
        c = pycountry.countries.get(alpha_2=iso)
        if c:
            return getattr(c, "common_name", None) or c.name
    return {"XK": "Kosovo"}.get(iso, iso)


@lru_cache(maxsize=1)
def countries() -> list[dict]:
    out = []
    for region in sorted(phonenumbers.SUPPORTED_REGIONS):
        meta = phonenumbers.PhoneMetadata.metadata_for_region(region)
        if meta is None:
            continue
        mobile_lengths = sorted(set(meta.mobile.possible_length or ())) if meta.mobile else []
        lengths = [n for n in mobile_lengths if n > 0] or sorted(n for n in (meta.general_desc.possible_length or ()) if n > 0)
        example = ""
        ex = phonenumbers.example_number_for_type(region, PhoneNumberType.MOBILE) or phonenumbers.example_number(region)
        if ex:
            example = phonenumbers.national_significant_number(ex)
        out.append({
            "iso": region, "name": _name(region), "dial": f"+{phonenumbers.country_code_for_region(region)}",
            "flag": flag(region), "lengths": lengths, "min_len": min(lengths) if lengths else 6,
            "max_len": max(lengths) if lengths else 15, "example": example,
        })
    out.sort(key=lambda c: (c["iso"] != DEFAULT_REGION, c["name"].casefold()))
    return out


def country(iso: str) -> dict | None:
    iso = (iso or "").upper()
    return next((c for c in countries() if c["iso"] == iso), None)


def _length_text(c: dict) -> str:
    ls = c["lengths"]
    if not ls:
        return "a valid number"
    if len(ls) == 1:
        return f"exactly {ls[0]} digits"
    return f"{ls[0]} to {ls[-1]} digits"


def parse_mobile(raw: str, iso: str = DEFAULT_REGION) -> tuple[str, str]:
    """Validate a mobile number for the given country. Returns (E.164, ISO region). Raises ValueError."""
    iso = (iso or DEFAULT_REGION).upper()
    text = str(raw or "").strip()
    c = country(iso)
    if c is None:
        raise ValueError("Choose a valid country for the phone number.")
    digits_only = re.sub(r"[\s\-().]", "", text)
    if not digits_only or not re.fullmatch(r"\+?\d+", digits_only):
        raise ValueError("Phone number can contain digits only.")
    try:
        num = phonenumbers.parse(digits_only if digits_only.startswith("+") else digits_only, None if digits_only.startswith("+") else iso)
    except NumberParseException:
        raise ValueError(f"Enter a valid {c['name']} mobile number ({_length_text(c)}).") from None
    region = phonenumbers.region_code_for_number(num) or iso
    if not phonenumbers.is_valid_number(num):
        if iso == "IN" and not digits_only.startswith("+"):
            raise ValueError("Indian mobile numbers must be exactly 10 digits and start with 6, 7, 8 or 9.")
        raise ValueError(f"Enter a valid {c['name']} mobile number ({_length_text(c)}).")
    if phonenumbers.number_type(num) not in SMS_TYPES:
        if region == "IN":
            raise ValueError("Indian mobile numbers must be exactly 10 digits and start with 6, 7, 8 or 9.")
        raise ValueError("Enter a mobile number that can receive SMS (landline and virtual numbers are not accepted).")
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164), region


def normalize_phone(value: str, iso: str = DEFAULT_REGION) -> str:
    """Return E.164. Strict for new input; falls back to legacy lenient rules for old records."""
    try:
        return parse_mobile(value, iso)[0]
    except ValueError:
        digits = re.sub(r"\D", "", str(value or ""))
        if len(digits) == 10:
            return "+91" + digits
        if len(digits) == 12 and digits.startswith("91"):
            return "+" + digits
        if len(digits) == 11 and digits.startswith("0"):
            return "+91" + digits[1:]
        if 10 <= len(digits) <= 15:
            return "+" + digits
        raise ValueError("Enter a valid phone number.") from None


def mask(e164: str) -> str:
    """+919876543210 -> +91•••••••210 (never show a full number back on public screens)."""
    return e164 if len(e164) <= 7 else e164[:3] + "•" * (len(e164) - 6) + e164[-3:]
