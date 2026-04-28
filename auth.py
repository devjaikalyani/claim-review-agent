"""
Authentication backend for the Rite Audit System.

Supported sign-in methods:
  - Email + Password
  - Email OTP     (SMTP — Gmail / Zoho SMTP / any SMTP)
  - Phone OTP     (Twilio — demo mode if credentials absent)
  - Google OAuth2 (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)
  - Zoho OAuth2   (ZOHO_CLIENT_ID / ZOHO_CLIENT_SECRET)

Required .env variables (all optional — app runs in demo mode without them):
  SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS / SMTP_FROM
  TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER
  GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET
  ZOHO_CLIENT_ID / ZOHO_CLIENT_SECRET
  SESSION_TTL_HOURS  (default 24)
  AUTH_DB_PATH       (default: <project root>/auth.db)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import secrets
import smtplib
import sqlite3
import string
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from dotenv import load_dotenv

# ── Paths & constants ──────────────────────────────────────────────────────────

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(Path(_ROOT).parent / ".env.shared")       # shared workspace credentials
load_dotenv(Path(_ROOT) / ".env", override=True)      # project-specific overrides
_DEFAULT_DB = os.path.join(_ROOT, "auth.db")

OTP_EXPIRY_MIN    = 10
SESSION_TTL_H     = int(os.getenv("SESSION_TTL_HOURS", "24"))
_RATE_WINDOW_MIN  = 15   # rolling window for failed attempt counting
_RATE_MAX_FAILS   = 5    # max failures before lockout


# ── Database ───────────────────────────────────────────────────────────────────

def _db(path: str | None = None) -> sqlite3.Connection:
    p = path or os.getenv("AUTH_DB_PATH", _DEFAULT_DB)
    conn = sqlite3.connect(p, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db(path: str | None = None) -> None:
    """Create auth tables if they do not exist (idempotent)."""
    with _db(path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                identifier   TEXT NOT NULL,
                attempted_at TEXT NOT NULL,
                success      INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_login_attempts
                ON login_attempts(identifier, attempted_at);

            CREATE TABLE IF NOT EXISTS users (
                id            TEXT PRIMARY KEY,
                employee_id   TEXT UNIQUE NOT NULL,
                name          TEXT NOT NULL,
                email         TEXT UNIQUE,
                phone         TEXT UNIQUE,
                password_hash TEXT,
                google_id     TEXT UNIQUE,
                zoho_id       TEXT UNIQUE,
                is_active     INTEGER DEFAULT 1,
                is_admin      INTEGER DEFAULT 0,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
                last_login    TEXT
            );

            CREATE TABLE IF NOT EXISTS otp_codes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                identifier  TEXT NOT NULL,
                code        TEXT NOT NULL,
                purpose     TEXT NOT NULL DEFAULT 'login',
                expires_at  TEXT NOT NULL,
                used        INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_otp
                ON otp_codes(identifier, purpose, used);

            CREATE TABLE IF NOT EXISTS sessions (
                token       TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL,
                expires_at  TEXT NOT NULL,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_sess_user
                ON sessions(user_id);
        """)


