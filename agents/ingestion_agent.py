"""
Ingestion Agent
Processes images and documents to extract text using OCR and vision models.
Summary PDFs are detected and stored separately for Critic 2.
"""
from typing import Dict, Any
from agents.state import ClaimState
from integrations.vision_ai import scan_receipts


def ingestion_agent(state: ClaimState) -> ClaimState:
    state["current_agent"] = "ingestion"

    images = state.get("images", [])
    vision_data = state.get("vision_data")

    if vision_data:
        # Fast path: pre-scanned data passed from app.py — no extra API calls
        _populate_from_scan_result(state, vision_data)
        return state

    # Fallback path (direct pipeline call without pre-scan):
    # scan_receipts batches all images into 1-2 Vision API calls and returns
    # type + amount + vendor + raw_text for every file.
    # _populate_from_scan_result converts that into the shape data_agent needs.
    # No separate per-image LLM calls required.
    scan_result = scan_receipts(images)
    _populate_from_scan_result(state, scan_result)
    return state


def _populate_from_scan_result(state: ClaimState, scan_result: Dict[str, Any]) -> None:
    """Hydrate ingestion state from pre-scanned OCR/classification data."""
    if scan_result.get("has_summary") and scan_result.get("employee_summary"):
        state["employee_summary"] = scan_result["employee_summary"]

    receipts = scan_result.get("receipts", [])
    extracted_text = []
    total_confidence = 0.0

    for receipt in receipts:
        confidence = float(receipt.get("confidence", 0.0) or 0.0)
        total_confidence += confidence
        extracted_text.append({
            "source": receipt.get("file", "unknown"),
            "text": receipt.get("raw_ocr", ""),
            "type": receipt.get("receipt_type", "other"),
            "data": _normalize_scan_receipt(receipt),
            "confidence": confidence,
        })

    state["extracted_text"] = extracted_text
    if receipts:
        state["ocr_confidence"] = total_confidence / len(receipts)
    elif scan_result.get("has_summary"):
        # A verified expense voucher is authoritative — assign high confidence
        state["ocr_confidence"] = 0.85
    else:
        state["ocr_confidence"] = 0.0


def _normalize_scan_receipt(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Convert scan_receipts output into the shape expected by data_agent."""
    amount = float(receipt.get("amount", 0) or 0.0)
    vendor = receipt.get("vendor", "Unknown")
    date = receipt.get("date", "")
    confidence = float(receipt.get("confidence", 0.0) or 0.0)
    doc_type = receipt.get("receipt_type", "other")

    normalized = {
        "vendor_name": vendor,
        "date": date if date != "N/A" else "",
        "total_amount": amount,
        "confidence": confidence,
        "raw_text": receipt.get("raw_ocr", ""),
    }

    if doc_type == "fasttag":
        normalized["transactions"] = [{
            "amount": amount,
            "date": normalized["date"],
            "toll_plaza": vendor,
        }]
    elif doc_type == "food_bill":
        normalized["category"] = "food"
    elif doc_type == "fuel_bill":
        normalized["category"] = "fuel"
    elif doc_type == "bus_ticket":
        normalized["category"] = "transport"
    elif doc_type == "upi_payment":
        normalized["category"] = "other"

    return normalized


