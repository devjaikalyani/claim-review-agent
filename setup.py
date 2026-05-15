"""
Fresh database setup script for Rite Audit System.
Creates auth.db, claims.db, and data/training.db from scratch with sample data.

Run from the project root:
    python db_example/setup.py
"""
import hashlib
import os
import secrets
import sqlite3
import sys
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── Password hashing (mirrors utils/auth.py) ──────────────────────────────────

def _hash_pw(password: str) -> str:
    salt = secrets.token_hex(32)
    dk   = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return f"{salt}:{dk.hex()}"


# ── auth.db ───────────────────────────────────────────────────────────────────

def setup_auth_db() -> None:
    path = ROOT / "auth.db"
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    conn.executescript("""
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

    # Admin employee IDs come from ADMIN_EMPLOYEE_IDS env var at runtime.
    # Mark the two sample admins here so the dev DB is ready without setting env.
    sample_employees = [
        ("EMP001", "Sample User One",   "user1@example.com",   0),
        ("EMP002", "Sample User Two",   "user2@example.com",   0),
        ("EMP003", "Sample User Three", "user3@example.com",   0),
        ("EMP004", "Sample User Four",  "user4@example.com",   0),
        ("EMP005", "Admin User",        "admin@example.com",   1),
        ("EMP006", "Admin Two",         "admin2@example.com",  1),
    ]

    now = datetime.now().isoformat()
    for emp_id, name, email, is_admin in sample_employees:
        already = conn.execute(
            "SELECT 1 FROM users WHERE employee_id = ?", (emp_id,)
        ).fetchone()
        if not already:
            user_id = secrets.token_hex(16)
            conn.execute(
                """INSERT INTO users
                   (id, employee_id, name, email, password_hash, is_admin, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, emp_id, name, email, _hash_pw(emp_id), is_admin, now),
            )
            print(f"  Created user: {emp_id} / {name}")

    conn.commit()
    conn.close()
    print(f"Created: {path}")


# ── claims.db ─────────────────────────────────────────────────────────────────

