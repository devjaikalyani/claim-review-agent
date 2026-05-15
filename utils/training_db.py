"""
Training Database for Admin Judgment

Stores past admin approve/reject decisions extracted from processed expense vouchers.
Used as few-shot examples by the admin_judgment_agent to replicate admin behavior.

Pre-seeded with 4 sample vouchers (83 decisions):
  - Voucher 3134: Employee A Nov 1-15 (7 rejections + 28 approvals)
  - Voucher 3141: Employee A Nov 18-30 (20 approvals, 0 rejections)
  - Voucher 3416: Employee B Mar 16-31 (15 approvals, 0 rejections)
  - Voucher 3450: Employee C Mar 16-30  (12 approvals, 0 rejections)
"""
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "training.db"

# â”€â”€ Seed data extracted from 4 real expense vouchers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_SEED = [

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # VOUCHER 3134 â€” Employee A (EMP562)  Nov 1â€“15 2025
    # Claimed â‚¹24,263 | Approved â‚¹18,459 | Rejected â‚¹5,804
    # Rejection patterns: exact duplicates (same date+amount, different description)
    # and items submitted without a receipt backup.
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    # â”€â”€ REJECTED â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Board and fastner sonwad side",
     "expense_date": "2025-11-02", "claimed_amount": 130.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "No supporting receipt provided â€” item rejected by admin"},

    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Ss board and Anchor fastner sonwad side",
     "expense_date": "2025-11-02", "claimed_amount": 130.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "No supporting receipt provided â€” item rejected by admin"},

    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Lug purchase nashik local purchase",
     "expense_date": "2025-11-04", "claimed_amount": 1534.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "Duplicate submission â€” same amount â‚¹1534 submitted twice on "
                         "4-Nov with different description; cleaner entry kept"},

    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Jalgaon testing team local vehicle arrangement Dy and AE testing team",
     "expense_date": "2025-11-04", "claimed_amount": 3500.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "Duplicate submission â€” same amount â‚¹3500 submitted twice on "
                         "4-Nov; other entry with clearer description approved"},

    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Flexible pipe and Bend purchase",
     "expense_date": "2025-11-07", "claimed_amount": 400.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "No supporting receipt provided â€” item rejected by admin"},

    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Bend purchase",
     "expense_date": "2025-11-08", "claimed_amount": 50.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "Duplicate â€” â‚¹50 bend purchase on same date; "
                         "'Bend purchase local' approved instead"},

    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Localy nut bolt purchase self thred",
     "expense_date": "2025-11-08", "claimed_amount": 60.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "Duplicate â€” â‚¹60 thread/screw purchase on same date; "
                         "'Local self thread screw purchase' approved instead"},

    # â”€â”€ APPROVED â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Anchor fastner local purchase 20 nos",
     "expense_date": "2025-11-04", "claimed_amount": 300.0, "approved_amount": 300.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Lug parcel by taxi collect",
     "expense_date": "2025-11-04", "claimed_amount": 100.0, "approved_amount": 100.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Jalgaon testing team vehicle arrange side visit",
     "expense_date": "2025-11-04", "claimed_amount": 3500.0, "approved_amount": 3500.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Lug purchase locally nashik",
     "expense_date": "2025-11-04", "claimed_amount": 1534.0, "approved_amount": 1534.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Anchor fastner purchase",
     "expense_date": "2025-11-04", "claimed_amount": 300.0, "approved_amount": 300.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Elbow purchase 10 nos",
     "expense_date": "2025-11-04", "claimed_amount": 100.0, "approved_amount": 100.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Shirasgaon substation labour charges pipe under ground work",
     "expense_date": "2025-11-06", "claimed_amount": 1700.0, "approved_amount": 1700.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Local vehicle arrange pipe distribution at side our supervisor",
     "expense_date": "2025-11-08", "claimed_amount": 150.0, "approved_amount": 150.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Bend purchase local",
     "expense_date": "2025-11-08", "claimed_amount": 50.0, "approved_amount": 50.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Bhavesh local vehicle arrange pipe side dispatch work",
     "expense_date": "2025-11-08", "claimed_amount": 150.0, "approved_amount": 150.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Local self thread screw purchase",
     "expense_date": "2025-11-08", "claimed_amount": 60.0, "approved_amount": 60.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Galangi side local board purchase",
     "expense_date": "2025-11-10", "claimed_amount": 150.0, "approved_amount": 150.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Table chair dispatch two side Nandurbar circle",
     "expense_date": "2025-11-10", "claimed_amount": 2850.0, "approved_amount": 2850.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Electric board Galangi side",
     "expense_date": "2025-11-10", "claimed_amount": 150.0, "approved_amount": 150.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Parcel givan parola ss work",
     "expense_date": "2025-11-11", "claimed_amount": 50.0, "approved_amount": 50.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Electric board velhane nimgul",
     "expense_date": "2025-11-11", "claimed_amount": 100.0, "approved_amount": 100.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "From Nagpur parcel handling charges traval point",
     "expense_date": "2025-11-11", "claimed_amount": 20.0, "approved_amount": 20.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Electric board purchase 10 nos",
     "expense_date": "2025-11-11", "claimed_amount": 750.0, "approved_amount": 750.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Flexible pipe purchase Chalisgaon side work",
     "expense_date": "2025-11-11", "claimed_amount": 225.0, "approved_amount": 225.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Local parcel shirpur bus",
     "expense_date": "2025-11-11", "claimed_amount": 50.0, "approved_amount": 50.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Velhane nimgul local board purchase",
     "expense_date": "2025-11-11", "claimed_amount": 100.0, "approved_amount": 100.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Local traval parcel handling charges",
     "expense_date": "2025-11-11", "claimed_amount": 20.0, "approved_amount": 20.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Local electric board purchase 10 nos",
     "expense_date": "2025-11-11", "claimed_amount": 750.0, "approved_amount": 750.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Wire bundle parcel Dhule to Amalner taxi",
     "expense_date": "2025-11-12", "claimed_amount": 50.0, "approved_amount": 50.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Sadal pack purchase Chalisgaon side",
     "expense_date": "2025-11-12", "claimed_amount": 50.0, "approved_amount": 50.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Parcel taxi drill machin",
     "expense_date": "2025-11-13", "claimed_amount": 70.0, "approved_amount": 70.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Bend purchase local",
     "expense_date": "2025-11-13", "claimed_amount": 70.0, "approved_amount": 70.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Table chair dispatch 6 side",
     "expense_date": "2025-11-15", "claimed_amount": 4900.0, "approved_amount": 4900.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3134", "employee_code": "EMP562", "category": "food",
     "description": "Dinner at Nadurbar side work",
     "expense_date": "2025-11-15", "claimed_amount": 160.0, "approved_amount": 160.0,
     "decision": "approved", "rejection_reason": ""},

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # VOUCHER 3141 â€” Employee A (EMP562)  Nov 18â€“30 2025
    # Claimed â‚¹24,062 | Approved â‚¹24,062 | Rejected â‚¹0  (full approval)
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "site_expenses",
     "description": "10 nos side table chair dispatch work Shirpur subdivision",
     "expense_date": "2025-11-18", "claimed_amount": 4000.0, "approved_amount": 4000.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "site_expenses",
     "description": "7 side material dispatch work",
     "expense_date": "2025-11-21", "claimed_amount": 3900.0, "approved_amount": 3900.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "site_expenses",
     "description": "1900 paid second day 7side material dispatch 21 dec recipt",
     "expense_date": "2025-11-22", "claimed_amount": 1900.0, "approved_amount": 1900.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "bus_travel",
     "description": "Nagpur to Dhule traval ticket",
     "expense_date": "2025-11-22", "claimed_amount": 895.0, "approved_amount": 895.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "food",
     "description": "DA",
     "expense_date": "2025-11-22", "claimed_amount": 500.0, "approved_amount": 500.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Nagpur porter paid Hingani to Office",
     "expense_date": "2025-11-22", "claimed_amount": 110.0, "approved_amount": 110.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Baba traval paid parcel box",
     "expense_date": "2025-11-22", "claimed_amount": 100.0, "approved_amount": 100.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "bus_travel",
     "description": "Dhule auto fare traval point to home",
     "expense_date": "2025-11-23", "claimed_amount": 30.0, "approved_amount": 30.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Parcel handling charges baba traval",
     "expense_date": "2025-11-24", "claimed_amount": 20.0, "approved_amount": 20.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "site_expenses",
     "description": "9 side table chair dispatch 2 part payment",
     "expense_date": "2025-11-24", "claimed_amount": 2000.0, "approved_amount": 2000.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "site_expenses",
     "description": "9 side material second part Payment",
     "expense_date": "2025-11-24", "claimed_amount": 1500.0, "approved_amount": 1500.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Self thred purchase",
     "expense_date": "2025-11-24", "claimed_amount": 650.0, "approved_amount": 650.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Lunch with MSEDCL Dy Dhule side visit. Dhule urban",
     "expense_date": "2025-11-25", "claimed_amount": 210.0, "approved_amount": 210.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Parcel paid from Nagpur to Dhule",
     "expense_date": "2025-11-25", "claimed_amount": 150.0, "approved_amount": 150.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Nandurbar 3 side material dispatch work",
     "expense_date": "2025-11-25", "claimed_amount": 3250.0, "approved_amount": 3250.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Sadal and Bend purchase local",
     "expense_date": "2025-11-25", "claimed_amount": 1132.0, "approved_amount": 1132.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Anchor fastner purchase",
     "expense_date": "2025-11-25", "claimed_amount": 525.0, "approved_amount": 525.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Parcel givan to chopda side",
     "expense_date": "2025-11-27", "claimed_amount": 150.0, "approved_amount": 150.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Parcel handling charges traval point",
     "expense_date": "2025-11-30", "claimed_amount": 40.0, "approved_amount": 40.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3141", "employee_code": "EMP562", "category": "site_expenses",
     "description": "Chavadi dusane bramanwel material dispatch work",
     "expense_date": "2025-11-30", "claimed_amount": 3000.0, "approved_amount": 3000.0,
     "decision": "approved", "rejection_reason": ""},

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # VOUCHER 3416 â€” Employee B (EMP438)  Mar 16â€“31 2026
    # Claimed â‚¹2,749 | Approved â‚¹2,749 | Rejected â‚¹0  (full approval)
    # Mix of 2-Wheeler, Auto, Sleeper Class Train, Other Expense, Food Allowance
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    {"voucher_no": "3416", "employee_code": "EMP438", "category": "two_wheeler",
     "description": "Visit ZP thane for billing Approval",
     "expense_date": "2026-03-16", "claimed_amount": 132.0, "approved_amount": 132.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "EMP438", "category": "two_wheeler",
     "description": "Visit Fort office Mumbai for billing work and Official work",
     "expense_date": "2026-03-26", "claimed_amount": 309.0, "approved_amount": 309.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "EMP438", "category": "bus_travel",
     "description": "Visit Bhiwandi to kalyan by Auto ZP thane for billing work",
     "expense_date": "2026-03-27", "claimed_amount": 50.0, "approved_amount": 50.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "EMP438", "category": "bus_travel",
     "description": "Visit Kalyan to thane by Local ZP thane for billing work",
     "expense_date": "2026-03-27", "claimed_amount": 10.0, "approved_amount": 10.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "EMP438", "category": "bus_travel",
     "description": "Visit Thane to ZP Office by Auto ZP thane for billing work",
     "expense_date": "2026-03-27", "claimed_amount": 100.0, "approved_amount": 100.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "EMP438", "category": "bus_travel",
     "description": "Visit ZP office to thane railway station by Auto ZP thane for billing work",
     "expense_date": "2026-03-27", "claimed_amount": 100.0, "approved_amount": 100.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "EMP438", "category": "bus_travel",
     "description": "Visit Thane to Fort Mumbai by Local for official work",
     "expense_date": "2026-03-27", "claimed_amount": 15.0, "approved_amount": 15.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "EMP438", "category": "bus_travel",
     "description": "Visit Mumbai to kalyan by Local for official work",
     "expense_date": "2026-03-27", "claimed_amount": 15.0, "approved_amount": 15.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "EMP438", "category": "bus_travel",
     "description": "Visit Kalyan to Bhiwandi by Auto for official work",
     "expense_date": "2026-03-27", "claimed_amount": 50.0, "approved_amount": 50.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "EMP438", "category": "bus_travel",
     "description": "Visit Bhiwandi to Kalyan st 2-person for fort office officials work",
     "expense_date": "2026-03-28", "claimed_amount": 100.0, "approved_amount": 100.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "EMP438", "category": "bus_travel",
     "description": "Visit Kalyan st to Mumbai st 2-person for fort office officials work",
     "expense_date": "2026-03-28", "claimed_amount": 30.0, "approved_amount": 30.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "EMP438", "category": "bus_travel",
     "description": "Visit Mumbai st to Kalyan st 2-person for fort office officials work",
     "expense_date": "2026-03-28", "claimed_amount": 30.0, "approved_amount": 30.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "EMP438", "category": "other",
     "description": "fort office late night work",
     "expense_date": "2026-03-28", "claimed_amount": 340.0, "approved_amount": 340.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "EMP438", "category": "two_wheeler",
     "description": "Visit ZP thane for approved bill received copy",
     "expense_date": "2026-03-30", "claimed_amount": 135.0, "approved_amount": 135.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3416", "employee_code": "EMP438", "category": "food",
     "description": "food allowance as on date 16.03.2026 to 31.03.2026",
     "expense_date": "2026-03-31", "claimed_amount": 1333.0, "approved_amount": 1333.0,
     "decision": "approved", "rejection_reason": ""},

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # VOUCHER 3450 â€” Employee C (EMP367)  Mar 16â€“30 2026
    # Claimed â‚¹3,219 | Approved â‚¹3,219 | Rejected â‚¹0  (full approval)
    # Pure 2-Wheeler travel for commissioning/installation with District/Block/Village detail
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    {"voucher_no": "3450", "employee_code": "EMP367", "category": "two_wheeler",
     "description": "District-Palghar Block-Vikramgad Village-shil Apati Bk vasuri For commissioning",
     "expense_date": "2026-03-16", "claimed_amount": 123.0, "approved_amount": 123.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "EMP367", "category": "two_wheeler",
     "description": "District-Palghar Block-vikramgadh Village-Deharje shelpada For commissioning",
     "expense_date": "2026-03-17", "claimed_amount": 219.0, "approved_amount": 219.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "EMP367", "category": "two_wheeler",
     "description": "District-Palghar Block-Vasai Village-depivali maljipada For commissioning",
     "expense_date": "2026-03-18", "claimed_amount": 66.0, "approved_amount": 66.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "EMP367", "category": "two_wheeler",
     "description": "District-Palghar Block-Vikramgadh Village-maan kev pole For commissioning",
     "expense_date": "2026-03-20", "claimed_amount": 267.0, "approved_amount": 267.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "EMP367", "category": "two_wheeler",
     "description": "District-Palghar Block-Dahanu Village-varoti For installation",
     "expense_date": "2026-03-21", "claimed_amount": 255.0, "approved_amount": 255.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "EMP367", "category": "two_wheeler",
     "description": "District-Palghar Block-Dahanu Village-Murbad For installation",
     "expense_date": "2026-03-23", "claimed_amount": 309.0, "approved_amount": 309.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "EMP367", "category": "two_wheeler",
     "description": "District-Palghar Block-Dahanu Village-vivalvedhe For installation",
     "expense_date": "2026-03-24", "claimed_amount": 282.0, "approved_amount": 282.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "EMP367", "category": "two_wheeler",
     "description": "District-Palghar Block-Dahanu Village-Saiwan For installation",
     "expense_date": "2026-03-25", "claimed_amount": 357.0, "approved_amount": 357.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "EMP367", "category": "two_wheeler",
     "description": "District-Palghar Block-Dahanu Village-Chandwad For installation",
     "expense_date": "2026-03-26", "claimed_amount": 381.0, "approved_amount": 381.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "EMP367", "category": "two_wheeler",
     "description": "District-Palghar Block-Dahanu Village-gorwadi For installation",
     "expense_date": "2026-03-27", "claimed_amount": 321.0, "approved_amount": 321.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "EMP367", "category": "two_wheeler",
     "description": "District-Palghar Block-Dahanu Village-ashagad jamshet For installation",
     "expense_date": "2026-03-28", "claimed_amount": 333.0, "approved_amount": 333.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "3450", "employee_code": "EMP367", "category": "two_wheeler",
     "description": "District-Palghar Block-Dahanu Village-jamshet For installation",
     "expense_date": "2026-03-30", "claimed_amount": 306.0, "approved_amount": 306.0,
     "decision": "approved", "rejection_reason": ""},

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # SYNTHETIC SEED EXAMPLES â€” Hotel, FASTag, Food, Car Conveyance
    # Added to balance training data across underrepresented categories.
    # Based on real company policy rates and typical field employee scenarios.
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    # â”€â”€ HOTEL â€” Grade C cities (most common for field employees) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {"voucher_no": "SEED_HOTEL", "employee_code": "SEED", "category": "hotel",
     "description": "Hotel stay Nashik site visit â€” 2 nights",
     "expense_date": "2026-01-10", "claimed_amount": 1400.0, "approved_amount": 1400.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_HOTEL", "employee_code": "SEED", "category": "hotel",
     "description": "Guest house Dhule project work â€” 3 nights",
     "expense_date": "2026-01-12", "claimed_amount": 2100.0, "approved_amount": 2100.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_HOTEL", "employee_code": "SEED", "category": "hotel",
     "description": "Hotel Amravati site commissioning â€” 1 night",
     "expense_date": "2026-01-15", "claimed_amount": 700.0, "approved_amount": 700.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_HOTEL", "employee_code": "SEED", "category": "hotel",
     "description": "Hotel Pune meeting with client â€” 1 night",
     "expense_date": "2026-01-20", "claimed_amount": 1800.0, "approved_amount": 1500.0,
     "decision": "partial",
     "rejection_reason": "Pune is Grade A city; technician cap Rs.1,000/night; partial-approved at policy cap"},
    {"voucher_no": "SEED_HOTEL", "employee_code": "SEED", "category": "hotel",
     "description": "Hotel Mumbai head office visit â€” 2 nights",
     "expense_date": "2026-02-01", "claimed_amount": 3200.0, "approved_amount": 2000.0,
     "decision": "partial",
     "rejection_reason": "Mumbai is Grade A city; technician cap Rs.1,000/night x 2 nights = Rs.2,000; partial-approved at cap"},
    {"voucher_no": "SEED_HOTEL", "employee_code": "SEED", "category": "hotel",
     "description": "Dharamshala/lodge Jalgaon side work â€” 4 nights",
     "expense_date": "2026-02-05", "claimed_amount": 2800.0, "approved_amount": 2800.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_HOTEL", "employee_code": "SEED", "category": "hotel",
     "description": "Hotel stay without bill â€” overnight project work",
     "expense_date": "2026-02-10", "claimed_amount": 1000.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "No hotel bill or receipt submitted; hotel claims require documentary proof"},
    {"voucher_no": "SEED_HOTEL", "employee_code": "SEED", "category": "hotel",
     "description": "Guest house Aurangabad district office visit â€” 2 nights",
     "expense_date": "2026-02-14", "claimed_amount": 1800.0, "approved_amount": 1800.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_HOTEL", "employee_code": "SEED", "category": "hotel",
     "description": "Hotel Nagpur 3 nights â€” project review",
     "expense_date": "2026-02-20", "claimed_amount": 3300.0, "approved_amount": 3000.0,
     "decision": "partial",
     "rejection_reason": "Nagpur is Grade B; technician cap Rs.900/night x 3 = Rs.2,700; approved at Rs.3,000 (senior exec rate Rs.1,000/night)"},
    {"voucher_no": "SEED_HOTEL", "employee_code": "SEED", "category": "hotel",
     "description": "Personal hotel stay â€” not on company work",
     "expense_date": "2026-02-25", "claimed_amount": 1200.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "No business purpose stated; personal hotel stay not reimbursable"},
    {"voucher_no": "SEED_HOTEL", "employee_code": "SEED", "category": "hotel",
     "description": "Lodge Chandrapur site deputation â€” 5 nights",
     "expense_date": "2026-03-01", "claimed_amount": 3500.0, "approved_amount": 3500.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_HOTEL", "employee_code": "SEED", "category": "hotel",
     "description": "Hotel Nanded project handover â€” 1 night",
     "expense_date": "2026-03-10", "claimed_amount": 850.0, "approved_amount": 850.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_HOTEL", "employee_code": "SEED", "category": "hotel",
     "description": "Hotel Hyderabad training program â€” 3 nights",
     "expense_date": "2026-03-15", "claimed_amount": 9000.0, "approved_amount": 3000.0,
     "decision": "partial",
     "rejection_reason": "Hyderabad Grade A; technician cap Rs.1,000/night x 3; approved at policy cap Rs.3,000"},
    {"voucher_no": "SEED_HOTEL", "employee_code": "SEED", "category": "hotel",
     "description": "Guest house Satara site work â€” 2 nights",
     "expense_date": "2026-03-20", "claimed_amount": 1400.0, "approved_amount": 1400.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_HOTEL", "employee_code": "SEED", "category": "hotel",
     "description": "Ashram/guest house Palghar village â€” 3 nights project work",
     "expense_date": "2026-04-01", "claimed_amount": 1800.0, "approved_amount": 1800.0,
     "decision": "approved", "rejection_reason": ""},

    # â”€â”€ FASTTAG / TOLL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {"voucher_no": "SEED_FASTTAG", "employee_code": "SEED", "category": "fasttag",
     "description": "Toll Mumbai-Pune expressway site visit",
     "expense_date": "2026-01-08", "claimed_amount": 360.0, "approved_amount": 360.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_FASTTAG", "employee_code": "SEED", "category": "fasttag",
     "description": "FASTag recharge for field travel Jan",
     "expense_date": "2026-01-15", "claimed_amount": 500.0, "approved_amount": 500.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_FASTTAG", "employee_code": "SEED", "category": "fasttag",
     "description": "Toll Nashik-Dhule highway â€” project site",
     "expense_date": "2026-01-22", "claimed_amount": 225.0, "approved_amount": 225.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_FASTTAG", "employee_code": "SEED", "category": "fasttag",
     "description": "Toll Nagpur-Amravati expressway",
     "expense_date": "2026-02-03", "claimed_amount": 180.0, "approved_amount": 180.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_FASTTAG", "employee_code": "SEED", "category": "fasttag",
     "description": "FASTag statement â€” 12 toll transactions mixed personal/work",
     "expense_date": "2026-02-10", "claimed_amount": 1800.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "FASTag statement includes personal travel; no breakdown provided; rejected until itemised proof submitted"},
    {"voucher_no": "SEED_FASTTAG", "employee_code": "SEED", "category": "fasttag",
     "description": "Toll Pune-Satara highway site commissioning",
     "expense_date": "2026-02-18", "claimed_amount": 310.0, "approved_amount": 310.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_FASTTAG", "employee_code": "SEED", "category": "fasttag",
     "description": "Toll Jaipur ring road â€” head office visit",
     "expense_date": "2026-03-05", "claimed_amount": 95.0, "approved_amount": 95.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_FASTTAG", "employee_code": "SEED", "category": "fasttag",
     "description": "Highway toll Kolhapur project â€” 4 trips",
     "expense_date": "2026-03-12", "claimed_amount": 480.0, "approved_amount": 480.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_FASTTAG", "employee_code": "SEED", "category": "fasttag",
     "description": "FASTag recharge monthly",
     "expense_date": "2026-03-01", "claimed_amount": 3500.0, "approved_amount": 3000.0,
     "decision": "partial",
     "rejection_reason": "Monthly FASTag cap Rs.3,000; partial-approved at policy cap"},
    {"voucher_no": "SEED_FASTTAG", "employee_code": "SEED", "category": "fasttag",
     "description": "Toll Navi Mumbai expressway â€” site work",
     "expense_date": "2026-03-22", "claimed_amount": 270.0, "approved_amount": 270.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_FASTTAG", "employee_code": "SEED", "category": "fasttag",
     "description": "Toll booth cash payment â€” no FASTag receipt",
     "expense_date": "2026-04-02", "claimed_amount": 150.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "No FASTag screenshot or toll receipt provided; cash toll claim not accepted without proof"},
    {"voucher_no": "SEED_FASTTAG", "employee_code": "SEED", "category": "fasttag",
     "description": "Expressway toll Latur site visit",
     "expense_date": "2026-04-08", "claimed_amount": 410.0, "approved_amount": 410.0,
     "decision": "approved", "rejection_reason": ""},

    # â”€â”€ FOOD â€” additional examples beyond the 3 in existing seed â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {"voucher_no": "SEED_FOOD", "employee_code": "SEED", "category": "food",
     "description": "Lunch and dinner Nashik site work 3 days",
     "expense_date": "2026-01-10", "claimed_amount": 1200.0, "approved_amount": 1200.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_FOOD", "employee_code": "SEED", "category": "food",
     "description": "DA food allowance 5 days site deputation",
     "expense_date": "2026-01-16", "claimed_amount": 2000.0, "approved_amount": 2000.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_FOOD", "employee_code": "SEED", "category": "food",
     "description": "Team lunch 8 people client visit",
     "expense_date": "2026-01-20", "claimed_amount": 3200.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "Team entertainment expenses not covered under individual food allowance policy"},
    {"voucher_no": "SEED_FOOD", "employee_code": "SEED", "category": "food",
     "description": "Dinner at Dhule site â€” overnight stay",
     "expense_date": "2026-01-25", "claimed_amount": 380.0, "approved_amount": 380.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_FOOD", "employee_code": "SEED", "category": "food",
     "description": "Food allowance 15 days field work",
     "expense_date": "2026-02-01", "claimed_amount": 6000.0, "approved_amount": 6000.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_FOOD", "employee_code": "SEED", "category": "food",
     "description": "DA food allowance monthly â€” 22 travel days",
     "expense_date": "2026-02-28", "claimed_amount": 8800.0, "approved_amount": 7000.0,
     "decision": "partial",
     "rejection_reason": "Monthly food cap Rs.7,000 for >15 travel days; partial-approved at cap"},
    {"voucher_no": "SEED_FOOD", "employee_code": "SEED", "category": "food",
     "description": "Breakfast and lunch Aurangabad â€” day trip no overnight stay",
     "expense_date": "2026-02-12", "claimed_amount": 200.0, "approved_amount": 200.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_FOOD", "employee_code": "SEED", "category": "food",
     "description": "Restaurant bill â€” personal dinner not on travel day",
     "expense_date": "2026-02-20", "claimed_amount": 850.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "Receipt date does not correspond to any travel/site visit day in this claim period"},
    {"voucher_no": "SEED_FOOD", "employee_code": "SEED", "category": "food",
     "description": "Food DA 8 days Jalgaon project",
     "expense_date": "2026-03-08", "claimed_amount": 3200.0, "approved_amount": 3200.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_FOOD", "employee_code": "SEED", "category": "food",
     "description": "Tea/snacks petrol pump â€” travel day",
     "expense_date": "2026-03-15", "claimed_amount": 120.0, "approved_amount": 120.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_FOOD", "employee_code": "SEED", "category": "food",
     "description": "Swiggy order to home address",
     "expense_date": "2026-03-22", "claimed_amount": 450.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "Delivery to home address â€” not a travel/site day meal"},
    {"voucher_no": "SEED_FOOD", "employee_code": "SEED", "category": "food",
     "description": "Hotel dinner Nanded site visit overnight",
     "expense_date": "2026-03-28", "claimed_amount": 400.0, "approved_amount": 400.0,
     "decision": "approved", "rejection_reason": ""},

    # â”€â”€ CAR CONVEYANCE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {"voucher_no": "SEED_CAR", "employee_code": "SEED", "category": "car_conveyance",
     "description": "Car fuel Nashik to project site and back",
     "expense_date": "2026-01-12", "claimed_amount": 2700.0, "approved_amount": 2700.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_CAR", "employee_code": "SEED", "category": "car_conveyance",
     "description": "Petrol reimbursement Mumbaiâ€“Pune client visit 120 km",
     "expense_date": "2026-01-18", "claimed_amount": 1080.0, "approved_amount": 1080.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_CAR", "employee_code": "SEED", "category": "car_conveyance",
     "description": "Car conveyance monthly â€” 400 km verified Unolo",
     "expense_date": "2026-01-31", "claimed_amount": 3600.0, "approved_amount": 3600.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_CAR", "employee_code": "SEED", "category": "car_conveyance",
     "description": "Diesel for company project car â€” Dhule circle",
     "expense_date": "2026-02-05", "claimed_amount": 4500.0, "approved_amount": 4500.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_CAR", "employee_code": "SEED", "category": "car_conveyance",
     "description": "Car hire Nagpur airport to project site",
     "expense_date": "2026-02-12", "claimed_amount": 1800.0, "approved_amount": 1800.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_CAR", "employee_code": "SEED", "category": "car_conveyance",
     "description": "Car conveyance claimed without any fuel bill or GPS proof",
     "expense_date": "2026-02-20", "claimed_amount": 5000.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "No fuel bill or distance proof submitted for car conveyance; required proof missing"},
    {"voucher_no": "SEED_CAR", "employee_code": "SEED", "category": "car_conveyance",
     "description": "Monthly car fuel â€” 1800 km unverified",
     "expense_date": "2026-02-28", "claimed_amount": 16200.0, "approved_amount": 15000.0,
     "decision": "partial",
     "rejection_reason": "Car conveyance monthly cap Rs.15,000; partial-approved at policy cap"},
    {"voucher_no": "SEED_CAR", "employee_code": "SEED", "category": "car_conveyance",
     "description": "Petrol Aurangabadâ€“Jalgaon project drive 300 km",
     "expense_date": "2026-03-05", "claimed_amount": 2700.0, "approved_amount": 2700.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_CAR", "employee_code": "SEED", "category": "car_conveyance",
     "description": "Taxi hire site visit â€” approved by manager",
     "expense_date": "2026-03-12", "claimed_amount": 1500.0, "approved_amount": 1500.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_CAR", "employee_code": "SEED", "category": "car_conveyance",
     "description": "Rapido cab local office commute â€” not business travel",
     "expense_date": "2026-03-18", "claimed_amount": 320.0, "approved_amount": 0.0,
     "decision": "rejected",
     "rejection_reason": "Local homeâ€“office commute not reimbursable; car conveyance covers site/project travel only"},
    {"voucher_no": "SEED_CAR", "employee_code": "SEED", "category": "car_conveyance",
     "description": "Car fuel Pune region project â€” 500 km GPS verified",
     "expense_date": "2026-03-25", "claimed_amount": 4500.0, "approved_amount": 4500.0,
     "decision": "approved", "rejection_reason": ""},
    {"voucher_no": "SEED_CAR", "employee_code": "SEED", "category": "car_conveyance",
     "description": "Car hire Balaji Car Garage UPI â‚¹14970 verified",
     "expense_date": "2026-04-02", "claimed_amount": 14970.0, "approved_amount": 14970.0,
     "decision": "approved", "rejection_reason": ""},
]