def migrate_auth_db(path: str | None = None) -> None:
    """Add columns introduced after initial schema (safe to call every startup)."""
    with _db(path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "is_admin" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")


def sync_admin_flags(path: str | None = None) -> None:
    """Set is_admin=1 for every employee_id listed in ADMIN_EMPLOYEE_IDS env var."""
    raw = os.getenv("ADMIN_EMPLOYEE_IDS", "").strip()
    if not raw:
        return
    ids = [e.strip() for e in raw.split(",") if e.strip()]
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    with _db(path) as conn:
        conn.execute(
            f"UPDATE users SET is_admin=1 WHERE employee_id IN ({placeholders})",
            ids,
        )


# ── User helpers ───────────────────────────────────────────────────────────────

def _safe(row: sqlite3.Row | Dict) -> Dict:
    d = dict(row)
    d.pop("password_hash", None)
    return d


def get_user(field: str, value: str, path: str | None = None) -> Optional[Dict]:
    allowed = {"id", "employee_id", "email", "phone", "google_id", "zoho_id"}
    if field not in allowed:
        raise ValueError(f"field must be one of {allowed}")
    with _db(path) as conn:
        row = conn.execute(
            f"SELECT * FROM users WHERE {field} = ? AND is_active = 1 LIMIT 1",
            (value,),
        ).fetchone()
    return _safe(row) if row else None


def update_user(
    user_id: str,
    fields: Dict[str, Any],
    path: str | None = None,
) -> Dict[str, Any]:
    """
    Update editable profile fields for *user_id*.

    Allowed fields: name, email, phone, password (plain-text — gets hashed).
    Returns {'success': True, 'user': <updated dict>} or {'error': str}.
    """
    allowed = {"name", "email", "phone", "password"}
    updates = {}

    for k, v in fields.items():
        if k not in allowed:
            continue
        if v is None:
            continue
        v = str(v).strip()
        if not v:
            continue
        if k == "password":
            salt = secrets.token_hex(16)
            hashed = hashlib.pbkdf2_hmac("sha256", v.encode(), salt.encode(), 260_000)
            updates["password_hash"] = salt + ":" + hashed.hex()
        else:
            updates[k] = v.lower() if k in ("email",) else v

    if not updates:
        return {"error": "Nothing to update."}

    # Uniqueness check for email / phone
    with _db(path) as conn:
        for col in ("email", "phone"):
            if col not in updates:
                continue
            conflict = conn.execute(
                f"SELECT id FROM users WHERE {col} = ? AND id != ? AND is_active = 1",
                (updates[col], user_id),
            ).fetchone()
            if conflict:
                return {"error": f"That {col} is already registered to another account."}

        set_clause = ", ".join(f"{col} = ?" for col in updates)
        values     = list(updates.values()) + [user_id]
        conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)

        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    return {"success": True, "user": _safe(row)} if row else {"error": "User not found."}


def _touch(user_id: str, path: str | None = None) -> None:
    with _db(path) as conn:
        conn.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (datetime.now().isoformat(), user_id),
        )


# ── Session management ─────────────────────────────────────────────────────────

def create_session(user_id: str, path: str | None = None) -> str:
    """Create a session token for user_id; return the token."""
    token = secrets.token_urlsafe(32)
    exp   = (datetime.now() + timedelta(hours=SESSION_TTL_H)).isoformat()
    with _db(path) as conn:
        # Prune old sessions for this user
        conn.execute(
            "DELETE FROM sessions WHERE user_id = ? AND expires_at < ?",
            (user_id, datetime.now().isoformat()),
        )
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, exp),
        )
    return token


def get_user_by_session(token: str | None, path: str | None = None) -> Optional[Dict]:
    """Return user dict for a valid, non-expired session token; None otherwise."""
    if not token:
        return None
    with _db(path) as conn:
        row = conn.execute(
            """SELECT u.* FROM sessions s
               JOIN users u ON u.id = s.user_id
               WHERE s.token = ? AND s.expires_at > ? AND u.is_active = 1""",
            (token, datetime.now().isoformat()),
        ).fetchone()
    return _safe(row) if row else None


def logout_session(token: str | None, path: str | None = None) -> None:
    if not token:
        return
    with _db(path) as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


# ── Rate limiting ─────────────────────────────────────────────────────────────

def _record_attempt(identifier: str, success: bool, path: str | None = None) -> None:
    """Log a login attempt (success or failure) for rate-limit tracking."""
    with _db(path) as conn:
        conn.execute(
            "INSERT INTO login_attempts (identifier, attempted_at, success) VALUES (?, ?, ?)",
            (identifier.lower(), datetime.now().isoformat(), 1 if success else 0),
        )


