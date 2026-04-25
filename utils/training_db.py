"""
Training Database for Admin Judgment

Stores past admin approve/reject decisions extracted from processed expense vouchers.
Used as few-shot examples by the admin_judgment_agent to replicate admin behavior.

Pre-seeded with 4 real vouchers (83 decisions):
  - Voucher 3134: Pavan Pawar Nov 1-15 (7 rejections + 28 approvals)
  - Voucher 3141: Pavan Pawar Nov 18-30 (20 approvals, 0 rejections)
  - Voucher 3416: Shahid Mirza Mar 16-31 (15 approvals, 0 rejections)
  - Voucher 3450: Suchit Patil Mar 16-30  (12 approvals, 0 rejections)
"""
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "training.db"

# ── Seed data extracted from 4 real expense vouchers ─────────────────────────
_SEED = [

    # ═══════════════════════════════════════════════════════════════════════════
    # VOUCHER 3134 — Pavan Pawar (RWSIPL562)  Nov 1–15 2025
    # Claimed ₹24,263 | Approved ₹18,459 | Rejected ₹5,804
    # Rejection patterns: exact duplicates (same date+amount, different description)
    # and items submitted without a receipt backup.
    # ═══════════════════════════════════════════════════════════════════════════

    # ── REJECTED ──────────────────────────────────────────────────────────────
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Board and fastner sonwad side",
     "expense_date": "2025-11-02", "claimed_amount": 130.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "No supporting receipt provided — item rejected by admin"},

    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Ss board and Anchor fastner sonwad side",
     "expense_date": "2025-11-02", "claimed_amount": 130.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "No supporting receipt provided — item rejected by admin"},

    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Lug purchase nashik local purchase",
     "expense_date": "2025-11-04", "claimed_amount": 1534.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "Duplicate submission — same amount ₹1534 submitted twice on "
                         "4-Nov with different description; cleaner entry kept"},

    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Jalgaon testing team local vehicle arrangement Dy and AE testing team",
     "expense_date": "2025-11-04", "claimed_amount": 3500.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "Duplicate submission — same amount ₹3500 submitted twice on "
                         "4-Nov; other entry with clearer description approved"},

    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Flexible pipe and Bend purchase",
     "expense_date": "2025-11-07", "claimed_amount": 400.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "No supporting receipt provided — item rejected by admin"},

    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Bend purchase",
     "expense_date": "2025-11-08", "claimed_amount": 50.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "Duplicate — ₹50 bend purchase on same date; "
                         "'Bend purchase local' approved instead"},

    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Localy nut bolt purchase self thred",
     "expense_date": "2025-11-08", "claimed_amount": 60.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "Duplicate — ₹60 thread/screw purchase on same date; "
                         "'Local self thread screw purchase' approved instead"},

    # ── APPROVED ──────────────────────────────────────────────────────────────
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Anchor fastner local purchase 20 nos",
     "expense_date": "2025-11-04", "claimed_amount": 300.0, "approved_amount": 300.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Lug parcel by taxi collect",
     "expense_date": "2025-11-04", "claimed_amount": 100.0, "approved_amount": 100.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Jalgaon testing team vehicle arrange side visit",
     "expense_date": "2025-11-04", "claimed_amount": 3500.0, "approved_amount": 3500.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Lug purchase locally nashik",
     "expense_date": "2025-11-04", "claimed_amount": 1534.0, "approved_amount": 1534.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Anchor fastner purchase",
     "expense_date": "2025-11-04", "claimed_amount": 300.0, "approved_amount": 300.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Elbow purchase 10 nos",
     "expense_date": "2025-11-04", "claimed_amount": 100.0, "approved_amount": 100.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Shirasgaon substation labour charges pipe under ground work",
     "expense_date": "2025-11-06", "claimed_amount": 1700.0, "approved_amount": 1700.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Local vehicle arrange pipe distribution at side our supervisor",
     "expense_date": "2025-11-08", "claimed_amount": 150.0, "approved_amount": 150.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Bend purchase local",
     "expense_date": "2025-11-08", "claimed_amount": 50.0, "approved_amount": 50.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Bhavesh local vehicle arrange pipe side dispatch work",
     "expense_date": "2025-11-08", "claimed_amount": 150.0, "approved_amount": 150.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Local self thread screw purchase",
     "expense_date": "2025-11-08", "claimed_amount": 60.0, "approved_amount": 60.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Galangi side local board purchase",
     "expense_date": "2025-11-10", "claimed_amount": 150.0, "approved_amount": 150.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Table chair dispatch two side Nandurbar circle",
     "expense_date": "2025-11-10", "claimed_amount": 2850.0, "approved_amount": 2850.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Electric board Galangi side",
     "expense_date": "2025-11-10", "claimed_amount": 150.0, "approved_amount": 150.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Parcel givan parola ss work",
     "expense_date": "2025-11-11", "claimed_amount": 50.0, "approved_amount": 50.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Electric board velhane nimgul",
     "expense_date": "2025-11-11", "claimed_amount": 100.0, "approved_amount": 100.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "From Nagpur parcel handling charges traval point",
     "expense_date": "2025-11-11", "claimed_amount": 20.0, "approved_amount": 20.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Electric board purchase 10 nos",
     "expense_date": "2025-11-11", "claimed_amount": 750.0, "approved_amount": 750.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Flexible pipe purchase Chalisgaon side work",
     "expense_date": "2025-11-11", "claimed_amount": 225.0, "approved_amount": 225.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Local parcel shirpur bus",
     "expense_date": "2025-11-11", "claimed_amount": 50.0, "approved_amount": 50.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Velhane nimgul local board purchase",
     "expense_date": "2025-11-11", "claimed_amount": 100.0, "approved_amount": 100.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Local traval parcel handling charges",
     "expense_date": "2025-11-11", "claimed_amount": 20.0, "approved_amount": 20.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Local electric board purchase 10 nos",
     "expense_date": "2025-11-11", "claimed_amount": 750.0, "approved_amount": 750.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Wire bundle parcel Dhule to Amalner taxi",
     "expense_date": "2025-11-12", "claimed_amount": 50.0, "approved_amount": 50.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Sadal pack purchase Chalisgaon side",
     "expense_date": "2025-11-12", "claimed_amount": 50.0, "approved_amount": 50.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Parcel taxi drill machin",
     "expense_date": "2025-11-13", "claimed_amount": 70.0, "approved_amount": 70.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Bend purchase local",
     "expense_date": "2025-11-13", "claimed_amount": 70.0, "approved_amount": 70.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Table chair dispatch 6 side",
     "expense_date": "2025-11-15", "claimed_amount": 4900.0, "approved_amount": 4900.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "RWSIPL562", "category": "food",
     "description": "Dinner at Nadurbar side work",
     "expense_date": "2025-11-15", "claimed_amount": 160.0, "approved_amount": 160.0,
     "decision": "approved", "rejection_reason": ""},

    # ═══════════════════════════════════════════════════════════════════════════
    # VOUCHER 3141 — Pavan Pawar (RWSIPL562)  Nov 18–30 2025
    # Claimed ₹24,062 | Approved ₹24,062 | Rejected ₹0  (full approval)
    # ═══════════════════════════════════════════════════════════════════════════
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "10 nos side table chair dispatch work Shirpur subdivision",
     "expense_date": "2025-11-18", "claimed_amount": 4000.0, "approved_amount": 4000.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "7 side material dispatch work",
     "expense_date": "2025-11-21", "claimed_amount": 3900.0, "approved_amount": 3900.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "1900 paid second day 7side material dispatch 21 dec recipt",
     "expense_date": "2025-11-22", "claimed_amount": 1900.0, "approved_amount": 1900.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "bus_travel",
     "description": "Nagpur to Dhule traval ticket",
     "expense_date": "2025-11-22", "claimed_amount": 895.0, "approved_amount": 895.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "food",
     "description": "DA",
     "expense_date": "2025-11-22", "claimed_amount": 500.0, "approved_amount": 500.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Nagpur porter paid Hingani to Office",
     "expense_date": "2025-11-22", "claimed_amount": 110.0, "approved_amount": 110.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Baba traval paid parcel box",
     "expense_date": "2025-11-22", "claimed_amount": 100.0, "approved_amount": 100.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "bus_travel",
     "description": "Dhule auto fare traval point to home",
     "expense_date": "2025-11-23", "claimed_amount": 30.0, "approved_amount": 30.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Parcel handling charges baba traval",
     "expense_date": "2025-11-24", "claimed_amount": 20.0, "approved_amount": 20.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "9 side table chair dispatch 2 part payment",
     "expense_date": "2025-11-24", "claimed_amount": 2000.0, "approved_amount": 2000.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "9 side material second part Payment",
     "expense_date": "2025-11-24", "claimed_amount": 1500.0, "approved_amount": 1500.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Self thred purchase",
     "expense_date": "2025-11-24", "claimed_amount": 650.0, "approved_amount": 650.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Lunch with MSEDCL Dy Dhule side visit. Dhule urban",
     "expense_date": "2025-11-25", "claimed_amount": 210.0, "approved_amount": 210.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Parcel paid from Nagpur to Dhule",
     "expense_date": "2025-11-25", "claimed_amount": 150.0, "approved_amount": 150.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Nandurbar 3 side material dispatch work",
     "expense_date": "2025-11-25", "claimed_amount": 3250.0, "approved_amount": 3250.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Sadal and Bend purchase local",
     "expense_date": "2025-11-25", "claimed_amount": 1132.0, "approved_amount": 1132.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Anchor fastner purchase",
     "expense_date": "2025-11-25", "claimed_amount": 525.0, "approved_amount": 525.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Parcel givan to chopda side",
     "expense_date": "2025-11-27", "claimed_amount": 150.0, "approved_amount": 150.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Parcel handling charges traval point",
     "expense_date": "2025-11-30", "claimed_amount": 40.0, "approved_amount": 40.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "RWSIPL562", "category": "site_expenses",
     "description": "Chavadi dusane bramanwel material dispatch work",
     "expense_date": "2025-11-30", "claimed_amount": 3000.0, "approved_amount": 3000.0,
     "decision": "approved", "rejection_reason": ""},

    # ═══════════════════════════════════════════════════════════════════════════
    # VOUCHER 3416 — Shahidbeg Ashikbeg Mirza (RWSIPL438)  Mar 16–31 2026
    # Claimed ₹2,749 | Approved ₹2,749 | Rejected ₹0  (full approval)
    # Mix of 2-Wheeler, Auto, Sleeper Class Train, Other Expense, Food Allowance
    # ═══════════════════════════════════════════════════════════════════════════
    {"voucher_no": "3416", "employee_code": "RWSIPL438", "category": "two_wheeler",
     "description": "Visit ZP thane for billing Approval",
     "expense_date": "2026-03-16", "claimed_amount": 132.0, "approved_amount": 132.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "RWSIPL438", "category": "two_wheeler",
     "description": "Visit Fort office Mumbai for billing work and Official work",
     "expense_date": "2026-03-26", "claimed_amount": 309.0, "approved_amount": 309.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "RWSIPL438", "category": "bus_travel",
     "description": "Visit Bhiwandi to kalyan by Auto ZP thane for billing work",
     "expense_date": "2026-03-27", "claimed_amount": 50.0, "approved_amount": 50.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "RWSIPL438", "category": "bus_travel",
     "description": "Visit Kalyan to thane by Local ZP thane for billing work",
     "expense_date": "2026-03-27", "claimed_amount": 10.0, "approved_amount": 10.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "RWSIPL438", "category": "bus_travel",
     "description": "Visit Thane to ZP Office by Auto ZP thane for billing work",
     "expense_date": "2026-03-27", "claimed_amount": 100.0, "approved_amount": 100.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "RWSIPL438", "category": "bus_travel",
     "description": "Visit ZP office to thane railway station by Auto ZP thane for billing work",
     "expense_date": "2026-03-27", "claimed_amount": 100.0, "approved_amount": 100.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "RWSIPL438", "category": "bus_travel",
     "description": "Visit Thane to Fort Mumbai by Local for official work",
     "expense_date": "2026-03-27", "claimed_amount": 15.0, "approved_amount": 15.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "RWSIPL438", "category": "bus_travel",
     "description": "Visit Mumbai to kalyan by Local for official work",
     "expense_date": "2026-03-27", "claimed_amount": 15.0, "approved_amount": 15.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "RWSIPL438", "category": "bus_travel",
     "description": "Visit Kalyan to Bhiwandi by Auto for official work",
     "expense_date": "2026-03-27", "claimed_amount": 50.0, "approved_amount": 50.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "RWSIPL438", "category": "bus_travel",
     "description": "Visit Bhiwandi to Kalyan st 2-person for fort office officials work",
     "expense_date": "2026-03-28", "claimed_amount": 100.0, "approved_amount": 100.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "RWSIPL438", "category": "bus_travel",
     "description": "Visit Kalyan st to Mumbai st 2-person for fort office officials work",
     "expense_date": "2026-03-28", "claimed_amount": 30.0, "approved_amount": 30.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "RWSIPL438", "category": "bus_travel",
     "description": "Visit Mumbai st to Kalyan st 2-person for fort office officials work",
     "expense_date": "2026-03-28", "claimed_amount": 30.0, "approved_amount": 30.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "RWSIPL438", "category": "other",
     "description": "fort office late night work",
     "expense_date": "2026-03-28", "claimed_amount": 340.0, "approved_amount": 340.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "RWSIPL438", "category": "two_wheeler",
     "description": "Visit ZP thane for approved bill received copy",
     "expense_date": "2026-03-30", "claimed_amount": 135.0, "approved_amount": 135.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "RWSIPL438", "category": "food",
     "description": "food allowance as on date 16.03.2026 to 31.03.2026",
     "expense_date": "2026-03-31", "claimed_amount": 1333.0, "approved_amount": 1333.0,
     "decision": "approved", "rejection_reason": ""},

    # ═══════════════════════════════════════════════════════════════════════════
    # VOUCHER 3450 — Suchit Bhalchandra Patil (TRWSIPL367)  Mar 16–30 2026
    # Claimed ₹3,219 | Approved ₹3,219 | Rejected ₹0  (full approval)
    # Pure 2-Wheeler travel for commissioning/installation with District/Block/Village detail
    # ═══════════════════════════════════════════════════════════════════════════
    {"voucher_no": "3450", "employee_code": "TRWSIPL367", "category": "two_wheeler",
     "description": "District-Palghar Block-Vikramgad Village-shil Apati Bk vasuri For commissioning",
     "expense_date": "2026-03-16", "claimed_amount": 123.0, "approved_amount": 123.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "TRWSIPL367", "category": "two_wheeler",
     "description": "District-Palghar Block-vikramgadh Village-Deharje shelpada For commissioning",
     "expense_date": "2026-03-17", "claimed_amount": 219.0, "approved_amount": 219.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "TRWSIPL367", "category": "two_wheeler",
     "description": "District-Palghar Block-Vasai Village-depivali maljipada For commissioning",
     "expense_date": "2026-03-18", "claimed_amount": 66.0, "approved_amount": 66.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "TRWSIPL367", "category": "two_wheeler",
     "description": "District-Palghar Block-Vikramgadh Village-maan kev pole For commissioning",
     "expense_date": "2026-03-20", "claimed_amount": 267.0, "approved_amount": 267.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "TRWSIPL367", "category": "two_wheeler",
     "description": "District-Palghar Block-Dahanu Village-varoti For installation",
     "expense_date": "2026-03-21", "claimed_amount": 255.0, "approved_amount": 255.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "TRWSIPL367", "category": "two_wheeler",
     "description": "District-Palghar Block-Dahanu Village-Murbad For installation",
     "expense_date": "2026-03-23", "claimed_amount": 309.0, "approved_amount": 309.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "TRWSIPL367", "category": "two_wheeler",
     "description": "District-Palghar Block-Dahanu Village-vivalvedhe For installation",
     "expense_date": "2026-03-24", "claimed_amount": 282.0, "approved_amount": 282.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "TRWSIPL367", "category": "two_wheeler",
     "description": "District-Palghar Block-Dahanu Village-Saiwan For installation",
     "expense_date": "2026-03-25", "claimed_amount": 357.0, "approved_amount": 357.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "TRWSIPL367", "category": "two_wheeler",
     "description": "District-Palghar Block-Dahanu Village-Chandwad For installation",
     "expense_date": "2026-03-26", "claimed_amount": 381.0, "approved_amount": 381.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "TRWSIPL367", "category": "two_wheeler",
     "description": "District-Palghar Block-Dahanu Village-gorwadi For installation",
     "expense_date": "2026-03-27", "claimed_amount": 321.0, "approved_amount": 321.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "TRWSIPL367", "category": "two_wheeler",
     "description": "District-Palghar Block-Dahanu Village-ashagad jamshet For installation",
     "expense_date": "2026-03-28", "claimed_amount": 333.0, "approved_amount": 333.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "TRWSIPL367", "category": "two_wheeler",
     "description": "District-Palghar Block-Dahanu Village-jamshet For installation",
     "expense_date": "2026-03-30", "claimed_amount": 306.0, "approved_amount": 306.0,
     "decision": "approved", "rejection_reason": ""},
]


