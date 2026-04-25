"""
Vision AI - Receipt & Screenshot Scanner

Uses Claude Vision API for images + pypdf for PDF summary extraction.
Summary PDF is stored separately for Critic 2 — NOT used as total_extracted.
Individual receipt amounts feed the calculator.
"""

import json
import os
import re
import time
import concurrent.futures
from pathlib import Path

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
# PDFs are also scannable via Claude's native document blocks
SUPPORTED_SCAN_EXTS  = SUPPORTED_IMAGE_EXTS | {".pdf"}

TRAVEL_KEYWORDS = {
    "km", "kilometer", "kilometre", "distance", "trip", "gps",
    "fuel", "petrol", "diesel", "fasttag", "toll", "odometer",
    "travel", "route", "unolo", "location", "tracking", "speed",
    "indian oil", "hp", "bharat petroleum", "iocl", "hpcl", "bpcl",
    "nhai", "highway", "expressway"
}

# Filename stems that indicate an odometer/trip-reading screenshot
_ODOMETER_FILENAME_KEYWORDS = {
    "odo", "odometer", "reading", "inreading", "outreading",
    "in_reading", "out_reading", "km_reading", "trip_reading",
    "speedometer", "mileage", "trip_km", "meter_reading",
}

EXPENSE_HEAD_MAP = {
    "site expenses":  "site_expenses",
    "site expense":   "site_expenses",
    "food allowance": "food",
    "food":           "food",
    "da":             "food",
    "daily allowance":"food",
    "ac bus":         "bus_travel",
    "bus":            "bus_travel",
    "auto":           "bus_travel",
    "taxi":           "bus_travel",
    "cab":            "bus_travel",
    "fuel":           "fuel_bill",
    "petrol":         "fuel_bill",
    "two wheeler":    "two_wheeler",
    "fasttag":        "fasttag",
    "toll":           "fasttag",
    "hotel":          "site_expenses",
    "accommodation":  "site_expenses",
    "lodging":        "site_expenses",
    "guest house":    "site_expenses",
    "paying guest":   "site_expenses",
    "dharamshala":    "site_expenses",
    "other":          "other",
}

# Images per API call. Smaller batches keep token usage per call low and avoid rate limits.
_BATCH_SIZE     = 3   # images per batch (smaller = more parallel, faster overall)
_PDF_BATCH_SIZE = 2   # PDFs per batch (multi-page → more tokens)
# Max concurrent Vision API calls. 4 workers process 12-13 images in ~2 rounds.
_MAX_WORKERS = 4

# Retry threshold: retry individually when amount=0 or confidence below this
_RETRY_CONFIDENCE_THRESHOLD = 0.50

