-- data/training.db schema
-- This database is created and seeded automatically by utils/training_db.py.
-- It is populated with 83 real admin decisions from 4 expense vouchers.
-- Run db_example/setup.py to regenerate it, or just start the app — the first
-- call to any public function in utils/training_db.py calls init_db() automatically.
--
-- Additional historical vouchers can be seeded via: python scripts/seed_vouchers.py

CREATE TABLE IF NOT EXISTS expense_decisions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    voucher_no       TEXT,              -- e.g. '3134'
    employee_code    TEXT,              -- e.g. 'RWSIPL562'
    category         TEXT,              -- 'travel' | 'meals' | 'site_expenses' | '2_wheeler' | ...
    description      TEXT,              -- line-item description as submitted
    expense_date     TEXT,              -- YYYY-MM-DD
    claimed_amount   REAL,
    approved_amount  REAL,              -- 0 if rejected
    decision         TEXT,              -- 'approved' | 'rejected'
    rejection_reason TEXT,              -- non-NULL only when decision = 'rejected'
    created_at       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cat      ON expense_decisions(category);
CREATE INDEX IF NOT EXISTS idx_decision ON expense_decisions(decision);
CREATE INDEX IF NOT EXISTS idx_voucher  ON expense_decisions(voucher_no);

-- Pre-seeded vouchers (from utils/training_db.py):
--
--   Voucher 3134 — Pavan Pawar (RWSIPL562)  Nov 1–15
--     Claimed ₹24,263 | Approved ₹18,459 | Rejected ₹5,804
--     Rejection patterns: exact duplicates, missing receipt backup
--
--   Voucher 3141 — Pavan Pawar (RWSIPL562)  Nov 18–30
--     Claimed ₹24,062 | Approved ₹24,062 (full approval, 0 rejections)
--
--   Voucher 3416 — Shahid Mirza (RWSIPL438)  Mar 16–31
--     Claimed ₹2,749  | Approved ₹2,749  (full approval)
--     Mix of 2-wheeler, auto, train, food
--
--   Voucher 3450 — Suchit Patil (TRWSIPL367)  Mar 16–30
--     Claimed ₹3,219  | Approved ₹3,219  (full approval)
--     Pure 2-wheeler travel with district/block/village detail
--
-- Additional vouchers: run  python scripts/seed_vouchers.py
