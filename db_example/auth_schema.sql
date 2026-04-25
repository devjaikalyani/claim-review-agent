-- auth.db schema + example users
-- Created automatically when the app starts (init_auth_db() in utils/auth.py is idempotent).
-- Run db_example/setup.py to bootstrap a fresh auth.db with sample employees.
--
-- Password hash format: PBKDF2-HMAC-SHA256, salt stored as hex prefix
--   stored value = "<salt_hex>:<dk_hex>"  (salt = secrets.token_hex(32), iterations = 260 000)
-- Default password for each sample user = their employee_id.
--
-- Admin employees are promoted at startup via ADMIN_EMPLOYEE_IDS env var
-- (sync_admin_flags() in utils/auth.py).  The is_admin column is the runtime cache.

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,          -- secrets.token_hex(16)
    employee_id   TEXT UNIQUE NOT NULL,      -- e.g. RWSIPL007
    name          TEXT NOT NULL,
    email         TEXT UNIQUE,               -- used for email-OTP and password login
    phone         TEXT UNIQUE,               -- used for phone-OTP login
    password_hash TEXT,                      -- NULL = OTP / OAuth only
    google_id     TEXT UNIQUE,               -- Google sub claim
    zoho_id       TEXT UNIQUE,               -- Zoho accountId
    is_active     INTEGER DEFAULT 1,
    is_admin      INTEGER DEFAULT 0,         -- synced from ADMIN_EMPLOYEE_IDS on startup
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    last_login    TEXT
);

CREATE TABLE IF NOT EXISTS otp_codes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    identifier  TEXT NOT NULL,              -- email or phone
    code        TEXT NOT NULL,              -- 6-digit string
    purpose     TEXT NOT NULL DEFAULT 'login',
    expires_at  TEXT NOT NULL,              -- ISO-8601, OTP_EXPIRY_MIN from env (default 10)
    used        INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_otp
    ON otp_codes(identifier, purpose, used);

CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,           -- secrets.token_urlsafe(32)
    user_id     TEXT NOT NULL,
    expires_at  TEXT NOT NULL,              -- ISO-8601, SESSION_TTL_HOURS from env (default 24)
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_sess_user
    ON sessions(user_id);

-- Example users (run setup.py to generate real hashes)
-- INSERT INTO users (id, employee_id, name, email, password_hash, is_admin, created_at)
-- VALUES
--   ('<token_hex_16>', 'RWSIPL001', 'Priya Sharma',  'priya.sharma@ritewater.in', '<run setup.py>', 0, datetime('now')),
--   ('...',            'RWSIPL002', 'Rahul Verma',   'rahul.verma@ritewater.in',  '<run setup.py>', 0, datetime('now')),
--   ('...',            'RWSIPL493', 'Admin User',    'admin@ritewater.in',        '<run setup.py>', 1, datetime('now')),
--   ('...',            'TRWSIPL834','Admin Two',     'admin2@ritewater.in',       '<run setup.py>', 1, datetime('now'));

-- To generate a valid password_hash in Python:
-- import hashlib, secrets
-- salt = secrets.token_hex(32)
-- dk   = hashlib.pbkdf2_hmac("sha256", b"RWSIPL001", salt.encode(), 260_000)
-- stored = salt + ":" + dk.hex()
