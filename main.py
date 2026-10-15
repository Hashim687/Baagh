from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import time
import unicodedata
import urllib.parse
import urllib.request
import urllib.error
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Header, Query, Request
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

import catalog
import geo
import gst
import phones
import reports
import sms

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
DB_PATH = Path(os.getenv("BAAGH_DB_PATH", str(BASE_DIR / "baagh.sqlite3")))
SECRET_KEY = os.getenv("BAAGH_SECRET_KEY", "development-only-change-this-secret-before-deployment")
TOKEN_TTL = int(os.getenv("BAAGH_TOKEN_TTL_SECONDS", "86400"))
ADMIN_NAME = os.getenv("BAAGH_ADMIN_NAME", "Baagh Administrator")
ADMIN_USERNAME = os.getenv("BAAGH_ADMIN_USERNAME", "baagh.admin").strip().lower()
ADMIN_PHONE = os.getenv("BAAGH_ADMIN_PHONE", "9000000000")
BOOTSTRAP_ADMIN_PASSWORD = "BgH!7pQ#K26_vN9$Zr4@La8"
PREVIOUS_BOOTSTRAP_ADMIN_PASSWORD = "Baagh#Root!Kashmir26"
ADMIN_PASSWORD = os.getenv("BAAGH_ADMIN_PASSWORD", BOOTSTRAP_ADMIN_PASSWORD)
BAAGH_ENV = os.getenv("BAAGH_ENV", "development").lower()
OTP_TTL_SECONDS = int(os.getenv("BAAGH_OTP_TTL_SECONDS", "300"))
SEED_DEMO = os.getenv("BAAGH_SEED_DEMO", "true").lower() == "true"
if BAAGH_ENV == "production":
    if SECRET_KEY == "development-only-change-this-secret-before-deployment" or len(SECRET_KEY) < 32 or "replace" in SECRET_KEY.lower() or "example" in SECRET_KEY.lower():
        raise RuntimeError("Set BAAGH_SECRET_KEY to a unique random secret of at least 32 characters before production deployment.")
    if ADMIN_PASSWORD == BOOTSTRAP_ADMIN_PASSWORD or len(ADMIN_PASSWORD) < 16:
        raise RuntimeError("Set BAAGH_ADMIN_PASSWORD to a private password of at least 16 characters before production deployment.")
    if SEED_DEMO:
        raise RuntimeError("Set BAAGH_SEED_DEMO=false before production deployment so demo accounts are not created.")

if BAAGH_ENV == "production" and sms.mode() == "none":
    print("WARNING: no SMS provider configured. New registrations cannot receive an OTP until Twilio is set up.")

app = FastAPI(title="Baagh Orchard Marketplace API", version="2.0.0", description="API for a Kashmir orchard produce marketplace.")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# ---------- Database ----------
@contextmanager
def db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(value.strip().split()).casefold()


def normalize_phone(value: str, country: str = "IN") -> str:
    return phones.normalize_phone(value, country)


def audit_event(conn, actor_user_id, event_type: str, entity_type: str, entity_id="", target_user_id=None, details=None):
    conn.execute(
        "INSERT INTO audit_events(actor_user_id,target_user_id,event_type,entity_type,entity_id,details_json,created_at) VALUES(?,?,?,?,?,?,?)",
        (actor_user_id, target_user_id, event_type, entity_type, str(entity_id or ""),
         json.dumps(details or {}, ensure_ascii=False, sort_keys=True), now_iso())
    )


def member_prefix(role: str) -> str:
    return {"admin":"ADM", "seller":"SEL", "buyer":"BUY", "inspector":"INSP"}.get(role, "MEM")


def otp_digest(phone: str, otp: str) -> str:
    return hmac.new(SECRET_KEY.encode(), f"reg:{phone}:{otp}".encode(), hashlib.sha256).hexdigest()


def add_columns(conn, table: str, columns: dict):
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for col, definition in columns.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")


