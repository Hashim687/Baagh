"""GST helpers: GSTIN validation, tax split (CGST/SGST/UTGST/IGST) and financial-year utilities."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import geo

IST = timezone(timedelta(hours=5, minutes=30))
_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_checksum_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        value = _CHARS.index(ch) * (2 if i % 2 else 1)
        total += value // 36 + value % 36
    return _CHARS[(36 - total % 36) % 36]


def validate_gstin(gstin: str) -> str:
    """Return the normalized GSTIN or raise ValueError."""
    g = re.sub(r"\s", "", str(gstin or "")).upper()
    if not _GSTIN_RE.match(g):
        raise ValueError("GSTIN must be 15 characters, e.g. 01ABCDE1234F1Z5.")
    if g[:2] not in geo.GST_CODE_TO_STATE and g[:2] not in ("97", "99"):
        raise ValueError("GSTIN starts with an unknown state code.")
    if gstin_checksum_char(g[:14]) != g[14]:
        raise ValueError("This GSTIN fails the checksum test. Re-check the number.")
    return g


def gstin_state_code(gstin: str) -> str:
    return gstin[:2] if gstin else ""


def d(value) -> Decimal:
    return Decimal(str(value or 0))


def money(value) -> Decimal:
    return d(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_tax(taxable, rate, supplier_state_code: str, place_of_supply_code: str,
                supplier_registered: bool, export: bool = False) -> dict:
    """Split GST for one supply line. All results are Decimals rounded to paise."""
    taxable = money(taxable)
    rate = d(rate)
    res = {"taxable": taxable, "rate": rate, "cgst": Decimal("0"), "sgst": Decimal("0"), "igst": Decimal("0"),
           "cgst_rate": Decimal("0"), "sgst_rate": Decimal("0"), "igst_rate": Decimal("0"),
           "utgst": supplier_state_code in geo_utgst(), "supply_type": "", "flag": ""}
    if export:
        res.update(supply_type="Export (zero-rated)", flag="Export of goods: shown at 0% under LUT/bond. Confirm export documents with your CA.")
    elif rate == 0:
        res.update(supply_type="Nil rated / exempt", flag="Nil-rated supply")
    elif not supplier_registered:
        res.update(supply_type="No GST charged", flag="Supplier has no GSTIN, so no GST can be charged on this invoice.")
    elif supplier_state_code and supplier_state_code == place_of_supply_code:
        half = (rate / 2)
        res["cgst_rate"] = res["sgst_rate"] = half
        res["cgst"] = money(taxable * half / 100)
        res["sgst"] = money(taxable * half / 100)
        res["supply_type"] = "Intra-state"
    else:
        res["igst_rate"] = rate
        res["igst"] = money(taxable * rate / 100)
        res["supply_type"] = "Inter-state"
        if not place_of_supply_code:
            res["flag"] = "Buyer state missing: treated as inter-state (IGST). Ask the buyer to add their state."
    res["total_tax"] = res["cgst"] + res["sgst"] + res["igst"]
    res["invoice_value"] = taxable + res["total_tax"]
    return res


def geo_utgst():
    return geo.UTGST_STATE_CODES


# ---- Financial year (India: 1 April to 31 March) ----
def fy_start_year(dt: date) -> int:
    return dt.year if dt.month >= 4 else dt.year - 1


def fy_label(start_year: int) -> str:
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def fy_for_date(dt: date) -> str:
    return fy_label(fy_start_year(dt))


def fy_bounds(label: str) -> tuple[date, date]:
    m = re.fullmatch(r"(\d{4})-(\d{2})", str(label or ""))
    if not m or (int(m.group(1)) + 1) % 100 != int(m.group(2)):
        raise ValueError("Financial year must look like 2026-27.")
    y = int(m.group(1))
    return date(y, 4, 1), date(y + 1, 3, 31)


def to_ist_date(iso_ts: str) -> date:
    dt = datetime.fromisoformat(iso_ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).date()
