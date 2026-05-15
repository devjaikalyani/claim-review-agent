"""
Data Agent

Structures extracted receipt data into expense categories.

Priority logic:
  1. When a verified expense voucher PDF (employee_summary) is present, use its
     category breakdown as the authoritative source. Individual receipt scans
     serve as supporting evidence — not the calculation basis.
  2. When no voucher is present, derive categories from individual receipt scans.
"""
from typing import Dict, Any
from agents.state import ClaimState, ExpenseCategory


# Maps receipt_type strings from OCR → ExpenseCategory values
_RECEIPT_TYPE_MAP: Dict[str, str] = {
    "site_expenses": ExpenseCategory.SITE_EXPENSES.value,
    "fuel_bill":     ExpenseCategory.TWO_WHEELER.value,
    "bus_ticket":    ExpenseCategory.BUS_TRAVEL.value,
    "fasttag":       ExpenseCategory.FASTTAG.value,
    "food_bill":     ExpenseCategory.FOOD.value,
    "upi_payment":   ExpenseCategory.SITE_EXPENSES.value,  # UPI = operational site payment
    "other":         ExpenseCategory.OTHER.value,
}

# Maps PDF expense-head category keys → ExpenseCategory values
_SUMMARY_CAT_MAP: Dict[str, str] = {
    # canonical keys returned by _VOUCHER_EXTRACT_PROMPT
    "site_expenses":    ExpenseCategory.SITE_EXPENSES.value,
    "bus_travel":       ExpenseCategory.BUS_TRAVEL.value,
    "food":             ExpenseCategory.FOOD.value,
    "fasttag":          ExpenseCategory.FASTTAG.value,
    "two_wheeler":      ExpenseCategory.TWO_WHEELER.value,
    "fuel_bill":        ExpenseCategory.TWO_WHEELER.value,
    "hotel":            ExpenseCategory.HOTEL.value,
    "car_conveyance":   ExpenseCategory.CAR_CONVEYANCE.value,
    "other":            ExpenseCategory.OTHER.value,
    # extra aliases that may appear if LLM uses the voucher's raw Expense Head names
    "ac_bus":                ExpenseCategory.BUS_TRAVEL.value,
    "ac bus":                ExpenseCategory.BUS_TRAVEL.value,
    "sleeper_class":         ExpenseCategory.BUS_TRAVEL.value,
    "sleeper class":         ExpenseCategory.BUS_TRAVEL.value,
    "sleeper_class_train":   ExpenseCategory.BUS_TRAVEL.value,
    "auto":                  ExpenseCategory.BUS_TRAVEL.value,
    "2_wheeler":             ExpenseCategory.TWO_WHEELER.value,
    "2 wheeler":             ExpenseCategory.TWO_WHEELER.value,
    "food_allowance":        ExpenseCategory.FOOD.value,
    "food allowance":        ExpenseCategory.FOOD.value,
    "da":                    ExpenseCategory.FOOD.value,
    "hotel_accommodation":   ExpenseCategory.HOTEL.value,
    "hotel accommodation":   ExpenseCategory.HOTEL.value,
    "accommodation":         ExpenseCategory.HOTEL.value,
    "lodge":                 ExpenseCategory.HOTEL.value,
    "guest_house":           ExpenseCategory.HOTEL.value,
    "guest house":           ExpenseCategory.HOTEL.value,
    "car":                   ExpenseCategory.CAR_CONVEYANCE.value,
    "car_fuel":              ExpenseCategory.CAR_CONVEYANCE.value,
    "car fuel":              ExpenseCategory.CAR_CONVEYANCE.value,
    "vehicle":               ExpenseCategory.CAR_CONVEYANCE.value,
    "toll":                  ExpenseCategory.FASTTAG.value,
    "toll_charges":          ExpenseCategory.FASTTAG.value,
    "other_expense":         ExpenseCategory.OTHER.value,
    "other expense":         ExpenseCategory.OTHER.value,
}