# â”€â”€ Public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
            "SELECT COUNT(*) FROM expense_decisions WHERE voucher_no IN "
            "('3134','3141','3416','3450','SEED_HOTEL','SEED_FASTTAG','SEED_FOOD','SEED_CAR')"
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

    # First pass â€” collect ALL items across all categories so we can
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

    # Build a lookup of (category, amount) â†’ approved descriptions so we can
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
            # Detect WHY it was rejected â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            dup_key = (cat_key, claimed)
            if dup_key in approved_amounts:
                # Same category + same amount has an approved counterpart
                # â†’ this is a duplicate submission
                approved_desc = approved_amounts[dup_key][0][:60]
                reason = (
                    f"Duplicate submission â€” same amount â‚¹{claimed:.0f} in {cat_key} "
                    f"submitted twice; '{approved_desc}' was approved instead"
                )
            else:
                # No matching approved item found â†’ likely missing receipt/proof
                reason = (
                    f"No supporting receipt or insufficient proof â€” "
                    f"rejected by admin (no approved counterpart found)"
                )
        elif approved < claimed * 0.99:
            decision = "partial"
            reason   = f"Partially approved: â‚¹{approved:.0f} of â‚¹{claimed:.0f} claimed"
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
    Uses claim_id as voucher_no â€” skips if already saved.
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


