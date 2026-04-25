"""
Calculator Agent

Applies reimbursement policy rules to calculate eligible amounts.
Sums all category claims, cross-validates against total_extracted_amount,
and writes a reconciliation note before handing off to Critic 2.
"""
from typing import Dict, Any, List
from agents.state import ClaimState
from config.policy import (
    REIMBURSEMENT_POLICY,
    DISTANCE_RULES,
    get_category_policy,
    calculate_eligible_amount,
)


def calculator_agent(state: ClaimState) -> ClaimState:
    """
    Calculate eligible reimbursement amounts per category.

    Changes vs previous version
    ───────────────────────────
    1. Computes `category_claimed_total` (sum of all category claims) and
       compares it to `total_extracted_amount` BEFORE running policy math,
       so Critic 2 gets a pre-built reconciliation note instead of having
       to rediscover the gap itself.
    2. Includes "other" and uncategorised amounts in the reconciliation so
       receipts that fell out of a named category are never silently ignored.
    3. `category_eligible` is written as Dict[str, Dict] consistently
       (matching how Critic 2 reads it) — the state TypedDict annotation is
       also fixed in state.py.
    """
    state["current_agent"] = "calculator"

    categories        = state.get("categories", {})
    unolo_distance    = state.get("unolo_distance_km")
    eligible_distance = state.get("eligible_distance_km")
    distance_for_calc = eligible_distance if eligible_distance is not None else unolo_distance
    total_extracted = state.get("total_extracted_amount", 0.0)

    period_start = state.get("claim_period_start", "")
    period_end   = state.get("claim_period_end", "")
    claim_days   = _calculate_days(period_start, period_end)

    # ── Step 1: Verify extracted total vs category sum ───────────────────
    # Do this BEFORE policy math so any gap is surfaced clearly to Critic 2.
    category_claimed_total = sum(
        cat_data.get("total_claimed", 0.0) for cat_data in categories.values()
    )
    extraction_gap = round(total_extracted - category_claimed_total, 2)
    reconciliation_note = ""

    if abs(extraction_gap) > 0.01:
        reconciliation_note = (
            f"⚠ Extraction gap detected: OCR total ₹{total_extracted:.2f} vs "
            f"category sum ₹{category_claimed_total:.2f} "
            f"(difference ₹{extraction_gap:.2f}). "
            f"This is usually caused by receipts categorised as 'other' or "
            f"skipped during data structuring — NOT a calculation error."
        )

    # ── Step 2: Apply policy rules per category ──────────────────────────
    category_eligible: Dict[str, Dict[str, Any]] = {}
    policy_violations: list[str] = []
    total_eligible = 0.0

    for cat_key, cat_data in categories.items():
        claimed    = cat_data.get("total_claimed", 0.0)
        item_count = cat_data.get("item_count", 1)
        policy     = get_category_policy(cat_key)

        eligible  = 0.0
        reasoning = ""

        # ── Two-wheeler ──────────────────────────────────────────────────
        if cat_key == "two_wheeler":
            if distance_for_calc:
                eligible, reasoning = calculate_eligible_amount(
                    category=cat_key,
                    claimed_amount=claimed,
                    distance_km=distance_for_calc,
                )
                expected_fuel_cost = distance_for_calc * policy.rate_per_km
                tolerance_limit    = expected_fuel_cost * (
                    1 + DISTANCE_RULES["tolerance_percent"] / 100
                )
                if claimed > tolerance_limit:
                    policy_violations.append(
                        f"Two-wheeler claim (₹{claimed:.2f}) exceeds expected "
                        f"cost for {distance_for_calc} km "
                        f"(₹{expected_fuel_cost:.2f} + "
                        f"{DISTANCE_RULES['tolerance_percent']}% tolerance = "
                        f"₹{tolerance_limit:.2f})"
                    )
            elif state.get("voucher_line_decisions"):
                # Voucher path: per-item judgment already approved these amounts
                # and _enforce_policy_caps already applied the monthly cap.
                # Do not require Unolo — the voucher is the authoritative source.
                eligible  = claimed
                reasoning = "Voucher-approved amount — policy caps applied per-item."
            else:
                if DISTANCE_RULES.get("require_unolo_for_two_wheeler", True):
                    eligible  = 0.0
                    reasoning = (
                        "Distance tracking proof (Unolo) required for "
                        "two-wheeler claims"
                    )
                    policy_violations.append(
                        "Missing Unolo distance tracking for two-wheeler claim"
                    )
                else:
                    eligible  = 0.0
                    reasoning = (
                        "Distance not provided — cannot calculate "
                        "two-wheeler reimbursement"
                    )
                    policy_violations.append(
                        "No distance provided for two-wheeler claim"
                    )

        # ── Food ─────────────────────────────────────────────────────────
        elif cat_key == "food":
            days_to_use = claim_days if claim_days > 0 else item_count
            eligible, reasoning = calculate_eligible_amount(
                category=cat_key,
                claimed_amount=claimed,
                days_count=days_to_use,
            )
            if claim_days == 0:
                reasoning += (
                    " (claim period days unknown — used receipt count "
                    "as day estimate)"
                )

        # ── Bus travel ───────────────────────────────────────────────────
        elif cat_key == "bus_travel":
            eligible, reasoning = calculate_eligible_amount(
                category=cat_key,
                claimed_amount=claimed,
                trip_count=item_count,
            )

        # ── All other named categories (fasttag, etc.) ───────────────────
        else:
            eligible, reasoning = calculate_eligible_amount(
                category=cat_key,
                claimed_amount=claimed,
            )

        # Flag if claimed exceeds monthly limit
        if hasattr(policy, "monthly_limit") and claimed > policy.monthly_limit:
            policy_violations.append(
                f"{policy.name}: Claimed ₹{claimed:.2f} exceeds monthly "
                f"limit ₹{policy.monthly_limit:.2f}"
            )

        # ── FIX: always write full dict so Critic 2 can read named fields ─
        category_eligible[cat_key] = {
            "claimed":      round(claimed, 2),
            "eligible":     round(eligible, 2),
            "reasoning":    reasoning,
            "items":        item_count,
            "policy_limit": getattr(policy, "monthly_limit", 0.0),
        }

        total_eligible += eligible

    # ── Step 3: Write results to state ───────────────────────────────────
    state["eligible_amount"]        = round(total_eligible, 2)
    state["category_eligible"]      = category_eligible
    state["policy_violations"]      = policy_violations
    # Pass reconciliation data forward so Critic 2 uses it correctly
    state["category_claimed_total"] = round(category_claimed_total, 2)
    state["extraction_gap"]         = extraction_gap
    state["reconciliation_note"]    = reconciliation_note

    return state


# ── Helpers ───────────────────────────────────────────────────────────────────

def _calculate_days(start_date: str, end_date: str) -> int:
    """Calculate number of days in claim period (inclusive)."""
    from datetime import datetime

    if not start_date or not end_date:
        return 0

    try:
        start = datetime.fromisoformat(start_date.split("T")[0])
        end   = datetime.fromisoformat(end_date.split("T")[0])
        return max((end - start).days + 1, 1)
    except Exception:
        return 0