def data_agent(state: ClaimState) -> ClaimState:
    state["current_agent"] = "data"

    summary = state.get("employee_summary")
    # Require only is_summary — categories may be empty if PDF uses ₹/Rs. symbols
    # that the older regex missed; _build_from_summary handles that gracefully.
    voucher_available = (
        summary
        and summary.get("is_summary")
    )

    if voucher_available:
        # ── Path A: Official expense voucher is present → use as primary source ──
        _build_from_summary(state, summary)
    else:
        # ── Path B: No voucher → derive from individual receipt scans ────────────
        _build_from_receipts(state)

    return state


# ── Path A ────────────────────────────────────────────────────────────────────

def _build_from_summary(state: ClaimState, summary: Dict[str, Any]) -> None:
    """
    Populate expenses and categories from the verified expense voucher.
    The voucher is an official company document — treat its amounts as correct.

    If the PDF parser extracted no category breakdown (e.g. PDF used ₹ symbols
    that bypassed the old regex), fall back to a single site_expenses entry
    for the voucher total so the correct amount is still honoured.
    """
    categories_data = summary.get("categories") or {}

    if not categories_data:
        # PDF detected as summary but category lines not parsed.
        # Use summary_total (claimed amount) so calculator can apply policy.
        total = float(summary.get("summary_total") or 0.0)
        if total > 0:
            mapped_cat = ExpenseCategory.SITE_EXPENSES.value
            expense = {
                "category":         mapped_cat,
                "amount":           total,
                "date":             "",
                "description":      "Expense Voucher (category breakdown not extracted)",
                "source_document":  summary.get("path", "expense_voucher"),
                "confidence":       0.90,
                "is_valid":         True,
                "validation_notes": "From verified expense voucher",
            }
            state["expenses"]               = [expense]
            state["categories"]             = {
                mapped_cat: {
                    "category":      mapped_cat,
                    "total_claimed": total,
                    "items":         [expense],
                    "item_count":    1,
                }
            }
            state["total_extracted_amount"] = total
        return

    expenses:   list  = []
    categories: dict  = {}
    total_amount      = 0.0

    for cat_key, cat_info in categories_data.items():
        claimed = float(cat_info.get("claimed", 0.0))
        if claimed <= 0:
            continue

        # Map voucher expense-head key → canonical ExpenseCategory (case-insensitive)
        mapped_cat = _SUMMARY_CAT_MAP.get(cat_key) \
                  or _SUMMARY_CAT_MAP.get(cat_key.lower()) \
                  or ExpenseCategory.OTHER.value

        if mapped_cat not in categories:
            categories[mapped_cat] = {
                "category":      mapped_cat,
                "total_claimed": 0.0,
                "items":         [],
                "item_count":    0,
            }

        categories[mapped_cat]["total_claimed"] += claimed
        item_list = cat_info.get("items", [])
        categories[mapped_cat]["item_count"] += len(item_list) or 1

        for item in item_list:
            item_amount = float(item.get("amount", 0.0))
            if item_amount <= 0:
                continue
            expense = {
                "category":         mapped_cat,
                "amount":           item_amount,
                "date":             item.get("date", ""),
                "description":      item.get("expense_head", "Expense"),
                "source_document":  summary.get("path", "expense_voucher"),
                "confidence":       0.90,
                "is_valid":         True,
                "validation_notes": "From expense voucher (claimed amount)",
            }
            categories[mapped_cat]["items"].append(expense)
            expenses.append(expense)

        total_amount += claimed

    state["expenses"]               = expenses
    state["categories"]             = categories
    state["total_extracted_amount"] = total_amount


# ── Path B ────────────────────────────────────────────────────────────────────