_BATCH_OCR_PROMPT = """You are an expert at reading Indian business receipts and payment screenshots for Rite Water Solutions India Limited, a water infrastructure company whose field employees submit fuel, hotel, food, site material, and travel expense claims.

You will receive MULTIPLE files (images or PDF documents). Analyse EACH file independently and return a JSON ARRAY where every element corresponds to one file, in the exact same order they were provided.

Each element must have these fields:
  "raw_text"    : all readable text from the image as a plain string
  "receipt_type": one of  upi_payment | site_expenses | fuel_bill | fasttag | bus_ticket | food_bill | other
  "vendor"      : merchant or payee name (or "Unknown")
  "date"        : date in YYYY-MM-DD format, or "N/A"
  "amount"      : numeric INR amount, no currency symbol (0 if not found)
  "confidence"  : float 0.0–1.0

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLASSIFICATION RULES (apply in this strict order):

  site_expenses — ANY of the following:
      • Material purchase receipts: hardware, tools, pipes, wire, sadal, bend, fastener, anchor,
        thread, lug, elbow, GI wire, conduit, cable, fitting, clamp, bracket, board, paint
      • Parcel / dispatch / courier bills for sending goods to site
      • Porter charges, labour charges, loading/unloading
      • Hotel, accommodation, lodging, guest house, paying guest (PG), dharamshala, inn, stay,
        room rent, room charges — ANY overnight stay bill regardless of what the place is called
      • UPI payments whose payee name or description mentions hotel, lodge, guest house, stay,
        accommodation, rent, material, hardware, parcel, site, or any of the above items

  upi_payment   — PhonePe, GPay, Google Pay, Paytm, BHIM, or any UPI transfer where the
                  purpose is unclear (person-to-person, salary advance, unknown vendor)

  fasttag       — FASTag / NHAI toll deduction screenshot or SMS; any toll plaza charge

  fuel_bill     — Petrol pump or diesel station printed receipt (HPCL, BPCL, IOCL, Indian Oil,
                  HP, Shell, Reliance, any petrol station)

  bus_ticket    — Bus ticket, train ticket, auto-rickshaw, cab (Ola, Uber, Rapido), local taxi,
                  or any personal travel transport receipt

  food_bill     — Restaurant bill, cafe receipt, dhaba bill, food delivery (Swiggy, Zomato),
                  daily allowance / DA voucher, canteen slip
                  NOTE: A place named "Hotel XYZ" that serves food (restaurant) is food_bill.
                        A place named "Hotel XYZ" that provides room stay is site_expenses.
                        Distinguish by whether the bill shows food items vs room/night charges.

  other         — Anything that does not fit the above categories clearly

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLASSIFICATION EXAMPLES — study before processing:

EXAMPLE 1 — Guest house UPI (→ site_expenses, NOT upi_payment):
  Image: PhonePe app showing "Payment Successful ₹2,800 to Shree Ganesh Guest House, UPI ID shreeganesh@ybl, 22-Mar-2025"
  Output: receipt_type = "site_expenses", vendor = "Shree Ganesh Guest House", amount = 2800, confidence = 0.95
  Reason: Payee name explicitly mentions guest house → accommodation → site_expenses

EXAMPLE 2 — Hardware store material bill (→ site_expenses):
  Image: Hand-written bill "M/s Shree Hardware, GI Wire 2kg ₹340, Anchor Bolt 20pcs ₹480, Total ₹820, Date 10/02/2025"
  Output: receipt_type = "site_expenses", vendor = "Shree Hardware", amount = 820, confidence = 0.88
  Reason: Site installation materials (wire, anchor bolts) → site_expenses

EXAMPLE 3 — BPCL fuel receipt (→ fuel_bill):
  Image: Printed receipt "Bharat Petroleum, Diesel 12.5L, Rate ₹92.50/L, Amount ₹1,156.25, Vehicle MH14CD5678, 05/01/2025 14:32"
  Output: receipt_type = "fuel_bill", vendor = "BPCL", amount = 1156.25, confidence = 0.98
  Reason: Petrol pump diesel receipt → fuel_bill

EXAMPLE 4 — FASTag toll deduction (→ fasttag):
  Image: NHAI SMS "FASTag Debit ₹75 at Khalapur Toll Plaza, Vehicle KA03MM4512, Balance ₹1,240, TxnID FASTG20250112XXXX"
  Output: receipt_type = "fasttag", vendor = "NHAI Khalapur", amount = 75, confidence = 0.97
  Reason: NHAI toll deduction → fasttag

EXAMPLE 5 — Restaurant food bill (→ food_bill):
  Image: "Hotel Shivaji Restaurant, Table 4, Veg Thali x2 ₹240, Lassi ₹80, GST 5% ₹16, Total ₹336, 18-Jan-2025"
  Output: receipt_type = "food_bill", vendor = "Hotel Shivaji Restaurant", amount = 336, confidence = 0.97
  Reason: "Hotel" in name but this is a restaurant serving food (Thali, Lassi) → food_bill, not site_expenses

EXAMPLE 6 — Person-to-person UPI (→ upi_payment):
  Image: "Google Pay, Paid ₹500 to Ramesh Kumar, UPI: rameshk@okaxis, 08 Feb 2025"
  Output: receipt_type = "upi_payment", vendor = "Ramesh Kumar", amount = 500, confidence = 0.90
  Reason: Payment to an individual with no business description → upi_payment

EXAMPLE 7 — Cab ride (→ bus_ticket):
  Image: "Ola Cabs, Trip Completed, Akola to MIDC, 14.2 km, Fare ₹220, 14/03/2025 09:15 AM"
  Output: receipt_type = "bus_ticket", vendor = "Ola Cabs", amount = 220, confidence = 0.96
  Reason: Cab ride for personal travel → bus_ticket

EXAMPLE 8 — DTDC courier of site goods (→ site_expenses):
  Image: "DTDC Courier, Booking No 12345, Sender: Pune Office, Receiver: Akola Site, 5kg parcel, Freight ₹350, 22/02/2025"
  Output: receipt_type = "site_expenses", vendor = "DTDC Courier", amount = 350, confidence = 0.93
  Reason: Courier dispatching goods to site → site_expenses

EXAMPLE 9 — PhonePe hotel room payment (→ site_expenses):
  Image: "PhonePe, Sent ₹1,200, To: Sunrise Lodge, Remarks: Room Rent Feb 15, UPI Ref: 9912XXXXXX, 15-02-2025"
  Output: receipt_type = "site_expenses", vendor = "Sunrise Lodge", amount = 1200, confidence = 0.94
  Reason: UPI remarks say "Room Rent" → accommodation → site_expenses

EXAMPLE 10 — Handwritten site material cash voucher (→ site_expenses):
  Image: Handwritten "Received from Ritewater, Pipes 4inch 6nos ₹1,800, Fittings ₹450, Total ₹2,250, Sign: [signature], Date 20-Jan-25"
  Output: receipt_type = "site_expenses", vendor = "Unknown", amount = 2250, confidence = 0.75
  Reason: Site material cash purchase; handwritten → lower confidence

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AMOUNT EXTRACTION — search strategies (try in order):

1. UPI screenshots (PhonePe/GPay/Paytm/BHIM): the payment amount is the large bold number near the top — NOT the wallet remaining balance shown below it
2. Fuel receipts: look for "Amount", "Total", or the product of (quantity × rate)
3. Hotel / guest house bills: look for "Total", "Net Amount", "Grand Total", "Bill Amount", "Room Charges Total"
4. Restaurant bills: look for "Total", "Grand Total", "Bill Total", "Amount Payable"
5. Handwritten bills: look for any underlined, circled, or boxed number at the bottom, or text labelled "Total"
6. Multi-item bills: use the GRAND TOTAL at the bottom, NOT the sum of individual visible items (the printed total already includes tax)
7. Courier/dispatch: look for "Freight", "Total Charges", "Amount"

COMMON MISTAKES TO AVOID:
- Do not confuse GSTIN (15-char alphanumeric) or mobile numbers with amounts
- Do not confuse invoice number with amount
- Do not confuse wallet balance (after deduction) with the payment amount
- Amounts like ₹1,250.00 → output 1250.0 (strip currency symbol and commas)
- If you see multiple candidate totals, prefer the one labelled "Total" or "Grand Total"
- Field employee expenses typically range ₹50 to ₹15,000 per receipt; outliers above ₹50,000 deserve scrutiny

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATE EXTRACTION RULES:

- Accept any Indian date format: DD/MM/YYYY, DD-MM-YYYY, DD MMM YYYY (e.g., 05 Jan 2025), YYYY-MM-DD, DD-MM-YY
- Normalise all dates to YYYY-MM-DD in your output (e.g., "05/01/2025" → "2025-01-05")
- If only month and year are visible (e.g., "Jan 2025"), output "2025-01-01"
- If date is completely absent or illegible, output "N/A"
- For SMS/app notifications: the date shown is the transaction date — use it

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONFIDENCE SCORING:

  0.95–1.00 : Machine-printed receipt, amount clearly visible, high contrast image
  0.80–0.94 : Amount visible but slight blur, shadow, or partial fold
  0.60–0.79 : Handwritten document, or faded thermal print — amount readable but uncertain
  0.40–0.59 : Multiple candidate amounts present; chose most likely; or image is rotated/tilted
  0.20–0.39 : Image is dark, blurry, or partially cut off; amount is a best guess
  0.00–0.19 : Amount is not visible at all; set amount = 0

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RAW_TEXT FORMATTING RULES:

- Replace every newline with a single space (no literal \\n inside the string value)
- Escape any double-quote characters inside the text as \\"
- Remove all control characters: tab (\\t), carriage return (\\r), null bytes, etc.
- Keep under 400 characters — truncate at a word boundary if longer
- Capture the most important identifying information: vendor name, date, amount, key items

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MULTI-FILE PROCESSING INSTRUCTIONS:

- Analyse each file completely independently — do not let one file's content influence another
- Return exactly one JSON object per file, in the same order the files were provided
- If a file is completely unreadable (blank, corrupted, or not a receipt), still return an object with confidence = 0.0 and amount = 0
- Do not merge or combine information across files
- Your output array length MUST equal the number of files sent

Respond with ONLY a valid JSON array — no extra text, no markdown fences, no explanations outside the array."""

