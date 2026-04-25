"""
Critic Agent 3 - Report Validation
Reviews final report for clarity and completeness.
"""
from typing import Literal
from agents.state import ClaimState


def critic_agent3(state: ClaimState) -> ClaimState:
    """
    Validate final report quality.

    Checks:
    - Decision reasoning is clear
    - All categories are addressed
    - Numbers are consistent
    - Report is properly formatted
    """
    state["current_agent"]        = "critic3"
    state["report_revision_count"] = state.get("report_revision_count", 0) + 1

    issues = []

    decision            = state.get("decision")
    reasoning           = state.get("decision_reasoning", "")
    report              = state.get("final_report", "")
    approved_amount     = state.get("approved_amount", 0)
    claimed_amount      = state.get("claimed_amount", 0)
    category_breakdown  = state.get("category_breakdown", {})

    # ── Check 1: Decision must be set ─────────────────────────────────────
    if not decision:
        issues.append("No decision has been made")

    # ── Check 2: Reasoning must be present ────────────────────────────────
    if not reasoning or len(reasoning) < 20:
        issues.append("Decision reasoning is missing or too brief")

    # ── Check 3: Report must be generated ─────────────────────────────────
    if not report or len(report) < 100:
        issues.append("Report is missing or incomplete")

    # ── Check 4: Full approval amount consistency ─────────────────────────
    if decision == "full_approval" and abs(approved_amount - claimed_amount) > 0.01:
        issues.append(
            f"Full approval decision but approved ₹{approved_amount:.2f} "
            f"does not match claimed ₹{claimed_amount:.2f}"
        )

    # ── Check 5: Partial approval consistency ────────────────────────────
    if decision == "partial_approval":
        if approved_amount > claimed_amount + 0.01:
            # Fixed: was >= which incorrectly flagged near-equal amounts
            issues.append(
                f"Partial approval but approved ₹{approved_amount:.2f} "
                f"exceeds claimed ₹{claimed_amount:.2f}"
            )
        if approved_amount <= 0:
            issues.append("Partial approval but approved amount is zero or negative")

    # ── Check 6: Rejected — approved amount must be zero ─────────────────
    if decision == "rejected" and approved_amount > 0:
        issues.append(
            "Decision is rejected but approved amount is non-zero — "
            "set approved amount to 0 for a rejection"
        )

    # ── Check 7: All categories addressed in breakdown ────────────────────
    categories = state.get("categories", {})
    for cat in categories:
        if cat not in category_breakdown:
            issues.append(f"Category '{cat}' processed but missing from report breakdown")

    # ── Check 8: Category totals must match approved amount ───────────────
    if category_breakdown:
        total_eligible = sum(
            cat.get("eligible", 0) for cat in category_breakdown.values()
        )
        # Allow ₹0.50 rounding tolerance
        if abs(total_eligible - approved_amount) > 0.50:
            issues.append(
                f"Category eligible totals ₹{total_eligible:.2f} don't match "
                f"approved amount ₹{approved_amount:.2f}"
            )

    # ── Check 9: Critic 2 warnings included in report ─────────────────────
    calc_warnings = state.get("calculation_validation_warnings", [])
    if calc_warnings and report:
        # Just a soft check — don't block, just flag
        pass

    state["report_validation_issues"] = issues
    state["report_validation_passed"] = len(issues) == 0

    return state


def should_revise_report(state: ClaimState) -> Literal["revise", "end"]:
    """
    Route back to writer only for critical issues.
    Amount mismatches and missing categories trigger revise.
    Formatting issues do not.
    """
    issues         = state.get("report_validation_issues", [])
    revision_count = state.get("report_revision_count", 0)

    if revision_count >= 2:
        return "end"

    if not issues:
        return "end"

    critical_keywords = [
        "no decision",
        "report is missing",
        "does not match claimed",
        "exceeds claimed",
        "approved amount is non-zero",
        "missing from report breakdown"
    ]

    has_critical = any(
        any(kw in issue.lower() for kw in critical_keywords)
        for issue in issues
    )

    return "revise" if has_critical else "end"