def _build_from_receipts(state: ClaimState) -> None:
    """Derive expense categories from individual OCR-scanned receipts."""
    extracted_text = state.get("extracted_text", [])
    expenses:   list = []
    categories: dict = {}
    total_amount     = 0.0

    for doc in extracted_text:
        doc_type = doc.get("type", "other")
        data     = doc.get("data", {})
        source   = doc.get("source", "unknown")
        amount   = float(data.get("total_amount", 0))

        if amount <= 0:
            continue

        if doc_type == "fasttag":
            for txn in data.get("transactions", []):
                _add_expense(
                    expenses, categories,
                    category    = ExpenseCategory.FASTTAG.value,
                    amount      = float(txn.get("amount", 0)),
                    date        = txn.get("date", ""),
                    description = f"Toll: {txn.get('toll_plaza', 'Unknown')}",
                    source      = source,
                    confidence  = data.get("confidence", 0.8),
                    source_type = "fasttag",
                )
        elif doc_type == "unolo":
            pass  # Distance only — not an expense line item
        else:
            category = _RECEIPT_TYPE_MAP.get(doc_type, ExpenseCategory.OTHER.value)

            # For UPI payments: look at vendor name to refine category
            if doc_type == "upi_payment":
                category = _refine_upi_category(data)

            _add_expense(
                expenses, categories,
                category    = category,
                amount      = amount,
                date        = data.get("date", ""),
                description = _build_description(doc_type, data),
                source      = source,
                confidence  = data.get("confidence", 0.8),
                notes       = "UPI payment — category inferred from vendor" if doc_type == "upi_payment" else "",
                source_type = "upi_payment" if doc_type == "upi_payment" else "receipt",
            )

    # Last resort: if still no receipts, try the summary as fallback
    summary = state.get("employee_summary")
    if not expenses and summary and summary.get("is_summary") and summary.get("categories"):
        _build_from_summary(state, summary)
        return

    # ── Deduplicate: group by (category, amount, normalised-date) ────────────────
    # ── Dedup: only remove IDENTICAL submissions (same file scanned twice) ──────
    #
    # We only remove an item here if it is an exact duplicate: same category +
    # amount + date + description. This catches the case where an employee
    # accidentally uploads the same receipt file twice.
    #
    # We do NOT remove items based on source_type (receipt vs upi_payment) here.
    # Two different payments can legitimately share the same amount and date
    # (e.g. hotel bill ₹15,120 AND a separate UPI to a different person for ₹15,120).
    # Near-duplicate detection (receipt + UPI for the same transaction) is handled
    # by the admin judgment agent which has LLM reasoning and training examples.

    # Resolve year hint once from claim period for partial-date normalisation
    period_start = state.get("claim_period_start", "")
    year_hint = 0
    if period_start:
        from datetime import datetime as _dt
        try:
            year_hint = _dt.fromisoformat(period_start).year
        except ValueError:
            pass

    # Group expenses by (category, amount, date, description) — exact match only
    groups: Dict[tuple, list] = {}
    for expense in expenses:
        desc_key = (expense.get("description") or "").strip().lower()[:60]
        key = (
            expense["category"],
            expense["amount"],
            _normalise_date(expense.get("date", ""), year_hint),
            desc_key,
        )
        groups.setdefault(key, []).append(expense)

    deduped:           list = []
    duplicates_removed: list = []

    for key, group in groups.items():
        deduped.append(group[0])
        for dup in group[1:]:
            duplicates_removed.append(
                f"{dup['description']} — Rs.{dup['amount']:,.2f} on "
                f"{dup.get('date') or 'unknown date'} "
                f"(identical submission — kept one copy)"
            )

    # Rebuild categories from the de-duplicated list
    categories_deduped: dict = {}
    for exp in deduped:
        cat = exp["category"]
        if cat not in categories_deduped:
            categories_deduped[cat] = {
                "category":      cat,
                "total_claimed": 0.0,
                "items":         [],
                "item_count":    0,
            }
        categories_deduped[cat]["total_claimed"] += exp["amount"]
        categories_deduped[cat]["items"].append(exp)
        categories_deduped[cat]["item_count"]    += 1
        total_amount += exp["amount"]

    state["expenses"]               = deduped
    state["categories"]             = categories_deduped
    state["total_extracted_amount"] = total_amount
    state["duplicates_removed"]     = duplicates_removed


def _add_expense(
    expenses: list,
    categories: dict,
    category: str,
    amount: float,
    date: str,
    description: str,
    source: str,
    confidence: float = 0.8,
    notes: str = "",
    source_type: str = "receipt",
) -> None:
    if amount <= 0:
        return
    expense = {
        "category":         category,
        "amount":           amount,
        "date":             date,
        "description":      description,
        "source_document":  source,
        "confidence":       confidence,
        "is_valid":         True,
        "validation_notes": notes,
        "source_type":      source_type,   # "upi_payment" | "receipt" | "fasttag"
    }
    expenses.append(expense)
    if category not in categories:
        categories[category] = {
            "category":      category,
            "total_claimed": 0.0,
            "items":         [],
            "item_count":    0,
        }
    categories[category]["total_claimed"] += amount
    categories[category]["items"].append(expense)
    categories[category]["item_count"]    += 1