def _check_rate_limit(identifier: str, path: str | None = None) -> Dict[str, Any]:
    """
    Return {"locked": True, "minutes_left": N} if the identifier has hit the
    failure threshold within the rolling window, else {"locked": False}.
    """
    window_start = (datetime.now() - timedelta(minutes=_RATE_WINDOW_MIN)).isoformat()
    key = identifier.lower()
    with _db(path) as conn:
        fail_count = conn.execute(
            "SELECT COUNT(*) FROM login_attempts "
            "WHERE identifier=? AND attempted_at>? AND success=0",
            (key, window_start),
        ).fetchone()[0]

        if fail_count >= _RATE_MAX_FAILS:
            # Unlock when the oldest failure in the window ages out
            oldest = conn.execute(
                "SELECT attempted_at FROM login_attempts "
                "WHERE identifier=? AND attempted_at>? AND success=0 "
                "ORDER BY attempted_at ASC LIMIT 1",
                (key, window_start),
            ).fetchone()
            if oldest:
                unlock_at  = datetime.fromisoformat(oldest[0]) + timedelta(minutes=_RATE_WINDOW_MIN)
                mins_left  = max(1, int((unlock_at - datetime.now()).total_seconds() / 60))
                return {"locked": True, "minutes_left": mins_left}

    return {"locked": False}


# ── Password helpers ───────────────────────────────────────────────────────────

def _hash_pw(password: str, salt: str = "") -> Tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return dk.hex(), salt


def _verify_pw(password: str, stored: str) -> bool:
    """stored is 'salt:hash'."""
    try:
        salt, pw_hash = stored.split(":", 1)
    except ValueError:
        return False
    dk, _ = _hash_pw(password, salt)
    return hmac.compare_digest(dk, pw_hash)


# ── OTP helpers ────────────────────────────────────────────────────────────────

def _gen_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def _store_otp(identifier: str, code: str, purpose: str = "login",
               path: str | None = None) -> None:
    exp = (datetime.now() + timedelta(minutes=OTP_EXPIRY_MIN)).isoformat()
    with _db(path) as conn:
        conn.execute(
            "UPDATE otp_codes SET used = 1 WHERE identifier = ? AND purpose = ? AND used = 0",
            (identifier, purpose),
        )
        conn.execute(
            "INSERT INTO otp_codes (identifier, code, purpose, expires_at) VALUES (?,?,?,?)",
            (identifier, code, purpose, exp),
        )


def _verify_otp_code(identifier: str, code: str, purpose: str = "login",
                     path: str | None = None) -> Dict[str, Any]:
    """Returns {'ok': True} or {'error': str}."""
    with _db(path) as conn:
        row = conn.execute(
            """SELECT * FROM otp_codes
               WHERE identifier = ? AND code = ? AND purpose = ? AND used = 0
               ORDER BY created_at DESC LIMIT 1""",
            (identifier, code, purpose),
        ).fetchone()
    if not row:
        return {"error": "Invalid OTP. Please try again."}
    row = dict(row)
    if datetime.fromisoformat(row["expires_at"]) < datetime.now():
        return {"error": f"OTP has expired. Please request a new one."}
    with _db(path) as conn:
        conn.execute("UPDATE otp_codes SET used = 1 WHERE id = ?", (row["id"],))
    return {"ok": True}


# ── Registration ───────────────────────────────────────────────────────────────

