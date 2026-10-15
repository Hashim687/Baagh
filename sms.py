"""OTP delivery. Reads configuration from the environment on each call.

Supported providers
  1. Twilio Verify  (recommended, works for India/DLT):  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_VERIFY_SERVICE_SID
  2. Twilio SMS     (we generate the code):               TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_PHONE
  3. None           development/demo mode: the code is returned to the browser instead of an SMS.
                    Never available when BAAGH_ENV=production.
Real SMS always costs money (carriers charge per message); there is no free production SMS service.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from fastapi import HTTPException


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def is_production() -> bool:
    return _env("BAAGH_ENV").lower() == "production"


def mode() -> str:
    sid, tok = _env("TWILIO_ACCOUNT_SID"), _env("TWILIO_AUTH_TOKEN")
    if sid and tok and _env("TWILIO_VERIFY_SERVICE_SID"):
        return "twilio_verify"
    if sid and tok and _env("TWILIO_FROM_PHONE"):
        return "twilio_sms"
    return "none"


def public_status() -> dict:
    m = mode()
    if m != "none":
        return {"sms": "live", "provider": m}
    if is_production():
        return {"sms": "unavailable", "provider": "none"}
    return {"sms": "demo", "provider": "none"}


def _post(url: str, fields: dict) -> tuple[int, dict]:
    sid, tok = _env("TWILIO_ACCOUNT_SID"), _env("TWILIO_AUTH_TOKEN")
    auth = base64.b64encode(f"{sid}:{tok}".encode()).decode()
    req = urllib.request.Request(
        url, data=urllib.parse.urlencode(fields).encode(),
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = resp.read().decode() or "{}"
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode() or "{}")
        except Exception:
            body = {}
        return exc.code, body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HTTPException(status_code=502, detail="Could not reach the SMS provider. Try again in a moment.") from exc


def send_code_sms(phone: str, message: str) -> None:
    status, body = _post(
        f"https://api.twilio.com/2010-04-01/Accounts/{_env('TWILIO_ACCOUNT_SID')}/Messages.json",
        {"To": phone, "From": _env("TWILIO_FROM_PHONE"), "Body": message})
    if status not in (200, 201):
        raise HTTPException(status_code=502, detail="The OTP SMS could not be delivered. Check the phone number and try again.")


def verify_start(phone: str) -> None:
    status, body = _post(
        f"https://verify.twilio.com/v2/Services/{_env('TWILIO_VERIFY_SERVICE_SID')}/Verifications",
        {"To": phone, "Channel": "sms"})
    if status not in (200, 201):
        raise HTTPException(status_code=502, detail="The OTP SMS could not be delivered. Check the phone number and try again.")


def verify_check(phone: str, code: str) -> bool:
    status, body = _post(
        f"https://verify.twilio.com/v2/Services/{_env('TWILIO_VERIFY_SERVICE_SID')}/VerificationCheck",
        {"To": phone, "Code": code})
    return status == 200 and body.get("status") == "approved"