_RETRY_OCR_PROMPT = """You are an expert at reading Indian business receipts, bills, and UPI payment screenshots for field employees of Rite Water Solutions India Limited. This specific image was flagged because an earlier scan returned amount = 0 or very low confidence. Your job is to look much more carefully and extract the data correctly.

Return ONLY a valid JSON object with these exact fields:
{
  "raw_text":     "<all visible text as a plain string, spaces instead of newlines, max 400 chars>",
  "receipt_type": "<one of: upi_payment | site_expenses | fuel_bill | fasttag | bus_ticket | food_bill | other>",
  "vendor":       "<merchant, payee, or business name — 'Unknown' if truly not visible>",
  "date":         "<date normalised to YYYY-MM-DD — 'N/A' if not visible>",
  "amount":       <total INR amount as a plain number, no currency symbol — 0 only if truly invisible>,
  "confidence":   <your confidence 0.0–1.0 that the extracted amount is correct>
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AMOUNT SEARCH — try every strategy before returning 0:

Strategy 1 — UPI App Screenshots (PhonePe, GPay, Google Pay, Paytm, BHIM, NPCI):
  • The payment amount is the LARGE BOLD number displayed prominently near the top or centre
  • Ignore the "Available Balance" or "Wallet Balance" shown at the bottom — that is NOT the amount paid
  • PhonePe shows: "₹XXXX" in large font → that is your amount
  • GPay shows: "You paid ₹XXXX" or "₹XXXX sent" → that is your amount
  • Paytm shows: "₹XXXX paid successfully" → that is your amount

Strategy 2 — Petrol / Diesel Station Receipts:
  • Look for "Amount", "Total Amount", "Bill Amount", or the product line (qty × rate = amount)
  • BPCL/HPCL/IOCL receipts typically show: "Qty: 10.00 L, Rate: 94.50, Amount: 945.00"
  • The amount is the final number after "Amount:" or at the bottom of the receipt

Strategy 3 — Hotel / Guest House / Lodge Bills:
  • Look for "Total", "Grand Total", "Net Amount", "Bill Amount", "Room Charges", "Amount Payable"
  • These bills sometimes have multiple numbers (GST, discount) — use the FINAL total
  • If you see "Room Rent: ₹800 × 2 nights = ₹1,600" — the amount is 1600

Strategy 4 — Restaurant / Dhaba / Food Bills:
  • Look for "Total", "Grand Total", "Bill Total", "Net Payable"
  • Include GST in the total — use the final "Amount Payable" figure

Strategy 5 — Hardware / Material / Courier Bills:
  • Look for "Total", "Grand Total", "Net Amount", "Total Amount Due"
  • Handwritten bills: look for a circled, underlined, or boxed number at the bottom
  • If you see a column of numbers with a horizontal line under the last one — that last number is the total

Strategy 6 — FASTag / NHAI Toll SMS:
  • SMS format: "FASTag Debit of Rs.XX at [Toll Plaza]" — XX is the amount
  • Screenshot format: "Deducted: ₹XX" or "Transaction Amount: ₹XX"

Strategy 7 — Multiple Numbers Present:
  • Prefer the number labelled "Total", "Grand Total", "Net Amount", or "Amount Payable"
  • If none of those labels exist, the amount is usually the LARGEST number that is a plausible expense (₹50–₹15,000)
  • Reject numbers that are clearly GSTIN (15 chars), phone numbers (10 digits), invoice numbers, or dates

Strategy 8 — Dark / Low Contrast Images:
  • Increase mental contrast: look for the number that stands out from the background
  • Thermal print fading: the amount is usually printed larger than other text
  • If image is rotated: read it sideways — the amount still exists somewhere

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLASSIFICATION RULES:

  site_expenses : hotel bills, guest house, accommodation, lodge, room rent, paying guest (PG),
                  dharamshala, inn, stay receipt, room charges,
                  hardware / material purchase bills, site supply invoices,
                  courier / parcel / dispatch bills for goods,
                  porter charges, labour charges for site work,
                  UPI payments whose description mentions hotel, lodge, stay, rent, material, hardware, site

  upi_payment   : PhonePe, GPay, Paytm, BHIM — payment to an individual or unnamed business
                  where the purpose is unclear (no mention of hotel/accommodation/material)

  fuel_bill     : petrol pump receipt, diesel station receipt (HPCL, BPCL, IOCL, Shell, HP)

  fasttag       : FASTag / NHAI toll deduction screenshot or SMS notification

  bus_ticket    : bus ticket, train ticket, auto-rickshaw, cab (Ola, Uber, Rapido), local taxi

  food_bill     : restaurant bill (even if named "Hotel XYZ Restaurant"), dhaba bill,
                  cafe receipt, food delivery bill (Swiggy, Zomato), daily allowance (DA) voucher
                  NOTE: "Hotel XYZ" that shows food items (Thali, Veg, Roti, etc.) → food_bill
                        "Hotel XYZ" that shows room/night charges → site_expenses

  other         : does not clearly fit any of the above

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONFIDENCE SCORING FOR RETRY:

  0.85–1.00 : Amount clearly visible after careful reading; high certainty
  0.65–0.84 : Amount found but image has blur/shadow/partial fold; reasonable certainty
  0.45–0.64 : Handwritten or faded; amount readable but could be misread
  0.25–0.44 : Very dark or rotated image; amount is a best guess from partial text
  0.10–0.24 : Amount barely visible; might be wrong
  0.00       : Amount truly not visible after exhaustive search — set amount = 0

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATE NORMALISATION:

  Input formats accepted: DD/MM/YYYY, DD-MM-YYYY, DD MMM YYYY, YYYY-MM-DD, DD-MM-YY, D/M/YY
  Output format required: YYYY-MM-DD always
  Examples: "05/01/2025" → "2025-01-05" | "5 Jan 25" → "2025-01-05" | "22-Feb-26" → "2026-02-22"
  If only month+year: use first of month → "Jan 2025" → "2025-01-01"
  If no date visible: output "N/A"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RETRY-SPECIFIC EXAMPLES (common failure cases):

CASE A — PhonePe with large balance shown:
  Image shows: "PhonePe • Sent ₹450 • to Ramesh Dhaba • Balance: ₹3,240 remaining"
  WRONG extraction: amount = 3240 (that is the wallet balance, not the payment)
  CORRECT extraction: amount = 450 (the "Sent" amount is the actual payment)

CASE B — Fuel receipt with faded thermal print:
  Image shows faded text: "Qty 8.5L Diesel Rate 93.20 ... [faded] ... 792.20"
  Look for the multiplication result at the bottom — 8.5 × 93.20 = 792.20 → amount = 792.20

CASE C — Handwritten cash voucher with no "Total" label:
  Image shows column of numbers: "250, 180, 320, 90" with a horizontal line and "840" below
  The number below the horizontal line IS the total → amount = 840

CASE D — Screenshot showing GST breakdown:
  Image shows: "Subtotal ₹1,200, CGST 9% ₹108, SGST 9% ₹108, Grand Total ₹1,416"
  CORRECT extraction: amount = 1416 (Grand Total includes all taxes — use it)

CASE E — Multi-day hotel bill:
  Image shows: "Room Charges: ₹800 × 3 nights = ₹2,400, Laundry ₹150, Total ₹2,550"
  CORRECT extraction: amount = 2550 (the final Total includes all charges)

CASE F — DTDC/Delhivery courier receipt with multiple charge types:
  Image shows: "Freight ₹250, Fuel Surcharge ₹40, GST ₹26, Total ₹316"
  CORRECT extraction: amount = 316 (full total including surcharges and GST)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VENDOR NAME EXTRACTION:

  For UPI screenshots: vendor = the payee name (recipient), not the sender
  For printed bills: vendor = the business name printed at the top of the bill
  For SMS notifications: vendor = the merchant or toll plaza name mentioned
  If no clear vendor name is visible: vendor = "Unknown"
  Keep vendor names concise — max 50 characters, remove address details

Return ONLY the JSON object — no markdown fences, no explanation, no extra text outside the JSON."""