# ── Public API ────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create schema and seed data on first run. Safe to call multiple times."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS expense_decisions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                voucher_no       TEXT,
                employee_code    TEXT,
                category         TEXT,
                description      TEXT,
                expense_date     TEXT,
                claimed_amount   REAL,
                approved_amount  REAL,
                decision         TEXT,
                rejection_reason TEXT,
                created_at       TEXT DEFAULT (datetime('now'))
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_cat      ON expense_decisions(category)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_decision ON expense_decisions(decision)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_voucher  ON expense_decisions(voucher_no)")

        already = con.execute(
            "SELECT COUNT(*) FROM expense_decisions WHERE voucher_no IN ('3134','3141','3416','3450')"
        ).fetchone()[0]

        if already == 0:
            con.executemany("""
                INSERT INTO expense_decisions
                  (voucher_no, employee_code, category, description,
                   expense_date, claimed_amount, approved_amount, decision, rejection_reason)
                VALUES
                  (:voucher_no, :employee_code, :category, :description,
                   :expense_date, :claimed_amount, :approved_amount, :decision, :rejection_reason)
            """, _SEED)


def save_voucher_decisions(voucher_data: Dict[str, Any],
                           employee_code: str = "") -> int:
    """
    Persist all line-item decisions from a newly processed expense voucher.
    Auto-detects rejection reasons (duplicate vs no receipt vs policy limit)
    so the LLM learns WHY items were rejected, not just that they were.
    Returns the number of rows inserted.
    """
    init_db()
    voucher_no = voucher_data.get("voucher_no", "")
    with _conn() as con:
        if con.execute(
            "SELECT COUNT(*) FROM expense_decisions WHERE voucher_no = ?",
            (voucher_no,)
        ).fetchone()[0]:
            return 0

    # First pass — collect ALL items across all categories so we can
    # cross-check rejected items against approved ones for duplicate detection.
    all_items: List[Dict] = []
    for cat_key, cat_data in (voucher_data.get("categories") or {}).items():
        for item in cat_data.get("items", []):
            claimed  = float(item.get("claimed_amount") or 0)
            approved = float(item.get("amount") or 0)
            if claimed <= 0:
                continue
            all_items.append({
                "cat_key":    cat_key,
                "description": item.get("expense_head", ""),
                "claimed":    claimed,
                "approved":   approved,
            })

    # Build a lookup of (category, amount) → approved descriptions so we can
    # recognise when a rejected item is a duplicate of an approved one.
    approved_amounts: Dict[tuple, List[str]] = {}
    for it in all_items:
        if it["approved"] > 0:
            key = (it["cat_key"], it["claimed"])
            approved_amounts.setdefault(key, []).append(it["description"])

    rows = []
    for it in all_items:
        claimed  = it["claimed"]
        approved = it["approved"]
        cat_key  = it["cat_key"]
        desc     = it["description"]

        if approved <= 0:
            decision = "rejected"
            # Detect WHY it was rejected ─────────────────────────────────────
            dup_key = (cat_key, claimed)
            if dup_key in approved_amounts:
                # Same category + same amount has an approved counterpart
                # → this is a duplicate submission
                approved_desc = approved_amounts[dup_key][0][:60]
                reason = (
                    f"Duplicate submission — same amount ₹{claimed:.0f} in {cat_key} "
                    f"submitted twice; '{approved_desc}' was approved instead"
                )
            else:
                # No matching approved item found → likely missing receipt/proof
                reason = (
                    f"No supporting receipt or insufficient proof — "
                    f"rejected by admin (no approved counterpart found)"
                )
        elif approved < claimed * 0.99:
            decision = "partial"
            reason   = f"Partially approved: ₹{approved:.0f} of ₹{claimed:.0f} claimed"
        else:
            decision = "approved"
            reason   = ""

        rows.append({
            "voucher_no":       voucher_no,
            "employee_code":    employee_code,
            "category":         cat_key,
            "description":      desc,
            "expense_date":     "",
            "claimed_amount":   claimed,
            "approved_amount":  approved,
            "decision":         decision,
            "rejection_reason": reason,
        })

    if not rows:
        return 0
    with _conn() as con:
        con.executemany("""
            INSERT INTO expense_decisions
              (voucher_no, employee_code, category, description,
               expense_date, claimed_amount, approved_amount, decision, rejection_reason)
            VALUES
              (:voucher_no, :employee_code, :category, :description,
               :expense_date, :claimed_amount, :approved_amount, :decision, :rejection_reason)
        """, rows)
    return len(rows)


