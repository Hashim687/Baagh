"""End-to-end regression tests: admin security, OTP sign-up (no admin approval), trade and audit.

Run with: python -m unittest discover -s tests -v
Uses an isolated temporary SQLite database and never touches a live DB.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

_TMP_DIR = tempfile.TemporaryDirectory(prefix="baagh-test-")
os.environ["BAAGH_DB_PATH"] = str(Path(_TMP_DIR.name) / "baagh-tests.sqlite3")
os.environ["BAAGH_SEED_DEMO"] = "false"
os.environ["BAAGH_ENV"] = "development"
for _k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_PHONE", "TWILIO_VERIFY_SERVICE_SID"):
    os.environ.pop(_k, None)

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

BOOTSTRAP_PASSWORD = "BgH!7pQ#K26_vN9$Zr4@La8"


def register_member(client, **over):
    """Full automatic sign-up: send OTP, confirm it, return the verify response."""
    body = {"name": "QA Buyer", "phone": "9876543212", "country": "IN", "password": "Buyer!Password-2026-QA",
            "role": "buyer", "state": "Delhi", "district": "North", "pincode": "110033"}
    body.update(over)
    sent = client.post("/api/auth/register", json=body)
    assert sent.status_code == 202, sent.text
    otp = sent.json()["dev_otp"]
    return client.post("/api/auth/verify-otp", json={"phone": body["phone"], "country": body["country"], "otp": otp})


class TestBaaghCoreWorkflows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main.DB_PATH = Path(_TMP_DIR.name) / "baagh-tests.sqlite3"
        main.SEED_DEMO = False
        main.OTP_RESEND_SECONDS = 0
        cls.client_context = TestClient(main.app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)
        _TMP_DIR.cleanup()

    def test_end_to_end_auth_otp_trade_and_audit(self):
        c = self.client
        # Admin bootstrap must be changed before any privileged API action.
        resp = c.post("/api/auth/login", json={"phone": "baagh.admin", "password": BOOTSTRAP_PASSWORD})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["user"]["must_change_password"])
        headers = {"Authorization": "Bearer " + resp.json()["access_token"]}
        self.assertEqual(c.get("/api/admin/overview", headers=headers).status_code, 403)
        # Public reference data must still load for that session.
        self.assertEqual(c.get("/api/catalog", headers=headers).status_code, 200)
        resp = c.post("/api/auth/change-password", headers=headers, json={
            "current_password": BOOTSTRAP_PASSWORD, "new_password": "QA!AdminPassword_Changed_2026"})
        self.assertEqual(resp.status_code, 200, resp.text)
        resp = c.post("/api/auth/login", json={"phone": "baagh.admin", "password": "QA!AdminPassword_Changed_2026"})
        admin_headers = {"Authorization": "Bearer " + resp.json()["access_token"]}
        self.assertEqual(c.get("/api/admin/overview", headers=admin_headers).status_code, 200)

        # Sign-up creates nothing until the OTP is confirmed.
        seller_body = {"name": "QA Orchard Seller", "phone": "9876543210", "country": "IN", "password": "Seller!Password-2026-QA",
                       "role": "seller", "state": "Jammu and Kashmir", "district": "Baramulla"}
        sent = c.post("/api/auth/register", json=seller_body)
        self.assertEqual(sent.status_code, 202, sent.text)
        self.assertNotIn("access_token", sent.json())
        self.assertEqual(c.post("/api/auth/login", json={"phone": "9876543210", "password": seller_body["password"]}).status_code, 401)
        otp = sent.json()["dev_otp"]
        wrong = "999999" if otp != "999999" else "999998"
        self.assertEqual(c.post("/api/auth/verify-otp", json={"phone": "9876543210", "otp": wrong}).status_code, 400)
        ok = c.post("/api/auth/verify-otp", json={"phone": "9876543210", "otp": otp})
        self.assertEqual(ok.status_code, 201, ok.text)
        seller = ok.json()
        self.assertTrue(seller["user"]["verified"], "OTP success must verify the member without admin approval")
        self.assertTrue(seller["user"]["member_code"].startswith("BG-SEL-"))
        sh = {"Authorization": "Bearer " + seller["access_token"]}
        # Used codes cannot be replayed.
        self.assertEqual(c.post("/api/auth/verify-otp", json={"phone": "9876543210", "otp": otp}).status_code, 400)

        # Duplicates are rejected after normalisation.
        self.assertEqual(c.post("/api/auth/register", json={**seller_body, "name": "  qa   ORCHARD seller ", "phone": "9876543211"}).status_code, 409)
        self.assertEqual(c.post("/api/auth/register", json={**seller_body, "name": "Different Name", "phone": "+91 98765 43210"}).status_code, 409)

        buyer = register_member(c, name="QA Produce Buyer").json()
        bh = {"Authorization": "Bearer " + buyer["access_token"]}
        self.assertTrue(buyer["user"]["member_code"].startswith("BG-BUY-"))

        resp = c.post("/api/listings", headers=sh, json={"crop": "Apple", "product_form": "Fresh", "variety": "QA Red Delicious", "grade": "A",
                                                          "quantity_kg": 100, "price_per_kg": 95, "district": "Baramulla", "description": "Regression listing"})
        self.assertEqual(resp.status_code, 201, resp.text)
        self.assertEqual((resp.json()["hsn_code"], resp.json()["gst_rate"]), ("0808", 0))
        listing_id = resp.json()["id"]
        offer_id = c.post(f"/api/listings/{listing_id}/offers", headers=bh, json={"offered_price": 90, "quantity_kg": 25}).json()["id"]
        order_id = c.post(f"/api/offers/{offer_id}/decision?decision=accept", headers=sh).json()["order_id"]
        self.assertEqual(c.post(f"/api/orders/{order_id}/dispatch", headers=sh).status_code, 200)
        self.assertEqual(c.post(f"/api/orders/{order_id}/deliver", headers=sh).status_code, 200)

        for headers in (sh, bh):
            report = c.get("/api/my/audit-summary", headers=headers)
            self.assertEqual(report.json()["summary"]["delivered_trade_value"], 2250.0)
            csv_resp = c.get("/api/my/audit-report.csv", headers=headers)
            self.assertIn("QA Red Delicious", csv_resp.text)
            gst_json = c.get("/api/my/gst-summary", headers=headers).json()
            self.assertEqual(gst_json["summary"]["total_tax"], 0, "fresh apples are nil rated")
            self.assertEqual(gst_json["summary"]["taxable"], 2250.0)

        # Admin can suspend and reinstate, and a suspended member is locked out of trading.
        uid = seller["user"]["id"]
        self.assertEqual(c.post(f"/api/admin/users/{uid}/verify?verified=false", headers=admin_headers).status_code, 200)
        locked = c.post("/api/listings", headers=sh, json={"crop": "Apple", "variety": "x1", "grade": "A", "quantity_kg": 1, "price_per_kg": 1, "district": "Baramulla"})
        self.assertEqual(locked.status_code, 403)
        self.assertEqual(c.post(f"/api/admin/users/{uid}/verify?verified=true", headers=admin_headers).status_code, 200)
        self.assertEqual(c.get("/api/admin/overview", headers=sh).status_code, 403)
        self.assertEqual(c.get("/api/admin/overview").status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