# ── Public API ────────────────────────────────────────────────────────────────

def _is_odometer_image(path: str) -> bool:
    """Return True if the filename strongly suggests an odometer/trip-reading screenshot."""
    stem = Path(path).stem.lower().replace("-", "_").replace(" ", "_")
    return any(kw in stem for kw in _ODOMETER_FILENAME_KEYWORDS)


def _is_gps_app_screenshot(path: str) -> bool:
    """
    Detect SpineHR-attached Unolo/GPS app screenshots by filename pattern.
    SpineHR names expense attachments: ExpVouch_{emp_code}_{datetime}_Screenshot_{date}.jpg
    These are almost never receipts — they are GPS tracking screenshots.
    """
    name = Path(path).name.lower()
    return (
        name.startswith("expvouch_")
        and "screenshot" in name
    )


def _looks_like_odometer(raw_text: str) -> bool:
    """
    Heuristic: raw_text looks like a vehicle odometer or GPS tracking app screenshot.
    Covers both physical odometer photos and Unolo/field-force app screenshots.
    """
    text = raw_text.lower()
    # Vehicle odometer / speedometer context
    has_odo_context = any(kw in text for kw in (
        "km/h", "kmh", " km", "gear", "rpm", "odo", "trip meter",
        # Unolo / GPS app context
        "unolo", "tracking", "total distance", "total km", "travelled",
        "distance covered", "in reading", "out reading", "start km", "end km",
        "check in", "check out", "check-in", "check-out",
    ))
    has_large_number  = bool(re.search(r"\b\d{3,6}\b", text))
    has_receipt_terms = any(kw in text for kw in (
        "rs.", "₹", "paid", "receipt", "invoice", "gst", "upi", "debit",
    ))
    return has_large_number and has_odo_context and not has_receipt_terms


def _scan_single_odometer(path: str, llm) -> dict:
    """
    Extract distance from one odometer or GPS app screenshot.
    Uses _UNOLO_PROMPT for SpineHR GPS app screenshots, _ODOMETER_PROMPT for physical odometers.
    """
    is_gps = _is_gps_app_screenshot(path)
    prompt_text = (
        "Extract the daily travel distance (km) from this GPS tracking app screenshot."
        if is_gps else
        "Extract the in and out odometer readings from this screenshot."
    )
    system_prompt = _UNOLO_PROMPT if is_gps else _ODOMETER_PROMPT

    try:
        raw = llm.invoke_with_images(
            prompt=prompt_text,
            images=[path],
            system_prompt=system_prompt,
            max_tokens=300,
        )
        cleaned = re.sub(r"```[a-z]*\n?", "", raw).strip()
        result  = json.loads(cleaned)
        result["file"] = Path(path).name

        # For physical odometers: calculate distance from in/out if not already set
        in_r  = result.get("in_reading")
        out_r = result.get("out_reading")
        if in_r is not None and out_r is not None and result.get("distance_km") is None:
            calc = out_r - in_r
            result["distance_km"] = calc if 0 < calc <= 500 else None

        return result
    except Exception as exc:
        return {
            "file":           Path(path).name,
            "in_reading":     None,
            "out_reading":    None,
            "distance_km":    None,
            "in_confidence":  0.0,
            "out_confidence": 0.0,
            "notes":          f"Scan failed: {exc}",
        }


def _calculate_odometer_total(readings: list[dict]) -> float | None:
    """
    Sum all readable trip distances.
    Returns None when no reading was successful at all.
    """
    total    = 0.0
    has_data = False
    for r in readings:
        km = r.get("distance_km")
        if km is not None and km > 0:
            total   += km
            has_data = True
    return round(total, 1) if has_data else None