def setup_claims_db() -> None:
    path = ROOT / "claims.db"
    conn = sqlite3.connect(str(path))

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS claims (
            id                    TEXT PRIMARY KEY,
            employee_id           TEXT NOT NULL,
            employee_name         TEXT,
            submission_date       TEXT NOT NULL,
            claim_period_start    TEXT,
            claim_period_end      TEXT,
            claimed_amount        REAL NOT NULL,
            approved_amount       REAL,
            decision              TEXT,
            decision_reasoning    TEXT,
            final_report          TEXT,
            status                TEXT DEFAULT 'pending',
            admin_status          TEXT DEFAULT 'pending_review',
            admin_approved_amount REAL,
            admin_reviewed_at     TEXT,
            admin_notes           TEXT,
            line_items_json       TEXT,
            category_eligible_json TEXT,
            created_at            TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at            TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_claims_emp  ON claims(employee_id);
        CREATE INDEX IF NOT EXISTS idx_claims_stat ON claims(status);

        CREATE TABLE IF NOT EXISTS expenses (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id         TEXT NOT NULL,
            category         TEXT NOT NULL,
            amount           REAL NOT NULL,
            date             TEXT,
            description      TEXT,
            source_document  TEXT,
            is_valid         INTEGER DEFAULT 1,
            validation_notes TEXT,
            eligible_amount  REAL,
            FOREIGN KEY (claim_id) REFERENCES claims(id)
        );

        CREATE TABLE IF NOT EXISTS documents (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id       TEXT NOT NULL,
            document_type  TEXT,
            file_path      TEXT,
            extracted_text TEXT,
            extracted_data TEXT,
            ocr_confidence REAL,
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (claim_id) REFERENCES claims(id)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id  TEXT NOT NULL,
            action    TEXT NOT NULL,
            agent     TEXT,
            details   TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (claim_id) REFERENCES claims(id)
        );
    """)

    now   = datetime.now().isoformat()
    today = datetime.now().strftime("%Y-%m-%d")

    # Sample claim 1 — approved
    c1_id = "sample-claim-001"
    if not conn.execute("SELECT 1 FROM claims WHERE id = ?", (c1_id,)).fetchone():
        conn.execute(
            """INSERT INTO claims
               (id, employee_id, employee_name, submission_date,
                claim_period_start, claim_period_end,
                claimed_amount, approved_amount,
                decision, status, admin_status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (c1_id, "EMP001", "Sample User One", today,
             "2025-11-01", "2025-11-15",
             3500.0, 3200.0,
             "approved_partial",
             "completed", "approved",
             now, now),
        )
        conn.executemany(
            "INSERT INTO expenses (claim_id,category,amount,date,description,eligible_amount) VALUES (?,?,?,?,?,?)",
            [
                (c1_id, "travel",       1800.0, "2025-11-05", "Train to client site",  1800.0),
                (c1_id, "meals",         950.0, "2025-11-05", "Lunch with client",       700.0),
                (c1_id, "site_expenses", 750.0, "2025-11-10", "Stationery for project",  700.0),
            ],
        )
        conn.execute(
            "INSERT INTO audit_log (claim_id,action,agent,details,timestamp) VALUES (?,?,?,?,?)",
            (c1_id, "submitted", "employee", "Claim submitted via web app", now),
        )
        conn.execute(
            "INSERT INTO audit_log (claim_id,action,agent,details,timestamp) VALUES (?,?,?,?,?)",
            (c1_id, "reviewed", "admin", "Approved with minor meal deduction", now),
        )
        print(f"  Sample claim: {c1_id} (approved_partial)")

    # Sample claim 2 — pending admin review
    c2_id = "sample-claim-002"
    if not conn.execute("SELECT 1 FROM claims WHERE id = ?", (c2_id,)).fetchone():
        conn.execute(
            """INSERT INTO claims
               (id, employee_id, employee_name, submission_date,
                claim_period_start, claim_period_end,
                claimed_amount, status, admin_status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (c2_id, "EMP002", "Sample User Two", today,
             "2025-11-16", "2025-11-30",
             5200.0,
             "pending", "pending_review",
             now, now),
        )
        conn.execute(
            "INSERT INTO expenses (claim_id,category,amount,date,description) VALUES (?,?,?,?,?)",
            (c2_id, "travel", 5200.0, "2025-11-20", "Intercity travel for training"),
        )
        conn.execute(
            "INSERT INTO audit_log (claim_id,action,agent,details,timestamp) VALUES (?,?,?,?,?)",
            (c2_id, "submitted", "employee", "Claim submitted via web app", now),
        )
        print(f"  Sample claim: {c2_id} (pending review)")

    conn.commit()
    conn.close()
    print(f"Created: {path}")


# ── data/training.db ──────────────────────────────────────────────────────────

def setup_training_db() -> None:
    """Delegates to utils/training_db.py which has its own seed data (83 decisions)."""
    try:
        from utils.training_db import init_db, get_all_decisions
        init_db()
        count = len(get_all_decisions())
        db_path = ROOT / "data" / "training.db"
        print(f"Created: {db_path}  ({count} seeded decisions)")
    except ImportError as exc:
        print(f"  [SKIP] training.db — could not import utils.training_db: {exc}")
    except Exception as exc:
        print(f"  [ERROR] training.db — {exc}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Setting up databases...")
    print()
    print("── auth.db ──────────────────────────────────────────────────────────")
    setup_auth_db()
    print()
    print("── claims.db ────────────────────────────────────────────────────────")
    setup_claims_db()
    print()
    print("── data/training.db ─────────────────────────────────────────────────")
    setup_training_db()
    print()
    print("Done. Start the app with: streamlit run app.py")
    print("Set ADMIN_EMPLOYEE_IDS env var to define admin employee codes.")
