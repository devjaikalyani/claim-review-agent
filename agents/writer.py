"""
Writer Agent

Generates the final decision report with detailed reasoning.
Handles three distinct cases:
  A. Full approval  — all expenses valid and within policy
  B. Partial approval via voucher — admin rejected some items in the expense voucher
  C. Partial approval via policy  — policy limits or missing proofs caused deductions
"""
import re
from datetime import datetime
from agents.state import ClaimState, DecisionType
from config.policy import GENERAL_POLICY, REIMBURSEMENT_POLICY


def writer_agent(state: ClaimState) -> ClaimState:
    state["current_agent"] = "writer"

    claimed_amount     = state.get("claimed_amount", 0)
    eligible_amount    = state.get("eligible_amount", 0)
    category_eligible  = state.get("category_eligible", {})
    policy_violations  = state.get("policy_violations", [])
    data_issues        = state.get("data_validation_issues", [])
    employee_summary   = state.get("employee_summary") or {}
    has_voucher        = bool(employee_summary.get("is_summary"))
    duplicates_removed = state.get("duplicates_removed", [])
    # True when this is an admin voucher review run through our pipeline
    # (as opposed to an employee submission that attached a SpineHR PDF)
    ai_voucher_review  = bool(state.get("voucher_line_decisions"))

    # Voucher amounts (for display and reasoning)
    voucher_claimed  = float(employee_summary.get("summary_total", 0) or 0)
    voucher_approved = float(employee_summary.get("summary_approved", 0) or 0)
    voucher_rejected = round(voucher_claimed - voucher_approved, 2) if has_voucher else 0.0

    # ── Decision ──────────────────────────────────────────────────────────────
    # Cap eligible at claimed — approved never exceeds what was claimed.
    approved_candidate = min(max(eligible_amount, 0.0), claimed_amount)
    deduction_candidate = round(claimed_amount - approved_candidate, 2)

    if approved_candidate < 0.01:
        # All expenses rejected — no amount to approve
        decision        = DecisionType.REJECTED.value
        approved_amount = 0.0
    elif deduction_candidate < 0.01:
        # Full approval: eligible >= claimed
        decision        = DecisionType.FULL_APPROVAL.value
        approved_amount = claimed_amount
    else:
        decision        = DecisionType.PARTIAL_APPROVAL.value
        approved_amount = approved_candidate

    deduction = claimed_amount - approved_amount

    # ── Determine WHY it's partial (voucher rejection vs policy cap) ─────────
    # "Voucher-based partial" = admin rejected items in the expense voucher
    # (only for legacy/employee-submitted vouchers, NOT our own AI review run)
    voucher_partial = (
        has_voucher
        and not ai_voucher_review
        and decision == DecisionType.PARTIAL_APPROVAL.value
        and voucher_rejected > 0.01
        and not policy_violations   # no policy violations — purely admin decision
    )
    # "Policy-based partial" = policy limits or missing proofs
    policy_partial = (
        decision == DecisionType.PARTIAL_APPROVAL.value
        and (policy_violations or data_issues or not has_voucher)
    )

    # ── Reasoning (shown in UI banner) ────────────────────────────────────────
    reasoning_parts = []

    if decision == DecisionType.REJECTED.value:
        reasoning_parts += [
            "REJECTED",
            "All submitted expenses were rejected. No amount is approved for processing.",
        ]
        all_issues = policy_violations + data_issues
        if all_issues:
            reasoning_parts.append("Reasons for rejection:")
            for issue in all_issues:
                reasoning_parts.append(f"  • {issue}")
        elif state.get("duplicates_removed"):
            reasoning_parts.append("Reasons for rejection:")
            reasoning_parts.append("  • All submitted items identified as duplicates or unsupported.")

    elif decision == DecisionType.FULL_APPROVAL.value:
        if ai_voucher_review:
            reasoning_parts += [
                "FULL APPROVAL",
                f"AI Claim Review System verified all line items against company policy. "
                f"Full amount of Rs.{approved_amount:,.2f} approved.",
            ]
        elif has_voucher:
            reasoning_parts += [
                "FULL APPROVAL",
                f"All expenses approved per verified expense voucher. "
                f"Full amount of Rs.{approved_amount:,.2f} approved.",
            ]
        elif duplicates_removed:
            reasoning_parts += [
                "FULL APPROVAL",
                f"Valid receipts (after removing {len(duplicates_removed)} duplicate(s)) "
                f"confirm the full claimed amount. "
                f"Full amount of Rs.{approved_amount:,.2f} approved.",
            ]
        else:
            reasoning_parts += [
                "FULL APPROVAL",
                f"All submitted expenses are valid and within policy limits. "
                f"Full amount of Rs.{approved_amount:,.2f} approved.",
            ]

    elif ai_voucher_review and decision != DecisionType.FULL_APPROVAL.value:
        line_decisions = state.get("voucher_line_decisions", [])
        rejected_items = [d for d in line_decisions if d.get("decision") == "reject"]
        partial_items  = [d for d in line_decisions if d.get("decision") == "partial"]
        reasoning_parts += [
            f"PARTIAL APPROVAL  Claimed: Rs.{claimed_amount:,.2f} | "
            f"Approved: Rs.{approved_amount:,.2f} | "
            f"Reduction: Rs.{deduction:,.2f}",
            "AI Claim Review System reviewed each line item against company policy.",
        ]
        if rejected_items or partial_items:
            reasoning_parts.append("Reasons for deduction:")
            for d in rejected_items + partial_items:
                head   = d.get("expense_head", "")
                date   = d.get("date", "")
                reason = d.get("reason", "")
                dec    = d.get("decision", "")
                label  = f"{head} ({date})" if date else head
                reasoning_parts.append(f"  • {label}: {dec} — {reason}")
        elif policy_violations:
            reasoning_parts.append("Reasons for deduction:")
            for v in policy_violations:
                reasoning_parts.append(f"  • {v}")

    elif voucher_partial:
        reasoning_parts += [
            f"PARTIAL APPROVAL  Claimed: Rs.{claimed_amount:,.2f} | "
            f"Approved: Rs.{approved_amount:,.2f} | "
            f"Reduction: Rs.{deduction:,.2f}",
            "Reason: Expense voucher partial approval.",
            f"  • Voucher approved Rs.{voucher_approved:,.2f} of Rs.{voucher_claimed:,.2f} claimed",
            f"  • Rs.{voucher_rejected:,.2f} was not covered in the expense voucher",
        ]

    else:  # policy_partial (or mixed)
        reasoning_parts.append(
            f"PARTIAL APPROVAL  Claimed: Rs.{claimed_amount:,.2f} | "
            f"Approved: Rs.{approved_amount:,.2f} | "
            f"Reduction: Rs.{deduction:,.2f}"
        )
        all_issues = policy_violations + data_issues
        reasons_found = False
        if duplicates_removed and not has_voucher:
            reasoning_parts.append("Reasons for partial approval:")
            reasoning_parts.append(
                f"  • {len(duplicates_removed)} duplicate receipt(s) automatically excluded "
                "(UPI screenshots removed where vendor receipt exists; identical submissions "
                "deduplicated to one copy)."
            )
            reasons_found = True
        if all_issues:
            if not reasons_found:
                reasoning_parts.append("Reasons for partial approval:")
            for issue in all_issues:
                reasoning_parts.append(f"  • {issue}")
            reasons_found = True
        if not reasons_found:
            reasoning_parts.append("Reasons for partial approval:")
            reasoning_parts.append("  • Amount exceeds applicable policy limits.")

    # ── Report ────────────────────────────────────────────────────────────────
    report = _generate_report(
        state, decision, approved_amount, reasoning_parts,
        voucher_partial=voucher_partial,
        voucher_claimed=voucher_claimed,
        voucher_approved=voucher_approved,
        voucher_rejected=voucher_rejected,
        ai_voucher_review=ai_voucher_review,
    )

    state["decision"]            = decision
    state["approved_amount"]     = approved_amount
    state["decision_reasoning"]  = "\n".join(reasoning_parts)
    state["final_report"]        = report
    state["processing_complete"] = True
    state["category_breakdown"]  = category_eligible

    # Auto-save voucher decisions to training DB so the system learns from every claim
    if has_voucher and employee_summary.get("voucher_no"):
        try:
            from utils.training_db import save_voucher_decisions
            saved = save_voucher_decisions(
                employee_summary,
                employee_code=state.get("employee_id", ""),
            )
            if saved:
                state["training_rows_saved"] = saved
        except Exception:
            pass

    return state


