"""
Critic Agent 2 — Calculation Validation

Verifies calculator output against:
  1. Policy rules (eligible never exceeds claimed)
  2. Employee summary PDF (if provided) — cross-checks category amounts
  3. Distance sanity checks
"""
from typing import Literal
from agents.state import ClaimState
from config.policy import DISTANCE_RULES


def critic_agent2(state: ClaimState) -> ClaimState:
    state["current_agent"]       = "critic2"
    state["calc_revision_count"] = state.get("calc_revision_count", 0) + 1

    issues:   list[str] = []
    warnings: list[str] = []

    claimed_amount    = state.get("claimed_amount", 0.0)
    eligible_amount   = state.get("eligible_amount", 0.0)
    total_extracted   = state.get("total_extracted_amount", 0.0)
    category_eligible = state.get("category_eligible", {})
    policy_violations = state.get("policy_violations", [])
    employee_summary  = state.get("employee_summary")  # From summary PDF

    category_claimed_total = state.get("category_claimed_total") or sum(
        cat.get("claimed", 0.0) for cat in category_eligible.values()
    )
    reconciliation_note = state.get("reconciliation_note", "")

    # ── Check 1: Eligible must not exceed claimed (HARD ERROR) ────────────
    if eligible_amount > claimed_amount + 0.01:
        issues.append(
            f"Calculation error: eligible ₹{eligible_amount:.2f} "
            f"exceeds claimed ₹{claimed_amount:.2f}. Re-run calculator."
        )

    # ── Check 2: Cross-check against employee summary PDF ─────────────────
    if employee_summary and employee_summary.get("is_summary"):
        # Use the admin-approved total for validation — this is the company's
        # official decision and is what our eligible amount should match.
        summary_approved   = employee_summary.get("summary_approved") or employee_summary.get("summary_total", 0.0)
        summary_categories = employee_summary.get("categories", {})

        # Compare calculator's category amounts vs summary approved amounts
        for cat, summary_data in summary_categories.items():
            summary_cat_approved = float(summary_data.get("approved") or summary_data.get("claimed", 0.0))
            calc_data            = category_eligible.get(cat, {})
            calc_claimed         = calc_data.get("claimed", 0.0)
            calc_eligible        = calc_data.get("eligible", 0.0)

            # Flag if calculator missed a category present in summary
            if summary_cat_approved > 0 and calc_claimed == 0:
                warnings.append(
                    f"Category '{cat}' has ₹{summary_cat_approved:.2f} approved in "
                    f"employee summary but ₹0 in calculator — receipts may be missing."
                )

            # Flag if eligible significantly less than what admin approved
            if summary_cat_approved > 0 and calc_eligible < summary_cat_approved * 0.5:
                warnings.append(
                    f"Category '{cat}': admin approved ₹{summary_cat_approved:.2f} "
                    f"but only ₹{calc_eligible:.2f} eligible per policy."
                )

        # Compare total eligible vs voucher approved total
        if summary_approved > 0:
            diff     = abs(eligible_amount - summary_approved)
            diff_pct = diff / summary_approved if summary_approved > 0 else 0

            if eligible_amount > summary_approved + 0.01:
                issues.append(
                    f"Calculation error: eligible ₹{eligible_amount:.2f} "
                    f"exceeds admin-approved voucher total ₹{summary_approved:.2f}."
                )
            elif diff_pct > 0.20:
                warnings.append(
                    f"Large gap between eligible ₹{eligible_amount:.2f} and "
                    f"admin-approved voucher total ₹{summary_approved:.2f} "
                    f"({diff_pct:.0%} difference) — verify policy application."
                )
            else:
                warnings.append(
                    f"✅ Calculator eligible ₹{eligible_amount:.2f} vs "
                    f"admin-approved voucher total ₹{summary_approved:.2f} — "
                    f"difference ₹{diff:.2f} ({diff_pct:.1%})."
                )

    # ── Check 3: Two-wheeler daily distance sanity ────────────────────────
    unolo_distance = state.get("unolo_distance_km")
    if unolo_distance and "two_wheeler" in category_eligible:
        max_daily = DISTANCE_RULES.get("max_daily_distance_km", 200)
        days      = _calculate_days(
            state.get("claim_period_start", ""),
            state.get("claim_period_end", "")
        ) or 30
        daily_avg = unolo_distance / days
        if daily_avg > max_daily:
            issues.append(
                f"High daily average distance: {daily_avg:.1f} km/day "
                f"(threshold: {max_daily} km/day). Verify Unolo data."
            )

    # ── Check 4: Non-zero eligible when valid expenses exist ──────────────
    if total_extracted > 0 and eligible_amount == 0 and not policy_violations:
        issues.append(
            "Eligible amount is ₹0 despite extracted expenses with no "
            "policy violations — review calculator logic."
        )

    # ── Check 5: Unusually low approval rate ─────────────────────────────
    # Skip when eligible already matches the admin-approved voucher total —
    # a "low" rate just means admin rejected items, which is a valid outcome.
    eligible_matches_voucher = (
        employee_summary
        and employee_summary.get("is_summary")
        and abs(eligible_amount - float(employee_summary.get("summary_approved") or 0)) < 0.01
    )
    if claimed_amount > 0 and not eligible_matches_voucher:
        approval_rate = eligible_amount / claimed_amount
        if approval_rate < 0.5:
            warnings.append(
                f"Low approval rate: {approval_rate:.1%} of claimed amount eligible. "
                "Verify all receipts were processed."
            )

    state["calculation_validation_issues"]   = issues
    state["calculation_validation_warnings"] = warnings
    state["calculation_validation_passed"]   = len(issues) == 0

    return state


def should_revise_calculation(state: ClaimState) -> Literal["revise", "end"]:
    issues         = state.get("calculation_validation_issues", [])
    revision_count = state.get("calc_revision_count", 0)

    if revision_count >= 2:
        return "end"
    if not issues:
        return "end"

    hard_errors = [i for i in issues if i.lower().startswith("calculation error")]
    return "revise" if hard_errors else "end"


def _calculate_days(start_date: str, end_date: str) -> int:
    from datetime import datetime
    if not start_date or not end_date:
        return 0
    try:
        start = datetime.fromisoformat(start_date.split("T")[0])
        end   = datetime.fromisoformat(end_date.split("T")[0])
        return max((end - start).days + 1, 1)
    except Exception:
        return 0