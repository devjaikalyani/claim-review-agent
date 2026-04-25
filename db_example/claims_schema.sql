-- claims.db schema + sample data
-- Created automatically on first app run (ClaimDatabase._init_db() in utils/db.py).
-- Run db_example/setup.py to bootstrap a fresh claims.db with two sample claims.
--
-- Migration columns (admin_status, line_items_json, etc.) are added via ALTER TABLE
-- at startup if the database was created before they existed.

CREATE TABLE IF NOT EXISTS claims (
    id                     TEXT PRIMARY KEY,       -- UUID string
    employee_id            TEXT NOT NULL,          -- e.g. RWSIPL007
    employee_name          TEXT,
    submission_date        TEXT NOT NULL,          -- YYYY-MM-DD
    claim_period_start     TEXT,                   -- YYYY-MM-DD
    claim_period_end       TEXT,                   -- YYYY-MM-DD
    claimed_amount         REAL NOT NULL,
    approved_amount        REAL,                   -- set after AI review
    decision               TEXT,                   -- 'approved' | 'approved_partial' | 'rejected'
    decision_reasoning     TEXT,                   -- AI reasoning summary
    final_report           TEXT,                   -- full markdown report
    status                 TEXT DEFAULT 'pending', -- 'pending' | 'completed'
    -- ── Admin review columns (added via migration if absent) ──────────────────
    admin_status           TEXT DEFAULT 'pending_review', -- 'pending_review' | 'approved' | 'rejected'
    admin_approved_amount  REAL,
    admin_reviewed_at      TEXT,
    admin_notes            TEXT,
    -- ── Structured JSON (added via migration if absent) ──────────────────────
    line_items_json        TEXT,                   -- JSON array of expense line items
    category_eligible_json TEXT,                   -- JSON object: {category: eligible_amount}
    created_at             TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at             TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_claims_emp  ON claims(employee_id);
CREATE INDEX IF NOT EXISTS idx_claims_stat ON claims(status);

CREATE TABLE IF NOT EXISTS expenses (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id         TEXT NOT NULL,
    category         TEXT NOT NULL,     -- 'travel' | 'meals' | 'site_expenses' | ...
    amount           REAL NOT NULL,
    date             TEXT,              -- YYYY-MM-DD
    description      TEXT,
    source_document  TEXT,              -- original receipt filename
    is_valid         INTEGER DEFAULT 1,
    validation_notes TEXT,
    eligible_amount  REAL,              -- after policy cap enforcement
    FOREIGN KEY (claim_id) REFERENCES claims(id)
);

CREATE TABLE IF NOT EXISTS documents (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id       TEXT NOT NULL,
    document_type  TEXT,               -- 'receipt' | 'invoice' | 'other'
    file_path      TEXT,               -- path to uploaded image / PDF
    extracted_text TEXT,               -- raw OCR text
    extracted_data TEXT,               -- JSON structured extraction
    ocr_confidence REAL,               -- 0.0 – 1.0
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (claim_id) REFERENCES claims(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id  TEXT NOT NULL,
    action    TEXT NOT NULL,           -- 'submitted' | 'reviewed' | 'admin_approved' | ...
    agent     TEXT,                    -- 'employee' | 'admin' | AI agent name
    details   TEXT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (claim_id) REFERENCES claims(id)
);

-- Example: approved claim
-- INSERT INTO claims (id, employee_id, employee_name, submission_date,
--     claim_period_start, claim_period_end, claimed_amount, approved_amount,
--     decision, status, admin_status)
-- VALUES ('sample-claim-001', 'RWSIPL001', 'Priya Sharma', date('now'),
--     '2025-11-01', '2025-11-15', 3500.0, 3200.0,
--     'approved_partial', 'completed', 'approved');