def scan_receipts(image_paths: list[str], on_progress=None) -> dict:
    """
    Scan uploaded files.
    - Summary PDF → extracted separately, stored in result["employee_summary"]
    - Individual receipts/screenshots → Claude Vision extracted, summed as total_extracted

    total_extracted = sum of individual receipt amounts (feeds calculator)
    employee_summary = parsed voucher data (feeds critic2 for validation)

    on_progress(done, total, label) — optional callback called from the main thread
    after each batch/PDF completes. Safe to call Streamlit UI methods inside it.
    """
    if not image_paths:
        return _empty_result()

    from utils.llm import get_vision_llm, get_voucher_llm
    vision_llm  = get_vision_llm()   # Haiku  — receipt image batches + retry
    voucher_llm = get_vision_llm()   # Haiku — fixed-template voucher PDF (Sonnet not needed)

    receipts         = []
    errors           = []
    all_text         = []
    employee_summary = None

    # ── Separate by file type ─────────────────────────────────────────────────
    all_pdf_paths = [p for p in image_paths if Path(p).suffix.lower() == ".pdf"]
    all_img_paths = [p for p in image_paths if Path(p).suffix.lower() in SUPPORTED_IMAGE_EXTS]
    other_paths   = [p for p in image_paths
                     if Path(p).suffix.lower() not in SUPPORTED_SCAN_EXTS]

    # Filename-detected odometer/GPS screenshots — scanned for distance, not as receipts
    odometer_by_name = [
        p for p in all_img_paths
        if _is_odometer_image(p) or _is_gps_app_screenshot(p)
    ]
    img_paths = [p for p in all_img_paths if p not in odometer_by_name]

    for path in other_paths:
        errors.append(f"{Path(path).name}: unsupported file type")

    # ── Classify PDFs synchronously (pypdf text only — no API call) ───────────
    # Voucher PDFs → structured extraction via Claude Vision (_process_pdf)
    # Non-voucher PDFs (individual bills, tickets) → receipt OCR via _scan_batch_claude
    voucher_pdf_paths: list[str] = []
    receipt_pdf_paths: list[str] = []
    for p in all_pdf_paths:
        if _is_voucher_pdf(p):
            voucher_pdf_paths.append(p)
        else:
            receipt_pdf_paths.append(p)

    # ── Build batches ─────────────────────────────────────────────────────────
    # Images batched at 4; PDF receipts batched at 2 (multi-page = more tokens)
    img_batches = [img_paths[i : i + _BATCH_SIZE]
                   for i in range(0, len(img_paths), _BATCH_SIZE)]
    pdf_rcpt_batches = [receipt_pdf_paths[i : i + _PDF_BATCH_SIZE]
                        for i in range(0, len(receipt_pdf_paths), _PDF_BATCH_SIZE)]
    all_batches = img_batches + pdf_rcpt_batches

    # Track files, not batches — so progress shows "5 / 13 files scanned"
    total_files   = len(image_paths)
    files_scanned = 0

    # ── Run all jobs concurrently ─────────────────────────────────────────────
    # as_completed iterates on the CALLING (main Streamlit) thread — safe for UI updates.
    max_workers = min(
        _MAX_WORKERS + len(voucher_pdf_paths),
        len(all_batches) + len(voucher_pdf_paths) + 1,
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:

        # Voucher PDFs → structured extraction (Sonnet)
        voucher_futures = {pool.submit(_process_pdf, p, voucher_llm): p for p in voucher_pdf_paths}

        # Image + PDF-receipt batches → OCR (Haiku)
        batch_future_map: dict = {}
        for i, batch in enumerate(all_batches):
            fut = pool.submit(_scan_batch_claude, batch, vision_llm)
            batch_future_map[fut] = (i, batch)

        ordered_batch_results: list = [None] * len(all_batches)

        all_futures = list(voucher_futures) + list(batch_future_map)
        for fut in concurrent.futures.as_completed(all_futures):

            if fut in voucher_futures:
                path  = voucher_futures[fut]
                label = Path(path).name
                files_scanned += 1
                try:
                    pdf_result = fut.result()
                    if pdf_result.get("is_summary"):
                        employee_summary = pdf_result
                    else:
                        reason = pdf_result.get("error") or "summary fields not detected"
                        errors.append(f"{Path(path).name}: voucher extraction failed ({reason})")
                except Exception as e:
                    errors.append(f"{Path(path).name}: PDF error: {e}")
            else:
                batch_idx, batch = batch_future_map[fut]
                label = Path(batch[0]).name + (f" +{len(batch)-1}" if len(batch) > 1 else "")
                files_scanned += len(batch)
                try:
                    ordered_batch_results[batch_idx] = fut.result()
                except Exception as e:
                    ordered_batch_results[batch_idx] = [{"error": str(e)}] * len(batch)

            if on_progress:
                on_progress(min(files_scanned, total_files), total_files, label)

        # ── Process batch results in original order ───────────────────────────
        # Collect items that need a retry (amount=0 or low confidence)
        needs_retry: list[tuple[str, int]] = []  # (path, receipts index)

        for batch, batch_results in zip(all_batches, ordered_batch_results):
            if not batch_results:
                continue
            for path, scan_result in zip(batch, batch_results):
                if scan_result.get("error"):
                    errors.append(f"{Path(path).name}: {scan_result['error']}")
                    continue
                raw_text   = scan_result.get("raw_text", "")
                amount     = float(scan_result.get("amount") or 0)
                confidence = float(scan_result.get("confidence") or 0.0)
                all_text.append(raw_text)
                receipt_idx = len(receipts)
                receipts.append({
                    "receipt_type": scan_result.get("receipt_type", "other"),
                    "vendor":       scan_result.get("vendor", "Unknown"),
                    "date":         scan_result.get("date", "N/A"),
                    "amount":       amount,
                    "confidence":   confidence,
                    "notes":        "" if amount > 0 else "Amount not detected",
                    "file":         Path(path).name,
                    "raw_ocr":      raw_text,
                })
                # Flag for retry if amount missing or confidence too low
                if amount == 0 or confidence < _RETRY_CONFIDENCE_THRESHOLD:
                    needs_retry.append((path, receipt_idx))

        # ── Retry failed / low-confidence receipts — run in parallel ─────────
        # Uses a focused single-image prompt with explicit search strategies.
        if needs_retry:
            retry_total = len(needs_retry)

            def _do_retry(args):
                path, idx = args
                try:
                    response = vision_llm.invoke_with_images(
                        prompt="Extract receipt data carefully:",
                        images=[path],
                        system_prompt=_RETRY_OCR_PROMPT,
                        max_tokens=600,
                    )
                    text = response.strip()
                    if "```json" in text:
                        text = text.split("```json")[1].split("```")[0]
                    elif "```" in text:
                        text = text.split("```")[1].split("```")[0]
                    return idx, json.loads(text.strip()), None
                except Exception as e:
                    return idx, None, str(e)

            retry_files_done = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS) as retry_pool:
                retry_futures = {retry_pool.submit(_do_retry, item): item for item in needs_retry}
                for fut in concurrent.futures.as_completed(retry_futures):
                    retry_files_done += 1
                    path, _ = retry_futures[fut]
                    idx, retry_result, err = fut.result()
                    if err:
                        errors.append(f"{Path(path).name}: retry failed — {err}")
                    elif retry_result:
                        retry_amount     = float(retry_result.get("amount") or 0)
                        retry_confidence = float(retry_result.get("confidence") or 0.0)
                        retry_raw        = retry_result.get("raw_text", "")
                        if retry_amount > 0 or retry_confidence > receipts[idx]["confidence"]:
                            receipts[idx].update({
                                "receipt_type": retry_result.get("receipt_type", receipts[idx]["receipt_type"]),
                                "vendor":       retry_result.get("vendor") or receipts[idx]["vendor"],
                                "date":         retry_result.get("date") or receipts[idx]["date"],
                                "amount":       retry_amount,
                                "confidence":   retry_confidence,
                                "notes":        "" if retry_amount > 0 else "Amount not detected after retry",
                                "raw_ocr":      retry_raw or receipts[idx]["raw_ocr"],
                            })
                            if retry_raw:
                                all_text.append(retry_raw)
                    if on_progress:
                        # Show total_files as ceiling — retries re-scan already-counted files
                        on_progress(
                            total_files,
                            total_files,
                            f"Re-scanning: {Path(path).name}",
                        )

    combined_text   = " ".join(all_text).lower()
    needs_unolo     = _requires_unolo(combined_text)
    total_extracted = sum(r.get("amount", 0) for r in receipts)

    by_category: dict[str, list] = {}
    for r in receipts:
        cat = r.get("receipt_type", "other")
        by_category.setdefault(cat, []).append(r)

    # ── Odometer scanning ─────────────────────────────────────────────────────
    # 1. Content-detected: "other" receipts with amount=0 that look like odometers
    content_odo_paths: list[str] = []
    for r in list(receipts):
        if (r.get("receipt_type") == "other"
                and float(r.get("amount") or 0) == 0
                and _looks_like_odometer(r.get("raw_ocr", ""))):
            fname = r.get("file", "")
            match = next((p for p in img_paths if Path(p).name == fname), None)
            if match:
                content_odo_paths.append(match)
                receipts.remove(r)

    all_odo_paths = odometer_by_name + content_odo_paths
    odometer_readings: list[dict] = []
    if all_odo_paths:
        for odo_path in all_odo_paths:
            reading = _scan_single_odometer(odo_path, vision_llm)
            odometer_readings.append(reading)
            if on_progress:
                on_progress(total_files, total_files, f"Odometer: {Path(odo_path).name}")

    odometer_distance_km = _calculate_odometer_total(odometer_readings)
    # Always fetch Unolo when we have odometer readings for cross-check
    if odometer_readings:
        needs_unolo = True

    return {
        "receipts":              receipts,
        "total_extracted":       total_extracted,
        "by_category":           by_category,
        "source":                "claude_vision",
        "errors":                errors,
        "needs_unolo":           needs_unolo,
        "has_summary":           employee_summary is not None,
        "employee_summary":      employee_summary,
        "odometer_readings":     odometer_readings,
        "odometer_distance_km":  odometer_distance_km,
    }


