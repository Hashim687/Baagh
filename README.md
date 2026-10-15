# Baagh — Kashmir Orchard Marketplace

Baagh is a responsive full-stack starter for connecting Kashmir orchard growers with produce buyers. This package includes the public website, FastAPI backend, persistent SQLite storage, role-specific dashboards, identity checks, OTP approval workflow, and per-member business audit exports.

## 1. Admin sign-in

**Default first-run administrator credentials**

- **Username:** `baagh.admin`
- **Initial password:** `BgH!7pQ#K26_vN9$Zr4@La8`
- Admin phone: `+919000000000`

Enter the username and initial password directly into the login form. The first sign-in is restricted to **Security settings** until the administrator changes this bootstrap password to a private password of at least 12 characters. One-click admin sign-in shortcuts have been removed. Change the secret key and administrator password before any public deployment.

The app only seeds an administrator if the database has none. When upgrading older databases, Baagh assigns missing usernames/member IDs and rotates known previous published bootstrap credentials, requiring the administrator to choose a private password. For an already-customized database, changing `.env` alone does not overwrite a private password hash stored in SQLite.

## 2. Run on Windows 10/11

1. Install Python 3.10 or newer and ensure the `py` launcher is available.
2. Extract the ZIP into a folder you can write to.
3. Double-click **`run_windows.bat`**. It creates `.venv`, installs dependencies, and starts Baagh.
4. Open **http://127.0.0.1:8000**.
5. Keep the command window open while using the site. Press `Ctrl+C` there to stop the server.

Linux/macOS:

```bash
chmod +x run_linux_mac.sh
./run_linux_mac.sh
```

API documentation is at **http://127.0.0.1:8000/docs** while the server is running.

## 3. What changed in this upgrade

### Unique identity and duplicate prevention

- Every account receives a stable public member code. Examples: `BG-SEL-000007` for a seller and `BG-BUY-000008` for a buyer. Codes are assigned from the persistent database ID and have a unique role prefix.
- Seller/buyer business names are unique without case sensitivity or repeated-space differences.
- Phone numbers are normalized before checking uniqueness, so `9876543210`, `+91 98765 43210`, and `+919876543210` are treated as the same Indian phone number.
- Phone uniqueness, username uniqueness, member-code uniqueness and seller/buyer name uniqueness are enforced by SQLite unique indexes as well as application validation.
- Users see their member code in the dashboard. New registration returns it, and the admin member list shows it.

### Automatic phone OTP sign-up (no admin approval)
Registering sends a 6-digit code to the phone number. The account is created, verified and signed in the moment the code is confirmed. Nothing is stored for a number until its OTP succeeds, so nobody can reserve someone else's number. Codes expire in 5 minutes, allow 5 wrong tries, can be re-sent after 60 seconds, and are capped at 5 per phone per hour. Admins can still **suspend / reinstate** members.

### Phone numbers for every country
Every country is listed with its dial code and flag. Rules come from Google's libphonenumber data: India must be exactly 10 digits starting 6-9, UAE 9 digits, and so on. Landlines and virtual numbers are rejected because they cannot receive SMS.

### India locations
All 36 states/UTs, their districts and 19,486 pincodes (India Post directory, `data/india_geo.json.gz`). A buyer's pincode must belong to the chosen district; typing a pincode fills in state and district. Sellers must be in Jammu & Kashmir or Ladakh. Buyers can join from any country.

### Produce catalog and Kashmir districts
Apple (21 varieties), Walnut, Almond and Saffron (Mongra/Lacha/Guchhi/Zarda) with forms, grades, HSN codes and GST rates in `catalog.py`. `geo.py` maps which of the 10 Kashmir districts grow each crop (indicative, not an official ranking).

### GST + Tally Excel report
Sellers and buyers download an `.xlsx` per financial year (April-March): Summary, Tally Voucher Register, Tally Ledger Entries (Dr/Cr, balanced), Tally Ledger Masters, GSTR-1 B2B and B2C (sellers), HSN Summary, Nil/Exempt Summary and Warnings. Rules applied: CGST+SGST (UTGST for UTs without a legislature) within a state, IGST between states, 0% for exports, no GST if the seller has no GSTIN. GSTINs are checked for format, checksum and state code.
Default rates (effective 22 Sep 2025): fresh apples nil, dried walnuts/almonds (HSN 0802) 5%, saffron (HSN 0910) 5%. These can change; edit `catalog.py` and have a CA review the output before filing returns.

### Refresh keeps you where you are
The address bar tracks the page (for example `#/app/audit` or `#market-rates`), so refreshing or sharing a link no longer sends you home.

### Business audit report for buyers and sellers

Open **Business audit report** in either buyer or seller dashboard. The report includes:

- Total agreed trade value, delivered trade value, order count and kilograms traded.
- A trade ledger showing each order, counterparty name and member ID, quantity, agreed unit price, calculated trade value, delivery status and payment status.
- Offer history, including declined/pending/accepted proposals and calculated offer values.
- Seller listing history and cold-storage booking ledger.
- Dispute ledger and account activity/audit events where those records relate to the member.
- **Download complete CSV report** for spreadsheet use, Excel review or bookkeeping.

