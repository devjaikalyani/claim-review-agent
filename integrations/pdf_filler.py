"""
PDF Filler

Fills the Approved Amount and Rejected Amount columns in a SpineHR expense
voucher PDF with AI-decided values, and returns the modified PDF as bytes.

Strategy:
  1. pdfplumber.find_tables() locates every table cell with its bounding box.
  2. We identify the header row to find which column index is Approved / Rejected.
  3. For each data row we white-out the existing cell contents and write the
     new amounts using PyMuPDF (fitz).

Coordinate systems:
  pdfplumber cell tuples: (x0, top, x1, bottom) — origin top-left, y downward.
  PyMuPDF fitz.Rect:      (x0, y0, x1, y1)      — origin top-left, y downward.
  They are directly compatible for single-page PDFs.
"""

from typing import Any, Dict, List, Optional, Tuple

try:
    import fitz          # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False


_FOOTER_KEYWORDS = ("gross payable", "net payable")
_FONT            = "helv"   # Helvetica — always available in PyMuPDF
_FONT_SIZE       = 8.0
_TEXT_COLOUR     = (0.0, 0.0, 0.0)   # black
_WHITE           = (1.0, 1.0, 1.0)


# ── Public API ────────────────────────────────────────────────────────────────

def fill_voucher_pdf(
    pdf_path: str,
    line_decisions: List[Dict[str, Any]],
) -> bytes:
    """
    Fill Approved Amount and Rejected Amount columns in a SpineHR voucher PDF.

    Args:
        pdf_path:       Path to the original PDF.
        line_decisions: One dict per data row (same order as the table), each with:
                          approved_amount: float
                          rejected_amount: float

    Returns:
        Modified PDF as bytes.
    """
    if not PYMUPDF_AVAILABLE:
        raise ImportError("PyMuPDF is required: pip install PyMuPDF")
    if not PDFPLUMBER_AVAILABLE:
        raise ImportError("pdfplumber is required: pip install pdfplumber")

    cell_map = _locate_cells(pdf_path)

    doc  = fitz.open(pdf_path)
    page = doc[0]

    # ── Fill data rows ────────────────────────────────────────────────────────
    for i, decision in enumerate(line_decisions):
        if i >= len(cell_map["data"]):
            break
        app_rect, rej_rect = cell_map["data"][i]
        _fill_cell(page, app_rect, f"{decision.get('approved_amount', 0.0):.2f}")
        _fill_cell(page, rej_rect, f"{decision.get('rejected_amount', 0.0):.2f}")

    # ── Fill Gross Payable and Net Payable totals ─────────────────────────────
    total_approved = sum(d.get("approved_amount", 0.0) for d in line_decisions)
    total_rejected = sum(d.get("rejected_amount", 0.0) for d in line_decisions)

    for app_rect, rej_rect in cell_map["footer"]:
        _fill_cell(page, app_rect, f"{total_approved:.2f}")
        _fill_cell(page, rej_rect, f"{total_rejected:.2f}")

    return doc.tobytes()


# ── Private helpers ───────────────────────────────────────────────────────────

def _locate_cells(pdf_path: str) -> Dict[str, List]:
    """
    Use pdfplumber to find the bounding boxes of each Approved / Rejected cell.

    Returns:
        {
            "data":   [(app_rect, rej_rect), ...],  # one per data row
            "footer": [(app_rect, rej_rect), ...],  # Gross Payable + Net Payable
        }
    """
    result: Dict[str, List] = {"data": [], "footer": []}

    with pdfplumber.open(pdf_path) as pdf:
        page   = pdf.pages[0]
        tables = page.find_tables()
        if not tables:
            return result

        tbl       = tables[0]
        text_rows = tbl.extract()   # list[list[str|None]]
        cell_rows = tbl.rows        # list[TableRow] — each has .cells: list[(x0,top,x1,bot)]

    if not text_rows or not cell_rows:
        return result

    # ── Identify Approved / Rejected column indices from the header row ───────
    app_col_idx: Optional[int] = None
    rej_col_idx: Optional[int] = None

    for row_idx, text_row in enumerate(text_rows):
        row_text = " ".join(str(c or "") for c in text_row).lower()
        if "expense head" in row_text:
            for col_idx, cell_text in enumerate(text_row):
                ct = str(cell_text or "").lower()
                if "approved" in ct:
                    app_col_idx = col_idx
                elif "rejected" in ct:
                    rej_col_idx = col_idx
            break

    # Fallback: last two columns are Approved / Rejected
    if app_col_idx is None or rej_col_idx is None:
        n_cols      = len(cell_rows[0].cells) if cell_rows else 7
        app_col_idx = n_cols - 2
        rej_col_idx = n_cols - 1

    # ── Categorise each row as header / data / footer ─────────────────────────
    header_passed = False

    for text_row, cell_row in zip(text_rows, cell_rows):
        row_text  = " ".join(str(c or "") for c in text_row).lower()
        is_footer = any(kw in row_text for kw in _FOOTER_KEYWORDS)
        is_header = "expense head" in row_text

        if is_header:
            header_passed = True
            continue

        if not header_passed:
            continue

        cells = cell_row.cells
        if len(cells) <= rej_col_idx:
            continue

        app_cell = cells[app_col_idx]  # (x0, top, x1, bottom)
        rej_cell = cells[rej_col_idx]

        if None in app_cell or None in rej_cell:
            continue

        pair = (
            fitz.Rect(app_cell[0], app_cell[1], app_cell[2], app_cell[3]),
            fitz.Rect(rej_cell[0], rej_cell[1], rej_cell[2], rej_cell[3]),
        )

        # Skip rows that are entirely empty (no text at all in the row)
        row_has_content = any(c for c in text_row if c and str(c).strip())
        if not row_has_content:
            continue

        if is_footer:
            result["footer"].append(pair)
        else:
            result["data"].append(pair)

    return result


def _fill_cell(page: "fitz.Page", rect: "fitz.Rect", text: str) -> None:
    """White-out a cell then write right-aligned text inside it."""
    # Shrink rect slightly so we don't erase the border lines
    inner = rect + fitz.Rect(1, 1, -1, -1)

    # White rectangle to erase existing content
    page.draw_rect(inner, color=_WHITE, fill=_WHITE)

    # Right-align: measure text width then position from right edge
    text_width = fitz.get_text_length(text, fontname=_FONT, fontsize=_FONT_SIZE)
    text_x = rect.x1 - text_width - 3
    text_y = rect.y0 + (rect.height / 2) + (_FONT_SIZE * 0.35)

    page.insert_text(
        fitz.Point(text_x, text_y),
        text,
        fontname=_FONT,
        fontsize=_FONT_SIZE,
        color=_TEXT_COLOUR,
    )