# ── Claude Vision OCR (batched) ───────────────────────────────────────────────

def _scan_batch_claude(image_paths: list[str], llm, max_retries: int = 2) -> list[dict]:
    """
    Send up to _BATCH_SIZE images in a single Claude Vision call.
    Returns a list of result dicts (one per image, in order).
    Retries with exponential backoff on rate-limit (429) errors.
    """
    # Filter out missing / unsupported files upfront (images + PDFs both accepted)
    valid   = []
    results = []
    for p in image_paths:
        path = Path(p)
        if not path.exists():
            results.append({"error": "File not found", "_path": p})
        elif path.suffix.lower() not in SUPPORTED_SCAN_EXTS:
            results.append({"error": f"Unsupported file type {path.suffix}", "_path": p})
        else:
            valid.append(p)
            results.append(None)   # placeholder

    if not valid:
        return results

    n = len(valid)
    prompt = (
        f"There are {n} image(s) attached. "
        f"Return a JSON array with exactly {n} objects, one per image in order."
    )

    # 4 images × ~600 tokens each = ~2400 tokens; 3000 gives headroom
    _batch_max_tokens = max(1500, n * 700)

    for attempt in range(max_retries):
        try:
            response = llm.invoke_with_images(
                prompt=prompt,
                images=valid,
                system_prompt=_BATCH_OCR_PROMPT,
                max_tokens=_batch_max_tokens,
            )
            parsed = _parse_batch_response(response, n)
            # Fill placeholders back into the full results list
            valid_iter = iter(parsed)
            for i, r in enumerate(results):
                if r is None:
                    results[i] = next(valid_iter)
            return results

        except Exception as e:
            err = str(e)
            is_rate_limit = (
                "429" in err or "529" in err
                or "rate_limit" in err.lower()
                or "overloaded" in err.lower()
                or "connection" in err.lower()
                or "timeout" in err.lower()
            )
            is_image_too_large = "image exceeds" in err.lower() or "5 mb" in err.lower()

            if is_rate_limit and attempt < max_retries - 1:
                # 8 s base + jitter so parallel workers don't all wake at once → 8–15 s wait
                import random
                wait = 8 * (2 ** attempt) + random.uniform(0, 5)
                time.sleep(wait)

            elif is_image_too_large and len(valid) > 1:
                # One oversized image is poisoning the whole batch.
                # Fall back to one-at-a-time so only the bad image fails.
                individual_results = []
                for single_path in valid:
                    single_results = _scan_batch_claude([single_path], llm, max_retries)
                    individual_results.extend(single_results)
                valid_iter = iter(individual_results)
                for i, r in enumerate(results):
                    if r is None:
                        results[i] = next(valid_iter)
                return results

            else:
                fallback = {"error": err}
                for i, r in enumerate(results):
                    if r is None:
                        results[i] = fallback
                return results

    return results


