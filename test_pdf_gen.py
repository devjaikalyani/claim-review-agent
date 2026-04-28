"""Quick smoke-test for generate_audit_pdf — checks for blank pages."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from utils.audit_pdf import generate_audit_pdf

state = {
    "claim_id": "CLM-2025-0042",
    "employee_name": "Rahul Sharma",
    "employee_id": "EMP-1021",
    "claimed_amount": 8750.0,
    "approved_amount": 6800.0,
    "decision": "partial_approval",
    "claim_description": "Field visit expenses for April 2025 — Pune to Nashik route",
    "claim_period_start": "2025-04-01",
    "claim_period_end": "2025-04-30",
    "submission_date": "2025-05-03",
    "unolo_distance_km": 320.5,
    "eligible_distance_km": 330.0,
    "emp_distance_km": 350.0,
    "total_extracted_amount": 8680.0,
    "category_claimed_total": 8750.0,
    "extraction_gap": -70.0,
    "ocr_confidence": 0.91,
    "reconciliation_note": "Small gap between OCR total and categorised total — one receipt was assigned to 'other'.",
    "admin_judgment_note": "Two-wheeler fuel claims are within GPS-verified range. Food expenses slightly exceed daily cap.",
    "admin_judgment_applied": True,
    "category_eligible": {
        "two_wheeler": {
            "claimed": 3200.0,
            "eligible": 2970.0,
            "reasoning": "Rate Rs.2.80/km x 330 km eligible distance = Rs.924. Monthly cap Rs.3000 applied.",
            "items": 8,
            "policy_limit": 3000.0,
        },
        "food": {
            "claimed": 2800.0,
            "eligible": 2100.0,
            "reasoning": "Daily cap Rs.150 x 14 working days = Rs.2100. Claimed Rs.2800 exceeds cap.",
            "items": 14,
            "policy_limit": 2100.0,
        },
        "fasttag": {
            "claimed": 750.0,
            "eligible": 750.0,
            "reasoning": "FASTag receipts verified. Within monthly limit.",
            "items": 3,
            "policy_limit": 1000.0,
        },
        "bus_travel": {
            "claimed": 1200.0,
            "eligible": 980.0,
            "reasoning": "2 intercity bus trips. Per-trip cap Rs.490 x 2 = Rs.980.",
            "items": 2,
            "policy_limit": 980.0,
        },
        "other": {
            "claimed": 800.0,
            "eligible": 0.0,
            "reasoning": "Uncategorised receipts — insufficient documentation to approve.",
            "items": 2,
            "policy_limit": 0.0,
        },
    },
    "policy_violations": [
        "Food: Claimed Rs.2800.00 exceeds monthly cap Rs.2100.00",
        "Bus Travel: Claimed Rs.1200.00 exceeds per-trip cap (2 trips x Rs.490 = Rs.980)",
        "Other: No valid category or documentation for 2 items totalling Rs.800",
    ],
    "data_validation_issues": [
        "Receipt #7 (fuel) has no vendor name — accepted on GPS evidence",
    ],
    "calculation_validation_issues": [],
    "calculation_validation_warnings": [
        "Two-wheeler rate applied to eligible distance (330 km), not employee-reported (350 km)",
    ],
    "report_validation_issues": [],
    "extracted_text": [
        {"source": "fuel_receipt_apr03.jpg", "receipt_type": "fuel", "extracted_amount": 450.0, "confidence": 0.95},
        {"source": "food_bill_apr05.jpg",    "receipt_type": "food", "extracted_amount": 210.0, "confidence": 0.88},
        {"source": "fasttag_apr08.jpg",      "receipt_type": "toll", "extracted_amount": 250.0, "confidence": 0.97},
        {"source": "bus_ticket_apr10.jpg",   "receipt_type": "bus",  "extracted_amount": 580.0, "confidence": 0.93},
        {"source": "fuel_receipt_apr15.jpg", "receipt_type": "fuel", "extracted_amount": 520.0, "confidence": 0.90},
        {"source": "food_upi_apr18.png",     "receipt_type": "food", "extracted_amount": 180.0, "confidence": 0.82},
        {"source": "unknown_receipt.jpg",    "receipt_type": "other","extracted_amount": 350.0, "confidence": 0.61},
    ],
    "expenses": [
        {"category": "two_wheeler", "description": "Petrol — Pune-Nashik (03 Apr)", "date": "2025-04-03", "amount": 450.0, "source_document": "fuel_receipt_apr03.jpg", "system_confidence": 0.95},
        {"category": "two_wheeler", "description": "Petrol — field visits week 2 (15 Apr)", "date": "2025-04-15", "amount": 520.0, "source_document": "fuel_receipt_apr15.jpg", "system_confidence": 0.90},
        {"category": "food", "description": "Lunch — Nashik field office (05 Apr)", "date": "2025-04-05", "amount": 210.0, "source_document": "food_bill_apr05.jpg", "system_confidence": 0.88},
        {"category": "fasttag", "description": "FASTag toll — Pune-Nashik expressway (08 Apr)", "date": "2025-04-08", "amount": 250.0, "source_document": "fasttag_apr08.jpg", "system_confidence": 0.97},
        {"category": "bus_travel", "description": "Bus — Nashik to Ahmednagar return (10 Apr)", "date": "2025-04-10", "amount": 580.0, "source_document": "bus_ticket_apr10.jpg", "system_confidence": 0.93},
    ],
    "rejected_expenses": [
        {"category": "food", "description": "Dinner UPI payment (18 Apr) — no vendor receipt", "date": "2025-04-18", "amount": 180.0, "system_reason": "UPI screenshot only; no physical bill to corroborate amount", "system_confidence": 0.72},
        {"category": "other", "description": "Unidentified expense (misc)", "date": "2025-04-20", "amount": 350.0, "system_reason": "Receipt unclear; category cannot be determined; no business justification", "system_confidence": 0.55},
        {"category": "other", "description": "Hardware purchase — site material", "date": "2025-04-22", "amount": 450.0, "system_reason": "Site material expenses require pre-approval and separate purchase order", "system_confidence": 0.68},
    ],
    "duplicates_removed": [
        "fuel_receipt_apr03.jpg matched UPI screenshot UPI_apr03_450.png — UPI copy removed",
    ],
    "employee_summary": {
        "is_summary": True,
        "voucher_no": "VCH-2025-0089",
        "period": "01 Apr 2025 to 30 Apr 2025",
        "employee_name": "Rahul Sharma",
        "summary_total": 8750.0,
        "summary_approved": 7200.0,
    },
    "voucher_line_decisions": [
        {"expense_head": "Fuel / Bike Travel", "date": "2025-04-03", "claimed_amount": 450.0,  "approved_amount": 450.0,  "decision": "approve",  "reason": "Within policy"},
        {"expense_head": "Fuel / Bike Travel", "date": "2025-04-15", "claimed_amount": 520.0,  "approved_amount": 520.0,  "decision": "approve",  "reason": "Within policy"},
        {"expense_head": "Food Allowance",     "date": "2025-04-05", "claimed_amount": 210.0,  "approved_amount": 210.0,  "decision": "approve",  "reason": "Approved by manager"},
        {"expense_head": "Food Allowance",     "date": "2025-04-18", "claimed_amount": 180.0,  "approved_amount": 180.0,  "decision": "approve",  "reason": "Approved by manager"},
        {"expense_head": "FASTag / Toll",      "date": "2025-04-08", "claimed_amount": 250.0,  "approved_amount": 250.0,  "decision": "approve",  "reason": "Toll receipt verified"},
        {"expense_head": "Bus Travel",         "date": "2025-04-10", "claimed_amount": 580.0,  "approved_amount": 490.0,  "decision": "partial",  "reason": "Per-trip cap applied"},
        {"expense_head": "Misc Expense",       "date": "2025-04-20", "claimed_amount": 350.0,  "approved_amount": 0.0,    "decision": "reject",   "reason": "No supporting document"},
        {"expense_head": "Misc Expense",       "date": "2025-04-22", "claimed_amount": 450.0,  "approved_amount": 0.0,    "decision": "reject",   "reason": "Pre-approval required"},
        {"expense_head": "Food Allowance",     "date": "2025-04-25", "claimed_amount": 2410.0, "approved_amount": 1710.0, "decision": "partial",  "reason": "Daily cap exceeded"},
        {"expense_head": "Fuel / Bike Travel", "date": "2025-04-28", "claimed_amount": 2300.0, "approved_amount": 2000.0, "decision": "partial",  "reason": "Distance cap applied"},
        {"expense_head": "FASTag / Toll",      "date": "2025-04-29", "claimed_amount": 500.0,  "approved_amount": 390.0,  "decision": "partial",  "reason": "Duplicate toll removed"},
    ],
}

form_snap = {
    "period_start": "01 Apr 2025",
    "period_end":   "30 Apr 2025",
}

print("Generating PDF...")
data = generate_audit_pdf(state, form_snap)
out = "test_detailed_report.pdf"
with open(out, "wb") as f:
    f.write(data)
print(f"OK — {len(data):,} bytes written to {out}")
