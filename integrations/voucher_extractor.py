"""
Voucher Extractor

Parses SpineHR expense voucher PDFs and extracts proof documents from ZIP archives.
Handles the standard Rite Water Solutions expense voucher format.
"""

import os
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False


_MONTH = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

# Maps SpineHR expense head labels → internal policy category keys
EXPENSE_HEAD_MAP: Dict[str, str] = {
    "2 wheeler":        "two_wheeler",
    "two wheeler":      "two_wheeler",
    "bike":             "two_wheeler",
    "food allowance":   "food",
    "food":             "food",
    "da":               "food",
    "daily allowance":  "food",
    "site expenses":    "site_expenses",
    "site expense":     "site_expenses",
    "hotel":            "site_expenses",
    "accommodation":    "site_expenses",
    "lodging":          "site_expenses",
    "bus":              "bus_travel",
    "train":            "bus_travel",
    "rail":             "bus_travel",
    "fasttag":          "fasttag",
    "toll":             "fasttag",
    "fuel":             "fuel_bill",
    "petrol":           "fuel_bill",
}

_SUPPORTED_PROOF_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"}
_FOOTER_KEYWORDS = ("gross payable", "net payable", "net payable/recoverable")


# ── Public API ────────────────────────────────────────────────────────────────

def extract_voucher_data(pdf_path: str) -> Dict[str, Any]:
    """
    Extract all structured data from a SpineHR expense voucher PDF.

    Returns:
        {
            voucher_no, voucher_date, employee_name, employee_code,
            period_start, period_end, cost_center, narration,
            currency, line_items: List[dict], gross_claimed: float
        }
    """
    if not PDFPLUMBER_AVAILABLE:
        raise ImportError("pdfplumber is required: pip install pdfplumber")

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        text = page.extract_text() or ""
        raw_tables = page.extract_tables()

    result: Dict[str, Any] = {
        "voucher_no":    _search(r"Voucher No\.\s*(\S+)", text),
        "voucher_date":  _parse_date(_search(r"Voucher date\s+(\S+)", text) or ""),
        "employee_name": _search(r"Employee Name\s+(.+?)\s+Employee Code", text),
        "employee_code": _search(r"Employee Code\s+(\S+)", text),
        "period_start":  None,
        "period_end":    None,
        "cost_center":   _search(r"Cost Center\s+(.+?)(?:\n|$)", text),
        "narration":     None,
        "currency":      "INR",
        "line_items":    [],
        "gross_claimed": 0.0,
    }

    # Period
    m = re.search(r"For the period\s+(\S+)\s+to\s+(\S+)", text, re.IGNORECASE)
    if m:
        result["period_start"] = _parse_date(m.group(1))
        result["period_end"]   = _parse_date(m.group(2))

    # Narration — single-line description before the expense table
    narr = _search(
        r"Narration\s+(.+?)(?=\nExpense Head|\nSr\.?\s*No|\nDate\s+Expense|\nPage\s*:|$)",
        text,
        re.DOTALL,
    )
    if narr:
        # Collapse whitespace and truncate to the first sentence / reasonable length
        narr_clean = " ".join(narr.split())
        result["narration"] = narr_clean[:200]  # cap at 200 chars

    # Line items from the first table on the page
    if raw_tables:
        result["line_items"] = _parse_expense_table(raw_tables[0])
        result["gross_claimed"] = sum(r["claimed_amount"] for r in result["line_items"])

    return result


def extract_zip_proofs(zip_path: str, extract_dir: str) -> List[str]:
    """
    Unzip proof documents from a ZIP archive.

    Returns sorted list of image/PDF file paths, skipping macOS metadata files.
    """
    os.makedirs(extract_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as z:
        # Only extract supported file types; skip __MACOSX and hidden files
        for member in z.namelist():
            name = Path(member).name
            if (
                name.startswith(".")
                or "__MACOSX" in member
                or Path(member).suffix.lower() not in _SUPPORTED_PROOF_EXTS
            ):
                continue
            z.extract(member, extract_dir)

    found: List[str] = []
    for root, _, files in os.walk(extract_dir):
        for f in files:
            if Path(f).suffix.lower() in _SUPPORTED_PROOF_EXTS:
                found.append(os.path.join(root, f))
    return sorted(found)


# ── Private helpers ───────────────────────────────────────────────────────────

def _search(pattern: str, text: str, flags: int = 0) -> Optional[str]:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _parse_date(s: str) -> str:
    """Convert d-MMM-YY or d-MMM-YYYY → YYYY-MM-DD. Returns input unchanged if unrecognised."""
    if not s:
        return s
    m = re.match(r"(\d{1,2})-([A-Za-z]{3})-(\d{2,4})", s)
    if not m:
        return s
    day, mon, yr = m.group(1), m.group(2).lower(), m.group(3)
    yr = ("20" + yr) if len(yr) == 2 else yr
    return f"{yr}-{_MONTH.get(mon, '01')}-{int(day):02d}"


def _to_float(s: Any) -> float:
    cleaned = re.sub(r"[^\d.]", "", str(s or ""))
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def _parse_expense_table(table: List[List]) -> List[Dict[str, Any]]:
    """
    Parse raw table rows from pdfplumber into structured line items.

    Handles two column layouts:
      7-col: Expense Head | Date | Remarks | Currency | Claimed | Approved | Rejected
      6-col: Expense Head | Date | Remarks | Claimed  | Approved | Rejected
    """
    items: List[Dict[str, Any]] = []
    header_found = False

    for row in table:
        if not row or not any(c for c in row if c):
            continue

        first = str(row[0] or "").strip()
        first_lower = first.lower()

        # Identify header row
        if "expense head" in first_lower:
            header_found = True
            continue

        # Skip footer rows but don't stop — multi-page vouchers may continue
        if any(kw in first_lower for kw in _FOOTER_KEYWORDS):
            continue

        if not header_found or not first:
            continue

        try:
            n = len(row)
            if n >= 7:
                expense_head = str(row[0] or "").strip()
                expense_date = str(row[1] or "").strip()
                remarks      = str(row[2] or "").strip()
                # row[3] = currency (INR)
                claimed      = _to_float(row[4])
                approved     = _to_float(row[5])
                rejected     = _to_float(row[6])
            elif n == 6:
                expense_head = str(row[0] or "").strip()
                expense_date = str(row[1] or "").strip()
                remarks      = str(row[2] or "").strip()
                claimed      = _to_float(row[3])
                approved     = _to_float(row[4])
                rejected     = _to_float(row[5])
            else:
                continue

            if not expense_head:
                continue

            category = EXPENSE_HEAD_MAP.get(expense_head.lower(), "other")

            items.append({
                "expense_head":    expense_head,
                "category":        category,
                "date":            _parse_date(expense_date),
                "remarks":         remarks,
                "claimed_amount":  claimed,
                "approved_amount": approved,   # existing value from SpineHR (may be 0)
                "rejected_amount": rejected,   # existing value from SpineHR (may be 0)
            })
        except (IndexError, ValueError):
            continue

    return items