**Accounting limitation:** the reported trade value is the agreed quantity multiplied by the order's unit price. The prototype does not process or verify payments, and these reports are not bank statements, tax invoices, or proof that money was paid.

### Other security and operations improvements

- Passwords are hashed with PBKDF2-HMAC-SHA256; sessions are signed and expire.
- Failed login attempts are rate-limited by a one-way identifier hash.
- Server-side role checks prevent buyers/sellers from performing admin operations or accessing another member's business report.
- Critical actions such as listing creation/removal, offers, order milestones, member approvals, inspection and storage booking decisions write an audit event.
- CSV exports mitigate spreadsheet formula injection in user-entered text cells.
- The **Security settings** dashboard page lets the signed-in user change their password. For a first-run admin account, the backend blocks protected API endpoints until this password is changed; public login screens do not expose a one-click admin login.
- The SQLite database persists across application restarts; older schemas are migrated at startup.

## 4. Demo accounts

These accounts are seeded on the first startup if `BAAGH_SEED_DEMO=true` and the appropriate demo data is not already present.

| Role | Login (phone or username) | Password |
|---|---|---|
| Admin | `baagh.admin` | `BgH!7pQ#K26_vN9$Zr4@La8` (initial; must be changed) |
| Seller / grower | `9800000002` | `Demo1234!` |
| Second seller | `9800000003` | `Demo1234!` |
| Buyer | `9800000004` | `Demo1234!` |
| Unverified seller sample | `9800000005` | `Demo1234!` |
| Inspector | `9000000006` | `InspectorDemo123!` |

Demo member IDs are assigned on initialization and can vary if a database already contains accounts. The admin username is configurable with `BAAGH_ADMIN_USERNAME`; the bootstrap password should only be used once and is forcibly changed at first sign-in. Do not use these demo accounts for a public production deployment.

## 5. Turn on real OTP SMS
Without SMS settings, development mode shows the code on screen (demo only). `BAAGH_ENV=production` refuses sign-ups until SMS is configured. SMS always costs money; there is no free production service.

Recommended (works with India's DLT rules): **Twilio Verify**. Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_VERIFY_SERVICE_SID`.
Alternative: Twilio SMS with `TWILIO_FROM_PHONE`. Twilio trial accounts only text numbers you have verified in Twilio.

## 6. Important limitations before commercial use

- Payments/escrow are not integrated. Status labels are records only; no money moves through Baagh.
- Live GPS/driver location is not integrated; dispatch and delivery are manually updated demo statuses.
- Market-rate values are seeded examples until an administrator records verified, timestamped source information.
- Cold storage capacity, rates and operator details are demo records and must be verified before accepting commercial bookings.
- Twilio SMS is optional and will not function until valid credentials and a sender are configured.
- This starter has not undergone an independent penetration test or production security certification. Before launch, arrange security testing, backups/restore drills, privacy/terms documentation, monitoring, log retention, disaster recovery and an appropriate production database/deployment setup.

## 7. API map
- Sign-up: `POST /api/auth/register` (sends OTP), `POST /api/auth/verify-otp`, `POST /api/auth/resend-otp`, `GET /api/auth/config`
- Reference data: `GET /api/catalog`, `/api/geo/countries`, `/api/geo/states`, `/api/geo/districts?state=`, `/api/geo/pincodes?state=&district=`, `/api/geo/pincode/{pin}`, `/api/geo/kashmir`
- Reports: `GET /api/my/gst-summary?fy=2026-27`, `GET /api/my/gst-report.xlsx?fy=2026-27`; buyers by location: `GET /api/buyers`

- `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/change-password`
- `GET /api/my/audit-summary`, `GET /api/my/audit-report.csv`
- `GET /api/listings`, `POST /api/listings`, `GET /api/listings/{id}`, `DELETE /api/listings/{id}`
- `POST /api/listings/{id}/offers`, `GET /api/my/offers`, `POST /api/offers/{id}/decision`
- `GET /api/orders`, `POST /api/orders/{id}/dispatch`, `POST /api/orders/{id}/deliver`, `POST /api/orders/{id}/disputes`
- `GET /api/rates`, `POST /api/rates`
- `GET /api/storage`, `POST /api/storage/bookings`, `GET /api/storage/bookings`, `POST /api/storage/bookings/{id}/decision`
- `GET /api/inspections`, `POST /api/inspections/{id}`
- `GET /api/admin/overview`, `POST /api/admin/users/{id}/verify?verified=false|true` (suspend / reinstate)
- `GET /api/disputes`, `POST /api/disputes/{id}/resolve`

## 8. Tests
`python -m unittest discover -s tests -v` (27 tests: OTP rules, phone and pincode validation, GSTIN checksum, GST splits, Excel integrity).

## 9. Free deployment note
On Render's free plan the SQLite file is wiped on each restart or redeploy, and the service sleeps when idle. Use it for demos; real data needs a persistent disk or hosted database.

> `QA_REVIEW.md` and `QA_TEST_REPORT.md` describe version 1 (admin-approved sign-up) and are kept for history.