def save_admin_override_decisions(
    claim_id: str,
    employee_code: str,
    line_items: List[Dict],
) -> int:
    """
    Save admin's final decisions from the dashboard review as training data.
    Each item must have: category, description, date, claimed_amount,
    admin_decision (approve/reject/partial), admin_approved_amount, admin_reason.
    Uses claim_id as voucher_no — skips if already saved.
    Returns number of rows inserted.
    """
    init_db()
    with _conn() as con:
        if con.execute(
            "SELECT COUNT(*) FROM expense_decisions WHERE voucher_no=?", (claim_id,)
        ).fetchone()[0]:
            return 0  # already saved for this claim

    rows = []
    for item in line_items:
        decision = item.get("admin_decision") or item.get("system_decision", "approve")
        claimed  = float(item.get("claimed_amount") or 0)
        approved = float(item.get("admin_approved_amount") or (claimed if decision == "approve" else 0))
        reason   = item.get("admin_reason") or item.get("system_reason", "")

        if claimed <= 0:
            continue

        rows.append({
            "voucher_no":       claim_id,
            "employee_code":    employee_code,
            "category":         item.get("category", "other"),
            "description":      item.get("description", ""),
            "expense_date":     item.get("date", ""),
            "claimed_amount":   claimed,
            "approved_amount":  approved,
            "decision":         decision,
            "rejection_reason": reason,
        })

    if not rows:
        return 0

    with _conn() as con:
        con.executemany("""
            INSERT INTO expense_decisions
              (voucher_no, employee_code, category, description,
               expense_date, claimed_amount, approved_amount, decision, rejection_reason)
            VALUES
              (:voucher_no, :employee_code, :category, :description,
               :expense_date, :claimed_amount, :approved_amount, :decision, :rejection_reason)
        """, rows)
    return len(rows)


