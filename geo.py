"""India geography (states, districts, pincodes) and Jammu & Kashmir production map.

The pincode dataset in data/india_geo.json.gz was built from the India Post
delivery-office directory (open government data, via the MIT-licensed `indiapins`
package). A pincode can span two districts, so lookups return every match.
"""
from __future__ import annotations

import gzip
import json
import re
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "data" / "india_geo.json.gz"

# GST state / UT codes (used for place of supply and GSTIN validation).
GST_STATE_CODES = {
    "Jammu and Kashmir": "01", "Himachal Pradesh": "02", "Punjab": "03", "Chandigarh": "04",
    "Uttarakhand": "05", "Haryana": "06", "Delhi": "07", "Rajasthan": "08", "Uttar Pradesh": "09",
    "Bihar": "10", "Sikkim": "11", "Arunachal Pradesh": "12", "Nagaland": "13", "Manipur": "14",
    "Mizoram": "15", "Tripura": "16", "Meghalaya": "17", "Assam": "18", "West Bengal": "19",
    "Jharkhand": "20", "Odisha": "21", "Chhattisgarh": "22", "Madhya Pradesh": "23", "Gujarat": "24",
    "Dadra and Nagar Haveli and Daman and Diu": "26", "Maharashtra": "27", "Karnataka": "29",
    "Goa": "30", "Lakshadweep": "31", "Kerala": "32", "Tamil Nadu": "33", "Puducherry": "34",
    "Andaman and Nicobar Islands": "35", "Telangana": "36", "Andhra Pradesh": "37", "Ladakh": "38",
}
GST_CODE_TO_STATE = {v: k for k, v in GST_STATE_CODES.items()}
# Union territories without a legislature charge UTGST instead of SGST.
UTGST_STATE_CODES = {"04", "26", "31", "35", "38"}

JK_STATE = "Jammu and Kashmir"
JK_STATES = (JK_STATE, "Ladakh")

# Kashmir Division (the apple, walnut, almond and saffron belt).
KASHMIR_DIVISION = [
    "Anantnag", "Bandipora", "Baramulla", "Budgam", "Ganderbal",
    "Kulgam", "Kupwara", "Pulwama", "Shopian", "Srinagar",
]

# Indicative production map: "major" = leading producing district, "grown" = commercially grown.
# Compiled from J&K Horticulture Department material; indicative, not an official ranking.
PRODUCTION = {
    "Apple": {
        "major": ["Shopian", "Baramulla", "Pulwama", "Kulgam", "Anantnag", "Kupwara"],
        "grown": ["Budgam", "Bandipora", "Ganderbal"],
    },
    "Walnut": {
        "major": ["Kupwara", "Baramulla", "Budgam", "Anantnag", "Kulgam"],
        "grown": ["Bandipora", "Ganderbal", "Pulwama", "Shopian", "Srinagar", "Doda", "Kishtwar", "Ramban"],
    },
    "Almond": {
        "major": ["Pulwama", "Budgam", "Srinagar", "Baramulla"],
        "grown": ["Anantnag", "Kupwara", "Shopian", "Kulgam", "Bandipora"],
    },
    "Saffron": {
        "major": ["Pulwama"],
        "grown": ["Budgam", "Srinagar", "Kishtwar"],
    },
}


def _title(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "")).strip().casefold()


@lru_cache(maxsize=1)
def _load():
    with gzip.open(DATA_FILE, "rt", encoding="utf-8") as fh:
        raw = json.load(fh)
    states = [("Dadra and Nagar Haveli and Daman and Diu" if s.startswith("The Dadra") else s) for s in raw["states"]]
    districts = [(states[s_idx], name) for s_idx, name in raw["districts"]]
    pins = {pin: [districts[i] for i in idxs] for pin, idxs in raw["pins"].items()}
    by_state: dict[str, list[str]] = {}
    for st, di in districts:
        by_state.setdefault(st, []).append(di)
    for st in by_state:
        by_state[st] = sorted(set(by_state[st]))
    pins_by_district: dict[tuple[str, str], list[str]] = {}
    for pin, locs in pins.items():
        for loc in locs:
            pins_by_district.setdefault(loc, []).append(pin)
    return {"states": sorted(states), "by_state": by_state, "pins": pins, "pins_by_district": pins_by_district}


def states() -> list[dict]:
    return [{"name": s, "gst_code": GST_STATE_CODES.get(s, "")} for s in _load()["states"]]


def canonical_state(name: str) -> str | None:
    key = _title(name)
    for s in _load()["states"]:
        if _title(s) == key:
            return s
    return None


def districts(state: str) -> list[str]:
    st = canonical_state(state)
    return list(_load()["by_state"].get(st, [])) if st else []


def canonical_district(state: str, name: str) -> str | None:
    key = _title(name)
    for d in districts(state):
        if _title(d) == key:
            return d
    return None


def pincodes(state: str, district: str) -> list[str]:
    st, di = canonical_state(state), None
    if st:
        di = canonical_district(st, district)
    if not st or not di:
        return []
    return sorted(_load()["pins_by_district"].get((st, di), []))


def lookup_pincode(pin: str) -> list[dict]:
    pin = str(pin or "").strip()
    return [{"state": s, "district": d, "gst_code": GST_STATE_CODES.get(s, "")} for s, d in _load()["pins"].get(pin, [])]


def validate_location(state: str, district: str, pincode: str) -> tuple[str, str, str]:
    """Return canonical (state, district, pincode) or raise ValueError with a user-facing message."""
    st = canonical_state(state)
    if not st:
        raise ValueError("Choose a valid Indian state or union territory.")
    di = canonical_district(st, district)
    if not di:
        raise ValueError(f"'{district}' is not a district of {st}. Choose a district from the list.")
    pin = re.sub(r"\s", "", str(pincode or ""))
    if not re.fullmatch(r"[1-9][0-9]{5}", pin):
        raise ValueError("Pincode must be exactly 6 digits and cannot start with 0.")
    matches = _load()["pins"].get(pin)
    if not matches:
        raise ValueError(f"Pincode {pin} was not found in the India Post directory.")
    if (st, di) not in matches:
        places = ", ".join(sorted({f"{d}, {s}" for s, d in matches}))
        raise ValueError(f"Pincode {pin} belongs to {places}, not {di}, {st}.")
    return st, di, pin


def jk_districts() -> list[str]:
    ld = _load()["by_state"]
    return sorted(set(ld.get(JK_STATE, [])) | set(ld.get("Ladakh", [])))


def kashmir_overview() -> dict:
    """Districts of the Kashmir valley with what grows where, plus other J&K districts."""
    out = []
    jk = set(_load()["by_state"].get(JK_STATE, []))
    for d in KASHMIR_DIVISION:
        crops = {}
        for crop, levels in PRODUCTION.items():
            if d in levels["major"]:
                crops[crop] = "major"
            elif d in levels["grown"]:
                crops[crop] = "grown"
        out.append({"district": d, "division": "Kashmir", "crops": crops})
    others = sorted(jk - set(KASHMIR_DIVISION))
    for d in others:
        crops = {c: "grown" for c, lv in PRODUCTION.items() if d in lv["grown"]}
        out.append({"district": d, "division": "Jammu / Other J&K", "crops": crops})
    return {"districts": out, "ladakh": _load()["by_state"].get("Ladakh", []),
            "note": "Indicative production map: major = leading producing districts, grown = commercially grown. Not an official ranking."}


def producing_districts(crop: str) -> dict:
    return PRODUCTION.get(crop, {"major": [], "grown": []})