def _parse_batch_response(response: str, expected: int) -> list[dict]:
    """
    Extract a JSON array from the model response using four strategies in order:
    1. Direct json.loads
    2. Strip control characters, then json.loads
    3. json_repair library (if installed: pip install json-repair)
    4. Object-by-object bracket-depth scanner (handles truncated responses)
    """
    # Strip markdown fences
    text = response
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    text = text.strip()

    def _normalize(parsed):
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list):
            return None
        while len(parsed) < expected:
            parsed.append({"error": "No result returned for this image"})
        return parsed[:expected]

    # Strategy 1: direct parse
    try:
        return _normalize(json.loads(text))
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip control characters (tabs, carriage returns, null bytes, etc.)
    try:
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        return _normalize(json.loads(cleaned))
    except json.JSONDecodeError:
        pass

    # Strategy 3: json_repair library
    try:
        import importlib
        jr = importlib.import_module("json_repair")
        return _normalize(json.loads(jr.repair_json(text)))
    except Exception:
        pass

    # Strategy 4: object-by-object bracket scanner — handles truncated responses
    objects = _extract_json_objects(text)
    if objects:
        while len(objects) < expected:
            objects.append({"error": "Could not parse result for this image"})
        return objects[:expected]

    return [{"error": "JSON parse failed after all strategies"}] * expected


def _extract_json_objects(text: str) -> list[dict]:
    """
    Scan `text` character-by-character and extract every complete top-level JSON
    object `{...}`. Correctly tracks string boundaries (including escaped quotes)
    so nested braces inside string values don't confuse the depth counter.
    """
    objects = []
    depth = 0
    start = -1
    in_str = False
    escape_next = False

    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_str:
            escape_next = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    objects.append(json.loads(text[start:i + 1]))
                except json.JSONDecodeError:
                    pass
                start = -1

    return objects


# ── PDF Processing ────────────────────────────────────────────────────────────

_VOUCHER_EXTRACT_PROMPT = """You are an expert at reading Indian company expense vouchers.
This is an official multi-page Expense Voucher PDF. Extract data and return ONLY a valid JSON object.

{
  "employee_name": "full name or empty string",
  "employee_code": "code or empty string",
  "period": "e.g. 2-Nov-25 to 15-Nov-25 or empty string",
  "voucher_no": "voucher number or empty string",
  "summary_total": <total Claimed Amount from Gross Payable row, numeric>,
  "categories": {
    "<category_key>": {
      "claimed": <sum of ALL Claimed Amounts for this category across all pages, numeric>,
      "items": [
        {
          "expense_head": "<Expense Head name, max 40 chars>",
          "date": "<Expense Date as written, e.g. 21-Feb-26>",
          "remarks": "<Remarks column text, max 60 chars, empty string if blank>",
          "amount": <Claimed Amount column value for this exact line, numeric>
        }
      ]
    }
  }
}

Category keys — assign EVERY line item to exactly one:
- "site_expenses"  → Site Expenses (materials, dispatch, labour, parcel, porter, tools, boards,
                     fasteners, pipes, wire, sadal, bend, anchor, lug, elbow) AND
                     Hotel / Accommodation / Lodging / Guest House / Paying Guest / Room Rent /
                     Dharamshala / Inn / Stay charges
- "food"           → Food Allowance / DA / Daily Allowance / Meals / Dinner / Lunch
- "bus_travel"     → Bus / Train / Auto / Cab / Taxi / Rapido / Local transport (personal travel)
- "two_wheeler"    → Two Wheeler / Fuel / Petrol / Bike
- "fasttag"        → FASTag / Toll / NHAI
- "other"          → anything else not covered above (cruise, event bookings, misc)

CRITICAL RULES — READ CAREFULLY:
1. summary_total = the number in the CLAIMED AMOUNT column on the "Gross Payable" row
2. For EVERY line item: item "amount" = the value in the CLAIMED AMOUNT column for that row
3. Include EVERY line item from ALL pages — never skip a row
4. The table columns are: Expense Head | Expense Date | Remarks | INR | Claimed Amount | Approved Amount | Rejected Amount
   Extract ONLY from the Claimed Amount column — ignore Approved Amount and Rejected Amount entirely
5. Return ONLY the JSON object — no markdown fences, no extra text"""


# ── Odometer / GPS prompt ─────────────────────────────────────────────────────

_ODOMETER_PROMPT = """You are reading a vehicle odometer/speedometer screenshot submitted by a field employee.

This image may be one of TWO types — identify which type it is first:

TYPE A — VEHICLE ODOMETER PHOTO (two physical displays side-by-side):
  Left display = reading BEFORE the trip (In / Start)
  Right display = reading AFTER the trip (Out / End)
  Extract the TOTAL ODOMETER km (large 5-digit cumulative counter, NOT the short trip meter).

TYPE B — GPS / UNOLO APP SCREENSHOT (mobile app interface):
  The app shows check-in time, check-out time, and total distance for the day.
  Extract the total km distance shown (e.g. "Total Distance: 124 km" or "Travelled: 87.3 km").
  Set in_reading = null, out_reading = null, distance_km = the total distance shown.

Return ONLY a valid JSON object — no markdown fences, no extra text:
{
  "screenshot_type": "odometer" | "gps_app",
  "in_reading":      <integer km for TYPE A, or null for TYPE B>,
  "out_reading":     <integer km for TYPE A, or null for TYPE B>,
  "distance_km":     <integer or float — trip distance. For TYPE A: out minus in. For TYPE B: total shown>,
  "in_confidence":   <float 0.0–1.0>,
  "out_confidence":  <float 0.0–1.0>,
  "notes":           "<any issues or empty string>"
}

RULES:
1. For TYPE A: distance_km = out_reading − in_reading. Must be positive and ≤ 500.
2. For TYPE B: look for labels like "Total Distance", "Travelled", "KM", "Distance Covered".
   Accept decimal values (e.g. 87.3 km → distance_km = 87.3).
3. If the image is unreadable (blank, completely blurry), set all numeric fields to null and confidence = 0.0.
4. If out_reading < in_reading (TYPE A), set distance_km = null."""


_UNOLO_PROMPT = """You are reading a Unolo GPS field-force tracking app screenshot submitted as proof of travel.

The screenshot shows an employee's daily trip record from the Unolo app. Extract the total distance for this day.

Look for any of these labels (exact label varies by app version):
  "Total Distance", "Total KM", "Travelled", "Distance Covered", "KM Travelled",
  "Distance", "Trip Distance", "Today's Distance"

Also look for:
  - A number followed by "km" or "KM" that represents the day's total travel
  - In/Out odometer readings if shown (In Reading / Out Reading in km)

Return ONLY a valid JSON object:
{
  "screenshot_type": "gps_app",
  "in_reading":      <integer if in/start odometer visible, else null>,
  "out_reading":     <integer if out/end odometer visible, else null>,
  "distance_km":     <float — total km for this day, or null if not readable>,
  "in_confidence":   <float 0.0–1.0>,
  "out_confidence":  <float 0.0–1.0>,
  "notes":           "<employee name or date if visible, plus any issues>"
}

If neither odometer readings nor total distance is visible, set distance_km = null and confidence = 0.0."""


