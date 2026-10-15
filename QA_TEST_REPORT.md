# Baagh QA / Reviewer Report

Date: 13 October 2026

## Automated checks run against the delivered source

- Python syntax compile (`python -m py_compile main.py`) — passed.
- Browser JavaScript syntax check (`node --check`) — passed.
- First-run database initialization, admin username login, and forced first-login password rotation — passed.
- Bootstrap admin protected-route lockout before password change; legacy published bootstrap credential migration — passed.
- Public auth screen no longer exposes one-click privileged admin login — passed.
- Registration rejects passwords shorter than 12 characters — passed.
- Legacy SQLite schema migration; member identity backfill; legacy bootstrap admin reset — passed.
- Seller/buyer member code assignment — passed.
- Duplicate member name checks (case and whitespace normalized) — passed.
- Duplicate phone checks (10-digit and +91 formatted number treated as the same phone) — passed.
- Direct admin approval bypass blocked — passed.
- OTP issue, incorrect-code rejection, correct approval and OTP reuse rejection — passed.
- Offer -> accepted order -> dispatch -> delivered lifecycle — passed.
- Seller and buyer business totals match the same order's agreed value — passed.
- Authenticated CSV audit download, including trade, offer and dispute sections — passed.
- Role-based denial for inspector accessing buyer/seller audit — passed.
- Password-change endpoint — passed.
- Failed-login attempts persisted and temporary lockout triggered — passed.
- Production-mode OTP request with no Twilio configuration returns an error and does not create an approval challenge — passed.
- Storefront route serves the upgraded UI — passed.

The package includes `tests/test_workflows.py` and `tests/test_core_workflows.py` to rerun core end-to-end flows locally. Both test suites passed after the update (2 tests total). Install `requirements-dev.txt`, then run:

```bash
python -m unittest discover -s tests -v
```

## Important review findings / limitations

- In development without Twilio, OTP is a test preview displayed to the admin; **it does not send a real SMS**. Configure Twilio for phone delivery. Production mode refuses OTP creation without configured SMS credentials.
- Agreed trade values in audit reports are computed from order quantity and unit price; no payment gateway or bank reconciliation exists.
- GPS, automatic live market prices, and real facility-capacity verification are not integrated.
- This QA report is an integration smoke-test record, not an independent penetration test or production certification.