def init_db():
    with db_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            district TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('seller','buyer','admin','inspector')),
            password_hash TEXT NOT NULL,
            verified INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            username TEXT,
            member_code TEXT,
            phone_normalized TEXT,
            name_normalized TEXT,
            must_change_password INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL REFERENCES users(id),
            crop TEXT NOT NULL,
            variety TEXT NOT NULL,
            grade TEXT NOT NULL CHECK(grade IN ('A','B','C')),
            quantity_kg REAL NOT NULL CHECK(quantity_kg > 0),
            available_kg REAL NOT NULL CHECK(available_kg >= 0),
            price_per_kg REAL NOT NULL CHECK(price_per_kg > 0),
            district TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','sold','removed')),
            inspection_status TEXT NOT NULL DEFAULT 'unverified',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL REFERENCES listings(id),
            buyer_id INTEGER NOT NULL REFERENCES users(id),
            offered_price REAL NOT NULL CHECK(offered_price > 0),
            quantity_kg REAL NOT NULL CHECK(quantity_kg > 0),
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','declined','withdrawn')),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL REFERENCES listings(id),
            seller_id INTEGER NOT NULL REFERENCES users(id),
            buyer_id INTEGER NOT NULL REFERENCES users(id),
            offer_id INTEGER NOT NULL REFERENCES offers(id),
            quantity_kg REAL NOT NULL,
            price_per_kg REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'Accepted',
            progress REAL NOT NULL DEFAULT 0,
            payment_status TEXT NOT NULL DEFAULT 'not_integrated',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS market_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crop TEXT NOT NULL,
            mandi TEXT NOT NULL,
            price_per_kg REAL NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(crop, mandi)
        );
        CREATE TABLE IF NOT EXISTS storage_sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            district TEXT NOT NULL,
            capacity_tonnes REAL NOT NULL,
            occupied_tonnes REAL NOT NULL DEFAULT 0,
            rate_per_kg_month REAL NOT NULL,
            temperature TEXT NOT NULL,
            suitable_for TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS storage_bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            storage_id INTEGER NOT NULL REFERENCES storage_sites(id),
            seller_id INTEGER NOT NULL REFERENCES users(id),
            quantity_kg REAL NOT NULL,
            months INTEGER NOT NULL,
            estimated_cost REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS disputes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            raised_by INTEGER NOT NULL REFERENCES users(id),
            received_grade TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            resolution TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approval_otps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            otp_hash TEXT NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            used_at REAL,
            delivery_status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER REFERENCES users(id),
            target_user_id INTEGER REFERENCES users(id),
            event_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL DEFAULT '',
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS login_throttle (
            identifier_hash TEXT PRIMARY KEY,
            failures INTEGER NOT NULL DEFAULT 0,
            window_started REAL NOT NULL,
            locked_until REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status);
        CREATE INDEX IF NOT EXISTS idx_offers_listing ON offers(listing_id);
        CREATE INDEX IF NOT EXISTS idx_orders_buyer ON orders(buyer_id);
        CREATE INDEX IF NOT EXISTS idx_orders_seller ON orders(seller_id);
        CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_events(actor_user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_events(target_user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_otp_user_created ON approval_otps(user_id, created_at);
        CREATE TABLE IF NOT EXISTS pending_registrations (
            phone TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            otp_hash TEXT,
            otp_mode TEXT NOT NULL,
            delivery_status TEXT NOT NULL,
            created_at REAL NOT NULL,
            last_sent REAL NOT NULL,
            expires_at REAL NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS otp_send_log (
            phone TEXT NOT NULL,
            sent_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_otp_send_log ON otp_send_log(phone, sent_at);
        """)
        # Columns added after the first release. Safe to run on every start.
        add_columns(conn, "users", {"country": "TEXT NOT NULL DEFAULT 'IN'", "state": "TEXT", "pincode": "TEXT", "address": "TEXT", "gstin": "TEXT"})
        add_columns(conn, "listings", {"product_form": "TEXT", "grade_label": "TEXT", "hsn_code": "TEXT", "gst_rate": "REAL"})
        add_columns(conn, "orders", {"hsn_code": "TEXT", "gst_rate": "REAL", "dispatched_at": "TEXT", "delivered_at": "TEXT"})
        # Migrate databases made by earlier versions. The first migration resets only the
        # legacy seeded admin password so the documented bootstrap credentials work.
        user_columns = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        legacy_users_schema = "member_code" not in user_columns
        for col, definition in {
            "username": "TEXT", "member_code": "TEXT", "phone_normalized": "TEXT",
            "name_normalized": "TEXT", "must_change_password": "INTEGER NOT NULL DEFAULT 0"
        }.items():
            if col not in user_columns:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
        if conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] == 0:
            conn.execute("INSERT INTO users(name,phone,district,role,password_hash,verified,created_at,must_change_password) VALUES(?,?,?,?,?,?,?,1)",
                         (ADMIN_NAME, ADMIN_PHONE, "Srinagar", "admin", hash_password(ADMIN_PASSWORD), 1, now_iso()))
        if conn.execute("SELECT COUNT(*) FROM market_rates").fetchone()[0] == 0:
            conn.executemany("INSERT INTO market_rates(crop,mandi,price_per_kg,updated_at) VALUES(?,?,?,?)", [
                ("Apple", "Sopore", 92, now_iso()), ("Apple", "Delhi Azadpur", 118, now_iso()),
                ("Walnut", "Kupwara", 320, now_iso()), ("Almond", "Pulwama", 680, now_iso()),
                ("Apple", "Shopian", 88, now_iso()), ("Walnut", "Srinagar", 350, now_iso())])
        if conn.execute("SELECT COUNT(*) FROM storage_sites").fetchone()[0] == 0:
            conn.executemany("INSERT INTO storage_sites(name,district,capacity_tonnes,occupied_tonnes,rate_per_kg_month,temperature,suitable_for) VALUES(?,?,?,?,?,?,?)", [
                ("Kashmir Cold Chain", "Sopore", 500, 320, 2.0, "0–2°C", "Apple"),
                ("Valley Fresh Storage", "Shopian", 300, 90, 2.5, "0–2°C", "Apple"),
                ("Pulwama Dry Store", "Pulwama", 150, 40, 1.5, "Cool & dry", "Walnut, Almond")])
        if SEED_DEMO and conn.execute("SELECT COUNT(*) FROM users WHERE role='seller'").fetchone()[0] == 0:
            def demo_gstin(prefix14: str) -> str:
                return prefix14 + gst.gstin_checksum_char(prefix14)

            def seed_user(name, phone, district, role, password, verified, state, pincode, gstin=None, address=""):
                return conn.execute(
                    "INSERT INTO users(name,phone,district,role,password_hash,verified,created_at,country,state,pincode,address,gstin) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (name, phone, district, role, hash_password(password), verified, now_iso(), "IN", state, pincode, address, gstin)).lastrowid

            def seed_listing(seller_id, crop, form, variety, grade, qty, price, district, text, inspection):
                info = catalog.form_info(crop, form)
                conn.execute(
                    "INSERT INTO listings(seller_id,crop,variety,grade,quantity_kg,available_kg,price_per_kg,district,description,status,inspection_status,created_at,product_form,grade_label,hsn_code,gst_rate) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (seller_id, crop, variety, grade, qty, qty, price, district, text, "open", inspection, now_iso(), form,
                     catalog.grade_label_for(crop, grade), info["hsn"], info["gst_rate"]))

            # Demo GSTINs are syntactically valid test numbers, not real registrations.
            seller_id = seed_user("Bashir Ahmad", "9800000002", "Baramulla", "seller", "Demo1234!", 1, "Jammu and Kashmir", "193201", None, "Sopore")
            seller2_id = seed_user("Ghulam Rasool", "9800000003", "Kupwara", "seller", "Demo1234!", 1, "Jammu and Kashmir", "193222", demo_gstin("01AAAPR1234Q1Z"), "Kupwara")
            seller3_id = seed_user("Pampore Saffron Growers", "9800000007", "Pulwama", "seller", "Demo1234!", 1, "Jammu and Kashmir", "192121", demo_gstin("01AAAFP4321K1Z"), "Pampore")
            buyer_id = seed_user("Azad Traders", "9800000004", "North", "buyer", "Demo1234!", 1, "Delhi", "110033", demo_gstin("07AAACA5678D1Z"), "Azadpur Mandi")
            seed_user("New Valley Grower", "9800000005", "Shopian", "seller", "Demo1234!", 0, "Jammu and Kashmir", "192303", None, "Shopian")
            seed_listing(seller_id, "Apple", "Fresh", "Royal Delicious", "A", 2000, 95, "Baramulla", "Crisp, deep-red fruit picked from a family orchard in Sopore.", "inspected")
            seed_listing(seller_id, "Walnut", "In shell (dry)", "Kagzi (Paper shell)", "A", 800, 335, "Baramulla", "Thin-shell walnuts, suitable for premium kernel buyers.", "unverified")
            seed_listing(seller2_id, "Almond", "In shell (dry)", "Waris", "B", 400, 640, "Kupwara", "Carefully sorted almonds from the Kashmir valley.", "unverified")
            seed_listing(seller3_id, "Saffron", "Whole stigma (threads)", "Mongra (Lacha) - Grade I", "A", 5, 295000, "Pulwama", "Hand-picked, shade-dried Pampore saffron threads.", "unverified")
            conn.execute("INSERT INTO users(name,phone,district,role,password_hash,verified,created_at,country,state) VALUES(?,?,?,?,?,?,?,?,?)",
                         ("Baagh Inspector", "9000000006", "Srinagar", "inspector", hash_password("InspectorDemo123!"), 1, now_iso(), "IN", "Jammu and Kashmir"))
        # Canonical identities are backfilled for all old accounts, then uniqueness is enforced.
        all_users = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        seen_phone = set()
        for account in all_users:
            uid, role = account["id"], account["role"]
            try:
                canonical_phone = normalize_phone(account["phone"])
            except ValueError:
                canonical_phone = "legacy-invalid-" + str(uid)
            if canonical_phone in seen_phone:
                canonical_phone = "legacy-duplicate-" + str(uid)
            seen_phone.add(canonical_phone)
            code_prefix = {"admin":"ADM", "seller":"SEL", "buyer":"BUY", "inspector":"INSP"}.get(role, "MEM")
            member_code = account["member_code"] or f"BG-{code_prefix}-{uid:06d}"
            if role == "admin":
                username = ADMIN_USERNAME
                if legacy_users_schema:
                    # Rotate legacy bootstrap credentials and force the administrator to set a private password.
                    conn.execute("UPDATE users SET password_hash=?,must_change_password=1 WHERE id=?", (hash_password(ADMIN_PASSWORD), uid))
                elif check_password(PREVIOUS_BOOTSTRAP_ADMIN_PASSWORD, account["password_hash"]):
                    # One-time compatibility upgrade for already-initialized packages using the prior published default.
                    conn.execute("UPDATE users SET password_hash=?,must_change_password=1 WHERE id=?", (hash_password(ADMIN_PASSWORD), uid))
            else:
                username = account["username"] or f"baagh.{code_prefix.lower()}.{uid:06d}"
            name_norm = normalize_name(account["name"])
            conn.execute("UPDATE users SET phone=?,phone_normalized=?,name_normalized=?,username=?,member_code=? WHERE id=?",
                         (canonical_phone, canonical_phone, name_norm, username, member_code, uid))
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone_normalized ON users(phone_normalized)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username COLLATE NOCASE)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_member_code ON users(member_code)")
        # Older accounts have no state/country: infer what is safe to infer.
        state_names = {geo.canonical_state(x["name"]) for x in geo.states()}
        for row in conn.execute("SELECT id,role,district FROM users WHERE state IS NULL OR state=''").fetchall():
            guess = geo.JK_STATE if row["role"] in ("seller", "admin", "inspector") else (geo.canonical_state(row["district"]) if geo.canonical_state(row["district"]) in state_names else "")
            conn.execute("UPDATE users SET state=? WHERE id=?", (guess or "", row["id"]))
        conn.execute("UPDATE listings SET product_form=? WHERE product_form IS NULL AND crop='Apple'", ("Fresh",))
        for row in conn.execute("SELECT id,crop FROM listings WHERE product_form IS NULL OR hsn_code IS NULL").fetchall():
            if catalog.get_crop(row["crop"]):
                form = catalog.default_form(row["crop"])
                info = catalog.form_info(row["crop"], form)
                conn.execute("UPDATE listings SET product_form=COALESCE(product_form,?),hsn_code=COALESCE(hsn_code,?),gst_rate=COALESCE(gst_rate,?) WHERE id=?",
                             (form, info["hsn"], info["gst_rate"], row["id"]))
        duplicate_names = conn.execute("SELECT name_normalized,COUNT(*) n FROM users WHERE role IN ('seller','buyer') GROUP BY name_normalized HAVING COUNT(*)>1").fetchall()
        if not duplicate_names:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_unique_trade_name ON users(name_normalized) WHERE role IN ('seller','buyer')")
        else:
            # Keep legacy data readable, but refuse new duplicates in register() via its normalized-name check.
            print("WARNING: legacy database has duplicate buyer/seller names; resolve those names to enable the database-level unique-name index.")


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return base64.urlsafe_b64encode(salt).decode().rstrip("=") + "$" + base64.urlsafe_b64encode(digest).decode().rstrip("=")


def check_password(password: str, encoded: str) -> bool:
    try:
        s, d = encoded.split("$", 1)
        salt = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
        expected = base64.urlsafe_b64decode(d + "=" * (-len(d) % 4))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def create_token(user_id: int, role: str) -> str:
    header = b64url(json.dumps({"alg":"HS256","typ":"JWT"}, separators=(",", ":")).encode())
    payload = b64url(json.dumps({"sub": user_id, "role": role, "exp": int(time.time()) + TOKEN_TTL}, separators=(",", ":")).encode())
    signing = f"{header}.{payload}"
    sig = b64url(hmac.new(SECRET_KEY.encode(), signing.encode(), hashlib.sha256).digest())
    return f"{signing}.{sig}"


def read_token(token: str):
    try:
        header, payload, signature = token.split(".")
        signing = f"{header}.{payload}"
        expected = b64url(hmac.new(SECRET_KEY.encode(), signing.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, signature):
            raise ValueError("signature")
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if int(data["exp"]) < int(time.time()):
            raise ValueError("expired")
        return data
    except Exception:
        raise HTTPException(status_code=401, detail="Session is invalid or expired. Please log in again.")


def user_public(row):
    return {"id": row["id"], "member_code": row["member_code"], "username": row["username"], "name": row["name"], "phone": row["phone"], "district": row["district"], "role": row["role"], "verified": bool(row["verified"]), "must_change_password": bool(row["must_change_password"]), "created_at": row["created_at"],
            "country": row["country"] or "IN", "state": row["state"] or "", "pincode": row["pincode"] or "", "address": row["address"] or "", "gstin": row["gstin"] or ""}


def get_current_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Please log in to continue.")
    data = read_token(authorization.split(" ", 1)[1].strip())
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (data.get("sub"),)).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Account not found.")
    return user_public(row)


@app.middleware("http")
async def enforce_initial_password_change(request: Request, call_next):
    """Do not allow a bootstrap admin session to use protected API routes before rotation."""
    path = request.url.path
    allowed_during_rotation = {
        "/api/health", "/api/auth/login", "/api/auth/register",
        "/api/auth/me", "/api/auth/change-password"
    }
    public_read = request.method == "GET" and (path.startswith(("/api/geo/", "/api/listings", "/api/rates", "/api/storage")) or path in ("/api/catalog", "/api/summary"))
    authorization = request.headers.get("authorization", "")
    if path.startswith("/api/") and path not in allowed_during_rotation and not path.startswith("/api/auth/") and not public_read and authorization.lower().startswith("bearer "):
        try:
            token_data = read_token(authorization.split(" ", 1)[1].strip())
            with db_conn() as conn:
                row = conn.execute("SELECT must_change_password FROM users WHERE id=?", (token_data.get("sub"),)).fetchone()
            if row and row["must_change_password"]:
                return JSONResponse(status_code=403, content={"detail": "Your initial administrator password must be changed before you can use protected Baagh features."})
        except HTTPException:
            # Let the route's normal authentication dependency return the standard 401.
            pass
    return await call_next(request)


def require_roles(*roles):
    def dependency(user=Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Your account does not have permission for this action.")
        return user
    return dependency


# ---------- Schemas ----------
class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=4, max_length=24)
    country: str = Field(default="IN", min_length=2, max_length=2)
    password: str = Field(min_length=12, max_length=128)
    role: str = Field(pattern="^(seller|buyer)$")
    state: str = Field(default="", max_length=80)
    district: str = Field(min_length=2, max_length=80)
    pincode: str = Field(default="", max_length=10)
    address: str = Field(default="", max_length=200)
    gstin: str = Field(default="", max_length=20)

class LoginIn(BaseModel):
    # Despite the legacy field name, this accepts either phone number or username.
    phone: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=1, max_length=128)
    country: str = Field(default="IN", min_length=2, max_length=2)

class OtpVerifyIn(BaseModel):
    phone: str = Field(min_length=4, max_length=24)
    country: str = Field(default="IN", min_length=2, max_length=2)
    otp: str = Field(pattern=r"^\d{6}$")

class OtpResendIn(BaseModel):
    phone: str = Field(min_length=4, max_length=24)
    country: str = Field(default="IN", min_length=2, max_length=2)

class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

class ListingIn(BaseModel):
    crop: str = Field(min_length=2, max_length=30)
    product_form: str = Field(default="", max_length=60)
    variety: str = Field(min_length=2, max_length=100)
    grade: str = Field(pattern="^[ABC]$")
    quantity_kg: float = Field(gt=0, le=1_000_000)
    price_per_kg: float = Field(gt=0, le=1_000_000)
    district: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=1200)

class OfferIn(BaseModel):
    offered_price: float = Field(gt=0, le=1_000_000)
    quantity_kg: float = Field(gt=0, le=1_000_000)

class RateIn(BaseModel):
    crop: str = Field(min_length=2, max_length=30)
    mandi: str = Field(min_length=2, max_length=100)
    price_per_kg: float = Field(gt=0, le=1_000_000)

class BookingIn(BaseModel):
    storage_id: int
    quantity_kg: float = Field(gt=0, le=1_000_000)
    months: int = Field(ge=1, le=24)

class DisputeIn(BaseModel):
    received_grade: str = Field(pattern="^[ABC]$")
    reason: str = Field(min_length=5, max_length=1500)


# ---------- Pages and health ----------
@app.get("/", include_in_schema=False)
def root():
    return FileResponse(BASE_DIR / "static" / "index.html")

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "baagh-marketplace", "time": now_iso()}


# ---------- Authentication ----------
# ---- Registration with automatic phone OTP (no administrator approval) ----
OTP_RESEND_SECONDS = int(os.getenv("BAAGH_OTP_RESEND_SECONDS", "60"))
OTP_MAX_SENDS_PER_HOUR = int(os.getenv("BAAGH_OTP_MAX_PER_HOUR", "5"))
OTP_MAX_ATTEMPTS = 5
IP_HOURLY_LIMIT = int(os.getenv("BAAGH_IP_OTP_LIMIT", "40"))
_ip_hits: dict = {}


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")) or "unknown"


def rate_limit_ip(request: Request, limit: Optional[int] = None):
    limit = limit or IP_HOURLY_LIMIT
    now = time.time()
    hits = [t for t in _ip_hits.get(client_ip(request), []) if now - t < 3600]
    if len(hits) >= limit:
        raise HTTPException(status_code=429, detail="Too many attempts from this network. Please try again in an hour.")
    hits.append(now)
    _ip_hits[client_ip(request)] = hits


def phone_or_422(raw: str, country: str) -> str:
    try:
        return phones.parse_mobile(raw, country)[0]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def validate_registration(data: RegisterIn) -> dict:
    country = data.country.upper()
    phone = phone_or_422(data.phone, country)
    name = " ".join(data.name.strip().split())
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Enter a valid full or business name.")
    state = district = pincode = ""
    if country == "IN":
        try:
            if data.role == "buyer" or data.pincode.strip():
                state, district, pincode = geo.validate_location(data.state, data.district, data.pincode)
            else:
                state = geo.canonical_state(data.state)
                district = geo.canonical_district(data.state, data.district) if state else None
                if not state or not district:
                    raise ValueError("Choose a valid state and district.")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if data.role == "seller" and state not in geo.JK_STATES:
            raise HTTPException(status_code=422, detail="Sellers must be located in Jammu & Kashmir or Ladakh.")
    else:
        if data.role == "seller":
            raise HTTPException(status_code=422, detail="Sellers must be located in India (Jammu & Kashmir or Ladakh). Buyers can join from any country.")
        phones_country = phones.country(country)
        district = data.district.strip()
        pincode = data.pincode.strip()
        if not phones_country:
            raise HTTPException(status_code=422, detail="Choose a valid country.")
    gstin = ""
    if data.gstin.strip():
        if country != "IN":
            raise HTTPException(status_code=422, detail="GSTIN applies to Indian businesses only.")
        try:
            gstin = gst.validate_gstin(data.gstin)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        expected = geo.GST_STATE_CODES.get(state)
        if expected and gstin[:2] != expected:
            raise HTTPException(status_code=422, detail=f"GSTIN starts with {gstin[:2]} ({geo.GST_CODE_TO_STATE.get(gstin[:2], 'unknown')}) but your state is {state} (code {expected}).")
    return {"name": name, "phone": phone, "role": data.role, "country": country, "state": state, "district": district,
            "pincode": pincode, "address": data.address.strip(), "gstin": gstin, "password_hash": hash_password(data.password)}


def issue_registration_otp(conn, phone: str) -> dict:
    """Send (or, in demo mode, prepare) a fresh OTP. Enforces cooldown and an hourly cap per phone."""
    status = sms.public_status()["sms"]
    if status == "unavailable":
        raise HTTPException(status_code=503, detail="SMS verification is not configured on this server yet. Please contact the Baagh administrator.")
    now = time.time()
    last = conn.execute("SELECT MAX(sent_at) FROM otp_send_log WHERE phone=?", (phone,)).fetchone()[0]
    if last and now - float(last) < OTP_RESEND_SECONDS:
        wait = int(OTP_RESEND_SECONDS - (now - float(last))) + 1
        raise HTTPException(status_code=429, detail=f"Please wait {wait} seconds before requesting another code.")
    if conn.execute("SELECT COUNT(*) FROM otp_send_log WHERE phone=? AND sent_at>?", (phone, now - 3600)).fetchone()[0] >= OTP_MAX_SENDS_PER_HOUR:
        raise HTTPException(status_code=429, detail="Code limit reached for this number. Try again after an hour.")
    mode = sms.mode()
    otp = otp_hash = None
    if mode == "twilio_verify":
        sms.verify_start(phone)
        otp_mode, delivery = "twilio_verify", "sms"
    else:
        otp = f"{secrets.randbelow(1_000_000):06d}"
        otp_hash = otp_digest(phone, otp)
        otp_mode = "local"
        if mode == "twilio_sms":
            sms.send_code_sms(phone, f"Baagh verification code: {otp}. It expires in {OTP_TTL_SECONDS // 60} minutes. Do not share this code.")
            delivery = "sms"
        else:
            delivery = "demo"
    conn.execute("INSERT INTO otp_send_log(phone,sent_at) VALUES(?,?)", (phone, now))
    return {"otp": otp, "otp_hash": otp_hash, "otp_mode": otp_mode, "delivery": delivery, "last_sent": now, "expires_at": now + OTP_TTL_SECONDS}


def otp_response(phone: str, issued: dict) -> dict:
    result = {"pending_verification": True, "phone": phones.mask(phone), "delivery": issued["delivery"],
              "expires_in_seconds": OTP_TTL_SECONDS, "resend_after_seconds": OTP_RESEND_SECONDS,
              "message": "We sent a 6-digit code by SMS." if issued["delivery"] == "sms" else
                         "Demo mode: SMS delivery is not configured, so the code is shown below instead of being sent."}
    if issued["delivery"] == "demo" and BAAGH_ENV != "production":
        result["dev_otp"] = issued["otp"]
    return result


@app.get("/api/auth/config")
def auth_config():
    return {**sms.public_status(), "otp_ttl_seconds": OTP_TTL_SECONDS, "resend_seconds": OTP_RESEND_SECONDS}


@app.post("/api/auth/register", status_code=202)
def register(data: RegisterIn, request: Request):
    """Step 1: validate everything and text an OTP. The account is only created once the code is confirmed."""
    rate_limit_ip(request)
    payload = validate_registration(data)
    phone, name_norm = payload["phone"], normalize_name(payload["name"])
    with db_conn() as conn:
        if conn.execute("SELECT 1 FROM users WHERE phone_normalized=?", (phone,)).fetchone():
            raise HTTPException(status_code=409, detail="This phone number already has a Baagh account. Log in instead.")
        if conn.execute("SELECT 1 FROM users WHERE name_normalized=? AND role IN ('seller','buyer')", (name_norm,)).fetchone():
            raise HTTPException(status_code=409, detail="A buyer or seller with this name already exists. Use the existing account or provide a distinct registered business name.")
        issued = issue_registration_otp(conn, phone)
        conn.execute(
            """INSERT INTO pending_registrations(phone,payload_json,otp_hash,otp_mode,delivery_status,created_at,last_sent,expires_at,attempts)
               VALUES(?,?,?,?,?,?,?,?,0)
               ON CONFLICT(phone) DO UPDATE SET payload_json=excluded.payload_json,otp_hash=excluded.otp_hash,otp_mode=excluded.otp_mode,
               delivery_status=excluded.delivery_status,created_at=excluded.created_at,last_sent=excluded.last_sent,expires_at=excluded.expires_at,attempts=0""",
            (phone, json.dumps(payload), issued["otp_hash"], issued["otp_mode"], issued["delivery"], issued["last_sent"], issued["last_sent"], issued["expires_at"]))
    return otp_response(phone, issued)


@app.post("/api/auth/resend-otp")
def resend_otp(data: OtpResendIn, request: Request):
    rate_limit_ip(request)
    phone = phone_or_422(data.phone, data.country.upper())
    with db_conn() as conn:
        pend = conn.execute("SELECT * FROM pending_registrations WHERE phone=?", (phone,)).fetchone()
        if not pend:
            raise HTTPException(status_code=400, detail="No sign-up is waiting for this number. Please fill in the registration form again.")
        issued = issue_registration_otp(conn, phone)
        conn.execute("UPDATE pending_registrations SET otp_hash=?,otp_mode=?,delivery_status=?,last_sent=?,expires_at=?,attempts=0 WHERE phone=?",
                     (issued["otp_hash"], issued["otp_mode"], issued["delivery"], issued["last_sent"], issued["expires_at"], phone))
    return otp_response(phone, issued)


@app.post("/api/auth/verify-otp", status_code=201)
def verify_registration(data: OtpVerifyIn, request: Request):
    """Step 2: confirm the code; the verified account is created and signed in immediately."""
    rate_limit_ip(request, limit=IP_HOURLY_LIMIT * 3)
    phone = phone_or_422(data.phone, data.country.upper())
    failure = None
    public = None
    with db_conn() as conn:
        pend = conn.execute("SELECT * FROM pending_registrations WHERE phone=?", (phone,)).fetchone()
        if not pend:
            raise HTTPException(status_code=400, detail="No sign-up is waiting for this number. Please fill in the registration form again.")
        now = time.time()
        if now > float(pend["expires_at"]):
            failure = (400, "This code has expired. Tap 'Resend code' to get a new one.")
        elif int(pend["attempts"]) >= OTP_MAX_ATTEMPTS:
            failure = (429, "Too many wrong attempts. Tap 'Resend code' to get a new code.")
        else:
            if pend["otp_mode"] == "twilio_verify":
                good = sms.verify_check(phone, data.otp)
            else:
                good = hmac.compare_digest(pend["otp_hash"] or "", otp_digest(phone, data.otp))
            if not good:
                conn.execute("UPDATE pending_registrations SET attempts=attempts+1 WHERE phone=?", (phone,))
                failure = (400, "That code is not correct.")
        if not failure:
            p = json.loads(pend["payload_json"])
            name_norm = normalize_name(p["name"])
            try:
                cur = conn.execute(
                    """INSERT INTO users(name,phone,district,role,password_hash,verified,created_at,username,member_code,phone_normalized,name_normalized,
                       must_change_password,country,state,pincode,address,gstin) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (p["name"], phone, p["district"], p["role"], p["password_hash"], 1, now_iso(),
                     f"baagh.{member_prefix(p['role']).lower()}.pending.{secrets.token_hex(3)}",
                     f"BG-{member_prefix(p['role'])}-PENDING-{secrets.token_hex(3).upper()}", phone, name_norm, 0,
                     p["country"], p["state"], p["pincode"], p["address"], p["gstin"] or None))
                uid = cur.lastrowid
                member_code = f"BG-{member_prefix(p['role'])}-{uid:06d}"
                conn.execute("UPDATE users SET username=?,member_code=? WHERE id=?", (f"baagh.{member_prefix(p['role']).lower()}.{uid:06d}", member_code, uid))
                conn.execute("DELETE FROM pending_registrations WHERE phone=?", (phone,))
                audit_event(conn, uid, "member_registered", "user", uid, target_user_id=uid,
                            details={"role": p["role"], "member_code": member_code, "phone_verified": True, "country": p["country"]})
                public = user_public(conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
            except sqlite3.IntegrityError as exc:
                raise HTTPException(status_code=409, detail="An account with this phone number or name was created a moment ago. Try logging in.") from exc
    if failure:
        raise HTTPException(status_code=failure[0], detail=failure[1])
    return {"access_token": create_token(public["id"], public["role"]), "token_type": "bearer", "user": public}


# ---- Reference data for forms ----
@app.get("/api/catalog")
def get_catalog():
    return catalog.public_catalog()


@app.get("/api/geo/countries")
def geo_countries():
    return phones.countries()


@app.get("/api/geo/states")
def geo_states():
    return geo.states()


@app.get("/api/geo/districts")
def geo_districts(state: str = Query(..., max_length=80)):
    result = geo.districts(state)
    if not result:
        raise HTTPException(status_code=404, detail="Unknown state.")
    return result


@app.get("/api/geo/pincodes")
def geo_pincodes(state: str = Query(..., max_length=80), district: str = Query(..., max_length=80)):
    return geo.pincodes(state, district)


@app.get("/api/geo/pincode/{pincode}")
def geo_pincode(pincode: str):
    found = geo.lookup_pincode(pincode)
    if not found:
        raise HTTPException(status_code=404, detail="Pincode not found in the India Post directory.")
    return found


@app.get("/api/geo/kashmir")
def geo_kashmir():
    return geo.kashmir_overview()


@app.post("/api/auth/login")
def login(data: LoginIn):
    identifier = data.phone.strip()
    try:
        canonical_identifier = normalize_phone(identifier, data.country.upper())
    except ValueError:
        canonical_identifier = identifier.casefold()
    throttle_key = hmac.new(SECRET_KEY.encode(), canonical_identifier.casefold().encode(), hashlib.sha256).hexdigest()
    now = time.time()
    login_failed = False
    with db_conn() as conn:
        throttle = conn.execute("SELECT * FROM login_throttle WHERE identifier_hash=?", (throttle_key,)).fetchone()
        if throttle and float(throttle["locked_until"]) > now:
            wait = max(1, int(float(throttle["locked_until"]) - now))
            raise HTTPException(status_code=429, detail=f"Too many failed login attempts. Try again in about {max(1, (wait+59)//60)} minute(s).")
        row = conn.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (identifier,)).fetchone()
        if not row and canonical_identifier.startswith("+"):
            row = conn.execute("SELECT * FROM users WHERE phone_normalized=?", (canonical_identifier,)).fetchone()
        if not row or not check_password(data.password, row["password_hash"]):
            window_started = float(throttle["window_started"]) if throttle else now
            failures = int(throttle["failures"]) if throttle and now-window_started <= 900 else 0
            if now-window_started > 900: window_started = now
            failures += 1
            locked_until = now + 900 if failures >= 5 else 0
            conn.execute("INSERT INTO login_throttle(identifier_hash,failures,window_started,locked_until) VALUES(?,?,?,?) ON CONFLICT(identifier_hash) DO UPDATE SET failures=excluded.failures,window_started=excluded.window_started,locked_until=excluded.locked_until",
                         (throttle_key, failures, window_started, locked_until))
            login_failed = True
        else:
            conn.execute("DELETE FROM login_throttle WHERE identifier_hash=?", (throttle_key,))
    if login_failed:
        # Raise only after committing the failed-attempt counter. Avoid revealing whether the account exists.
        raise HTTPException(status_code=401, detail="Username/phone or password is incorrect.")
    public = user_public(row)
    return {"access_token": create_token(public["id"], public["role"]), "token_type": "bearer", "user": public}

@app.post("/api/auth/change-password")
def change_password(data: ChangePasswordIn, user=Depends(get_current_user)):
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        if not row or not check_password(data.current_password, row["password_hash"]):
            raise HTTPException(status_code=400, detail="Current password is incorrect.")
        if data.current_password == data.new_password:
            raise HTTPException(status_code=400, detail="Choose a new password different from the current password.")
        conn.execute("UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?", (hash_password(data.new_password), user["id"]))
        audit_event(conn, user["id"], "password_changed", "user", user["id"], target_user_id=user["id"], details={"changed_by":"self"})
    with db_conn() as conn:
        updated = conn.execute("SELECT must_change_password FROM users WHERE id=?", (user["id"],)).fetchone()
    return {"ok": True, "message": "Password changed successfully.", "must_change_password": bool(updated["must_change_password"])}

@app.get("/api/auth/me")
def me(user=Depends(get_current_user)):
    return user


# ---------- Business audit reports ----------
@app.get("/api/my/audit-summary")
def my_audit_summary(user=Depends(require_roles("seller", "buyer"))):
    uid, role = user["id"], user["role"]
    with db_conn() as conn:
        member = conn.execute("SELECT member_code,name,username,role,phone,district,created_at FROM users WHERE id=?", (uid,)).fetchone()
        if role == "seller":
            order_rows = conn.execute("""SELECT o.*,l.crop,l.variety,l.grade,l.district,b.name AS buyer_name,b.member_code AS buyer_member_code,
                    s.name AS seller_name,s.member_code AS seller_member_code
                    FROM orders o JOIN listings l ON l.id=o.listing_id JOIN users s ON s.id=o.seller_id
                    JOIN users b ON b.id=o.buyer_id WHERE o.seller_id=? ORDER BY o.created_at DESC""", (uid,)).fetchall()
            offer_rows = conn.execute("""SELECT o.*,l.crop,l.variety,l.grade,l.district,b.name AS counterparty_name,b.member_code AS counterparty_member_code
                    FROM offers o JOIN listings l ON l.id=o.listing_id JOIN users b ON b.id=o.buyer_id
                    WHERE l.seller_id=? ORDER BY o.created_at DESC""", (uid,)).fetchall()
            listing_rows = conn.execute("SELECT * FROM listings WHERE seller_id=? ORDER BY created_at DESC", (uid,)).fetchall()
            booking_rows = conn.execute("""SELECT b.*,s.name AS storage_name,s.district AS storage_district FROM storage_bookings b
                    JOIN storage_sites s ON s.id=b.storage_id WHERE b.seller_id=? ORDER BY b.created_at DESC""", (uid,)).fetchall()
            disputes_rows = conn.execute("""SELECT d.*,o.seller_id,o.buyer_id,l.crop,l.variety,o.quantity_kg,o.price_per_kg
                    FROM disputes d JOIN orders o ON o.id=d.order_id JOIN listings l ON l.id=o.listing_id
                    WHERE o.seller_id=? ORDER BY d.created_at DESC""", (uid,)).fetchall()
        else:
            order_rows = conn.execute("""SELECT o.*,l.crop,l.variety,l.grade,l.district,b.name AS buyer_name,b.member_code AS buyer_member_code,
                    s.name AS seller_name,s.member_code AS seller_member_code
                    FROM orders o JOIN listings l ON l.id=o.listing_id JOIN users s ON s.id=o.seller_id
                    JOIN users b ON b.id=o.buyer_id WHERE o.buyer_id=? ORDER BY o.created_at DESC""", (uid,)).fetchall()
            offer_rows = conn.execute("""SELECT o.*,l.crop,l.variety,l.grade,l.district,s.name AS counterparty_name,s.member_code AS counterparty_member_code
                    FROM offers o JOIN listings l ON l.id=o.listing_id JOIN users s ON s.id=l.seller_id
                    WHERE o.buyer_id=? ORDER BY o.created_at DESC""", (uid,)).fetchall()
            listing_rows, booking_rows = [], []
            disputes_rows = conn.execute("""SELECT d.*,o.seller_id,o.buyer_id,l.crop,l.variety,o.quantity_kg,o.price_per_kg
                    FROM disputes d JOIN orders o ON o.id=d.order_id JOIN listings l ON l.id=o.listing_id
                    WHERE d.raised_by=? ORDER BY d.created_at DESC""", (uid,)).fetchall()
        activity_rows = conn.execute("""SELECT a.*,actor.name AS actor_name,actor.member_code AS actor_member_code,
                    target.name AS target_name,target.member_code AS target_member_code
                    FROM audit_events a LEFT JOIN users actor ON actor.id=a.actor_user_id
                    LEFT JOIN users target ON target.id=a.target_user_id
                    WHERE a.actor_user_id=? OR a.target_user_id=? ORDER BY a.created_at DESC LIMIT 2000""", (uid,uid)).fetchall()
    orders = []
    for r in order_rows:
        item = dict(r)
        item["trade_value"] = round(float(r["quantity_kg"]) * float(r["price_per_kg"]), 2)
        item["counterparty_name"] = r["buyer_name"] if role == "seller" else r["seller_name"]
        item["counterparty_member_code"] = r["buyer_member_code"] if role == "seller" else r["seller_member_code"]
        orders.append(item)
    trades_value = sum(x["trade_value"] for x in orders)
    delivered = [x for x in orders if x["status"] == "Delivered"]
    delivered_value = sum(x["trade_value"] for x in delivered)
    offers = [dict(r) for r in offer_rows]
    listings = [dict(r) for r in listing_rows]
    bookings = [dict(r) for r in booking_rows]
    activity = []
    for r in activity_rows:
        x = dict(r)
        try: x["details"] = json.loads(x.pop("details_json") or "{}")
        except (ValueError, TypeError): x["details"] = {}
        activity.append(x)
    summary = {
        "orders": len(orders), "delivered_orders": len(delivered),
        "total_trade_value": round(trades_value, 2), "delivered_trade_value": round(delivered_value, 2),
        "total_quantity_kg": round(sum(float(x["quantity_kg"]) for x in orders), 2),
        "offer_count": len(offers), "accepted_offers": sum(x["status"] == "accepted" for x in offers),
        "pending_offers": sum(x["status"] == "pending" for x in offers),
        "active_listings": sum(x["status"] == "open" for x in listings), "listing_count": len(listings),
        "storage_bookings": len(bookings), "storage_estimated_cost": round(sum(float(x["estimated_cost"]) for x in bookings), 2),
        "disputes": len(disputes_rows), "open_disputes": sum(x["status"] == "open" for x in disputes_rows),
        "trade_value_label": "Agreed order value; payment is not verified by this prototype"
    }
    return {"member": dict(member), "summary": summary, "trades": orders, "offers": offers,
            "listings": listings, "storage_bookings": bookings, "disputes": [dict(r) for r in disputes_rows], "activity": activity}

@app.get("/api/my/audit-report.csv")
def download_audit_report(user=Depends(require_roles("seller", "buyer"))):
    report = my_audit_summary(user)
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    def write_row(values=()):
        safe = []
        for value in values:
            if isinstance(value, str):
                cell = value
                if cell.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                    cell = "'" + cell
                safe.append(cell)
            else:
                safe.append(value)
        writer.writerow(safe)
    write_row(["Baagh Business Audit Report"])
    write_row(["Member ID", report["member"]["member_code"]])
    write_row(["Name", report["member"]["name"]])
    write_row(["Role", report["member"]["role"]])
    write_row(["Generated at (UTC)", now_iso()])
    write_row(["Note", report["summary"]["trade_value_label"]])
    write_row([])
    write_row(["Metric", "Value"])
    for key, value in report["summary"].items(): write_row([key, value])
    write_row([])
    write_row(["Trade Ledger"])
    write_row(["Order ID", "Date", "Crop", "Variety", "Quantity kg", "Price per kg INR", "Trade value INR", "Status", "Payment status", "Counterparty", "Counterparty member ID"])
    for t in report["trades"]:
        write_row([t["id"],t["created_at"],t["crop"],t["variety"],t["quantity_kg"],t["price_per_kg"],t["trade_value"],t["status"],t["payment_status"],t["counterparty_name"],t["counterparty_member_code"]])
    write_row([])
    write_row(["Offer Ledger"])
    write_row(["Offer ID", "Date", "Crop", "Variety", "Offer price per kg INR", "Quantity kg", "Calculated offer value INR", "Status", "Counterparty", "Counterparty member ID"])
    for o in report["offers"]:
        write_row([o["id"],o["created_at"],o["crop"],o["variety"],o["offered_price"],o["quantity_kg"],round(float(o["offered_price"])*float(o["quantity_kg"]),2),o["status"],o.get("counterparty_name",""),o.get("counterparty_member_code","")])
    write_row([])
    write_row(["Listings Ledger"])
    write_row(["Listing ID", "Date", "Crop", "Variety", "Grade", "Original quantity kg", "Available quantity kg", "Price per kg INR", "Status", "Inspection status"])
    for l in report["listings"]:
        write_row([l["id"],l["created_at"],l["crop"],l["variety"],l["grade"],l["quantity_kg"],l["available_kg"],l["price_per_kg"],l["status"],l["inspection_status"]])
    write_row([])
    write_row(["Storage Booking Ledger"])
    write_row(["Booking ID", "Date", "Storage", "District", "Quantity kg", "Months", "Estimated cost INR", "Status"])
    for b in report["storage_bookings"]:
        write_row([b["id"],b["created_at"],b["storage_name"],b["storage_district"],b["quantity_kg"],b["months"],b["estimated_cost"],b["status"]])
    write_row([])
    write_row(["Dispute Ledger"])
    write_row(["Dispute ID", "Order ID", "Date", "Crop", "Variety", "Reason", "Received grade", "Status", "Resolution"])
    for d in report["disputes"]:
        write_row([d["id"],d["order_id"],d["created_at"],d["crop"],d["variety"],d["reason"],d["received_grade"],d["status"],d["resolution"]])
    write_row([])
    write_row(["Activity Audit Trail"])
    write_row(["Event ID", "Date", "Event", "Entity", "Entity ID", "Actor", "Target", "Details JSON"])
    for a in report["activity"]:
        write_row([a["id"],a["created_at"],a["event_type"],a["entity_type"],a["entity_id"],a.get("actor_name"),a.get("target_name"),json.dumps(a.get("details",{}),ensure_ascii=False,sort_keys=True)])
    filename = f"baagh-audit-{report['member']['member_code'].lower()}.csv"
    return Response(content="\ufeff"+out.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ---------- Marketplace ----------
@app.get("/api/summary")
def summary():
    with db_conn() as conn:
        return {
            "open_listings": conn.execute("SELECT COUNT(*) FROM listings WHERE status='open'").fetchone()[0],
            "verified_members": conn.execute("SELECT COUNT(*) FROM users WHERE verified=1 AND role!='admin'").fetchone()[0],
            "crops": len(catalog.CROPS),
            "districts": conn.execute("SELECT COUNT(DISTINCT district) FROM listings WHERE status='open'").fetchone()[0],
        }

@app.get("/api/listings")
def list_listings(crop: str = Query("All"), district: str = Query("All"), form: str = Query("All"), search: str = Query("", max_length=100), limit: int = Query(100, ge=1, le=300)):
    sql = """SELECT l.*, u.name AS seller_name, u.verified AS seller_verified FROM listings l JOIN users u ON u.id=l.seller_id WHERE l.status='open' AND u.verified=1"""
    args = []
    if crop != "All": sql += " AND l.crop=?"; args.append(crop)
    if district != "All": sql += " AND l.district=?"; args.append(district)
    if form != "All": sql += " AND l.product_form=?"; args.append(form)
    if search.strip():
        q = f"%{search.strip()}%"
        sql += " AND (l.crop LIKE ? OR l.variety LIKE ? OR l.district LIKE ? OR l.description LIKE ? OR l.product_form LIKE ?)"
        args.extend([q,q,q,q,q])
    sql += " ORDER BY l.created_at DESC LIMIT ?"; args.append(limit)
    with db_conn() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(r) | {"seller_verified": bool(r["seller_verified"])} for r in rows]

@app.get("/api/listings/{listing_id}")
def get_listing(listing_id: int):
    with db_conn() as conn:
        row = conn.execute("SELECT l.*,u.name AS seller_name,u.district AS seller_district,u.verified AS seller_verified FROM listings l JOIN users u ON u.id=l.seller_id WHERE l.id=?", (listing_id,)).fetchone()
    if not row: raise HTTPException(status_code=404, detail="Listing not found.")
    return dict(row) | {"seller_verified": bool(row["seller_verified"])}

@app.post("/api/listings", status_code=201)
def create_listing(data: ListingIn, user=Depends(require_roles("seller"))):
    if not user["verified"]: raise HTTPException(status_code=403, detail="Your seller account has been suspended. Contact the Baagh administrator.")
    crop = catalog.get_crop(data.crop)
    if not crop: raise HTTPException(status_code=422, detail="Choose a produce type from the list: " + ", ".join(catalog.crop_names()) + ".")
    form = data.product_form.strip() or catalog.default_form(data.crop)
    info = catalog.form_info(data.crop, form)
    if not info: raise HTTPException(status_code=422, detail=f"'{form}' is not a valid form for {data.crop}. Choose one of: " + ", ".join(crop["forms"]) + ".")
    district = next((d for d in geo.jk_districts() if d.casefold() == data.district.strip().casefold()), None)
    if not district: raise HTTPException(status_code=422, detail="Choose the Jammu & Kashmir district where this produce was grown.")
    with db_conn() as conn:
        cur = conn.execute("INSERT INTO listings(seller_id,crop,variety,grade,quantity_kg,available_kg,price_per_kg,district,description,status,inspection_status,created_at,product_form,grade_label,hsn_code,gst_rate) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (user["id"],data.crop,data.variety.strip(),data.grade,data.quantity_kg,data.quantity_kg,data.price_per_kg,district,data.description.strip(),"open","unverified",now_iso(),
                            form,catalog.grade_label_for(data.crop, data.grade),info["hsn"],info["gst_rate"]))
        row = conn.execute("SELECT * FROM listings WHERE id=?",(cur.lastrowid,)).fetchone()
        audit_event(conn, user["id"], "listing_created", "listing", cur.lastrowid, target_user_id=user["id"],
                    details={"crop":data.crop,"form":form,"variety":data.variety.strip(),"quantity_kg":data.quantity_kg,"price_per_kg":data.price_per_kg,"hsn":info["hsn"],"gst_rate":info["gst_rate"]})
    return dict(row)

@app.get("/api/my/listings")
def my_listings(user=Depends(require_roles("seller","admin"))):
    with db_conn() as conn:
        rows = conn.execute("SELECT l.*, (SELECT COUNT(*) FROM offers o WHERE o.listing_id=l.id) AS offer_count FROM listings l WHERE (?='admin' OR seller_id=?) ORDER BY l.created_at DESC", (user["role"],user["id"])).fetchall()
    return [dict(r) for r in rows]

@app.delete("/api/listings/{listing_id}")
def delete_listing(listing_id: int, user=Depends(get_current_user)):
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM listings WHERE id=?", (listing_id,)).fetchone()
        if not row: raise HTTPException(status_code=404, detail="Listing not found.")
        if user["role"] != "admin" and (user["role"] != "seller" or row["seller_id"] != user["id"]): raise HTTPException(status_code=403, detail="You cannot remove this listing.")
        if row["status"] != "open": raise HTTPException(status_code=409, detail="Only open listings can be removed.")
        conn.execute("UPDATE listings SET status='removed' WHERE id=?", (listing_id,))
        audit_event(conn, user["id"], "listing_removed", "listing", listing_id, target_user_id=row["seller_id"], details={"variety":row["variety"]})
    return {"ok": True}

@app.post("/api/listings/{listing_id}/offers", status_code=201)
def create_offer(listing_id: int, data: OfferIn, user=Depends(require_roles("buyer"))):
    if not user["verified"]: raise HTTPException(status_code=403, detail="Your buyer account has been suspended. Contact the Baagh administrator.")
    with db_conn() as conn:
        listing = conn.execute("SELECT l.* FROM listings l JOIN users seller ON seller.id=l.seller_id WHERE l.id=? AND l.status='open' AND seller.verified=1", (listing_id,)).fetchone()
        if not listing: raise HTTPException(status_code=404, detail="This listing is no longer available.")
        if listing["seller_id"] == user["id"]: raise HTTPException(status_code=400, detail="You cannot make an offer on your own listing.")
        if data.quantity_kg > listing["available_kg"]: raise HTTPException(status_code=400, detail="Offer quantity exceeds available stock.")
        cur = conn.execute("INSERT INTO offers(listing_id,buyer_id,offered_price,quantity_kg,status,created_at) VALUES(?,?,?,?,?,?)", (listing_id,user["id"],data.offered_price,data.quantity_kg,"pending",now_iso()))
        audit_event(conn, user["id"], "offer_created", "offer", cur.lastrowid, target_user_id=listing["seller_id"],
                    details={"listing_id":listing_id,"offered_price":data.offered_price,"quantity_kg":data.quantity_kg})
        return dict(conn.execute("SELECT * FROM offers WHERE id=?", (cur.lastrowid,)).fetchone())

@app.get("/api/my/offers")
def my_offers(user=Depends(get_current_user)):
    with db_conn() as conn:
        if user["role"] == "buyer":
            rows = conn.execute("SELECT o.*,l.crop,l.variety,l.grade,l.district,l.seller_id,u.name AS seller_name FROM offers o JOIN listings l ON l.id=o.listing_id JOIN users u ON u.id=l.seller_id WHERE o.buyer_id=? ORDER BY o.created_at DESC", (user["id"],)).fetchall()
        elif user["role"] == "seller":
            rows = conn.execute("SELECT o.*,l.crop,l.variety,l.grade,l.district,l.seller_id,u.name AS buyer_name FROM offers o JOIN listings l ON l.id=o.listing_id JOIN users u ON u.id=o.buyer_id WHERE l.seller_id=? ORDER BY o.created_at DESC", (user["id"],)).fetchall()
        else:
            rows = conn.execute("SELECT o.*,l.crop,l.variety,l.grade,l.district,l.seller_id,u.name AS buyer_name FROM offers o JOIN listings l ON l.id=o.listing_id JOIN users u ON u.id=o.buyer_id ORDER BY o.created_at DESC").fetchall()
    return [dict(r) for r in rows]

@app.post("/api/offers/{offer_id}/decision")
def decide_offer(offer_id: int, decision: str = Query(..., pattern="^(accept|decline)$"), user=Depends(require_roles("seller"))):
    if not user["verified"]: raise HTTPException(status_code=403, detail="Your seller account has been suspended. Contact the Baagh administrator.")
    with db_conn() as conn:
        offer = conn.execute("SELECT o.*,l.seller_id,l.id AS listing_real_id,l.available_kg,l.status AS listing_status,l.crop AS l_crop,l.product_form AS l_form,l.hsn_code AS l_hsn,l.gst_rate AS l_rate,b.verified AS buyer_verified FROM offers o JOIN listings l ON l.id=o.listing_id JOIN users b ON b.id=o.buyer_id WHERE o.id=?", (offer_id,)).fetchone()
        if not offer: raise HTTPException(status_code=404, detail="Offer not found.")
        if offer["seller_id"] != user["id"]: raise HTTPException(status_code=403, detail="This offer does not belong to your listing.")
        if offer["status"] != "pending": raise HTTPException(status_code=409, detail="This offer has already been handled.")
        if decision == "decline":
            conn.execute("UPDATE offers SET status='declined' WHERE id=?", (offer_id,))
            audit_event(conn, user["id"], "offer_declined", "offer", offer_id, target_user_id=offer["buyer_id"], details={"listing_id":offer["listing_real_id"]})
            return {"ok": True, "status": "declined"}
        if not offer["buyer_verified"]:
            raise HTTPException(status_code=409, detail="The buyer account is no longer verified; the offer cannot be accepted.")
        if offer["listing_status"] != "open" or offer["quantity_kg"] > offer["available_kg"]:
            raise HTTPException(status_code=409, detail="There is not enough stock to accept this offer.")
        conn.execute("UPDATE offers SET status='accepted' WHERE id=?", (offer_id,))
        conn.execute("UPDATE offers SET status='declined' WHERE listing_id=? AND id!=? AND status='pending'", (offer["listing_real_id"],offer_id))
        remaining = offer["available_kg"] - offer["quantity_kg"]
        conn.execute("UPDATE listings SET available_kg=?,status=? WHERE id=?", (remaining, "sold" if remaining <= 0 else "open", offer["listing_real_id"]))
        fallback = catalog.form_info(offer["l_crop"], offer["l_form"] or "") or (catalog.form_info(offer["l_crop"], catalog.default_form(offer["l_crop"])) if catalog.get_crop(offer["l_crop"]) else {}) or {}
        cur = conn.execute("INSERT INTO orders(listing_id,seller_id,buyer_id,offer_id,quantity_kg,price_per_kg,status,progress,payment_status,created_at,hsn_code,gst_rate) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                           (offer["listing_real_id"],user["id"],offer["buyer_id"],offer_id,offer["quantity_kg"],offer["offered_price"],"Accepted",0,"not_integrated",now_iso(),
                            offer["l_hsn"] or fallback.get("hsn"), offer["l_rate"] if offer["l_rate"] is not None else fallback.get("gst_rate", 0)))
        trade_value = round(float(offer["quantity_kg"]) * float(offer["offered_price"]), 2)
        audit_event(conn, user["id"], "offer_accepted_order_created", "order", cur.lastrowid, target_user_id=offer["buyer_id"],
                    details={"offer_id":offer_id,"listing_id":offer["listing_real_id"],"quantity_kg":offer["quantity_kg"],"price_per_kg":offer["offered_price"],"agreed_trade_value":trade_value})
        return {"ok": True, "status": "accepted", "order_id": cur.lastrowid}

# ---------- Orders / tracking / disputes ----------
@app.get("/api/orders")
def list_orders(user=Depends(get_current_user)):
    with db_conn() as conn:
        if user["role"] == "admin":
            rows = conn.execute("SELECT o.*,l.crop,l.variety,s.name AS seller_name,b.name AS buyer_name FROM orders o JOIN listings l ON l.id=o.listing_id JOIN users s ON s.id=o.seller_id JOIN users b ON b.id=o.buyer_id ORDER BY o.created_at DESC").fetchall()
        elif user["role"] == "inspector":
            return []
        else:
            rows = conn.execute("SELECT o.*,l.crop,l.variety,s.name AS seller_name,b.name AS buyer_name FROM orders o JOIN listings l ON l.id=o.listing_id JOIN users s ON s.id=o.seller_id JOIN users b ON b.id=o.buyer_id WHERE o.seller_id=? OR o.buyer_id=? ORDER BY o.created_at DESC", (user["id"],user["id"])).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/orders/{order_id}/dispatch")
def dispatch_order(order_id: int, user=Depends(get_current_user)):
    with db_conn() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?",(order_id,)).fetchone()
        if not order: raise HTTPException(status_code=404, detail="Order not found.")
        if user["role"] not in ("admin", "seller") or (user["role"] == "seller" and order["seller_id"] != user["id"]): raise HTTPException(status_code=403, detail="You cannot dispatch this order.")
        if order["status"] not in ("Accepted", "In transit"): raise HTTPException(status_code=409, detail="This order cannot be dispatched from its current state.")
        conn.execute("UPDATE orders SET status='In transit',progress=CASE WHEN progress<0.05 THEN 0.05 ELSE progress END,dispatched_at=COALESCE(dispatched_at,?) WHERE id=?",(now_iso(),order_id))
        audit_event(conn, user["id"], "order_dispatched", "order", order_id, target_user_id=order["buyer_id"], details={"seller_id":order["seller_id"],"buyer_id":order["buyer_id"]})
        if user["role"] == "admin": audit_event(conn, user["id"], "order_dispatched_admin", "order", order_id, target_user_id=order["seller_id"], details={"buyer_id":order["buyer_id"]})
    return {"ok": True, "status": "In transit", "note": "Demo status update; live GPS requires a driver app or tracker integration."}

@app.post("/api/orders/{order_id}/deliver")
def deliver_order(order_id: int, user=Depends(get_current_user)):
    with db_conn() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?",(order_id,)).fetchone()
        if not order: raise HTTPException(status_code=404, detail="Order not found.")
        if user["role"] not in ("admin", "seller") or (user["role"] == "seller" and order["seller_id"] != user["id"]): raise HTTPException(status_code=403, detail="You cannot update this order.")
        if order["status"] != "In transit": raise HTTPException(status_code=409, detail="Only in-transit orders can be marked delivered.")
        conn.execute("UPDATE orders SET status='Delivered',progress=1,delivered_at=?,dispatched_at=COALESCE(dispatched_at,?) WHERE id=?",(now_iso(),now_iso(),order_id))
        audit_event(conn, user["id"], "order_delivered", "order", order_id, target_user_id=order["buyer_id"], details={"seller_id":order["seller_id"],"buyer_id":order["buyer_id"],"trade_value":round(float(order["quantity_kg"])*float(order["price_per_kg"]),2)})
        if user["role"] == "admin": audit_event(conn, user["id"], "order_delivered_admin", "order", order_id, target_user_id=order["seller_id"], details={"buyer_id":order["buyer_id"]})
    return {"ok": True, "status": "Delivered"}

@app.post("/api/orders/{order_id}/disputes", status_code=201)
def create_dispute(order_id: int, data: DisputeIn, user=Depends(require_roles("buyer"))):
    with db_conn() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?",(order_id,)).fetchone()
        if not order: raise HTTPException(status_code=404, detail="Order not found.")
        if order["buyer_id"] != user["id"]: raise HTTPException(status_code=403, detail="Only the buyer can raise a dispute for this order.")
        if order["status"] != "Delivered": raise HTTPException(status_code=409, detail="A dispute can be raised after delivery in this demo.")
        cur = conn.execute("INSERT INTO disputes(order_id,raised_by,received_grade,reason,status,created_at) VALUES(?,?,?,?,?,?)",(order_id,user["id"],data.received_grade,data.reason.strip(),"open",now_iso()))
        conn.execute("UPDATE orders SET payment_status='disputed' WHERE id=?",(order_id,))
        audit_event(conn, user["id"], "dispute_raised", "dispute", cur.lastrowid, target_user_id=order["seller_id"], details={"order_id":order_id,"reason":data.reason.strip()})
        return dict(conn.execute("SELECT * FROM disputes WHERE id=?",(cur.lastrowid,)).fetchone())

@app.get("/api/disputes")
def list_disputes(user=Depends(get_current_user)):
    with db_conn() as conn:
        if user["role"] == "admin":
            rows = conn.execute("SELECT d.*,o.seller_id,o.buyer_id,o.price_per_kg,o.quantity_kg,l.crop,l.variety,b.name AS buyer_name,s.name AS seller_name FROM disputes d JOIN orders o ON o.id=d.order_id JOIN listings l ON l.id=o.listing_id JOIN users b ON b.id=o.buyer_id JOIN users s ON s.id=o.seller_id ORDER BY d.created_at DESC").fetchall()
        elif user["role"] == "buyer":
            rows = conn.execute("SELECT d.*,o.seller_id,o.buyer_id,o.price_per_kg,o.quantity_kg,l.crop,l.variety,b.name AS buyer_name,s.name AS seller_name FROM disputes d JOIN orders o ON o.id=d.order_id JOIN listings l ON l.id=o.listing_id JOIN users b ON b.id=o.buyer_id JOIN users s ON s.id=o.seller_id WHERE d.raised_by=? ORDER BY d.created_at DESC", (user["id"],)).fetchall()
        elif user["role"] == "seller":
            rows = conn.execute("SELECT d.*,o.seller_id,o.buyer_id,o.price_per_kg,o.quantity_kg,l.crop,l.variety,b.name AS buyer_name,s.name AS seller_name FROM disputes d JOIN orders o ON o.id=d.order_id JOIN listings l ON l.id=o.listing_id JOIN users b ON b.id=o.buyer_id JOIN users s ON s.id=o.seller_id WHERE o.seller_id=? ORDER BY d.created_at DESC", (user["id"],)).fetchall()
        else: rows = []
    return [dict(r) for r in rows]

@app.post("/api/disputes/{dispute_id}/resolve")
def resolve_dispute(dispute_id: int, resolution: str = Query(..., pattern="^(price_adjustment|dismiss)$"), user=Depends(require_roles("admin"))):
    with db_conn() as conn:
        d = conn.execute("SELECT * FROM disputes WHERE id=?",(dispute_id,)).fetchone()
        if not d: raise HTTPException(status_code=404, detail="Dispute not found.")
        if d["status"] != "open": raise HTTPException(status_code=409, detail="This dispute has already been resolved.")
        label = "10% price adjustment recommended" if resolution == "price_adjustment" else "Dispute dismissed"
        conn.execute("UPDATE disputes SET status='resolved',resolution=? WHERE id=?",(label,dispute_id))
        order = conn.execute("SELECT seller_id,buyer_id FROM orders WHERE id=?",(d["order_id"],)).fetchone()
        if resolution == "price_adjustment": conn.execute("UPDATE orders SET payment_status='adjustment_recommended' WHERE id=?",(d["order_id"],))
        else: conn.execute("UPDATE orders SET payment_status='not_integrated' WHERE id=?",(d["order_id"],))
        audit_event(conn, user["id"], "dispute_resolved", "dispute", dispute_id, target_user_id=order["buyer_id"], details={"resolution":label,"order_id":d["order_id"]})
        audit_event(conn, user["id"], "dispute_resolution_notice", "dispute", dispute_id, target_user_id=order["seller_id"], details={"resolution":label,"order_id":d["order_id"]})
    return {"ok": True, "resolution": label}

# ---------- Market rates / storage ----------
@app.get("/api/rates")
def get_rates():
    with db_conn() as conn: rows = conn.execute("SELECT * FROM market_rates ORDER BY crop,mandi").fetchall()
    return [dict(r) for r in rows]

@app.post("/api/rates", status_code=201)
def upsert_rate(data: RateIn, user=Depends(require_roles("admin"))):
    with db_conn() as conn:
        conn.execute("INSERT INTO market_rates(crop,mandi,price_per_kg,updated_at) VALUES(?,?,?,?) ON CONFLICT(crop,mandi) DO UPDATE SET price_per_kg=excluded.price_per_kg,updated_at=excluded.updated_at", (data.crop.strip(),data.mandi.strip(),data.price_per_kg,now_iso()))
        row = conn.execute("SELECT * FROM market_rates WHERE crop=? AND mandi=?",(data.crop.strip(),data.mandi.strip())).fetchone()
        audit_event(conn, user["id"], "market_rate_updated", "market_rate", row["id"], details={"crop":data.crop.strip(),"mandi":data.mandi.strip(),"price_per_kg":data.price_per_kg})
    return dict(row)

@app.get("/api/storage")
def get_storage():
    with db_conn() as conn:
        rows = conn.execute("SELECT s.*, (s.capacity_tonnes-s.occupied_tonnes) AS free_tonnes FROM storage_sites s ORDER BY district").fetchall()
    return [dict(r) for r in rows]

@app.post("/api/storage/bookings", status_code=201)
def book_storage(data: BookingIn, user=Depends(require_roles("seller"))):
    if not user["verified"]: raise HTTPException(status_code=403, detail="Your seller account has been suspended. Contact the Baagh administrator.")
    with db_conn() as conn:
        site = conn.execute("SELECT * FROM storage_sites WHERE id=?",(data.storage_id,)).fetchone()
        if not site: raise HTTPException(status_code=404, detail="Storage site not found.")
        if data.quantity_kg / 1000 > site["capacity_tonnes"] - site["occupied_tonnes"]: raise HTTPException(status_code=409, detail="There is not enough free capacity for this booking.")
        cost = data.quantity_kg * data.months * site["rate_per_kg_month"]
        cur = conn.execute("INSERT INTO storage_bookings(storage_id,seller_id,quantity_kg,months,estimated_cost,status,created_at) VALUES(?,?,?,?,?,?,?)",(data.storage_id,user["id"],data.quantity_kg,data.months,cost,"pending",now_iso()))
        audit_event(conn, user["id"], "storage_booking_requested", "storage_booking", cur.lastrowid, target_user_id=user["id"], details={"storage_id":data.storage_id,"quantity_kg":data.quantity_kg,"months":data.months,"estimated_cost":cost})
        return dict(conn.execute("SELECT * FROM storage_bookings WHERE id=?",(cur.lastrowid,)).fetchone()) | {"storage_name":site["name"],"district":site["district"]}

@app.get("/api/storage/bookings")
def get_bookings(user=Depends(get_current_user)):
    with db_conn() as conn:
        sql = "SELECT b.*,s.name AS storage_name,s.district,u.name AS seller_name FROM storage_bookings b JOIN storage_sites s ON s.id=b.storage_id JOIN users u ON u.id=b.seller_id"
        args=[]
        if user["role"] == "seller": sql += " WHERE b.seller_id=?"; args=[user["id"]]
        elif user["role"] not in ("admin",): raise HTTPException(status_code=403, detail="You cannot view storage bookings.")
        sql += " ORDER BY b.created_at DESC"
        rows=conn.execute(sql,args).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/storage/bookings/{booking_id}/decision")
def decide_booking(booking_id: int, decision: str = Query(..., pattern="^(approve|reject)$"), user=Depends(require_roles("admin"))):
    with db_conn() as conn:
        booking=conn.execute("SELECT * FROM storage_bookings WHERE id=?",(booking_id,)).fetchone()
        if not booking: raise HTTPException(status_code=404, detail="Booking not found.")
        if booking["status"] != "pending": raise HTTPException(status_code=409, detail="Booking already processed.")
        if decision == "approve":
            site=conn.execute("SELECT * FROM storage_sites WHERE id=?",(booking["storage_id"],)).fetchone()
            if booking["quantity_kg"]/1000 > site["capacity_tonnes"]-site["occupied_tonnes"]: raise HTTPException(status_code=409, detail="Not enough storage capacity remains.")
            conn.execute("UPDATE storage_sites SET occupied_tonnes=occupied_tonnes+? WHERE id=?",(booking["quantity_kg"]/1000,booking["storage_id"]))
            status="approved"
        else: status="rejected"
        conn.execute("UPDATE storage_bookings SET status=? WHERE id=?",(status,booking_id))
        audit_event(conn, user["id"], "storage_booking_"+status, "storage_booking", booking_id, target_user_id=booking["seller_id"], details={"quantity_kg":booking["quantity_kg"],"estimated_cost":booking["estimated_cost"]})
    return {"ok":True,"status":status}

# ---------- Listing inspection ----------
@app.get("/api/inspections")
def inspection_queue(user=Depends(require_roles("inspector", "admin"))):
    with db_conn() as conn:
        rows = conn.execute("SELECT l.*,u.name AS seller_name FROM listings l JOIN users u ON u.id=l.seller_id WHERE l.status!='removed' ORDER BY CASE WHEN l.inspection_status='inspected' THEN 1 ELSE 0 END, l.created_at DESC").fetchall()
    return [dict(r) for r in rows]

@app.post("/api/inspections/{listing_id}")
def update_inspection(listing_id: int, status: str = Query(..., pattern="^(inspected|unverified)$"), user=Depends(require_roles("inspector", "admin"))):
    with db_conn() as conn:
        row = conn.execute("SELECT id,seller_id,variety FROM listings WHERE id=? AND status!='removed'", (listing_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Listing not found.")
        conn.execute("UPDATE listings SET inspection_status=? WHERE id=?", (status, listing_id))
        audit_event(conn, user["id"], "listing_inspection_updated", "listing", listing_id, target_user_id=row["seller_id"], details={"status":status,"variety":row["variety"]})
    return {"ok": True, "listing_id": listing_id, "inspection_status": status}

# ---------- Admin ----------
@app.get("/api/admin/overview")
def admin_overview(user=Depends(require_roles("admin"))):
    with db_conn() as conn:
        total_users=conn.execute("SELECT COUNT(*) FROM users WHERE role!='admin'").fetchone()[0]
        pending_users=conn.execute("SELECT COUNT(*) FROM users WHERE verified=0 AND role IN ('buyer','seller')").fetchone()[0]
        open_listings=conn.execute("SELECT COUNT(*) FROM listings WHERE status='open'").fetchone()[0]
        pending_offers=conn.execute("SELECT COUNT(*) FROM offers WHERE status='pending'").fetchone()[0]
        order_count=conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        open_disputes=conn.execute("SELECT COUNT(*) FROM disputes WHERE status='open'").fetchone()[0]
        users=conn.execute("SELECT id,name,phone,district,role,verified,created_at,username,member_code,country,state,pincode,gstin FROM users ORDER BY created_at DESC").fetchall()
        listings=conn.execute("SELECT l.*,u.name AS seller_name FROM listings l JOIN users u ON u.id=l.seller_id ORDER BY l.created_at DESC").fetchall()
        offers=conn.execute("SELECT o.*,l.crop,l.variety,l.grade,u.name AS buyer_name,s.name AS seller_name FROM offers o JOIN listings l ON l.id=o.listing_id JOIN users u ON u.id=o.buyer_id JOIN users s ON s.id=l.seller_id ORDER BY o.created_at DESC").fetchall()
    return {"stats":{"users":total_users,"pending_users":pending_users,"open_listings":open_listings,"pending_offers":pending_offers,"orders":order_count,"open_disputes":open_disputes},"users":[dict(r)|{"verified":bool(r["verified"])} for r in users],"listings":[dict(r) for r in listings],"offers":[dict(r) for r in offers]}

@app.post("/api/admin/users/{user_id}/verify")
def set_member_status(user_id: int, verified: bool = Query(True), user=Depends(require_roles("admin"))):
    """Suspend (verified=false) or reinstate (verified=true) a member. New members are verified automatically by phone OTP."""
    with db_conn() as conn:
        row=conn.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
        if not row: raise HTTPException(status_code=404, detail="User not found.")
        if row["role"] in ("admin",): raise HTTPException(status_code=400, detail="Admin accounts cannot be suspended here.")
        conn.execute("UPDATE users SET verified=? WHERE id=?",(1 if verified else 0,user_id))
        audit_event(conn, user["id"], "member_reinstated" if verified else "member_suspended", "user", user_id, target_user_id=user_id, details={"member_code":row["member_code"]})
    return {"ok":True,"verified":bool(verified)}

# ---------- Buyer directory ----------
@app.get("/api/buyers")
def buyer_directory(state: str = Query("All", max_length=80), district: str = Query("All", max_length=80), pincode: str = Query("", max_length=10),
                    search: str = Query("", max_length=80), user=Depends(require_roles("seller","admin"))):
    sql = "SELECT id,member_code,name,country,state,district,pincode,gstin,created_at FROM users WHERE role='buyer' AND verified=1"
    args=[]
    if state != "All": sql += " AND state=?"; args.append(state)
    if district != "All": sql += " AND district=?"; args.append(district)
    if pincode.strip(): sql += " AND pincode=?"; args.append(pincode.strip())
    if search.strip(): sql += " AND name LIKE ?"; args.append(f"%{search.strip()}%")
    sql += " ORDER BY state,district,name LIMIT 500"
    with db_conn() as conn: rows=conn.execute(sql,args).fetchall()
    return [{"member_code":r["member_code"],"name":r["name"],"country":r["country"] or "IN","state":r["state"] or "","district":r["district"],"pincode":r["pincode"] or "",
             "gst_registered":bool(r["gstin"]),"member_since":(r["created_at"] or "")[:10]} for r in rows]

# ---------- GST / Tally reports ----------
def _fy_range(fy: str):
    if fy.lower() == "all": return None, None, "All"
    try: start, end = gst.fy_bounds(fy)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    return start, end, fy

@app.get("/api/my/gst-summary")
def gst_summary(fy: str = Query("current", max_length=10), user=Depends(require_roles("seller","buyer"))):
    if fy == "current": fy = gst.fy_for_date(datetime.now(gst.IST).date())
    start, end, label = _fy_range(fy)
    with db_conn() as conn:
        invoices = reports.collect_invoices(conn, user, start, end)
        years = reports.financial_years(conn, user)
    summary = reports.summarize(invoices)
    return {"fy": label, "financial_years": years, "summary": summary, "gstin": user.get("gstin",""), "note": reports.DISCLAIMER,
            "invoices": [{"invoice_no":i["invoice_no"],"date":i["date"].isoformat(),"party":i["seller"] if user["role"]=="buyer" else i["buyer"],"item":i["item"],"hsn":i["hsn"],
                          "taxable":float(i["tax"]["taxable"]),"gst_rate":float(i["tax"]["rate"]),"cgst":float(i["tax"]["cgst"]),"sgst":float(i["tax"]["sgst"]),"igst":float(i["tax"]["igst"]),
                          "invoice_value":float(i["tax"]["invoice_value"]),"supply_type":i["tax"]["supply_type"],"basis":i["basis"]} for i in invoices]}

@app.get("/api/my/gst-report.xlsx")
def gst_report_xlsx(fy: str = Query("current", max_length=10), user=Depends(require_roles("seller","buyer"))):
    if fy == "current": fy = gst.fy_for_date(datetime.now(gst.IST).date())
    start, end, label = _fy_range(fy)
    with db_conn() as conn:
        member = conn.execute("SELECT member_code,name,gstin,state FROM users WHERE id=?",(user["id"],)).fetchone()
        invoices = reports.collect_invoices(conn, user, start, end)
        audit_event(conn, user["id"], "gst_report_downloaded", "report", label, target_user_id=user["id"], details={"fy":label,"invoices":len(invoices)})
    data = reports.build_workbook(dict(member), user["role"], invoices, label)
    filename = f"baagh-tally-gst-{member['member_code'].lower()}-{label.replace('/','-')}.xlsx"
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@app.on_event("startup")
def on_startup():
    init_db()