def get_paired_examples(category: str, limit: int = 6) -> List[Dict]:
    """
    Return rejected items paired with their corresponding approved counterpart
    (same category + same amount, different description).
    This shows the LLM exactly what duplicate patterns look like.
    """
    init_db()
    with _conn() as con:
        rejected = con.execute("""
            SELECT r.description AS rejected_desc,
                   r.claimed_amount,
                   r.rejection_reason,
                   a.description AS approved_desc
            FROM   expense_decisions r
            JOIN   expense_decisions a
                   ON  a.category       = r.category
                   AND a.claimed_amount = r.claimed_amount
                   AND a.decision       = 'approved'
                   AND a.voucher_no     = r.voucher_no
            WHERE  r.category = ?
              AND  r.decision  = 'rejected'
            ORDER  BY r.id DESC
            LIMIT  ?
        """, (category, limit)).fetchall()
        return [dict(r) for r in rejected]


def get_examples(category: str, limit: int = 20) -> List[Dict]:
    """
    Return past decisions for a given category, sorted by most recent first.
    Used to build the few-shot context for the admin judgment agent.
    """
    init_db()
    with _conn() as con:
        rows = con.execute("""
            SELECT category, description, claimed_amount, approved_amount,
                   decision, rejection_reason
            FROM   expense_decisions
            WHERE  category = ?
            ORDER  BY id DESC
            LIMIT  ?
        """, (category, limit)).fetchall()
        return [dict(r) for r in rows]


def get_rejection_patterns() -> List[Dict]:
    """Return the most common rejection reasons across all categories."""
    init_db()
    with _conn() as con:
        rows = con.execute("""
            SELECT category, rejection_reason, COUNT(*) AS frequency
            FROM   expense_decisions
            WHERE  decision = 'rejected'
            GROUP  BY category, rejection_reason
            ORDER  BY frequency DESC
            LIMIT  20
        """).fetchall()
        return [dict(r) for r in rows]


def get_stats() -> Dict[str, Any]:
    init_db()
    with _conn() as con:
        total    = con.execute("SELECT COUNT(*) FROM expense_decisions").fetchone()[0]
        approved = con.execute("SELECT COUNT(*) FROM expense_decisions WHERE decision='approved'").fetchone()[0]
        rejected = con.execute("SELECT COUNT(*) FROM expense_decisions WHERE decision='rejected'").fetchone()[0]
        vouchers = con.execute("SELECT COUNT(DISTINCT voucher_no) FROM expense_decisions").fetchone()[0]
        return {"total": total, "approved": approved, "rejected": rejected, "vouchers": vouchers}


# ── Internal ──────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    return con
