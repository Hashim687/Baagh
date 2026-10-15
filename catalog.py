"""Produce catalog: crops, product forms, varieties, grades, HSN codes and GST rates.

GST rates here are defaults at the time of writing (rates effective 22 September 2025, per
CBIC Notification 9/2025-Central Tax (Rate) and 10/2025-Central Tax (Rate)):
  * Fresh fruit (apples, HSN 0808)            -> Nil rated
  * Dried nuts incl. walnuts, almonds (0802)  -> 5 % (2.5 % CGST + 2.5 % SGST, or 5 % IGST)
  * Saffron (0910 20)                         -> 5 %
Rates change by Council notification. Verify before invoicing; edit the numbers below if they change.
"""
from __future__ import annotations

CATALOG_VERSION = "2026-10 (rates effective 22-Sep-2025)"

# Tally / GST unit: KGS = kilograms.
CROPS = {
    "Apple": {
        "emoji": "🍎",
        "forms": {
            "Fresh": {"hsn": "0808", "gst_rate": 0, "description": "Apples, fresh"},
        },
        "varieties": [
            "Royal Delicious", "American (Trel)", "Red Delicious", "Golden Delicious", "Ambri (Kashmiri Ambri)",
            "Maharaji", "Razakwadi", "Hazratbali", "Cox's Orange Pippin", "Kullu Delicious",
            "Royal Gala", "Gale Gala", "Red Gold", "Granny Smith", "Fuji", "Oregon Spur", "Scarlet Spur",
            "Red Chief", "Super Chief", "Jeromine", "Cripps Pink", "Other",
        ],
        "grades": {"Extra Fancy": "A", "Fancy": "B", "Commercial": "C"},
    },
    "Walnut": {
        "emoji": "🌰",
        "forms": {
            "In shell (dry)": {"hsn": "0802", "gst_rate": 5, "description": "Walnuts, dried, in shell"},
            "Kernel (shelled)": {"hsn": "0802", "gst_rate": 5, "description": "Walnuts, dried, shelled (kernels)"},
        },
        "varieties": [
            "Kagzi (Paper shell)", "Burzul", "Sopore walnut", "Hard shell (Desi)", "Sulaiman",
            "Opex Caulchry", "Lake English", "Hansen", "Wonder walnut",
            "Kernel - Light halves (LH)", "Kernel - Extra light halves", "Kernel - Amber halves",
            "Kernel - Quarters", "Kernel - Pieces (broken)", "Other",
        ],
        "grades": {"Premium": "A", "Standard": "B", "Commercial": "C"},
    },
    "Almond": {
        "emoji": "🥜",
        "forms": {
            "In shell (dry)": {"hsn": "0802", "gst_rate": 5, "description": "Almonds, dried, in shell"},
            "Kernel (shelled)": {"hsn": "0802", "gst_rate": 5, "description": "Almonds, dried, shelled (kernels)"},
        },
        "varieties": [
            "Waris", "Makhdoom", "Shalimar", "Drake", "Non Pareil", "Merced", "Kagzi (Paper shell)",
            "Primorskiy", "Kashmiri Mamra-type", "Other",
        ],
        "grades": {"Premium": "A", "Standard": "B", "Commercial": "C"},
    },
    "Saffron": {
        "emoji": "🌸",
        "forms": {
            "Whole stigma (threads)": {"hsn": "0910", "gst_rate": 5, "description": "Saffron, stigmas (threads)"},
            "Powder": {"hsn": "0910", "gst_rate": 5, "description": "Saffron, ground (powder)"},
        },
        "varieties": [
            "Mongra (Lacha) - Grade I", "Lacha - Grade II", "Guchhi - Grade III", "Zarda - Grade IV",
            "Kashmir saffron (GI-tagged, Pampore)", "Other",
        ],
        "grades": {"Mongra (Grade I)": "A", "Lacha (Grade II)": "B", "Guchhi / Zarda (Grade III-IV)": "C"},
    },
}

UNIT = "KGS"
UNIT_NAME = "KILOGRAMS"


def crop_names() -> list[str]:
    return list(CROPS)


def get_crop(crop: str) -> dict | None:
    return CROPS.get(crop)


def form_info(crop: str, form: str) -> dict | None:
    c = CROPS.get(crop)
    return c["forms"].get(form) if c else None


def default_form(crop: str) -> str:
    return next(iter(CROPS[crop]["forms"]))


def grade_label_for(crop: str, grade: str) -> str:
    c = CROPS.get(crop)
    if not c:
        return grade
    for label, g in c["grades"].items():
        if g == grade:
            return label
    return grade


def public_catalog() -> dict:
    return {
        "version": CATALOG_VERSION,
        "unit": UNIT,
        "crops": [
            {
                "crop": name,
                "emoji": c["emoji"],
                "forms": [{"form": f, **info} for f, info in c["forms"].items()],
                "varieties": c["varieties"],
                "grades": [{"label": label, "grade": g} for label, g in c["grades"].items()],
            }
            for name, c in CROPS.items()
        ],
        "note": "GST rates are defaults. Fresh fruit is nil rated; dried nuts and saffron are 5%. Verify against current CBIC notifications before filing.",
    }
