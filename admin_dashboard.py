"""
Admin Dashboard

Two pages:
  render_dashboard_page()    — lists all claims, summary stats, filter tabs
  render_admin_review_page() — line-item review + editable admin decisions
                               Saves overrides to DB and training DB on submit.
"""
import json
import uuid
import streamlit as st
import pandas as pd
from datetime import datetime, date


_PAGE_SIZE = 10   # claims per page in the admin list

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_db():
    from utils.db import get_db
    return get_db()


def _fmt_inr(v):
    try:
        return f"Rs.{float(v):,.0f}" if v is not None else "—"
    except Exception:
        return "—"


def _status_label(status: str) -> str:
    if status == "pending_review":
        return "Pending Review"
    if status == "admin_reviewed":
        return "Reviewed"
    return status or "—"


def _period_label(start: str, end: str) -> str:
    def _fmt(s):
        try:
            return datetime.fromisoformat(s.split("T")[0]).strftime("%d %b %y")
        except Exception:
            return s or "—"
    return f"{_fmt(start)} - {_fmt(end)}"


# ── Dashboard page ────────────────────────────────────────────────────────────

def _count_test_claims(db) -> int:
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    cur  = conn.execute(
        "SELECT COUNT(*) FROM claims WHERE id LIKE 'TEST-%' OR id LIKE 'VCH-TEST-%'"
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


def _delete_test_claims(db) -> int:
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    cur  = conn.execute(
        "DELETE FROM claims WHERE id LIKE 'TEST-%' OR id LIKE 'VCH-TEST-%'"
    )
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


def render_dashboard_page() -> None:
    st.markdown("## Admin Dashboard")

    db    = _get_db()
    stats = db.get_claim_stats()

    # Summary cards — row 1
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Claims",         stats.get("total", 0))
    c2.metric("Pending Review",       stats.get("pending", 0))
    c3.metric("Total Claimed",        _fmt_inr(stats.get("total_claimed")))
    c4.metric("Total Final Approved", _fmt_inr(stats.get("total_final_approved")))

    # Summary cards — row 2
    total_claimed = stats.get("total_claimed") or 0
    total_final   = stats.get("total_final_approved") or 0
    approval_rate = round(total_final / total_claimed * 100, 1) if total_claimed else None
    overrides     = int(stats.get("total_overrides") or 0)
    avg_days      = stats.get("avg_review_days")

    r1, r2, r3 = st.columns(3)
    r1.metric("Approval Rate",    f"{approval_rate:.1f}%" if approval_rate is not None else "—")
    r2.metric("Admin Overrides",  overrides)
    r3.metric("Avg. Review Time", f"{avg_days:.1f} days" if avg_days is not None else "—")

    # ── Clear test claims ──────────────────────────────────────────
    test_count = _count_test_claims(db)
    if test_count > 0:
        st.warning(f"{test_count} test claim(s) in the database (IDs starting with TEST- or VCH-TEST-).")
        if st.button(f"🗑 Clear {test_count} test claim(s)", key="btn_clear_test_claims"):
            deleted = _delete_test_claims(db)
            st.success(f"Deleted {deleted} test claim(s).")
            st.rerun()

    st.markdown("---")

    tab_all, tab_pending, tab_reviewed, tab_voucher = st.tabs(
        ["All Claims", "Pending Review", "Reviewed", "Voucher Review"]
    )

    for tab, status_filter, tab_key in [
        (tab_all,      "all",            "all"),
        (tab_pending,  "pending_review", "pend"),
        (tab_reviewed, "admin_reviewed", "rev"),
    ]:
        with tab:
            _render_claims_table(db, status_filter, tab_key)

    with tab_voucher:
        _render_voucher_review_tab()


def _render_claims_table(db, status_filter: str, tab_key: str = "all") -> None:
    pg_key = f"pg_{tab_key}"
    if pg_key not in st.session_state:
        st.session_state[pg_key] = 0

    total       = db.count_claims(status_filter=status_filter)
    total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page        = min(st.session_state[pg_key], total_pages - 1)
    st.session_state[pg_key] = page
    offset      = page * _PAGE_SIZE

    claims = db.get_all_claims(status_filter=status_filter, limit=_PAGE_SIZE, offset=offset)

    if not claims:
        st.info("No claims found.")
        return

    for claim in claims:
        claim_id  = claim["id"]
        name      = claim.get("employee_name") or claim.get("employee_id", "—")
        period    = _period_label(
            claim.get("claim_period_start", ""),
            claim.get("claim_period_end", ""),
        )
        claimed   = claim.get("claimed_amount", 0)
        sys_appvd = claim.get("approved_amount", 0)
        adm_appvd = claim.get("admin_approved_amount")
        status    = claim.get("admin_status", "pending_review")
        submitted = (claim.get("submission_date") or claim.get("created_at") or "")[:10]

        with st.container():
            col_info, col_amounts, col_action = st.columns([4, 3, 2])

            with col_info:
                st.markdown(f"**{name}**")
                age_str = ""
                if submitted and status == "pending_review":
                    try:
                        age_days = (date.today() - date.fromisoformat(submitted)).days
                        age_str = f"  ·  {age_days}d pending"
                    except Exception:
                        pass
                st.caption(f"{period}  |  Submitted {submitted}{age_str}")
                st.caption(f"ID: `{claim_id}`")

            with col_amounts:
                st.markdown(
                    f"Claimed: **{_fmt_inr(claimed)}**  |  "
                    f"System: **{_fmt_inr(sys_appvd)}**"
                )
                if adm_appvd is not None:
                    delta     = float(adm_appvd) - float(sys_appvd or 0)
                    delta_str = (
                        f"  (+{_fmt_inr(delta)})"  if delta > 0 else
                        f"  ({_fmt_inr(delta)})"   if delta < 0 else ""
                    )
                    st.markdown(f"Admin: **{_fmt_inr(adm_appvd)}**{delta_str}")
                st.caption(_status_label(status))

            with col_action:
                btn_label = "Review" if status == "pending_review" else "View / Edit"
                if st.button(btn_label, key=f"btn_{tab_key}_{claim_id}", width="stretch"):
                    st.session_state["page"]            = "admin_review"
                    st.session_state["review_claim_id"] = claim_id
                    st.rerun()

            st.divider()

    # Pagination controls
    if total_pages > 1:
        pc_left, pc_mid, pc_right = st.columns([1, 3, 1])
        with pc_left:
            if st.button("← Prev", key=f"prev_{tab_key}",
                         disabled=(page == 0), use_container_width=True):
                st.session_state[pg_key] = page - 1
                st.rerun()
        with pc_mid:
            st.caption(
                f"Page {page + 1} of {total_pages}  ·  {total} claim(s) total",
                help=f"Showing {offset + 1}–{min(offset + _PAGE_SIZE, total)} of {total}",
            )
        with pc_right:
            if st.button("Next →", key=f"next_{tab_key}",
                         disabled=(page >= total_pages - 1), use_container_width=True):
                st.session_state[pg_key] = page + 1
                st.rerun()


# ── Report tab renderer ───────────────────────────────────────────────────────

def _render_report_tab(claim: dict) -> None:
    import re
    from utils.report_renderer import render_structured_report

    report = claim.get("final_report", "")
    if not report:
        st.info("No report saved for this claim.")
        return

    # Extract policy notes and duplicates from the stored report text
    def _extract_section(text: str, heading: str) -> list:
        pattern = rf"  {re.escape(heading)}\n[-=]{{10,}}(.*?)(?=\n  [A-Z]{{3}}|\Z)"
        m = re.search(pattern, text, re.DOTALL)
        if not m:
            return []
        block = m.group(1).strip()
        lines = [l.strip().lstrip("-•123456789. ").strip() for l in block.splitlines() if l.strip()]
        return [l for l in lines if l and not l.startswith("=") and not l.startswith("-" * 5)]

    policy_notes       = _extract_section(report, "POLICY NOTES")
    duplicates_removed = _extract_section(report, "DUPLICATE RECEIPTS REMOVED")

    cat_eligible = {}
    try:
        raw = claim.get("category_eligible_json")
        if raw:
            cat_eligible = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        pass

    render_structured_report(
        result={},
        claim_id=claim.get("id", ""),
        employee_name=claim.get("employee_name") or claim.get("employee_id", "—"),
        employee_id=claim.get("employee_id", ""),
        claimed_amount=float(claim.get("claimed_amount") or 0),
        approved_amount=float(claim.get("approved_amount") or 0),
        decision=claim.get("decision") or "",
        category_eligible=cat_eligible,
        policy_violations=policy_notes,
        duplicates_removed=duplicates_removed,
        unolo_distance=None,
        period_start=claim.get("claim_period_start", ""),
        period_end=claim.get("claim_period_end", ""),
    )

    reasoning = claim.get("decision_reasoning", "")
    if reasoning:
        with st.expander("AI Decision Reasoning", expanded=False):
            st.caption(reasoning)


# ── Admin review page ─────────────────────────────────────────────────────────

def render_admin_review_page() -> None:
    claim_id = st.session_state.get("review_claim_id")
    if not claim_id:
        st.error("No claim selected.")
        return

    db    = _get_db()
    claim = db.get_claim(claim_id)
    if not claim:
        st.error(f"Claim {claim_id} not found.")
        return

    name   = claim.get("employee_name") or claim.get("employee_id", "—")
    period = _period_label(claim.get("claim_period_start", ""), claim.get("claim_period_end", ""))
    st.markdown(f"## {name}  —  {period}")

    # Compute avg AI confidence from stored line items
    _items_for_conf = db.get_line_items(claim_id)
    _confs = [float(it["system_confidence"]) for it in _items_for_conf
              if it.get("system_confidence") is not None]
    avg_conf = round(sum(_confs) / len(_confs) * 100) if _confs else None

    h1, h2, h3, h4, h5 = st.columns(5)
    h1.metric("Claimed",         _fmt_inr(claim.get("claimed_amount")))
    h2.metric("System Approved", _fmt_inr(claim.get("approved_amount")))
    h3.metric(
        "Admin Approved",
        _fmt_inr(claim.get("admin_approved_amount"))
        if claim.get("admin_approved_amount") is not None else "—",
    )
    h4.metric("AI Confidence",   f"{avg_conf}%" if avg_conf is not None else "—")
    h5.metric("Status",          _status_label(claim.get("admin_status", "pending_review")))

    cat_eligible = {}
    try:
        raw = claim.get("category_eligible_json")
        if raw:
            cat_eligible = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        pass

    if cat_eligible:
        claimed_total = float(claim.get("claimed_amount") or 1)
        with st.expander("Category Breakdown", expanded=False):
            hdr = st.columns([3, 2, 2])
            hdr[0].markdown("**Category**")
            hdr[1].markdown("**Eligible**")
            hdr[2].markdown("**% of Claimed**")
            def _elig_val(v):
                if isinstance(v, dict):
                    return float(v.get("eligible") or 0)
                return float(v or 0)

            for cat, eligible in sorted(cat_eligible.items(), key=lambda x: -_elig_val(x[1])):
                elig_amount = _elig_val(eligible)
                row = st.columns([3, 2, 2])
                row[0].write(str(cat).replace("_", " ").title())
                row[1].write(_fmt_inr(elig_amount))
                row[2].write(f"{elig_amount / claimed_total * 100:.1f}%")

    st.markdown("---")

    tab_items, tab_report = st.tabs(["Expense Line Items", "AI Report"])

    with tab_items:
        _render_line_items_editor(db, claim, claim_id)

    with tab_report:
        _render_report_tab(claim)


def _render_line_items_editor(db, claim: dict, claim_id: str) -> None:
    line_items = db.get_line_items(claim_id)

    if not line_items:
        st.info(
            "No line items saved for this claim. "
            "Claims submitted before the dashboard feature was added will not have line items."
        )
        return

    st.caption(
        "Review the system's decisions below. "
        "Change Admin Decision, Approved (Rs.), and Reason for any item, "
        "then click Save Admin Decisions."
    )

    # ── Init session state with system defaults on first render ───
    for i, item in enumerate(line_items):
        if f"dec_{claim_id}_{i}" not in st.session_state:
            st.session_state[f"dec_{claim_id}_{i}"] = item.get("system_decision", "approve")
        if f"amt_{claim_id}_{i}" not in st.session_state:
            st.session_state[f"amt_{claim_id}_{i}"] = float(item.get("system_approved_amount") or 0)
        if f"rsn_{claim_id}_{i}" not in st.session_state:
            st.session_state[f"rsn_{claim_id}_{i}"] = item.get("system_reason", "") or ""

    COL_W = [3.0, 1, 1.2, 0.85, 0.75, 0.75, 1.15, 0.9, 2.4]

    # ── Column headers ─────────────────────────────────────────────
    hdr_cols = st.columns(COL_W)
    for col, label in zip(hdr_cols, [
        "Description", "Date", "Category", "Claimed (Rs.)",
        "System", "AI Conf.", "Admin Decision", "Approved (Rs.)", "Reason / Notes",
    ]):
        col.markdown(
            f"<p style='margin:0 0 2px;font-size:0.76rem;font-weight:700;"
            f"color:#6b7280;text-transform:uppercase;letter-spacing:0.05em'>{label}</p>",
            unsafe_allow_html=True,
        )
    st.divider()

    # ── One row per line item ──────────────────────────────────────
    changed_count = 0
    DEC_COLOR = {"approve": "#16a34a", "reject": "#dc2626", "partial": "#d97706"}

    for i, item in enumerate(line_items):
        sys_dec      = item.get("system_decision", "approve")
        sys_approved = float(item.get("system_approved_amount") or 0)
        claimed      = float(item.get("claimed_amount") or 0)
        category     = (item.get("category") or "").replace("_", " ").title()
        description  = item.get("description", "")
        date_str     = item.get("date", "") or "—"
        dec_color    = DEC_COLOR.get(sys_dec, "#6b7280")

        row = st.columns(COL_W)
        row[0].markdown(
            f"<div style='padding:6px 4px 6px 0;font-size:0.875rem;line-height:1.45;"
            f"word-break:break-word'>{description}</div>",
            unsafe_allow_html=True,
        )
        row[1].markdown(
            f"<div style='padding:6px 2px;font-size:0.875rem'>{date_str}</div>",
            unsafe_allow_html=True,
        )
        row[2].markdown(
            f"<div style='padding:6px 2px;font-size:0.875rem'>{category}</div>",
            unsafe_allow_html=True,
        )
        row[3].markdown(
            f"<div style='padding:6px 2px;font-size:0.875rem;text-align:right'>"
            f"₹{claimed:,.2f}</div>",
            unsafe_allow_html=True,
        )
        row[4].markdown(
            f"<div style='padding:6px 2px;font-size:0.82rem;font-weight:700;"
            f"color:{dec_color}'>{sys_dec}</div>",
            unsafe_allow_html=True,
        )
        # Confidence indicator
        raw_conf = item.get("system_confidence")
        if raw_conf is not None:
            conf_pct = int(float(raw_conf) * 100)
            conf_color = (
                "#16a34a" if conf_pct >= 90 else
                "#d97706" if conf_pct >= 70 else
                "#dc2626"
            )
            row[5].markdown(
                f"<div style='padding:6px 2px;font-size:0.82rem;font-weight:700;"
                f"color:{conf_color}'>{conf_pct}%</div>",
                unsafe_allow_html=True,
            )
        else:
            row[5].markdown(
                "<div style='padding:6px 2px;font-size:0.82rem;color:#6b7280'>—</div>",
                unsafe_allow_html=True,
            )
        with row[6]:
            st.selectbox(
                "Admin Decision", ["approve", "reject", "partial"],
                key=f"dec_{claim_id}_{i}",
                label_visibility="collapsed",
            )
        with row[7]:
            st.number_input(
                "Approved Rs.", min_value=0.0, format="%.2f",
                key=f"amt_{claim_id}_{i}",
                label_visibility="collapsed",
            )
        with row[8]:
            st.text_area(
                "Reason",
                key=f"rsn_{claim_id}_{i}",
                label_visibility="collapsed",
                placeholder="reason…",
                height=68,
            )

        cur_dec = st.session_state.get(f"dec_{claim_id}_{i}", sys_dec)
        cur_amt = st.session_state.get(f"amt_{claim_id}_{i}", sys_approved)
        if cur_dec != sys_dec or cur_amt != sys_approved:
            changed_count += 1

        if i < len(line_items) - 1:
            st.markdown(
                "<hr style='margin:2px 0;border:none;border-top:1px solid rgba(0,0,0,0.06)'>",
                unsafe_allow_html=True,
            )

    if changed_count:
        st.warning(f"{changed_count} item(s) changed from system decision. Review before saving.")

    st.markdown("---")
    notes_col, btn_col = st.columns([5, 2])
    admin_notes = notes_col.text_area(
        "Overall notes (optional)",
        placeholder="e.g. Hotel bill approved as per manager confirmation.",
        key=f"notes_{claim_id}",
        height=68,
    )

    with btn_col:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Save Admin Decisions", type="primary", width="stretch"):
            edited_rows = []
            for i, item in enumerate(line_items):
                sys_dec = item.get("system_decision", "approve")
                edited_rows.append({
                    "description":           item.get("description", ""),
                    "date":                  item.get("date", "") or "—",
                    "category":              (item.get("category") or "").replace("_", " ").title(),
                    "claimed_amount":        float(item.get("claimed_amount") or 0),
                    "system_decision":       sys_dec,
                    "system_approved":       float(item.get("system_approved_amount") or 0),
                    "admin_decision":        st.session_state.get(f"dec_{claim_id}_{i}", sys_dec),
                    "admin_approved_amount": st.session_state.get(f"amt_{claim_id}_{i}", 0.0),
                    "admin_reason":          st.session_state.get(f"rsn_{claim_id}_{i}", ""),
                })
            edited_df = pd.DataFrame(edited_rows)
            _save_admin_decisions(db, claim, claim_id, edited_df, line_items, admin_notes)


def _save_admin_decisions(
    db,
    claim: dict,
    claim_id: str,
    edited_df: "pd.DataFrame",
    original_items: list,
    admin_notes: str,
) -> None:
    from utils.training_db import save_admin_override_decisions

    final_items = []
    for i, (_, row) in enumerate(edited_df.iterrows()):
        orig = original_items[i] if i < len(original_items) else {}
        final_items.append({
            **orig,
            "admin_decision":        row["admin_decision"],
            "admin_approved_amount": float(row["admin_approved_amount"] or 0),
            "admin_reason":          row["admin_reason"] or "",
        })

    admin_total = sum(
        it["admin_approved_amount"]
        for it in final_items
        if it["admin_decision"] != "reject"
    )

    db.update_admin_decision(
        claim_id=claim_id,
        admin_approved_amount=round(admin_total, 2),
        admin_notes=admin_notes,
    )

    import sqlite3
    conn = sqlite3.connect(db.db_path)
    conn.execute(
        "UPDATE claims SET line_items_json=? WHERE id=?",
        (json.dumps(final_items), claim_id),
    )
    conn.commit()
    conn.close()

    employee_code = claim.get("employee_id", "")
    is_test = claim_id.startswith("TEST-") or claim_id.startswith("VCH-TEST-")

    if is_test:
        saved = 0
        training_note = "Test claim — training DB not updated."
    else:
        saved = save_admin_override_decisions(claim_id, employee_code, final_items)
        training_note = (
            f"Added {saved} training examples." if saved
            else "Training data already saved for this claim."
        )

    st.success(
        f"Admin decisions saved.  "
        f"Admin approved: Rs.{admin_total:,.2f}  |  "
        + training_note
    )
    st.rerun()


# ── Voucher Review tab ────────────────────────────────────────────────────────

def _render_voucher_review_tab() -> None:
    """
    Admin uploads a SpineHR expense voucher PDF (already approved by previous
    stages) plus an optional ZIP of proof documents. The AI cross-checks every
    line item against company policy and proof, then returns the PDF with
    Approved / Rejected columns filled in.
    """
    import tempfile, os
    from integrations.voucher_extractor import extract_voucher_data, extract_zip_proofs
    from integrations.pdf_filler import fill_voucher_pdf
    from graph import review_voucher_stream

    st.markdown("### Voucher Review")
    st.caption(
        "Upload the expense voucher PDF received after all approval stages, "
        "along with the proof documents ZIP. The AI will verify each line item "
        "against company policy and return the PDF with corrected Approved / "
        "Rejected amounts."
    )

    col_up1, col_up2 = st.columns(2)
    with col_up1:
        voucher_file = st.file_uploader(
            "Expense Voucher PDF (SpineHR)",
            type=["pdf"],
            key="adm_voucher_pdf",
        )
    with col_up2:
        proof_zip = st.file_uploader(
            "Proof Documents ZIP (optional)",
            type=["zip"],
            key="adm_voucher_zip",
        )

    test_mode = st.checkbox(
        "Test mode (skip LLM judgment — rule-based policy caps only, no API cost)",
        value=False,
        key="adm_voucher_test_mode",
    )

    if not voucher_file:
        st.info("Upload a voucher PDF to begin.")
        return

    # ── Extract voucher immediately on upload (before button click) ────────
    tmp_dir  = tempfile.mkdtemp(prefix="adm_voucher_")
    pdf_path = os.path.join(tmp_dir, "voucher.pdf")
    with open(pdf_path, "wb") as f:
        f.write(voucher_file.read())

    try:
        voucher_data = extract_voucher_data(pdf_path)
    except Exception as e:
        st.error(f"Could not read voucher PDF: {e}")
        return

    line_items = voucher_data.get("line_items", [])
    if not line_items:
        st.error("No expense line items found in this PDF.")
        return

    # ── Voucher header summary ────────────────────────────────────────────
    h1, h2, h3 = st.columns(3)
    h1.markdown(
        f"**{voucher_data.get('employee_name','—')}**  \n"
        f"`{voucher_data.get('employee_code','—')}`"
    )
    h2.markdown(
        f"Voucher **{voucher_data.get('voucher_no','—')}**  \n"
        f"Date: {voucher_data.get('voucher_date','—')}"
    )
    h3.markdown(
        f"Period: {voucher_data.get('period_start','—')} → {voucher_data.get('period_end','—')}  \n"
        f"Cost Center: {voucher_data.get('cost_center','—')}"
    )
    if voucher_data.get("narration"):
        narr = voucher_data["narration"]
        st.markdown(
            f"<div style='font-size:0.85rem;color:#9ca3af;padding:4px 0'>"
            f"<b>Narration:</b> {narr}</div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Line items preview table ──────────────────────────────────────────
    gross = sum(it.get("claimed_amount", 0) for it in line_items)
    st.markdown(
        f"**Extracted Line Items** — {len(line_items)} rows  |  "
        f"Total Claimed: **Rs.{gross:,.2f}**"
    )
    _col_w = [3, 1.4, 3, 1.2, 1.2, 1.2]
    hdr = st.columns(_col_w)
    for col, lbl in zip(hdr, ["Expense Head", "Date", "Remarks", "Claimed", "Approved", "Rejected"]):
        col.markdown(
            f"<p style='margin:0;font-size:0.74rem;font-weight:700;color:#6b7280;"
            f"text-transform:uppercase;letter-spacing:0.04em'>{lbl}</p>",
            unsafe_allow_html=True,
        )
    st.markdown(
        "<hr style='margin:4px 0 2px;border:none;border-top:1px solid rgba(255,255,255,0.1)'>",
        unsafe_allow_html=True,
    )
    for it in line_items:
        row = st.columns(_col_w)
        row[0].markdown(
            f"<div style='font-size:0.875rem;padding:3px 0'>{it.get('expense_head','—')}</div>",
            unsafe_allow_html=True,
        )
        row[1].markdown(
            f"<div style='font-size:0.875rem;padding:3px 0'>{it.get('date','—')}</div>",
            unsafe_allow_html=True,
        )
        row[2].markdown(
            f"<div style='font-size:0.82rem;color:#9ca3af;padding:3px 0'>"
            f"{(it.get('remarks') or '—')[:40]}</div>",
            unsafe_allow_html=True,
        )
        row[3].markdown(
            f"<div style='font-size:0.875rem;text-align:right;padding:3px 0'>"
            f"₹{it.get('claimed_amount',0):,.0f}</div>",
            unsafe_allow_html=True,
        )
        row[4].markdown(
            f"<div style='font-size:0.875rem;text-align:right;padding:3px 0;color:#9ca3af'>"
            f"₹{it.get('approved_amount',0):,.0f}</div>",
            unsafe_allow_html=True,
        )
        rej = it.get("rejected_amount", 0) or 0
        row[5].markdown(
            f"<div style='font-size:0.875rem;text-align:right;padding:3px 0;"
            f"{'color:#dc2626' if rej > 0 else ''}'>"
            f"₹{rej:,.0f}</div>",
            unsafe_allow_html=True,
        )
    st.markdown(
        "<hr style='margin:2px 0 8px;border:none;border-top:1px solid rgba(255,255,255,0.1)'>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Note: Approved/Rejected columns above show the **original SpineHR values** from the PDF. "
        f"The AI review below will calculate its own approved amounts based on company policy."
    )

    st.markdown("---")

    if not st.button(
        "Run AI Review",
        type="primary",
        width="stretch",
        key="adm_btn_review_voucher",
    ):
        return

    # ── Extract proof ZIP (after button click) ───────────────────────────
    proof_files = []
    if proof_zip:
        zip_path = os.path.join(tmp_dir, "proofs.zip")
        with open(zip_path, "wb") as f:
            f.write(proof_zip.read())
        with st.spinner("Extracting proof documents…"):
            proof_dir   = os.path.join(tmp_dir, "proofs")
            proof_files = extract_zip_proofs(zip_path, proof_dir)
        st.caption(f"{len(proof_files)} proof file(s) extracted.")

    # ── Fetch Unolo GPS distance via API ──────────────────────────────────
    unolo_api_km = None
    emp_code     = voucher_data.get("employee_code", "")
    period_start = voucher_data.get("period_start", "")
    period_end   = voucher_data.get("period_end", "")
    if emp_code and period_start and period_end:
        with st.spinner(f"Fetching GPS distance from Unolo API for {emp_code}…"):
            try:
                from integrations.unolo_api import fetch_unolo_distance
                unolo_result = fetch_unolo_distance(emp_code, period_start, period_end)
                km    = unolo_result.get("distance_km")
                err   = unolo_result.get("error")
                # Always show what the API returned so it's debuggable
                if km and km > 0:
                    unolo_api_km = km
                    st.success(f"Unolo API → **{km:,.1f} km** for {emp_code} ({period_start} to {period_end})")
                elif km == 0:
                    st.warning(
                        f"Unolo API returned 0 km for {emp_code} ({period_start} to {period_end}). "
                        f"Check that the employee ID and date format match the Unolo account."
                    )
                elif err:
                    st.error(f"Unolo API error: {err}")
                else:
                    st.warning(f"Unolo API returned no distance data. Raw response: {unolo_result}")
            except Exception as e:
                st.error(f"Unolo API call failed: {type(e).__name__}: {e}")
    else:
        st.warning(
            f"Cannot call Unolo API — missing: "
            f"{'employee code' if not emp_code else ''} "
            f"{'period start' if not period_start else ''} "
            f"{'period end' if not period_end else ''}".strip()
        )

    # ── OCR proof documents (GPS screenshots + receipts) ──────────────────
    proof_ocr_receipts  = []
    proof_odometer_readings = []
    proof_odometer_km   = None
    if proof_files:
        _scan_progress = st.empty()
        _scan_progress.info(
            f"Scanning proof documents with AI Vision…  0 / {len(proof_files)} files done"
        )
        try:
            from integrations.vision_ai import scan_receipts

            def _on_progress(done, total, label):
                _scan_progress.info(
                    f"Scanning proof documents with AI Vision…  "
                    f"**{done} / {total}** files scanned  ·  {label}"
                )

            ocr_result              = scan_receipts(proof_files, on_progress=_on_progress)
            proof_ocr_receipts      = ocr_result.get("receipts", [])
            proof_odometer_readings = ocr_result.get("odometer_readings", [])
            proof_odometer_km       = ocr_result.get("odometer_distance_km")
        except Exception as e:
            st.warning(f"Proof OCR failed — continuing without proof data: {e}")
        finally:
            _scan_progress.empty()   # always clear — even if an exception occurred

    # ── Cross-check screenshot distance vs Unolo API ──────────────────────
    # Both sources must agree (within 15%) for the distance to be trusted.
    final_distance_km = None
    if unolo_api_km and proof_odometer_km:
        diff_pct = abs(unolo_api_km - proof_odometer_km) / max(unolo_api_km, proof_odometer_km)
        if diff_pct <= 0.15:
            final_distance_km = unolo_api_km  # API is authoritative when both match
            st.success(
                f"GPS distance verified: Unolo API **{unolo_api_km:,.1f} km** matches "
                f"screenshots **{proof_odometer_km:,.1f} km** — using **{final_distance_km:,.1f} km** "
                f"for two-wheeler calculation."
            )
        else:
            final_distance_km = min(unolo_api_km, proof_odometer_km)
            st.warning(
                f"GPS distance mismatch: Unolo API **{unolo_api_km:,.1f} km** vs "
                f"screenshots **{proof_odometer_km:,.1f} km** ({diff_pct:.0%} gap). "
                f"Using lower value **{final_distance_km:,.1f} km** for calculation."
            )
    elif unolo_api_km:
        final_distance_km = unolo_api_km
        note = "No GPS screenshots provided" if not proof_files else "Screenshots could not be parsed"
        st.info(f"GPS distance from Unolo API: **{unolo_api_km:,.1f} km**. {note}.")
    elif proof_odometer_km:
        final_distance_km = proof_odometer_km
        st.warning(
            f"GPS distance from screenshots only: **{proof_odometer_km:,.1f} km**. "
            f"Unolo API data not available — distance not independently verified."
        )
    else:
        st.warning(
            "No GPS distance available (Unolo API unavailable and no readable GPS screenshots). "
            "Two-wheeler claim will be checked against monthly policy cap only."
        )

    # ── Full agent pipeline (mirrors employee claim flow) ─────────────────
    vch_prefix = "VCH-TEST" if test_mode else "VCH"
    claim_id   = f"{vch_prefix}-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    status_placeholder = st.empty()
    result = None
    for node_name, label, state in review_voucher_stream(
        claim_id=claim_id,
        voucher_data=voucher_data,
        proof_ocr_results=proof_ocr_receipts,
        odometer_distance_km=final_distance_km,
        test_mode=test_mode,
    ):
        status_placeholder.info(f"Agent running: **{label}**…")
        result = state

    status_placeholder.empty()

    if not result or not result.get("final_report"):
        st.error("Pipeline failed — no report generated.")
        return

    # ── Save to claims DB (same path as employee flow) ─────────────────────
    try:
        db = _get_db()
        decisions = result.get("voucher_line_decisions", [])
        db_line_items = [
            {
                "description":            f"{d['expense_head']} — {d.get('remarks','')}",
                "date":                   d.get("date", ""),
                "category":               d.get("category", "other"),
                "claimed_amount":         d["claimed_amount"],
                "system_decision":        d["decision"],
                "system_approved_amount": d["approved_amount"],
                "system_reason":          d.get("reason", ""),
                "source_type":            "voucher",
            }
            for d in decisions
        ]
        claim_data = {
            **result,
            "employee_name":      voucher_data.get("employee_name", ""),
            "claimed_amount":     result.get("claimed_amount", 0),
            "claim_period_start": voucher_data.get("period_start", ""),
            "claim_period_end":   voucher_data.get("period_end", ""),
            "submission_date":    datetime.now().isoformat(),
            "processing_complete": True,
        }
        db.save_full_claim(claim_data, db_line_items)
    except Exception as e:
        st.warning(f"DB save failed (non-blocking): {e}")

    # ── Generate filled PDF ───────────────────────────────────────────────
    filled_bytes = None
    fname = f"reviewed_voucher_{voucher_data.get('voucher_no', 'output')}.pdf"
    with st.spinner("Generating filled PDF…"):
        try:
            filled_bytes = fill_voucher_pdf(pdf_path, decisions)
        except Exception as e:
            st.warning(f"PDF generation failed: {e}")

    # ── Redirect to result page (same session state as employee flow) ─────
    st.session_state["last_result"]           = result
    st.session_state["last_claim_id"]         = claim_id
    st.session_state["last_employee_id"]      = voucher_data.get("employee_code", "")
    st.session_state["last_employee_name"]    = voucher_data.get("employee_name", "")
    st.session_state["last_claimed"]          = result.get("claimed_amount", 0)
    st.session_state["last_approved"]         = result.get("approved_amount", 0)
    st.session_state["last_distance"]         = final_distance_km
    st.session_state["last_odometer_readings"] = proof_odometer_readings
    st.session_state["last_vision"]           = {
        "receipts":         proof_ocr_receipts,
        "employee_summary": result.get("employee_summary"),
    }
    st.session_state["last_form_snapshot"] = {
        "period_start": voucher_data.get("period_start", ""),
        "period_end":   voucher_data.get("period_end",   ""),
    }
    st.session_state["last_voucher_pdf"]      = filled_bytes
    st.session_state["last_voucher_pdf_name"] = fname
    st.session_state["page"] = "result"
    st.rerun()
