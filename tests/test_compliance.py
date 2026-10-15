"""Pure-logic tests: GSTIN checksum, tax split, financial year, phone rules by country, pincode checks."""
import unittest
from datetime import date
from decimal import Decimal

import geo
import gst
import phones
import reports


class GstinTests(unittest.TestCase):
    def test_known_valid_and_checksum_failure(self):
        self.assertEqual(gst.validate_gstin("27AAPFU0939F1ZV"), "27AAPFU0939F1ZV")
        with self.assertRaises(ValueError):
            gst.validate_gstin("27AAPFU0939F1ZX")
        with self.assertRaises(ValueError):
            gst.validate_gstin("99XYZ")
        with self.assertRaises(ValueError):
            gst.validate_gstin("50AAPFU0939F1Z" + gst.gstin_checksum_char("50AAPFU0939F1Z"))  # unknown state code


class TaxSplitTests(unittest.TestCase):
    def test_intra_state_splits_evenly(self):
        t = gst.compute_tax(100000, 5, "01", "01", True)
        self.assertEqual((t["cgst"], t["sgst"], t["igst"]), (Decimal("2500.00"), Decimal("2500.00"), Decimal("0")))
        self.assertEqual(t["invoice_value"], Decimal("105000.00"))
        self.assertFalse(t["utgst"])

    def test_inter_state_uses_igst(self):
        t = gst.compute_tax(100000, 5, "01", "07", True)
        self.assertEqual((t["igst"], t["cgst"]), (Decimal("5000.00"), Decimal("0")))

    def test_ut_without_legislature_uses_utgst(self):
        self.assertTrue(gst.compute_tax(1000, 5, "38", "38", True)["utgst"])

    def test_unregistered_nil_rated_and_export(self):
        self.assertEqual(gst.compute_tax(1000, 5, "01", "07", False)["total_tax"], Decimal("0"))
        self.assertEqual(gst.compute_tax(1000, 0, "01", "07", True)["supply_type"], "Nil rated / exempt")
        e = gst.compute_tax(1000, 5, "01", "96", True, export=True)
        self.assertEqual((e["total_tax"], e["supply_type"]), (Decimal("0"), "Export (zero-rated)"))

    def test_rounding_is_to_paise(self):
        t = gst.compute_tax("333.33", 5, "01", "01", True)
        self.assertEqual(t["cgst"], Decimal("8.33"))
        self.assertEqual(t["sgst"], Decimal("8.33"))

    def test_missing_buyer_state_is_flagged(self):
        t = gst.compute_tax(1000, 5, "01", "", True)
        self.assertEqual(t["supply_type"], "Inter-state")
        self.assertIn("missing", t["flag"])


class FinancialYearTests(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(gst.fy_for_date(date(2026, 3, 31)), "2025-26")
        self.assertEqual(gst.fy_for_date(date(2026, 4, 1)), "2026-27")
        self.assertEqual(gst.fy_bounds("2026-27"), (date(2026, 4, 1), date(2027, 3, 31)))
        with self.assertRaises(ValueError):
            gst.fy_bounds("2026-28")

    def test_ist_conversion_moves_late_utc_into_next_day(self):
        self.assertEqual(gst.to_ist_date("2026-03-31T20:00:00+00:00"), date(2026, 4, 1))


class PhoneTests(unittest.TestCase):
    def test_india_rules(self):
        self.assertEqual(phones.parse_mobile("9876543210", "IN")[0], "+919876543210")
        self.assertEqual(phones.parse_mobile("09876543210", "IN")[0], "+919876543210")
        self.assertEqual(phones.parse_mobile("+91 98765 43210", "IN")[0], "+919876543210")
        for bad in ("987654321", "98765432100", "5876543210", "abcdefghij"):
            with self.assertRaises(ValueError, msg=bad):
                phones.parse_mobile(bad, "IN")

    def test_other_countries(self):
        self.assertEqual(phones.parse_mobile("501234567", "AE")[0], "+971501234567")
        self.assertEqual(phones.parse_mobile("2025550123", "US")[0], "+12025550123")
        with self.assertRaises(ValueError):
            phones.parse_mobile("12345", "AE")
        with self.assertRaises(ValueError):
            phones.parse_mobile("9876543210", "ZZ")

    def test_country_list_and_hints(self):
        by = {c["iso"]: c for c in phones.countries()}
        self.assertGreater(len(by), 200)
        self.assertEqual(phones.countries()[0]["iso"], "IN")
        self.assertEqual((by["IN"]["dial"], by["IN"]["lengths"]), ("+91", [10]))
        self.assertEqual(by["AE"]["lengths"], [9])
        self.assertEqual(by["IN"]["flag"], "🇮🇳")

    def test_mask_hides_middle_digits(self):
        self.assertEqual(phones.mask("+919876543210"), "+91•••••••210")


class GeoTests(unittest.TestCase):
    def test_all_states_have_districts_and_pincodes(self):
        self.assertEqual(len(geo.states()), 36)
        self.assertEqual(sum(1 for s in geo.states() if not geo.districts(s["name"])), 0)
        self.assertGreater(len(geo._load()["pins"]), 19000)

    def test_location_validation(self):
        self.assertEqual(geo.validate_location("jammu and kashmir", "pulwama", "192121"), ("Jammu and Kashmir", "Pulwama", "192121"))
        with self.assertRaises(ValueError):
            geo.validate_location("Delhi", "North", "190001")
        with self.assertRaises(ValueError):
            geo.validate_location("Delhi", "North", "12345")

    def test_kashmir_division_has_ten_districts_and_saffron_in_pulwama(self):
        self.assertEqual(len(geo.KASHMIR_DIVISION), 10)
        self.assertIn("Pulwama", geo.PRODUCTION["Saffron"]["major"])
        for d in geo.KASHMIR_DIVISION:
            self.assertIn(d, geo.jk_districts())


class ReportSafetyTests(unittest.TestCase):
    def test_text_starting_with_equals_is_never_a_formula(self):
        from openpyxl import Workbook
        ws = Workbook().active
        c = reports._cell(ws, 1, 1, '=HYPERLINK("http://evil")')
        self.assertEqual(c.data_type, "s")
        f = reports._cell(ws, 2, 1, "=SUM(A1:A1)", formula=True)
        self.assertEqual(f.data_type, "f")


if __name__ == "__main__":
    unittest.main(verbosity=2)