def _refine_upi_category(data: Dict[str, Any]) -> str:
    """
    Try to determine a more specific category from a UPI payment's vendor/description.
    Defaults to site_expenses (most common operational payment type).
    """
    text = (
        (data.get("vendor_name") or "") + " " +
        (data.get("raw_text") or "")
    ).lower()

    if any(k in text for k in ["petrol", "diesel", "fuel", "hpcl", "bpcl", "iocl", "indian oil"]):
        return ExpenseCategory.TWO_WHEELER.value
    if any(k in text for k in ["restaurant", "hotel", "food", "cafe", "swiggy", "zomato", "da ", "allowance"]):
        return ExpenseCategory.FOOD.value
    if any(k in text for k in ["bus", "train", "ticket", "msrtc", "ksrtc", "irctc"]):
        return ExpenseCategory.BUS_TRAVEL.value
    if any(k in text for k in ["fasttag", "toll", "nhai", "highway"]):
        return ExpenseCategory.FASTTAG.value
    # Default: treat UPI payments as site expenses (operational payments)
    return ExpenseCategory.SITE_EXPENSES.value


def _build_description(doc_type: str, data: Dict[str, Any]) -> str:
    vendor = data.get("vendor_name", "")
    labels = {
        "site_expenses": f"Site Expense: {vendor or 'Operational'}",
        "upi_payment":   f"UPI: {vendor or 'Payment'}",
        "fuel_bill":     f"Fuel: {vendor or 'Petrol Pump'}",
        "bus_ticket":    f"Bus/Train: {vendor or 'Transport'}",
        "fasttag":       f"Toll: {vendor or 'FASTag'}",
        "food_bill":     f"Food: {vendor or 'Meal'}",
    }
    return labels.get(doc_type, vendor or "Receipt")


def _vendor_prefix(expense: Dict[str, Any]) -> str:
    """
    Return a normalised vendor key for cross-source deduplication.
    Strips category prefixes like "UPI:", "Site Expense:", "Rapido:" etc.
    and returns the first meaningful word in lowercase so that
    "Hotel Alaknanda" and "UPI: Hotel Alaknanda" map to the same key,
    while "Hotel Alaknanda" and "Md Shahjad" remain distinct.
    """
    desc = (expense.get("description") or "").strip()
    # Strip common prefixes that encode the payment channel, not the vendor
    for prefix in ("upi:", "upi payment:", "site expense:", "site expenses:",
                   "rapido:", "fasttag:", "fuel:", "food:", "bus ticket:",
                   "bus travel:", "other:"):
        if desc.lower().startswith(prefix):
            desc = desc[len(prefix):].strip()
            break
    # Take the first word as the vendor key (lowercased, alphanumeric only)
    first_word = desc.split()[0] if desc.split() else ""
    return first_word.lower().strip(".,;:-")


def _normalise_date(date_str: str, year_hint: int = 0) -> str:
    """
    Normalise any date string to YYYY-MM-DD for reliable deduplication.
    Claude Vision may return DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY, DD-Mon-YY, etc.

    year_hint: fallback year (e.g. from claim_period_start) used for partial
    dates like "25 Jan" that have no year component. Pass 0 to use the current year.

    Returns "" when the date cannot be parsed so downstream dedup keys stay clean
    rather than containing raw unparseable strings.
    """
    if not date_str or date_str.upper() in ("N/A", "NA", ""):
        return ""
    from datetime import datetime
    # Full date formats (with year)
    for fmt in (
        "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y",
        "%d/%m/%y", "%d-%m-%y",
        "%d-%b-%Y", "%d-%b-%y",
        "%d %b %Y", "%d %b %y",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Partial date formats (no year) — infer year from claim period or current year
    infer_year = year_hint if year_hint else datetime.now().year
    for fmt in ("%d %b", "%d-%b", "%d/%b", "%d %B", "%d-%B"):
        try:
            d = datetime.strptime(f"{date_str.strip()} {infer_year}", f"{fmt} %Y")
            return d.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Could not parse — return empty string; caller should not rely on raw strings
    return ""