def _generate_report(
    state: ClaimState,
    decision: str,
    approved_amount: float,
    reasoning: list,
    voucher_partial: bool = False,
    voucher_claimed: float = 0.0,
    voucher_approved: float = 0.0,
    voucher_rejected: float = 0.0,
    ai_voucher_review: bool = False,
) -> str:
    claim_id          = state.get("claim_id", "N/A")
    employee_name     = state.get("employee_name", "N/A")
    employee_id       = state.get("employee_id", "N/A")
    claimed_amount    = state.get("claimed_amount", 0)
    period_start      = state.get("claim_period_start", "N/A")
    period_end        = state.get("claim_period_end", "N/A")
    submission_date   = state.get("submission_date", "")
    category_eligible = state.get("category_eligible", {})
    unolo_distance    = state.get("unolo_distance_km")
    violations        = state.get("policy_violations", [])
    data_issues       = state.get("data_validation_issues", [])
    description         = state.get("claim_description", "")
    employee_summary    = state.get("employee_summary") or {}
    has_voucher         = bool(employee_summary.get("is_summary"))
    duplicates_removed  = state.get("duplicates_removed", [])
    voucher_no        = employee_summary.get("voucher_no", "")
    voucher_period    = employee_summary.get("period", "")
    approval_rate     = (approved_amount / claimed_amount * 100) if claimed_amount > 0 else 0

    if submission_date:
        try:
            submission_date = datetime.fromisoformat(submission_date).strftime("%d %b %Y")
        except Exception:
            pass

    W = 68

    def divider(char="-"):
        return char * W

    def row(label, value, width=24):
        return f"  {label:<{width}}: {value}"

    lines = []

    # ── Header ────────────────────────────────────────────────────────────────
    lines += [
        divider("="),
        "  RITE WATER SOLUTIONS (INDIA) PVT. LTD.",
        "  EXPENSE CLAIM REVIEW REPORT",
        f"  Policy effective: {GENERAL_POLICY.get('policy_effective_date', 'Nov 2023')}",
        divider("="),
        "",
    ]

    # ── Claim Information ─────────────────────────────────────────────────────
    lines += [
        "  CLAIM INFORMATION",
        divider(),
        row("Claim ID",     claim_id),
        row("Employee",     f"{employee_name}  [{employee_id}]"),
        row("Claim Period", f"{period_start}  to  {period_end}"),
        row("Submitted On", submission_date or datetime.now().strftime("%d %b %Y")),
    ]
    if description:
        lines.append(row("Description", description[:60] + ("..." if len(description) > 60 else "")))
    if has_voucher:
        if voucher_no:
            lines.append(row("Expense Voucher No.", voucher_no))
        if voucher_period:
            lines.append(row("Voucher Period", voucher_period))
        if ai_voucher_review:
            lines.append(row("Evidence Source", "Expense voucher + AI policy review"))
        else:
            lines.append(row("Evidence Source", "Verified expense voucher (primary)"))
    else:
        lines.append(row("Evidence Source", "Individual receipt scans only"))
        lines.append(row("Note", "No expense voucher uploaded — amounts based"))
        lines.append(row("",    "on OCR from individual receipts. Admin-level"))
        lines.append(row("",    "approvals/rejections are not reflected here."))
    lines.append("")

    # ── Financial Summary ─────────────────────────────────────────────────────
    deduction = claimed_amount - approved_amount
    lines += [
        "  FINANCIAL SUMMARY",
        divider(),
        row("Amount Claimed",  f"Rs. {claimed_amount:>12,.2f}"),
    ]
    if has_voucher and voucher_claimed > 0 and not ai_voucher_review:
        lines.append(row("Voucher Claimed",  f"Rs. {voucher_claimed:>12,.2f}"))
        lines.append(row("Voucher Approved", f"Rs. {voucher_approved:>12,.2f}"))
        if voucher_rejected > 0.01:
            lines.append(row("Voucher Rejected", f"Rs. {voucher_rejected:>12,.2f}"))
    lines += [
        row("Amount Approved", f"Rs. {approved_amount:>12,.2f}"),
        row("Deduction",       f"Rs. {deduction:>12,.2f}"),
        row("Approval Rate",   f"{approval_rate:>11.1f}%"),
        "",
    ]

    # ── Decision ──────────────────────────────────────────────────────────────
    decision_label = decision.upper().replace("_", " ")
    lines += [
        f"  DECISION: {decision_label}",
        divider(),
    ]
    if decision == DecisionType.REJECTED.value:
        lines.append("  All submitted expenses have been rejected.")
        lines.append("  No amount is approved for processing.")
        all_issues = violations + data_issues
        if all_issues:
            lines.append("")
            lines.append("  Reasons:")
            for issue in all_issues:
                lines.append(f"    - {issue}")
    elif decision == DecisionType.FULL_APPROVAL.value:
        if ai_voucher_review:
            lines.append("  AI Claim Review System verified all line items against company policy.")
        elif has_voucher:
            lines.append("  All expenses are approved per the verified expense voucher.")
        else:
            lines.append("  All submitted expenses are valid and within policy limits.")
        lines.append(f"  Full amount of Rs.{approved_amount:,.2f} is approved for processing.")
    elif ai_voucher_review:
        line_decisions = state.get("voucher_line_decisions", [])
        rejected_items = [d for d in line_decisions if d.get("decision") == "reject"]
        partial_items  = [d for d in line_decisions if d.get("decision") == "partial"]
        lines.append("  AI Claim Review System reviewed each line item against company policy.")
        lines.append(f"  Approved: Rs.{approved_amount:,.2f}  |  Deduction: Rs.{deduction:,.2f}")
        if rejected_items or partial_items:
            lines.append("")
            lines.append("  Items with deductions:")
            for d in rejected_items + partial_items:
                head   = d.get("expense_head", "")
                date   = d.get("date", "")
                reason = d.get("reason", "")
                dec    = d.get("decision", "")
                label  = f"{head} ({date})" if date else head
                lines.append(f"    - {label}: {dec} — {reason}")
    elif voucher_partial:
        lines += [
            "  The expense voucher has been partially approved.",
            f"  Voucher approved Rs.{voucher_approved:,.2f} of Rs.{voucher_claimed:,.2f} claimed.",
            f"  Rs.{voucher_rejected:,.2f} was not covered in the expense voucher.",
        ]
    else:
        lines.append("  Partial approval granted. Certain expenses exceed policy limits")
        lines.append("  or could not be verified against submitted documentation.")
        if deduction > 0:
            lines.append(f"  A deduction of Rs.{deduction:,.2f} has been applied.")
    lines.append("")

    # ── Expense Voucher Table (admin-style line items) ────────────────────────
    expenses = state.get("expenses", [])
    if expenses or category_eligible:
        # Build line-item table from individual expense records
        H = ["Expense Head", "Date", "Remarks", "Claimed (₹)", "Approved (₹)", "Rejected (₹)"]
        col = [22, 12, 24, 12, 12, 12]
        sep = "  " + "-" * (sum(col) + len(col) * 2)

        def _fmt_row(vals):
            return "  " + "  ".join(
                f"{str(v):<{col[i]}}" if i < 3 else f"{str(v):>{col[i]}}"
                for i, v in enumerate(vals)
            )

        lines += ["  EXPENSE VOUCHER", divider(), _fmt_row(H), sep]

        # Per-category eligible lookup for prorating approved amounts to line items
        total_claimed_all  = 0.0
        total_approved_all = 0.0
        total_rejected_all = 0.0

        for expense in expenses:
            cat_key     = expense.get("category", "other")
            cat_data    = category_eligible.get(cat_key, {})
            cat_claimed  = cat_data.get("claimed", 0) or 0
            cat_eligible = cat_data.get("eligible", 0) or 0

            item_claimed = expense.get("amount", 0)
            # Prorate eligible down to item level using category approval ratio
            if cat_claimed > 0:
                ratio = min(cat_eligible / cat_claimed, 1.0)
            else:
                ratio = 0.0
            item_approved = round(item_claimed * ratio, 2)
            item_rejected = round(item_claimed - item_approved, 2)

            exp_head = (expense.get("description") or "Expense")[:22]
            date     = (expense.get("date") or "")[:12]
            remarks  = (expense.get("validation_notes") or "")[:24]

            lines.append(_fmt_row([
                exp_head, date, remarks,
                f"{item_claimed:,.2f}",
                f"{item_approved:,.2f}",
                f"{item_rejected:,.2f}",
            ]))

            total_claimed_all  += item_claimed
            total_approved_all += item_approved
            total_rejected_all += item_rejected

        lines += [
            sep,
            _fmt_row([
                "Gross Payable", "", "",
                f"{total_claimed_all:,.2f}",
                f"{total_approved_all:,.2f}",
                f"{total_rejected_all:,.2f}",
            ]),
            sep,
            "",
        ]

    # ── Category Policy Summary ───────────────────────────────────────────────
    if category_eligible:
        col_w = [26, 12, 12, 12]
        header = (
            f"  {'Category':<{col_w[0]}}"
            f"{'Claimed':>{col_w[1]}}"
            f"{'Approved':>{col_w[2]}}"
            f"{'Policy Cap':>{col_w[3]}}"
        )
        lines += [
            "  CATEGORY POLICY SUMMARY",
            divider(),
            header,
            "  " + divider("-")[2:],
        ]
        for cat_key, cat_data in category_eligible.items():
            policy   = REIMBURSEMENT_POLICY.get(cat_key)
            cat_name = policy.name if policy else cat_key.replace("_", " ").title()
            cat_claimed  = cat_data.get("claimed", 0)
            cat_eligible = cat_data.get("eligible", 0)
            cap          = cat_data.get("policy_limit", 0)
            lines.append(
                f"  {cat_name:<{col_w[0]}}"
                f"Rs.{cat_claimed:>8,.0f}"
                f"  Rs.{cat_eligible:>8,.0f}"
                f"  Rs.{cap:>8,.0f}"
            )
            note = cat_data.get("reasoning", "")
            if note and ("capped" in note.lower() or "distance" in note.lower()):
                lines.append(f"  {'':>{col_w[0]}}  Note: {note}")
        lines.append("")

    # ── Distance Verification ─────────────────────────────────────────────────
    if unolo_distance:
        lines += [
            "  DISTANCE VERIFICATION",
            divider(),
            row("Tracked Distance", f"{unolo_distance:,.1f} km  (Unolo GPS)"),
            "",
        ]

    # ── Policy Notes ──────────────────────────────────────────────────────────
    all_issues = violations + data_issues
    if all_issues:
        lines += ["  POLICY NOTES", divider()]
        for i, issue in enumerate(all_issues, 1):
            lines.append(f"  {i}. {issue}")
        lines.append("")

    # ── Duplicate Receipts Removed (autonomous dedup — no voucher) ────────────
    # Show this section for BOTH full and partial approval so the employee
    # knows duplicates were detected.  For full approval, it's informational
    # (remaining receipts still justify the claimed amount); for partial it's
    # a contributing reason for the deduction.
    if not has_voucher and duplicates_removed:
        dup_amount = 0.0
        lines += ["  DUPLICATE RECEIPTS REMOVED (AUTONOMOUS)", divider()]
        lines.append(
            "  The following receipts were identified as duplicates and excluded."
        )
        lines.append(
            "  UPI screenshots are removed when a vendor receipt exists for the"
        )
        lines.append("  same transaction; identical receipts keep only one copy.")
        lines.append("")
        for i, dup in enumerate(duplicates_removed, 1):
            lines.append(f"  {i}. {dup}")
            # Extract amount — handles both Rs.100 and Rs.100.00
            m = re.search(r"Rs\.([\d,]+(?:\.\d+)?)", dup)
            if m:
                dup_amount += float(m.group(1).replace(",", ""))
        lines.append("")
        if dup_amount > 0:
            lines.append(
                f"  Total excluded (duplicates): Rs.{dup_amount:,.2f}"
            )
            lines.append("")

    # ── Recommendations ───────────────────────────────────────────────────────
    recs = []
    if decision == DecisionType.REJECTED.value:
        recs.append(
            "This claim has been rejected. Review the reasons listed above, "
            "attach the required supporting documents, and resubmit."
        )
    elif ai_voucher_review and deduction > 0:
        line_decisions = state.get("voucher_line_decisions", [])
        rejected_items = [d for d in line_decisions if d.get("decision") == "reject"]
        partial_items  = [d for d in line_decisions if d.get("decision") == "partial"]
        if rejected_items or partial_items:
            recs.append(
                f"Rs.{deduction:,.2f} was not approved by the AI Claim Review System due to "
                "policy violations or missing proof. See the itemised deductions above for details."
            )
    elif voucher_partial:
        recs.append(
            f"Rs.{voucher_rejected:,.2f} was not covered in the expense voucher. "
            "Contact HR or your reporting manager if you believe any item was rejected in error."
        )
    else:
        if not has_voucher and duplicates_removed:
            recs.append(
                f"{len(duplicates_removed)} duplicate receipt(s) were automatically excluded "
                "by the system (UPI screenshots de-duplicated against vendor receipts, and "
                "identical submissions kept once). Upload the official Expense Voucher PDF to "
                "confirm admin's exact approval breakdown."
            )
        elif not has_voucher:
            recs.append(
                "This review is based on individual receipt scans only. For admin-approved "
                "amounts (including any rejections), upload the official Expense Voucher PDF."
            )
        if any("duplicate" in i.lower() for i in all_issues):
            recs.append("Remove duplicate receipts and resubmit the affected items.")
        if unolo_distance is None and "two_wheeler" in category_eligible:
            recs.append("Provide Unolo GPS tracking screenshot to support two-wheeler claim.")
        if any("missing" in i.lower() for i in all_issues):
            recs.append("Attach missing supporting documents for flagged line items.")
        if deduction > 0 and not voucher_partial:
            recs.append(
                f"Unapproved amount Rs.{deduction:,.2f} — resubmit with corrected "
                "documentation to claim the balance."
            )

    if recs:
        lines += ["  RECOMMENDATIONS", divider()]
        for rec in recs:
            lines.append(f"  - {rec}")
        lines.append("")

    # ── Footer ────────────────────────────────────────────────────────────────
    lines += [
        divider("="),
        row("Report Generated", datetime.now().strftime("%d %b %Y  %H:%M:%S"), width=24),
        row("Reviewed by",      "AI Claim Review System",                       width=24),
        row("Company",          "Rite Water Solutions (India) Pvt. Ltd.",       width=24),
        divider("="),
    ]

    return "\n".join(lines)
