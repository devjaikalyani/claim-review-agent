"""
Shared structured report renderer.
Used by both the employee result page (app.py) and the admin review page
(admin_dashboard.py) so both show an identical report layout.
"""
import html as _html
import streamlit as st


def render_structured_report(
    result:             dict,
    claim_id:           str,
    employee_name:      str,
    employee_id:        str,
    claimed_amount:     float,
    approved_amount:    float,
    decision:           str,
    category_eligible:  dict,
    policy_violations:  list,
    duplicates_removed: list,
    unolo_distance,
    period_start:       str,
    period_end:         str,
) -> None:
    """Render the claim review report as a structured, themed card."""
    deduction      = claimed_amount - approved_amount
    approval_rate  = (approved_amount / claimed_amount * 100) if claimed_amount > 0 else 0
    is_full        = "FULL" in decision.upper()
    decision_label = decision.replace("_", " ").title()

    emp_summary      = result.get("employee_summary") or {}
    has_voucher      = bool(emp_summary.get("is_summary"))
    voucher_claimed  = float(emp_summary.get("summary_total",    0) or 0)
    voucher_approved = float(emp_summary.get("summary_approved", 0) or 0)
    voucher_rejected = round(voucher_claimed - voucher_approved, 2)
    voucher_no       = emp_summary.get("voucher_no", "")
    voucher_period   = emp_summary.get("period", "")
    data_issues      = result.get("data_validation_issues", []) or []
    all_issues       = (policy_violations or []) + data_issues

    # ── Header bar ────────────────────────────────────────────────────────────
    st.markdown(
        '<div class="rpt-header-bar">'
        '<div class="rpt-company">Rite Water Solutions (India) Pvt. Ltd.</div>'
        '<div class="rpt-doc-label">Expense Claim Review Report</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Body wrapper open ─────────────────────────────────────────────────────
    st.markdown('<div class="rpt-body">', unsafe_allow_html=True)

    # ── Two-column: Claim Info | Financial Summary ────────────────────────────
    ci_col, fs_col = st.columns(2)

    with ci_col:
        st.markdown('<div class="rpt-block-title">Claim Information</div>', unsafe_allow_html=True)
        info_rows = (
            f"<tr><td>Claim ID</td><td><code>{_html.escape(claim_id)}</code></td></tr>"
            f"<tr><td>Employee</td><td>{_html.escape(employee_name)}"
            f" &nbsp;<span style='opacity:.55'>[{_html.escape(employee_id)}]</span></td></tr>"
            f"<tr><td>Period</td><td>{_html.escape(period_start)} &rarr; {_html.escape(period_end)}</td></tr>"
        )
        if voucher_no:
            info_rows += f"<tr><td>Voucher No.</td><td><code>{_html.escape(voucher_no)}</code></td></tr>"
        if voucher_period:
            info_rows += f"<tr><td>Voucher Period</td><td>{_html.escape(voucher_period)}</td></tr>"
        evidence = "Verified expense voucher (primary)" if has_voucher else "Individual receipt scans only"
        info_rows += f"<tr><td>Evidence</td><td style='font-style:italic;opacity:.7'>{evidence}</td></tr>"
        st.markdown(f'<table class="rpt-kv">{info_rows}</table>', unsafe_allow_html=True)

    with fs_col:
        st.markdown('<div class="rpt-block-title">Financial Summary</div>', unsafe_allow_html=True)
        fin_rows = f"<tr><td>Amount Claimed</td><td><strong>Rs.{claimed_amount:,.2f}</strong></td></tr>"
        if has_voucher and voucher_claimed > 0:
            fin_rows += (
                f"<tr><td>Voucher Claimed</td><td>Rs.{voucher_claimed:,.2f}</td></tr>"
                f"<tr><td>Voucher Approved</td><td>Rs.{voucher_approved:,.2f}</td></tr>"
            )
            if voucher_rejected > 0.01:
                fin_rows += f"<tr><td>Voucher Rejected</td><td style='color:#ef4444'>Rs.{voucher_rejected:,.2f}</td></tr>"
        deduction_color = "color:#ef4444" if deduction > 0.01 else ""
        approved_color  = "color:#22c55e" if is_full else "color:#fbbf24"
        fin_rows += (
            f"<tr><td>Amount Approved</td><td style='{approved_color}'>"
            f"<strong>Rs.{approved_amount:,.2f}</strong></td></tr>"
            f"<tr><td>Deduction</td><td style='{deduction_color}'>Rs.{deduction:,.2f}</td></tr>"
            f"<tr><td>Approval Rate</td><td><strong>{approval_rate:.1f}%</strong></td></tr>"
        )
        st.markdown(f'<table class="rpt-kv">{fin_rows}</table>', unsafe_allow_html=True)

    # ── Decision badge ────────────────────────────────────────────────────────
    badge_grad = (
        "linear-gradient(135deg,#15803d,#22c55e)"
        if is_full else
        "linear-gradient(135deg,#b45309,#f59e0b)"
    )
    st.markdown(
        f'<div class="rpt-decision-badge" style="background:{badge_grad}">{decision_label}</div>',
        unsafe_allow_html=True,
    )

    # ── Expense breakdown table ───────────────────────────────────────────────
    if category_eligible:
        _TYPE_NAMES = {
            "two_wheeler":    "Two Wheeler / Bike",
            "car_conveyance": "Car Conveyance",
            "bus_travel":     "Bus / Train Travel",
            "fasttag":        "FASTag / Toll",
            "food":           "Food / Meals",
            "hotel":          "Hotel / Accommodation",
            "site_expenses":  "Site Expenses",
            "other":          "Other Expenses",
        }
        rows_html = ""
        for cat_key, cat_data in category_eligible.items():
            cat_name    = _TYPE_NAMES.get(cat_key, cat_key.replace("_", " ").title())
            cat_claimed = float(cat_data.get("claimed", 0) or 0)
            cat_elig    = float(cat_data.get("eligible", 0) or 0)
            cap         = float(cat_data.get("policy_limit", 0) or 0)
            note        = cat_data.get("reasoning", "")
            is_capped   = cat_elig < cat_claimed - 0.01
            elig_class  = "rpt-td-reduced" if is_capped else "rpt-td-ok"
            cap_tag     = '<span class="rpt-capped">capped</span>' if is_capped else ""
            rows_html += (
                f"<tr>"
                f"<td>{_html.escape(cat_name)}</td>"
                f"<td>Rs.{cat_claimed:,.0f}</td>"
                f'<td class="{elig_class}">Rs.{cat_elig:,.0f}{cap_tag}</td>'
                f"<td>Rs.{cap:,.0f}</td>"
                f"</tr>"
            )
            if note and is_capped:
                rows_html += f'<tr class="rpt-note-row"><td colspan="4">{_html.escape(note)}</td></tr>'

        st.markdown('<div class="rpt-block-title" style="margin-top:20px">Expense Breakdown</div>', unsafe_allow_html=True)
        st.markdown(
            f'<table class="rpt-table">'
            f'<thead><tr><th>Category</th><th>Claimed</th><th>Approved</th><th>Policy Cap</th></tr></thead>'
            f'<tbody>{rows_html}</tbody>'
            f'</table>',
            unsafe_allow_html=True,
        )

    # ── Distance verification ─────────────────────────────────────────────────
    if unolo_distance:
        st.info(f"GPS distance (Unolo): **{unolo_distance:,.1f} km**")

    # ── Policy notes ──────────────────────────────────────────────────────────
    if all_issues:
        st.markdown('<div class="rpt-block-title" style="margin-top:20px">Policy Notes</div>', unsafe_allow_html=True)
        for issue in all_issues:
            st.warning(issue, icon=None)

    # ── Duplicates removed ────────────────────────────────────────────────────
    if duplicates_removed and not has_voucher:
        st.markdown('<div class="rpt-block-title" style="margin-top:20px">Duplicates Auto-Removed</div>', unsafe_allow_html=True)
        for d in duplicates_removed:
            st.caption(f"• {d}")

    # ── Body wrapper close ────────────────────────────────────────────────────
    st.markdown('</div>', unsafe_allow_html=True)
