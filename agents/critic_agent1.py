"""
Critic Agent 1 - Data Validation

Validates extracted data for completeness and accuracy.
"""
from typing import Dict, Any, List, Literal
from agents.state import ClaimState
from config.policy import (
    VALIDATION_RULES,
    get_required_proofs,
    REIMBURSEMENT_POLICY
)


def critic_agent1(state: ClaimState) -> ClaimState:
    """
    Validate extracted data quality and completeness.
    
    Checks:
    - All required proofs are present for each category
    - Date fields are populated
    - Amounts are reasonable
    - No duplicate receipts
    - OCR confidence is acceptable
    
    Args:
        state: Current claim state
        
    Returns:
        Updated state with validation results
    """
    state["current_agent"] = "critic1"
    
    # Increment revision count when entering this node
    state["data_revision_count"] = state.get("data_revision_count", 0) + 1
    
    issues = []
    categories = state.get("categories", {})
    expenses = state.get("expenses", [])
    extracted_text = state.get("extracted_text", [])
    
    # Check OCR confidence
    ocr_confidence = state.get("ocr_confidence", 0.0)
    if ocr_confidence < VALIDATION_RULES["min_receipt_quality_score"]:
        issues.append(
            f"Low document quality (confidence: {ocr_confidence:.2%}). "
            "Some receipts may not be clearly readable."
        )
    
    # Check for required proofs per category.
    # Skip when an expense voucher summary is present — the voucher IS the proof.
    has_voucher_summary = bool(
        state.get("employee_summary") and
        state.get("employee_summary", {}).get("is_summary")
    )

    if not has_voucher_summary:
        doc_types = {doc.get("type", "") for doc in extracted_text}
        proof_map = {
            "fuel_bill":          ["fuel_bill"],
            "unolo_distance":     ["unolo"],
            "ticket":             ["bus_ticket"],
            # "receipt" = any non-UPI document counts as proof of payment
            "receipt":            ["receipt", "food_bill", "fuel_bill",
                                   "site_expenses", "bus_ticket", "other"],
            "fasttag_screenshot": ["fasttag"],
            "toll_receipt":       ["fasttag"],
            "food_bill":          ["food_bill", "receipt", "other"],
            "hotel_bill":         ["site_expenses", "receipt", "other"],
            "justification":      [],  # never auto-satisfied, but non-blocking
        }

        for cat_key, cat_data in categories.items():
            required = get_required_proofs(cat_key)
            missing_proofs = [
                req for req in required
                if not any(t in doc_types for t in proof_map.get(req, [req]))
            ]
            if missing_proofs:
                policy = REIMBURSEMENT_POLICY.get(cat_key)
                cat_name = policy.name if policy else cat_key.replace("_", " ").title()
                issues.append(
                    f"{cat_name}: Missing proofs - {', '.join(missing_proofs)}"
                )
    
    # Check for date on receipts (skip for voucher-sourced items — dates live in the PDF)
    if VALIDATION_RULES["require_date_on_receipt"] and not has_voucher_summary:
        for expense in expenses:
            if not expense.get("date"):
                issues.append(
                    f"Missing date on receipt: {expense.get('description', 'Unknown')}"
                )
    
    # Check for duplicate receipts (same amount, same date, same category)
    # Skip when a verified expense voucher is present — it is the authoritative source
    # and individual scans intentionally include both UPI screenshots + vendor receipts.
    if VALIDATION_RULES["flag_duplicate_receipts"] and not has_voucher_summary:
        seen = set()
        for expense in expenses:
            key = (
                expense.get("category"),
                expense.get("amount"),
                expense.get("date")
            )
            if key in seen and expense.get("amount", 0) > 0:
                issues.append(
                    f"Possible duplicate: {expense.get('description')} - ₹{expense.get('amount')} on {expense.get('date')}"
                )
            seen.add(key)
    
    # Check for unreasonable amounts
    for expense in expenses:
        amount = expense.get("amount", 0)
        cat = expense.get("category", "other")
        policy = REIMBURSEMENT_POLICY.get(cat)
        
        if policy and policy.per_trip_limit and amount > policy.per_trip_limit * 2:
            issues.append(
                f"Unusually high amount: {expense.get('description')} - ₹{amount}"
            )
    
    # Set validation status
    state["data_validation_issues"] = issues
    state["data_validation_passed"] = len(issues) == 0
    
    return state


def should_revise_data(state: ClaimState) -> Literal["revise", "end"]:
    """
    Determine if data extraction should be revised.
    
    Returns:
        "revise" if critical issues found and revisions available
        "end" to proceed to calculator
    """
    issues = state.get("data_validation_issues", [])
    revision_count = state.get("data_revision_count", 0)
    max_revisions = 2  # Max 2 revisions per stage
    
    # Always end if max revisions reached - this is the safety check
    if revision_count >= max_revisions:
        return "end"
    
    # No issues? End
    if not issues:
        return "end"
    
    # Only revise for critical issues (missing proofs, quality issues)
    critical_keywords = ["missing proof", "low document quality", "cannot read"]
    has_critical = any(
        any(kw in issue.lower() for kw in critical_keywords)
        for issue in issues
    )
    
    if has_critical:
        return "revise"
    
    return "end"