_SPARSE_THRESHOLD = 10  # minimum training examples before trusting LLM judgment for a category


def has_sufficient_examples(category: str, threshold: int = _SPARSE_THRESHOLD) -> bool:
    """Return True if the category has enough examples for reliable LLM judgment."""
    init_db()
    with _conn() as con:
        count = con.execute(
            "SELECT COUNT(*) FROM expense_decisions WHERE category=?", (category,)
        ).fetchone()[0]
    return count >= threshold


def get_rule_based_judgment(category: str, amount: float, description: str = "") -> Dict[str, Any]:
    """
    Conservative rule-based judgment for categories with sparse training data.
    Applies the monthly policy cap; otherwise approves at face value.
    Confidence is kept low (0.55â€“0.65) so the admin knows this needs verification.
    """
    from config.policy import get_category_policy
    policy = get_category_policy(category)
    if policy.monthly_limit and amount > policy.monthly_limit:
        return {
            "decision":        "partial",
            "approved_amount": policy.monthly_limit,
            "reason":          (
                f"Rule-based: amount â‚¹{amount:.0f} exceeds monthly policy cap "
                f"â‚¹{policy.monthly_limit:.0f} for {category}; approved at cap. "
                "Admin should verify."
            ),
            "confidence":  0.65,
            "rule_based":  True,
        }
    return {
        "decision":        "approve",
        "approved_amount": amount,
        "reason":          (
            f"Rule-based approval â€” insufficient training data for category '{category}'. "
            "Admin should confirm this decision."
        ),
        "confidence":  0.55,
        "rule_based":  True,
    }


# â”€â”€ Internal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    return con

