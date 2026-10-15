# Baagh QA and security review

## Automated checks run for this package

The end-to-end regression suite is included under `tests/test_core_workflows.py`.
Run it from the project folder:

```bash
python -m unittest discover -s tests -v
```

Coverage includes bootstrap admin login and mandatory password rotation, protection of admin API routes before rotation, case/whitespace-insensitive duplicate-name handling, normalized duplicate phone detection, member ID prefixes, unverified trade restrictions, OTP approval (including rejection of incorrect codes), listing/offer/order lifecycle, seller and buyer audit summaries, CSV exports, and role-based API access.

The development test suite uses a temporary SQLite file and does not modify your normal marketplace database.

## Review notes

- First-run admin credentials: `baagh.admin` / `BgH!7pQ#K26_vN9$Zr4@La8`. This is a bootstrap credential, not for production. The backend restricts protected API calls until it is changed.
- OTP delivery is real only when Twilio credentials are configured. Without SMS settings in local development, the code is clearly marked as a development-only preview; no text message is sent.
- Business totals are calculated from accepted orders. Delivered value is separately calculated from orders marked delivered. Since payment processing is not integrated, these amounts are agreement values, not proof of payment.
- Before public launch, configure production secrets, disable demo seeding, configure an SMS provider, enable HTTPS, back up the database, and commission a security review / penetration test.
