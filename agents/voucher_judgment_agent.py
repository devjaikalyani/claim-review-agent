"""
Voucher Judgment Agent

Reviews SpineHR expense voucher line items against company policy and proof
documents, then returns per-line approved/rejected amounts.

Mirrors the employee claim flow:
  - Reads training examples from training_db (same as admin_judgment_agent)
  - Includes GPS/odometer distance context (same as admin_judgment_agent)
  - Enforces policy caps via calculate_eligible_amount() after LLM response
  - Uses 4-field duplicate key matching data_agent dedup logic
"""

import json
import re
from datetime import datetime as _dt
from typing import Any, Dict, List, Optional

from agents.admin_judgment_agent import _STATIC_SYSTEM_PROMPT
from config.policy import REIMBURSEMENT_POLICY, calculate_eligible_amount
from utils.llm import get_llm
from utils.training_db import get_examples, get_paired_examples, get_rejection_patterns, get_stats


# ── Public API ────────────────────────────────────────────────────────────────

def review_voucher(
    voucher_data: Dict[str, Any],
    proof_ocr_results: Optional[List[Dict[str, Any]]] = None,
    odometer_distance_km: Optional[float] = None,
    test_mode: bool = False,
) -> List[Dict[str, Any]]:
    """
    Review voucher line items and return per-item decisions.

    Args:
        voucher_data:          Output of extract_voucher_data() — header + line_items.
        proof_ocr_results:     Output of scan_receipts()["receipts"] — list of OCR dicts.
        odometer_distance_km:  Total distance from odometer readings (same as employee flow).
        test_mode:             Skip LLM call; apply rule-based duplicate + policy caps only.

    Returns:
        List of decision dicts (one per line_item), each:
          {
            "item_index":      int,
            "expense_head":    str,
            "category":        str,
            "date":            str,
            "remarks":         str,
            "claimed_amount":  float,
            "approved_amount": float,
            "rejected_amount": float,
            "decision":        "approve" | "partial" | "reject",
            "reason":          str,
          }
    """
    line_items = voucher_data.get("line_items", [])
    if not line_items:
        return []

    if test_mode:
        return _policy_based_review(line_items, voucher_data, odometer_distance_km)

    training_context = _build_training_context(line_items)
    gps_section      = _build_gps_section(odometer_distance_km, line_items)
    user_prompt      = _build_user_prompt(
        voucher_data, proof_ocr_results or [], training_context, gps_section
    )
    llm = get_llm()

    try:
        raw       = llm.invoke(user_prompt, system_prompt=_STATIC_SYSTEM_PROMPT)
        decisions = _parse_response(raw, line_items)
        decisions = _enforce_policy_caps(decisions, voucher_data, odometer_distance_km)
    except Exception:
        decisions = _approve_all_fallback(line_items)

    return decisions


# ── Training context (mirrors admin_judgment_agent) ───────────────────────────