def register_user(
    name: str,
    employee_id: str,
    email: str = "",
    phone: str = "",
    password: str = "",
    path: str | None = None,
) -> Dict[str, Any]:
    """
    Create a new user, or activate a pre-created employee account.

    Pre-created accounts (imported from HR) have employee_id + name but no
    email/phone/password.  When an employee registers with their employee_id,
    we detect that case and update the existing record with their contact
    details and password instead of rejecting them as a duplicate.

    Returns {'success': True, 'user': {...}, 'token': str}
         or {'error': str}.
    """
    name        = name.strip()
    employee_id = employee_id.strip().upper()
    email       = email.strip().lower() or None
    phone       = phone.strip() or None

    if not name:
        return {"error": "Full name is required."}
    if not employee_id:
        return {"error": "Employee ID is required."}
    if not email and not phone:
        return {"error": "At least one of email or phone is required."}

    pw_stored = None
    if password:
        dk, salt = _hash_pw(password)
        pw_stored = f"{salt}:{dk}"

    # Check if a pre-created account exists for this employee_id
    existing = get_user("employee_id", employee_id, path)
    if existing:
        has_contact = existing.get("email") or existing.get("phone")
        if has_contact:
            # Fully registered account — direct them to sign in
            return {"error": "This Employee ID is already registered. Please sign in instead."}

        # Pre-created account with no contact info — activate it
        updates: list = []
        params:  list = []
        if email:
            # Check email not taken by another account
            clash = get_user("email", email, path)
            if clash and clash["id"] != existing["id"]:
                return {"error": "This email is already used by another account."}
            updates.append("email = ?")
            params.append(email)
        if phone:
            clash = get_user("phone", phone, path)
            if clash and clash["id"] != existing["id"]:
                return {"error": "This phone number is already used by another account."}
            updates.append("phone = ?")
            params.append(phone)
        if pw_stored:
            updates.append("password_hash = ?")
            params.append(pw_stored)
        # Allow employee to correct their display name if needed
        if name and name != existing.get("name", ""):
            updates.append("name = ?")
            params.append(name)

        if updates:
            params.append(existing["id"])
            with _db(path) as conn:
                conn.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                    params,
                )

        _touch(existing["id"], path)
        user  = get_user("id", existing["id"], path)
        token = create_session(existing["id"], path)
        return {"success": True, "user": user, "token": token, "activated": True}

    # Brand-new employee not in the system yet — create a fresh record
    user_id = secrets.token_hex(16)
    try:
        with _db(path) as conn:
            conn.execute(
                """INSERT INTO users
                   (id, employee_id, name, email, phone, password_hash)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, employee_id, name, email, phone, pw_stored),
            )
    except sqlite3.IntegrityError as exc:
        msg = str(exc)
        if "email" in msg:
            return {"error": "This email is already registered."}
        if "phone" in msg:
            return {"error": "This phone number is already registered."}
        return {"error": f"Registration failed: {exc}"}

    user  = get_user("id", user_id, path)
    token = create_session(user_id, path)
    return {"success": True, "user": user, "token": token}


def complete_oauth_registration(
    name: str,
    employee_id: str,
    email: str = "",
    phone: str = "",
    google_id: str = "",
    zoho_id: str = "",
    path: str | None = None,
) -> Dict[str, Any]:
    """Finish registration for a user who just signed in via Google/Zoho."""
    name        = name.strip()
    employee_id = employee_id.strip().upper()
    email       = email.strip().lower() or None
    phone       = phone.strip() or None

    if not name or not employee_id:
        return {"error": "Full name and Employee ID are required."}

    user_id = secrets.token_hex(16)
    try:
        with _db(path) as conn:
            conn.execute(
                """INSERT INTO users
                   (id, employee_id, name, email, phone, google_id, zoho_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, employee_id, name, email, phone,
                 google_id or None, zoho_id or None),
            )
    except sqlite3.IntegrityError as exc:
        msg = str(exc)
        if "employee_id" in msg:
            return {"error": "Employee ID is already registered."}
        if "email" in msg:
            return {"error": "This email is already registered."}
        return {"error": f"Registration failed: {exc}"}

    _touch(user_id, path)
    user  = get_user("id", user_id, path)
    token = create_session(user_id, path)
    return {"success": True, "user": user, "token": token}


# ── Password login ─────────────────────────────────────────────────────────────

def login_password(identifier: str, password: str,
                   path: str | None = None) -> Dict[str, Any]:
    """
    Authenticate with email / Employee ID + password.
    Returns {'success': True, 'user': {...}, 'token': str} or {'error': str}.
    """
    identifier = identifier.strip()
    limit_check = _check_rate_limit(identifier, path)
    if limit_check.get("locked"):
        return {"error": f"Too many failed attempts. Please wait {limit_check['minutes_left']} minute(s) and try again."}

    user = get_user("email", identifier.lower(), path)
    if not user:
        user = get_user("employee_id", identifier.upper(), path)
    if not user:
        _record_attempt(identifier, success=False, path=path)
        return {"error": "No account found with that email or Employee ID."}

    stored = user.get("password_hash") or (
        # password_hash stripped by _safe — re-fetch raw row
        _raw_pw(user["id"], path)
    )
    if not stored:
        return {"error": "This account has no password set. "
                         "Please sign in with OTP, Google, or Zoho."}
    if not _verify_pw(password, stored):
        _record_attempt(identifier, success=False, path=path)
        return {"error": "Incorrect password."}

    _record_attempt(identifier, success=True, path=path)
    _touch(user["id"], path)
    token = create_session(user["id"], path)
    return {"success": True, "user": user, "token": token}


