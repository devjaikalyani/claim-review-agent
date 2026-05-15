"""
Admin Judgment Agent

Uses Claude with few-shot examples from the training database to replicate
the judgment of an experienced finance admin.

Only runs when there is NO expense voucher (no pre-approved amounts).
When a voucher IS present, the admin has already decided — skip this agent.

How it works:
  1. Load relevant past decisions per category from training_db
  2. Build a few-shot prompt: company policy + real past decisions
  3. Ask Claude to judge each expense item — approve / reject / partial
  4. Apply decisions: remove rejected items, adjust partial amounts
  5. Rebuild categories so calculator gets clean, pre-judged data
"""
import json
import hashlib
from typing import Dict, Any, List
from agents.state import ClaimState
from config.policy import REIMBURSEMENT_POLICY
from utils.training_db import (
    get_examples, get_paired_examples, get_rejection_patterns, get_stats,
    has_sufficient_examples, get_rule_based_judgment,
)


def _get_policy_hash() -> str:
    """Return a short hash of the current policy config.
    Embedding this in the system prompt ensures Anthropic's prompt cache is
    automatically invalidated whenever policy rates or limits change — no manual
    TTL management required.
    """
    policy_repr = json.dumps(
        {
            k: {
                "monthly_limit": v.monthly_limit,
                "rate_per_km":   v.rate_per_km,
                "daily_limit":   v.daily_limit,
            }
            for k, v in REIMBURSEMENT_POLICY.items()
        },
        sort_keys=True,
    )
    return hashlib.sha256(policy_repr.encode()).hexdigest()[:12]


def _build_static_system_prompt() -> str:
    """Build the static (per-company) system prompt once at module load.
    This string never changes between claims, so Anthropic's prompt cache
    will serve hits for every claim after the first within the 5-min TTL window.
    The embedded policy checksum ensures the cache is busted automatically
    when any rate or limit in config/policy.py changes.
    """
    policy_lines = []
    for cat_key, policy in REIMBURSEMENT_POLICY.items():
        name  = getattr(policy, "name",          cat_key)
        limit = getattr(policy, "monthly_limit", 0)
        rate  = getattr(policy, "rate_per_km",   None)
        if rate:
            policy_lines.append(f"  • {name}: ₹{rate}/km, monthly cap ₹{limit:,.0f}")
        elif limit:
            policy_lines.append(f"  • {name}: actual expenses reimbursed, monthly cap ₹{limit:,.0f}")
    policy_summary = "\n".join(policy_lines) or "  See company policy document."

    return f"""You are an experienced finance admin at Rite Water Solutions India Limited, a water infrastructure company with field employees who travel to project sites, buy materials, stay in hotels/guest houses, and claim fuel expenses.
Policy checksum: {_get_policy_hash()}

Your role: review employee expense claim items and decide which to approve, partially approve, or reject — exactly as a senior finance admin would.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMPANY REIMBURSEMENT POLICY:
{policy_summary}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DECISION RULES — apply strictly in this order:

RULE 1 — UPI PAYMENTS ARE AUTHORITATIVE:
  A UPI payment screenshot is an irrefutable bank transaction record — it is ABSOLUTE proof of
  what the employee actually paid. Always approve at the UPI amount.

  When BOTH a UPI screenshot AND a formal vendor receipt exist for the same vendor/date:
    • The UPI amount is the authoritative approved amount (it is what was actually debited).
    • The formal receipt is supporting documentation only — do NOT approve it separately.
    • Count the transaction ONCE, at the UPI amount.
    • Small differences between UPI amount and receipt amount are normal (GST, rounding, charges).
  Example:
    • UPI ₹14,970 to Balaji Car Garage on Apr 2 + garage bill ₹14,910 on Apr 2
      → APPROVE at ₹14,970 (the UPI amount). The bill is documentation, not the claim amount.

  Only reject a UPI if:
    • The identical UTR / transaction ID appears more than once in the same claim (true duplicate).
    • There is clear evidence it is a personal payment with zero business purpose.

  Do NOT reject or reduce a UPI payment merely because a formal receipt also exists.

RULE 2 — GPS / FUEL MISMATCH:
  For two-wheeler and fuel expense items:
    • If GPS-verified distance is provided and the total fuel claimed significantly exceeds
      (GPS km × ₹3/km × 1.10 tolerance), partial-approve at the GPS-calculated cap.
    • If NO GPS data is available, approve the fuel claim at face value.
      Do NOT penalise an employee for missing GPS tracker data — it is a company tool, not theirs.

RULE 3 — NO BUSINESS PURPOSE:
  Reject items that have no plausible business justification or no receipt backing.
  Example: personal grocery purchase, personal pharmacy bill, personal clothing receipt.
  Do NOT reject items just because the description is vague — field expenses often have short descriptions.

RULE 4 — POLICY CAP:
  If a claimed amount clearly exceeds the monthly category cap, partial-approve at the policy cap.
  Example: hotel claimed ₹2,500/night in a Tier-2 city where cap is ₹1,500/night → partial at cap.

RULE 5 — APPROVE WHEN IN DOUBT:
  When you are genuinely uncertain between approving and rejecting:
    APPROVE — it is far better to let the human admin make the final call than to wrongly
    reject a legitimate field business expense. Field employees often have minimal proof.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT:
Return a JSON array — one object per item. Each object must have:
  "item_index"      : integer matching the input list index
  "decision"        : "approve" | "reject" | "partial"
  "approved_amount" : numeric — full amount for approve, reduced amount for partial, 0 for reject
  "reason"          : brief explanation — required for reject and partial, optional for approve
  "confidence"      : float 0.0–1.0 — your confidence in this specific decision
                        0.9–1.0  clear-cut case (obvious approval or clear policy violation)
                        0.7–0.89 reasonable certainty (standard policy case, good evidence)
                        0.5–0.69 uncertain (edge case, vague description, missing context)
                        below 0.5 very uncertain — flag for careful admin review

Return ONLY the JSON array. No markdown fences. No text before or after the array."""