def _is_voucher_pdf(pdf_path: str) -> bool:
    """
    Decide if a PDF is an official company expense voucher.
    Checks filename first (fast, no pypdf), then PDF text content.
    Returns True when combined signals reach threshold of 2.
    """
    filename_lower = Path(pdf_path).stem.lower()
    # "voucher" or "summary" in filename = 1 strong signal each
    # Deliberately narrow: "vouch" alone (e.g. ExpVouch_ receipt files) is NOT a match
    filename_score = sum(1 for kw in ("voucher", "summary") if kw in filename_lower)

    if not PYPDF_AVAILABLE:
        return filename_score >= 1

    try:
        reader = PdfReader(pdf_path)
        text   = "\n".join(page.extract_text() or "" for page in reader.pages[:3]).lower()
    except Exception:
        return filename_score >= 1

    content_signals = [
        "gross payable", "net payable", "expense voucher",
        "expense head", "claimed amount", "approved amount",
    ]
    content_score = sum(1 for s in content_signals if s in text)
    return (filename_score + content_score) >= 2


def _process_pdf(pdf_path: str, llm=None) -> dict:
    """
    Extract structured data from a confirmed expense voucher PDF.
    Only called after _is_voucher_pdf() returned True.

    Uses Claude Vision (native PDF document block) for structured table extraction.
    Falls back to regex parsing if Claude is unavailable.
    """
    if not PYPDF_AVAILABLE:
        return {"is_summary": False, "error": "pypdf not installed — run: pip install pypdf"}

    try:
        reader = PdfReader(pdf_path)
        text   = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        return {"is_summary": False, "error": str(e)}

    # ── Claude Vision extracts the structured table data ─────────────────────
    # pypdf is unreliable for multi-column tables (numbers land on wrong lines).
    # Claude reads the PDF natively and always returns correct column values.
    if llm is not None:
        try:
            response = llm.invoke_with_images(
                prompt="Extract expense voucher data as instructed:",
                images=[pdf_path],
                system_prompt=_VOUCHER_EXTRACT_PROMPT,
                max_tokens=3000,
            )
            parsed = json.loads(
                response.split("```json")[1].split("```")[0] if "```json" in response
                else response.split("```")[1].split("```")[0] if "```" in response
                else response
            )
            parsed["is_summary"] = True
            parsed["path"]       = pdf_path
            parsed["raw_text"]   = text
            # Ensure numeric fields are floats
            parsed["summary_total"]    = float(parsed.get("summary_total") or 0)
            parsed["summary_approved"] = float(parsed.get("summary_approved") or 0)
            return parsed
        except Exception:
            pass  # fall through to regex backup

    # ── Regex fallback (single-column PDFs or if Claude unavailable) ─────────
    total_claimed  = 0.0
    total_approved = 0.0
    text_lower = text.lower()
    gp_match = re.search(r"(?:gross payable|net payable)(.+?)(?:\n|$)", text_lower)
    if gp_match:
        gp_floats = []
        for n in re.findall(r"[\d,]+\.?\d*", gp_match.group(1)):
            try:
                gp_floats.append(float(n.replace(",", "")))
            except ValueError:
                pass
        if gp_floats:
            total_claimed  = gp_floats[0]
            total_approved = gp_floats[1] if len(gp_floats) >= 2 else total_claimed

    categories = {}
    for line in text.splitlines():
        line_lower = line.lower().strip()
        if not line_lower:
            continue
        if any(skip in line_lower for skip in [
            "expense head", "claimed amount", "approved amount",
            "gross payable", "net payable", "rejected amount"
        ]):
            continue
        inr_match = re.search(r"(?:inr|rs\.?|₹)\s*([\d,]+\.?\d*)", line, re.IGNORECASE)
        if not inr_match:
            if _map_expense_head(line_lower) != "other":
                inr_match = re.search(r"\b([\d,]+\.\d{2})\b", line)
        if not inr_match:
            continue
        try:
            claimed_amt = float(inr_match.group(1).replace(",", ""))
        except ValueError:
            continue
        if claimed_amt <= 0:
            continue
        rest = line[inr_match.end():]
        next_nums = re.findall(r"\b([\d,]+\.\d{2})\b", rest)
        try:
            approved_amt = float(next_nums[0].replace(",", "")) if next_nums else claimed_amt
        except ValueError:
            approved_amt = claimed_amt
        cat = _map_expense_head(line_lower)
        if cat not in categories:
            categories[cat] = {"claimed": 0.0, "approved": 0.0, "items": []}
        categories[cat]["claimed"]  += claimed_amt
        categories[cat]["approved"] += approved_amt
        if approved_amt > 0:
            categories[cat]["items"].append({
                "expense_head":   line.strip()[:80],
                "amount":         approved_amt,
                "claimed_amount": claimed_amt,
            })

    return {
        "is_summary":       True,
        "path":             pdf_path,
        "summary_total":    total_claimed,
        "summary_approved": total_approved,
        "categories":       categories,
        "employee_name": _extract_field(text, r"employee name\s*[:\-]?\s*([\w\s]+?)(?:employee code|\n)"),
        "employee_code": _extract_field(text, r"employee code\s*[:\-]?\s*(\S+)"),
        "period":        _extract_field(text, r"for the period\s+([\d\w\-\s]+to[\d\w\-\s]+?)(?:\n|cost center)").strip(),
        "voucher_no":    _extract_field(text, r"voucher no\.?\s*[:\-]?\s*(\S+)"),
        "raw_text":      text,
    }


def _map_expense_head(text: str) -> str:
    for keyword, cat in EXPENSE_HEAD_MAP.items():
        if keyword in text:
            return cat
    return "other"


def _extract_field(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _requires_unolo(text_lower: str) -> bool:
    return any(keyword in text_lower for keyword in TRAVEL_KEYWORDS)


def _empty_result() -> dict:
    return {
        "receipts":             [],
        "total_extracted":      0,
        "by_category":          {},
        "source":               "claude_vision",
        "errors":               [],
        "needs_unolo":          False,
        "has_summary":          False,
        "employee_summary":     None,
        "odometer_readings":    [],
        "odometer_distance_km": None,
    }