def _raw_pw(user_id: str, path: str | None = None) -> str:
    with _db(path) as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return row["password_hash"] if row else ""


# ── Email OTP ──────────────────────────────────────────────────────────────────

def send_email_otp(email: str, path: str | None = None) -> Dict[str, Any]:
    """
    Send a 6-digit OTP to *email* via SMTP.
    Returns {'success': True} or {'success': True, 'demo': True, 'otp': str}
         or {'error': str}.
    """
    email = email.strip().lower()
    if not get_user("email", email, path):
        return {"error": "No account found with this email. Please register first."}

    otp = _gen_otp()
    _store_otp(email, otp, "login", path)

    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    pw   = os.getenv("SMTP_PASS", "")
    frm  = os.getenv("SMTP_FROM", user)

    if not user or not pw:
        print(f"[AUTH DEMO] Email OTP for {email}: {otp}  (expires {OTP_EXPIRY_MIN} min)")
        return {"success": True, "demo": True, "otp": otp}

    msg             = MIMEMultipart("alternative")
    msg["Subject"]  = "Your sign-in OTP — Claim Portal"
    msg["From"]     = frm
    msg["To"]       = email
    html = f"""<html><body style="font-family:DM Sans,sans-serif;max-width:480px;
        margin:40px auto;padding:0 20px">
      <div style="border-radius:20px;background:#0c1018;padding:32px 28px">
        <p style="color:#ff6b35;font-weight:700;letter-spacing:.12em;
                  text-transform:uppercase;font-size:.82rem;margin:0 0 8px">
          Rite Water Solutions
        </p>
        <h2 style="color:#f7f4ed;margin:0 0 20px;font-size:1.5rem">
          Your sign-in code
        </h2>
        <div style="background:#1e2638;border-radius:14px;padding:20px;
                    text-align:center;font-size:2.4rem;font-weight:700;
                    letter-spacing:.35em;color:#ff8c5a;margin-bottom:20px">
          {otp}
        </div>
        <p style="color:#8fa8c8;font-size:.9rem;margin:0">
          Expires in {OTP_EXPIRY_MIN} minutes. Do not share this code.
        </p>
      </div>
    </body></html>"""
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.ehlo()
            s.starttls()
            s.login(user, pw)
            s.sendmail(frm, email, msg.as_string())
        return {"success": True}
    except Exception as exc:
        return {"error": str(exc)}


def login_email_otp(email: str, code: str,
                    path: str | None = None) -> Dict[str, Any]:
    email = email.strip().lower()
    limit_check = _check_rate_limit(email, path)
    if limit_check.get("locked"):
        return {"error": f"Too many failed attempts. Please wait {limit_check['minutes_left']} minute(s) and try again."}
    res = _verify_otp_code(email, code, "login", path)
    if res.get("error"):
        _record_attempt(email, success=False, path=path)
        return res
    user = get_user("email", email, path)
    if not user:
        return {"error": "No account found for this email."}
    _record_attempt(email, success=True, path=path)
    _touch(user["id"], path)
    token = create_session(user["id"], path)
    return {"success": True, "user": user, "token": token}


# ── Phone OTP ──────────────────────────────────────────────────────────────────

def send_phone_otp(phone: str, path: str | None = None) -> Dict[str, Any]:
    """
    Send a 6-digit OTP to *phone* via Twilio SMS.
    Falls back to demo mode if TWILIO_ACCOUNT_SID is not set.
    """
    phone = phone.strip()
    if not get_user("phone", phone, path):
        return {"error": "No account found with this phone number. Please register first."}

    otp = _gen_otp()
    _store_otp(phone, otp, "login", path)

    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    tok = os.getenv("TWILIO_AUTH_TOKEN", "")
    frm = os.getenv("TWILIO_FROM_NUMBER", "")

    if not sid or not tok:
        print(f"[AUTH DEMO] SMS OTP for {phone}: {otp}  (expires {OTP_EXPIRY_MIN} min)")
        return {"success": True, "demo": True, "otp": otp}

    try:
        from twilio.rest import Client  # type: ignore
        Client(sid, tok).messages.create(
            body=f"Claim Portal OTP: {otp} (valid {OTP_EXPIRY_MIN} min). Do not share.",
            from_=frm,
            to=phone,
        )
        return {"success": True}
    except ImportError:
        print(f"[AUTH DEMO] Twilio not installed. SMS OTP for {phone}: {otp}")
        return {"success": True, "demo": True, "otp": otp}
    except Exception as exc:
        return {"error": str(exc)}