# Static system prompt — built once at module load, identical for every claim.
# llm.invoke() adds cache_control: ephemeral to it, so Anthropic caches it
# and every subsequent claim within the 5-min TTL window is a cache hit.
_STATIC_SYSTEM_PROMPT: str = _build_static_system_prompt()


def admin_judgment_agent(state: ClaimState) -> ClaimState:
    """
    Apply LLM-based admin judgment to non-voucher expense claims.
    When voucher_line_decisions is present (admin voucher review path),
    applies those pre-computed decisions directly instead of re-running LLM.
    """
    state["current_agent"] = "admin_judgment"

    # Voucher path: per-item decisions already computed by voucher_judgment_agent
    if state.get("voucher_line_decisions"):
        _apply_voucher_decisions(state, state["voucher_line_decisions"])
        state["admin_judgment_applied"] = True
        state["admin_judgment_note"] = (
            f"Voucher per-item decisions applied "
            f"({len(state['voucher_line_decisions'])} line items)."
        )
        return state

    # Skip in test mode — policy-only evaluation, no DB-based LLM judgment
    if state.get("test_mode"):
        state["admin_judgment_note"] = "Test mode — LLM judgment skipped, rule-based evaluation only."
        return state

    # Skip if already ran — critic1 revision loop sends state back through data
    # and then here again, but the expenses haven't changed so re-running wastes
    # an LLM call and could incorrectly re-flag already-kept items.
    if state.get("admin_judgment_applied"):
        return state

    expenses = state.get("expenses", [])
    if not expenses:
        return state

    # Check training DB has enough examples
    stats = get_stats()
    if stats["total"] < 5:
        state["admin_judgment_note"] = (
            f"Training DB has only {stats['total']} examples — "
            "rule-based evaluation applied, LLM judgment skipped."
        )
        return state

    # Fetch relevant examples per category in claim
    categories_in_claim = {e.get("category", "") for e in expenses}
    example_lines = []
    pair_lines    = []

    for cat in categories_in_claim:
        # Regular examples (approved + rejected)
        for r in get_examples(cat, limit=8):
            icon       = "✓" if r["decision"] == "approved" else "✗"
            reason_txt = f"  ← {r['rejection_reason']}" if r["rejection_reason"] else ""
            example_lines.append(
                f"  {icon} [{r['category']}] {r['description'][:70]}"
                f" — ₹{r['claimed_amount']:.0f}"
                f" → {r['decision'].upper()}{reason_txt}"
            )
        # Paired examples: show rejected item side-by-side with the approved duplicate
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

    # ── GPS / Unolo context ───────────────────────────────────────────────────
    unolo_km   = state.get("unolo_distance_km")
    eligible_km = state.get("eligible_distance_km")
    distance_km = eligible_km if eligible_km is not None else unolo_km

    # Two-wheeler policy: ₹3/km
    tw_rate = 3.0
    for _k, _p in REIMBURSEMENT_POLICY.items():
        if _k == "two_wheeler" and getattr(_p, "rate_per_km", None):
            tw_rate = float(_p.rate_per_km)
            break

    gps_lines: list[str] = []
    if distance_km:
        expected_tw = distance_km * tw_rate
        tolerance   = expected_tw * 1.10
        gps_lines.append(f"  GPS Tracked Distance : {distance_km:,.1f} km  (Unolo API)")
        gps_lines.append(f"  Expected Fuel Cost   : ₹{expected_tw:,.0f}  (at ₹{tw_rate}/km)")
        gps_lines.append(f"  Approved Fuel Cap    : ₹{tolerance:,.0f}  (+10% tolerance)")
        gps_lines.append(
            "  → For two-wheeler/fuel items, approve up to the GPS cap above."
        )
        gps_lines.append(
            "    Partial-approve if total fuel claimed exceeds GPS cap; "
            "set approved_amount = GPS cap."
        )
    else:
        gps_lines.append(
            "  No GPS data available for this claim period."
        )
        gps_lines.append(
            "  → Do NOT penalise fuel/two-wheeler items for missing GPS."
            "  Apply policy monthly cap only."
        )
    gps_section = "\n".join(gps_lines)

    # Build items list for the LLM
    items_payload = [
        {
            "item_index":  i,
            "category":    e.get("category", ""),
            "description": e.get("description", ""),
            "amount":      e.get("amount", 0),
            "date":        e.get("date", ""),
        }
        for i, e in enumerate(expenses)
    ]

    # Detect obvious in-batch duplicates to hint the LLM
    dup_hints = _find_duplicate_hints(expenses)
    dup_section = ""
    if dup_hints:
        dup_section = (
            "\nDUPLICATE HINTS (same amount+category on same/adjacent date):\n"
            + "\n".join(f"  Indices {a} and {b} look like duplicates"
                        for a, b in dup_hints)
        )

    # Annotate two-wheeler items with GPS vs claimed comparison
    gps_note = ""
    if distance_km:
        tw_items   = [(i, e) for i, e in enumerate(expenses)
                      if e.get("category") == "two_wheeler"]
        tw_total   = sum(e.get("amount", 0) for _, e in tw_items)
        if tw_items:
            gps_cap = distance_km * tw_rate * 1.10
            gps_note = (
                f"\nFUEL/TWO-WHEELER SUMMARY:"
                f"\n  Total claimed: ₹{tw_total:,.0f}"
                f"  |  GPS cap (incl. 10% tolerance): ₹{gps_cap:,.0f}"
            )
            if tw_total > gps_cap:
                over = tw_total - gps_cap
                gps_note += (
                    f"\n  ⚠ Claimed exceeds GPS cap by ₹{over:,.0f}."
                    f" Partial-approve fuel items proportionally."
                )
            else:
                gps_note += "\n  ✓ Claimed is within GPS-verified distance cap."

    # Dynamic context goes in the user message — static system prompt is cached separately
    prompt = (
        f"GPS / DISTANCE CONTEXT:\n{gps_section}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"PAST ADMIN DECISIONS — learn from these real examples:\n{examples_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"DUPLICATE PAIRS SEEN BEFORE (rejected ↔ approved for same amount):\n{pairs_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"COMMON REJECTION PATTERNS:\n{patterns_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"EXPENSE ITEMS TO REVIEW:\n"
        f"{json.dumps(items_payload, indent=2)}"
        f"{dup_section}"
        f"{gps_note}\n\n"
        f"Return your decisions as a JSON array now."
    )

    # Apply rule-based judgment for categories with insufficient training examples
    # before sending to LLM, so the LLM only handles well-represented categories.
    sparse_decisions = []
    llm_expenses     = []
    for i, e in enumerate(expenses):
        cat = e.get("category", "other")
        if not has_sufficient_examples(cat):
            rb = get_rule_based_judgment(cat, e.get("amount", 0), e.get("description", ""))
            rb["item_index"] = i
            sparse_decisions.append(rb)
        else:
            llm_expenses.append((i, e))

    try:
        from utils.llm import get_llm
        llm      = get_llm()
        response = llm.invoke(prompt, system_prompt=_STATIC_SYSTEM_PROMPT, max_tokens=2048)
        decisions = _parse_decisions(response)

        # Merge LLM decisions with rule-based decisions for sparse categories
        all_decisions = sparse_decisions + decisions

        if all_decisions:
            rejected_items = _apply_decisions(state, expenses, all_decisions)
            state["admin_judgment_applied"] = True
            rb_count  = len(sparse_decisions)
            llm_count = len(decisions)
            state["admin_judgment_note"] = (
                f"Admin judgment applied: {llm_count} LLM decision(s) "
                f"(using {stats['total']} training examples, {stats['vouchers']} vouchers), "
                f"{rb_count} rule-based decision(s) for categories with sparse training data. "
                f"{len(rejected_items)} item(s) rejected."
            )
            if rejected_items:
                state.setdefault("duplicates_removed", []).extend(rejected_items)
        else:
            # LLM returned nothing and no sparse decisions — force pending review
            state["admin_judgment_failed"] = True
            state["decision"]             = "pending_review"
            state["admin_judgment_note"]  = (
                "LLM returned no decisions and no rule-based fallback applied. "
                "Claim requires manual admin review."
            )

    except Exception as exc:
        # LLM call failed — do NOT let expenses silently pass through as approved.
        # Force the claim to pending_review so a human admin must decide.
        state["admin_judgment_failed"] = True
        state["decision"]             = "pending_review"
        state["admin_judgment_note"]  = (
            f"Judgment agent error: {exc}. "
            "Claim flagged for mandatory manual admin review — no auto-approval."
        )
        # Apply rule-based decisions for any sparse categories that were already computed
        if sparse_decisions:
            _apply_decisions(state, expenses, sparse_decisions)

    return state


# ── Helpers ───────────────────────────────────────────────────────────────────

def _apply_voucher_decisions(state: ClaimState, decisions: List[Dict]) -> None:
    """
    Apply pre-computed voucher per-item decisions to the pipeline state.
    Replaces the expense list (built from claimed amounts by data_agent) with
    post-judgment amounts, exactly as _apply_decisions() does for LLM results.
    """
    approved_list: List[Dict] = []
    rejected_desc: List[str]  = []

    for dec in decisions:
        if dec["decision"] == "reject":
            rejected_desc.append(
                f"{dec['expense_head']} ({dec.get('date','')}) — "
                f"₹{dec['claimed_amount']:,.2f} ({dec.get('reason','')})"
            )
            state.setdefault("rejected_expenses", []).append({
                "description":     f"{dec['expense_head']} — {dec.get('remarks','')}",
                "date":            dec.get("date", ""),
                "category":        dec.get("category", "other"),
                "amount":          dec["claimed_amount"],
                "system_decision": "reject",
                "system_reason":   dec.get("reason", ""),
                "source_type":     "voucher",
            })
        else:
            approved_list.append({
                "category":         dec.get("category", "other"),
                "amount":           dec["approved_amount"],
                "date":             dec.get("date", ""),
                "description":      f"{dec['expense_head']} — {dec.get('remarks','')}",
                "source_document":  "expense_voucher",
                "confidence":       0.95,
                "is_valid":         True,
                "validation_notes": dec.get("reason", "") if dec["decision"] == "partial" else "",
                "source_type":      "voucher",
            })

    # Rebuild categories from the approved (and partial) list
    categories: Dict[str, Any] = {}
    total = 0.0
    for exp in approved_list:
        cat = exp["category"]
        if cat not in categories:
            categories[cat] = {
                "category":      cat,
                "total_claimed": 0.0,
                "items":         [],
                "item_count":    0,
            }
        categories[cat]["total_claimed"] += exp["amount"]
        categories[cat]["items"].append(exp)
        categories[cat]["item_count"]    += 1
        total += exp["amount"]

    state["expenses"]               = approved_list
    state["categories"]             = categories
    state["total_extracted_amount"] = total
    if rejected_desc:
        state.setdefault("duplicates_removed", []).extend(rejected_desc)


def _find_duplicate_hints(expenses: List[Dict]) -> List[tuple]:
    """Return index pairs where two items share same category+amount on same date."""
    hints = []
    seen: Dict[tuple, int] = {}
    for i, e in enumerate(expenses):
        key = (e.get("category", ""), e.get("amount", 0), e.get("date", ""))
        if key[1] > 0 and key in seen:
            hints.append((seen[key], i))
        else:
            seen[key] = i
    return hints


def _parse_decisions(response: str) -> List[Dict]:
    try:
        txt = response
        if "```json" in txt:
            txt = txt.split("```json")[1].split("```")[0]
        elif "```" in txt:
            txt = txt.split("```")[1].split("```")[0]
        parsed = json.loads(txt.strip())
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    return []


def _apply_decisions(state: ClaimState,
                     expenses: List[Dict],
                     decisions: List[Dict]) -> List[str]:
    """
    Apply LLM decisions to the expense list.
    Returns a list of human-readable strings describing what was rejected.
    """
    dec_map = {d["item_index"]: d for d in decisions}

    approved_list: List[Dict] = []
    rejected_desc: List[str]  = []

    for i, expense in enumerate(expenses):
        dec = dec_map.get(i)
        if dec is None:
            approved_list.append(expense)
            continue

        action = dec.get("decision", "approve")

        confidence = min(1.0, max(0.0, float(dec.get("confidence") or 1.0)))

        if action == "reject":
            expense["is_valid"]          = False
            expense["validation_notes"]  = dec.get("reason", "Rejected by admin judgment")
            expense["system_confidence"] = confidence
            rejected_desc.append(
                f"{expense.get('description', 'Expense')} — "
                f"₹{expense.get('amount', 0):,.2f} on {expense.get('date', 'unknown date')} "
                f"({dec.get('reason', 'admin judgment')})"
            )
            # Store structured rejected item for admin review dashboard
            state.setdefault("rejected_expenses", []).append({
                "description":     expense.get("description", ""),
                "date":            expense.get("date", ""),
                "category":        expense.get("category", ""),
                "amount":          expense.get("amount", 0),
                "system_decision": "reject",
                "system_reason":   dec.get("reason", "Rejected by admin judgment"),
                "system_confidence": confidence,
                "source_type":     expense.get("source_type", "receipt"),
            })
        elif action == "partial":
            adj = float(dec.get("approved_amount") or expense["amount"])
            expense["amount"]            = adj
            expense["validation_notes"]  = dec.get("reason", "Partially approved")
            expense["system_confidence"] = confidence
            approved_list.append(expense)
        else:
            expense["system_confidence"] = confidence
            approved_list.append(expense)

    # Rebuild categories from approved list
    categories: Dict[str, Any] = {}
    total = 0.0
    for exp in approved_list:
        cat = exp["category"]
        if cat not in categories:
            categories[cat] = {
                "category":      cat,
                "total_claimed": 0.0,
                "items":         [],
                "item_count":    0,
            }
        categories[cat]["total_claimed"] += exp["amount"]
        categories[cat]["items"].append(exp)
        categories[cat]["item_count"]   += 1
        total += exp["amount"]

    state["expenses"]               = approved_list
    state["categories"]             = categories
    state["total_extracted_amount"] = total
    return rejected_desc