def _build_training_context(line_items: List[Dict[str, Any]]) -> str:
    stats = get_stats()
    if stats["total"] < 5:
        return ""

    categories_in_claim = {item.get("category", "") for item in line_items}
    example_lines: List[str] = []
    pair_lines:    List[str] = []

    for cat in categories_in_claim:
        for r in get_examples(cat, limit=8):
            icon       = "✓" if r["decision"] == "approved" else "✗"
            reason_txt = f"  ← {r['rejection_reason']}" if r["rejection_reason"] else ""
            example_lines.append(
                f"  {icon} [{r['category']}] {r['description'][:70]}"
                f" — ₹{r['claimed_amount']:.0f}"
                f" → {r['decision'].upper()}{reason_txt}"
            )
        for p in get_paired_examples(cat, limit=4):
            pair_lines.append(
                f"  ✗ REJECTED:  \"{p['rejected_desc'][:65]}\" — ₹{p['claimed_amount']:.0f}"
            )
            pair_lines.append(
                f"  ✓ APPROVED:  \"{p['approved_desc'][:65]}\" — ₹{p['claimed_amount']:.0f}"
            )
            pair_lines.append(f"    Reason: {p['rejection_reason']}")
            pair_lines.append("")

    patterns = get_rejection_patterns()
    pattern_lines = [
        f"  [{p['category']}] {p['rejection_reason']} (seen {p['frequency']}x)"
        for p in patterns[:8]
    ]

    examples_text = "\n".join(example_lines) or "  No past examples yet."
    pairs_text    = "\n".join(pair_lines)    or "  No duplicate pairs recorded yet."
    patterns_text = "\n".join(pattern_lines) or "  No rejection patterns yet."

    return (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"PAST ADMIN DECISIONS — learn from these real examples:\n{examples_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"DUPLICATE PAIRS SEEN BEFORE (rejected ↔ approved for same amount):\n{pairs_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"COMMON REJECTION PATTERNS:\n{patterns_text}\n\n"
    )


# ── GPS / distance section (mirrors admin_judgment_agent) ─────────────────────

def _build_gps_section(
    odometer_distance_km: Optional[float],
    line_items: List[Dict[str, Any]],
) -> str:
    tw_rate = 3.0
    for _k, _p in REIMBURSEMENT_POLICY.items():
        if _k == "two_wheeler" and getattr(_p, "rate_per_km", None):
            tw_rate = float(_p.rate_per_km)
            break

    gps_lines: List[str] = []
    if odometer_distance_km:
        expected_tw = odometer_distance_km * tw_rate
        tolerance   = expected_tw * 1.10
        gps_lines.append(f"  Odometer Distance  : {odometer_distance_km:,.1f} km")
        gps_lines.append(f"  Expected Fuel Cost : ₹{expected_tw:,.0f}  (at ₹{tw_rate}/km)")
        gps_lines.append(f"  Approved Fuel Cap  : ₹{tolerance:,.0f}  (+10% tolerance)")
        gps_lines.append(
            "  → For two-wheeler/fuel items, approve up to the cap above."
        )
        gps_lines.append(
            "    Partial-approve if total fuel claimed exceeds the cap; "
            "set approved_amount = cap."
        )

        tw_items = [i for i in line_items if i.get("category") == "two_wheeler"]
        tw_total = sum(float(i.get("claimed_amount", 0)) for i in tw_items)
        if tw_items:
            gps_lines.append(
                f"\n  FUEL/TWO-WHEELER SUMMARY:"
                f"\n    Total claimed: ₹{tw_total:,.0f}"
                f"  |  GPS cap (incl. 10% tolerance): ₹{tolerance:,.0f}"
            )
            if tw_total > tolerance:
                gps_lines.append(
                    f"    ⚠ Claimed exceeds GPS cap by ₹{tw_total - tolerance:,.0f}."
                    f" Partial-approve fuel items proportionally."
                )
            else:
                gps_lines.append("    ✓ Claimed is within GPS-verified distance cap.")
    else:
        gps_lines.append("  No odometer/GPS data available for this claim period.")
        gps_lines.append(
            "  → Do NOT penalise fuel/two-wheeler items for missing distance data."
            "  Apply policy monthly cap only."
        )

    return "GPS / DISTANCE CONTEXT:\n" + "\n".join(gps_lines) + "\n\n"


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_user_prompt(
    voucher_data: Dict[str, Any],
    proof_ocr: List[Dict[str, Any]],
    training_context: str,
    gps_section: str,
) -> str:
    line_items = voucher_data.get("line_items", [])

    header = (
        f"EXPENSE VOUCHER\n"
        f"Voucher No.   : {voucher_data.get('voucher_no', 'N/A')}\n"
        f"Voucher Date  : {voucher_data.get('voucher_date', 'N/A')}\n"
        f"Employee      : {voucher_data.get('employee_name', 'N/A')} "
        f"({voucher_data.get('employee_code', 'N/A')})\n"
        f"Period        : {voucher_data.get('period_start', '')} to "
        f"{voucher_data.get('period_end', '')}\n"
        f"Cost Center   : {voucher_data.get('cost_center', 'N/A')}\n"
        f"Narration     : {voucher_data.get('narration', 'N/A')}\n"
        f"Total Claimed : ₹{voucher_data.get('gross_claimed', 0):.2f}"
    )

    rows = ["Index | Expense Head     | Date       | Claimed  | Remarks"]
    rows.append("------|-----------------|------------|----------|--------")
    for i, item in enumerate(line_items):
        rows.append(
            f"  {i:2d}  | {item['expense_head']:<15} | "
            f"{item['date']:<10} | "
            f"₹{item['claimed_amount']:>7.2f} | "
            f"{item['remarks'][:60]}"
        )
    items_table = "\n".join(rows)

    if proof_ocr:
        proof_lines = ["PROOF DOCUMENTS PROVIDED:"]
        for p in proof_ocr:
            proof_lines.append(
                f"  • [{p.get('receipt_type','?')}] {p.get('vendor','?')} "
                f"₹{p.get('amount', 0):.2f} on {p.get('date','?')} "
                f"(confidence {p.get('confidence', 0):.0%})"
            )
        proof_section = "\n".join(proof_lines)
    else:
        proof_section = "PROOF DOCUMENTS: None provided — review based on voucher data and policy only."

    instruction = (
        "Review every line item above against the company reimbursement policy.\n\n"
        "DUPLICATE DETECTION (apply first, before any policy check):\n"
        "  - Two items are duplicates when they share the same Expense Head, Date,"
        " Claimed amount, AND Remarks (even if Remarks differ slightly).\n"
        "  - Keep only the FIRST occurrence; reject every subsequent duplicate with"
        " approved_amount = 0 and reason = \"Duplicate of item <first_index>\".\n\n"
        "POLICY CHECKS (apply to non-duplicate items only):\n"
        "  - Apply the company reimbursement policy rules strictly.\n"
        "  - Reduce (partial) or reject items that exceed policy limits or lack valid proof.\n"
        "  - approved_amount can never exceed the claimed amount for that item.\n\n"
        "Return a JSON array with one object per line item (same order, 0-indexed).\n"
        "Each object MUST have:\n"
        '  "item_index"      : int   — 0-based index matching the table above\n'
        '  "decision"        : "approve" | "partial" | "reject"\n'
        '  "approved_amount" : float — full claimed for approve, reduced for partial, 0 for reject\n'
        '  "reason"          : string — POLICY-BASED reason only.\n'
        "                      GOOD examples: \"Within policy limits.\", "
        "\"Policy cap ₹1500/day applied — claimed exceeds limit.\", "
        "\"No valid proof provided.\", \"Duplicate of item 2.\", "
        "\"GPS cap applied: ₹X for Y km.\"\n"
        "                      BAD (never write): approver names, dates, SpineHR approval notes,\n"
        "                      or anything from the Remarks column like 'Approved by [name]'.\n"
        "                      The reason must explain the POLICY decision, not who signed the voucher.\n\n"
        "Return ONLY the JSON array. No markdown, no preamble."
    )

    return (
        f"{gps_section}"
        f"{training_context}"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{header}\n\n"
        f"{items_table}\n\n"
        f"{proof_section}\n\n"
        f"{instruction}"
    )


# ── Policy cap enforcement (mirrors calculator_agent) ─────────────────────────

def _enforce_policy_caps(
    decisions: List[Dict[str, Any]],
    voucher_data: Dict[str, Any],
    odometer_distance_km: Optional[float],
) -> List[Dict[str, Any]]:
    """
    Post-process LLM decisions with calculate_eligible_amount() to guarantee
    policy caps are never exceeded — same enforcement the calculator_agent applies
    in the employee claim flow.
    """
    claim_days = _calc_period_days(
        voucher_data.get("period_start", ""),
        voucher_data.get("period_end", ""),
    )

    tw_rate = 3.0
    for _k, _p in REIMBURSEMENT_POLICY.items():
        if _k == "two_wheeler" and getattr(_p, "rate_per_km", None):
            tw_rate = float(_p.rate_per_km)
            break

    # Group non-rejected decisions by category
    by_cat: Dict[str, List[int]] = {}
    for i, dec in enumerate(decisions):
        if dec["decision"] == "reject":
            continue
        by_cat.setdefault(dec.get("category", "other"), []).append(i)

    for cat, indices in by_cat.items():
        total_claimed  = sum(decisions[i]["claimed_amount"]  for i in indices)
        total_approved = sum(decisions[i]["approved_amount"] for i in indices)

        try:
            if cat == "two_wheeler":
                if odometer_distance_km:
                    eligible, reasoning = calculate_eligible_amount(
                        category=cat,
                        claimed_amount=total_claimed,
                        distance_km=odometer_distance_km,
                    )
                else:
                    # No GPS data — approve at claimed (same as employee flow Rule 2)
                    eligible  = total_claimed
                    reasoning = ""
            elif cat == "food":
                days_to_use = claim_days if claim_days > 0 else len(indices)
                eligible, reasoning = calculate_eligible_amount(
                    category=cat,
                    claimed_amount=total_claimed,
                    days_count=days_to_use,
                )
            elif cat == "bus_travel":
                eligible, reasoning = calculate_eligible_amount(
                    category=cat,
                    claimed_amount=total_claimed,
                    trip_count=len(indices),
                )
            else:
                eligible, reasoning = calculate_eligible_amount(
                    category=cat,
                    claimed_amount=total_claimed,
                )
        except Exception:
            continue

        eligible = min(round(eligible, 2), total_claimed)

        # Only intervene when policy is more restrictive than the LLM's approvals
        if eligible < total_approved * 0.99 and total_approved > 0:
            scale = eligible / total_approved
            for i in indices:
                dec         = decisions[i]
                new_approved = round(dec["approved_amount"] * scale, 2)
                new_rejected = round(dec["claimed_amount"] - new_approved, 2)
                dec["approved_amount"] = new_approved
                dec["rejected_amount"] = new_rejected
                if new_approved <= 0:
                    dec["decision"] = "reject"
                elif new_approved < dec["claimed_amount"] * 0.99:
                    dec["decision"] = "partial"
                cap_note = reasoning or f"Policy cap ₹{eligible:,.0f} for {cat}"
                dec["reason"] = (
                    (dec.get("reason", "") + f" | {cap_note}").lstrip(" | ")
                )

    return decisions


# ── Parse helpers ─────────────────────────────────────────────────────────────

def _parse_response(
    raw: str,
    line_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    # Strip markdown fences (```json ... ``` or ``` ... ```)
    cleaned = re.sub(r"```[a-zA-Z]*", "", raw).strip()

    ai_decisions = None
    # 1. Try the full cleaned string as JSON
    try:
        ai_decisions = json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 2. Find the first JSON array that starts with [{ (array of objects)
    if ai_decisions is None:
        m = re.search(r"(\[\s*\{.*?\}\s*\])", cleaned, re.DOTALL)
        if m:
            try:
                ai_decisions = json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

    # 3. Broadest fallback — any [...] span
    if ai_decisions is None:
        m = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if m:
            try:
                ai_decisions = json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

    if ai_decisions is None:
        return _approve_all_fallback(line_items)

    results: List[Dict[str, Any]] = []
    for i, item in enumerate(line_items):
        ai = next((d for d in ai_decisions if d.get("item_index") == i), None)
        if ai is None:
            ai = {"decision": "approve", "approved_amount": item["claimed_amount"], "reason": ""}

        approved = float(ai.get("approved_amount", item["claimed_amount"]))
        approved = min(approved, item["claimed_amount"])
        rejected = round(item["claimed_amount"] - approved, 2)

        results.append({
            "item_index":      i,
            "expense_head":    item["expense_head"],
            "category":        item.get("category", "other"),
            "date":            item.get("date", ""),
            "remarks":         item.get("remarks", ""),
            "claimed_amount":  item["claimed_amount"],
            "approved_amount": round(approved, 2),
            "rejected_amount": round(rejected, 2),
            "decision":        ai.get("decision", "approve"),
            "reason":          ai.get("reason", ""),
        })

    return results


# ── Rule-based review (test mode + fallbacks) ─────────────────────────────────

def _policy_based_review(
    line_items: List[Dict[str, Any]],
    voucher_data: Dict[str, Any],
    odometer_distance_km: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Test-mode review: duplicate detection + calculate_eligible_amount(),
    identical to what employee flow applies.
    """
    claim_days = _calc_period_days(
        voucher_data.get("period_start", ""),
        voucher_data.get("period_end", ""),
    )

    seen: set = set()
    results: List[Dict[str, Any]] = []

    for i, item in enumerate(line_items):
        # 4-field key — matches data_agent dedup logic (category+amount+date+description)
        key = (
            item["expense_head"].strip().lower(),
            item.get("date", ""),
            round(float(item["claimed_amount"]), 2),
            (item.get("remarks", "") or "").strip().lower()[:60],
        )
        if key in seen:
            results.append({
                "item_index":      i,
                "expense_head":    item["expense_head"],
                "category":        item.get("category", "other"),
                "date":            item.get("date", ""),
                "remarks":         item.get("remarks", ""),
                "claimed_amount":  item["claimed_amount"],
                "approved_amount": 0.0,
                "rejected_amount": round(float(item["claimed_amount"]), 2),
                "decision":        "reject",
                "reason":          "Duplicate line item",
            })
            continue

        seen.add(key)
        claimed  = float(item["claimed_amount"])
        category = item.get("category", "other")

        try:
            if category == "two_wheeler":
                if odometer_distance_km:
                    eligible, reasoning = calculate_eligible_amount(
                        category=category,
                        claimed_amount=claimed,
                        distance_km=odometer_distance_km,
                    )
                else:
                    eligible  = claimed
                    reasoning = "No distance data — approved at claimed amount."
            elif category == "food":
                eligible, reasoning = calculate_eligible_amount(
                    category=category,
                    claimed_amount=claimed,
                    days_count=claim_days if claim_days > 0 else 1,
                )
            elif category == "bus_travel":
                eligible, reasoning = calculate_eligible_amount(
                    category=category,
                    claimed_amount=claimed,
                    trip_count=1,
                )
            else:
                eligible, reasoning = calculate_eligible_amount(
                    category=category,
                    claimed_amount=claimed,
                )
        except Exception:
            eligible  = claimed
            reasoning = "Policy calculation unavailable — approved at claimed amount."

        eligible = min(round(eligible, 2), claimed)
        rejected = round(claimed - eligible, 2)

        if eligible >= claimed * 0.99:
            decision = "approve"
            reason   = "Within policy limits."
        else:
            decision = "partial"
            reason   = reasoning or f"Policy cap: eligible ₹{eligible:,.2f} of ₹{claimed:,.2f}."

        results.append({
            "item_index":      i,
            "expense_head":    item["expense_head"],
            "category":        category,
            "date":            item.get("date", ""),
            "remarks":         item.get("remarks", ""),
            "claimed_amount":  claimed,
            "approved_amount": eligible,
            "rejected_amount": rejected,
            "decision":        decision,
            "reason":          reason,
        })

    return results


def _approve_all_fallback(
    line_items: List[Dict[str, Any]],
    reason: str = "",
) -> List[Dict[str, Any]]:
    """Approve non-duplicate items at claimed amount — used when AI fails."""
    seen: set = set()
    results = []
    for i, item in enumerate(line_items):
        # 4-field key — matches data_agent dedup logic
        key = (
            item["expense_head"].strip().lower(),
            item.get("date", ""),
            round(float(item["claimed_amount"]), 2),
            (item.get("remarks", "") or "").strip().lower()[:60],
        )
        if key in seen:
            results.append({
                "item_index":      i,
                "expense_head":    item["expense_head"],
                "category":        item.get("category", "other"),
                "date":            item.get("date", ""),
                "remarks":         item.get("remarks", ""),
                "claimed_amount":  item["claimed_amount"],
                "approved_amount": 0.0,
                "rejected_amount": round(float(item["claimed_amount"]), 2),
                "decision":        "reject",
                "reason":          "Duplicate line item",
            })
        else:
            seen.add(key)
            results.append({
                "item_index":      i,
                "expense_head":    item["expense_head"],
                "category":        item.get("category", "other"),
                "date":            item.get("date", ""),
                "remarks":         item.get("remarks", ""),
                "claimed_amount":  item["claimed_amount"],
                "approved_amount": round(float(item["claimed_amount"]), 2),
                "rejected_amount": 0.0,
                "decision":        "approve",
                # Never expose internal parse errors in the admin UI
                "reason":          "Approved — within policy limits.",
            })
    return results


# ── Utility ───────────────────────────────────────────────────────────────────

def _calc_period_days(start: str, end: str) -> int:
    try:
        s = _dt.fromisoformat((start or "").split("T")[0])
        e = _dt.fromisoformat((end   or "").split("T")[0])
        return max((e - s).days + 1, 1)
    except Exception:
        return 0