def login_phone_otp(phone: str, code: str,
                    path: str | None = None) -> Dict[str, Any]:
    phone = phone.strip()
    limit_check = _check_rate_limit(phone, path)
    if limit_check.get("locked"):
        return {"error": f"Too many failed attempts. Please wait {limit_check['minutes_left']} minute(s) and try again."}
    res = _verify_otp_code(phone, code, "login", path)
    if res.get("error"):
        _record_attempt(phone, success=False, path=path)
        return res
    user = get_user("phone", phone, path)
    if not user:
        return {"error": "No account found for this phone number."}
    _record_attempt(phone, success=True, path=path)
    _touch(user["id"], path)
    token = create_session(user["id"], path)
    return {"success": True, "user": user, "token": token}


# ── Google OAuth2 ──────────────────────────────────────────────────────────────

def google_auth_url(redirect_uri: str, theme: str = "Dark") -> str:
    """Return the Google OAuth2 authorization URL, or '' if not configured."""
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    if not client_id:
        return ""
    safe_theme = theme if theme in ("Dark", "Light", "System") else "Dark"
    state = f"google_{safe_theme}_{secrets.token_urlsafe(12)}"
    params = urllib.parse.urlencode({
        "client_id":     client_id,
        "redirect_uri":  redirect_uri,
        "response_type": "code",
        "scope":         "openid email profile",
        "state":         state,
        "prompt":        "select_account",
    })
    return f"https://accounts.google.com/o/oauth2/v2/auth?{params}"


def google_callback(code: str, redirect_uri: str,
                    path: str | None = None) -> Dict[str, Any]:
    """Exchange Google OAuth code for a user. Returns user dict or error/new_user."""
    client_id     = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return {"error": "Google OAuth is not configured on this server."}

    # Exchange code → token
    body = urllib.parse.urlencode({
        "code":          code,
        "client_id":     client_id,
        "client_secret": client_secret,
        "redirect_uri":  redirect_uri,
        "grant_type":    "authorization_code",
    }).encode()
    try:
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token", data=body, method="POST"
        )
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=15) as r:
            token_info = json.loads(r.read())
    except Exception as exc:
        return {"error": f"Google token exchange failed: {exc}"}

    access_token = token_info.get("access_token")
    if not access_token:
        return {"error": f"Google returned no access token. Response: {token_info}"}

    # Fetch user info
    try:
        req = urllib.request.Request("https://www.googleapis.com/oauth2/v2/userinfo")
        req.add_header("Authorization", f"Bearer {access_token}")
        with urllib.request.urlopen(req, timeout=15) as r:
            ginfo = json.loads(r.read())
    except Exception as exc:
        return {"error": f"Google userinfo fetch failed: {exc}"}

    google_id = ginfo.get("id", "")
    email     = (ginfo.get("email") or "").strip().lower()
    name      = ginfo.get("name", "")

    # Find existing user
    user = (get_user("google_id", google_id, path) if google_id else None) or \
           (get_user("email",     email,     path) if email     else None)
    if user:
        if not user.get("google_id") and google_id:
            with _db(path) as conn:
                conn.execute(
                    "UPDATE users SET google_id = ? WHERE id = ?",
                    (google_id, user["id"]),
                )
        _touch(user["id"], path)
        token = create_session(user["id"], path)
        return {"success": True, "user": user, "token": token}

    # New Google user — needs employee_id to complete registration
    return {
        "success":  True,
        "new_user": True,
        "google_id": google_id,
        "email":    email,
        "name":     name,
    }


# ── Zoho OAuth2 ────────────────────────────────────────────────────────────────

def zoho_auth_url(redirect_uri: str, theme: str = "Dark") -> str:
    """Return the Zoho OAuth2 authorization URL, or '' if not configured."""
    client_id = os.getenv("ZOHO_CLIENT_ID", "")
    if not client_id:
        return ""
    safe_theme = theme if theme in ("Dark", "Light", "System") else "Dark"
    state = f"zoho_{safe_theme}_{secrets.token_urlsafe(12)}"
    # Zoho India domain; for global accounts use accounts.zoho.com
    base = os.getenv("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.in")
    params = urllib.parse.urlencode({
        "client_id":     client_id,
        "redirect_uri":  redirect_uri,
        "response_type": "code",
        "scope":         "ZohoMail.accounts.READ",
        "state":         state,
        "access_type":   "offline",
        "prompt":        "consent",
    })
    return f"{base}/oauth/v2/auth?{params}"


def zoho_callback(code: str, redirect_uri: str,
                  path: str | None = None) -> Dict[str, Any]:
    """Exchange Zoho OAuth code for a user. Returns user dict or error/new_user."""
    client_id     = os.getenv("ZOHO_CLIENT_ID", "")
    client_secret = os.getenv("ZOHO_CLIENT_SECRET", "")
    base          = os.getenv("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.in")
    if not client_id or not client_secret:
        return {"error": "Zoho OAuth is not configured on this server."}

    body = urllib.parse.urlencode({
        "code":          code,
        "client_id":     client_id,
        "client_secret": client_secret,
        "redirect_uri":  redirect_uri,
        "grant_type":    "authorization_code",
    }).encode()
    try:
        req = urllib.request.Request(
            f"{base}/oauth/v2/token", data=body, method="POST"
        )
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=15) as r:
            token_info = json.loads(r.read())
    except Exception as exc:
        return {"error": f"Zoho token exchange failed: {exc}"}

    access_token = token_info.get("access_token")
    if not access_token:
        return {"error": f"Zoho returned no access token. Response: {token_info}"}

    # Fetch Zoho account info
    zoho_api = os.getenv("ZOHO_MAIL_API", "https://mail.zoho.in")
    try:
        req = urllib.request.Request(f"{zoho_api}/api/accounts")
        req.add_header("Authorization", f"Zoho-oauthtoken {access_token}")
        with urllib.request.urlopen(req, timeout=15) as r:
            zdata = json.loads(r.read())
    except Exception as exc:
        return {"error": f"Zoho account info fetch failed: {exc}"}

    accs = zdata.get("data", [])
    if not accs:
        return {"error": "No Zoho mail accounts found for this user."}

    acc       = accs[0]
    zoho_id   = str(acc.get("accountId", ""))
    name      = acc.get("displayName", "")

    # emailAddress can be a string, a list of strings, or a list of dicts
    # Zoho API v2 returns list of dicts: [{"mailId": "x@y.z", "isPrimary": true}, ...]
    email_raw = acc.get("emailAddress") or ""
    if isinstance(email_raw, list):
        if email_raw and isinstance(email_raw[0], dict):
            # list of dicts — prefer primary, fall back to first
            primary = next((e for e in email_raw if e.get("isPrimary")), email_raw[0])
            email = (primary.get("mailId") or primary.get("mail") or "").strip().lower()
        else:
            email = (email_raw[0] if email_raw else "").strip().lower()
    else:
        email = email_raw.strip().lower()

    user = (get_user("zoho_id", zoho_id, path) if zoho_id else None) or \
           (get_user("email",   email,   path) if email   else None)
    if user:
        if not user.get("zoho_id") and zoho_id:
            with _db(path) as conn:
                conn.execute(
                    "UPDATE users SET zoho_id = ? WHERE id = ?",
                    (zoho_id, user["id"]),
                )
        _touch(user["id"], path)
        token = create_session(user["id"], path)
        return {"success": True, "user": user, "token": token}

    return {
        "success":  True,
        "new_user": True,
        "zoho_id":  zoho_id,
        "email":    email,
        "name":     name,
    }
