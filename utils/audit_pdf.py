"""
Audit-style PDF report generator — detailed version.

Mirrors the Travel Expense Audit Report structure:
  Title block + metadata table
  1. Executive Summary
  2. Methodology
  3. Expense-by-Expense Analysis  (per category: details, every item, key findings)
  4. Pattern Analysis and Risk Assessment
  5. Recommendations
  6. Conclusion

Every data point the pipeline produces is surfaced in the relevant section.
"""
import io
from datetime import datetime
from fpdf import FPDF

# ── Label maps ─────────────────────────────────────────────────────────────────

_CAT_LABELS = {
    "two_wheeler":    "Two-Wheeler / Bike Travel",
    "car_conveyance": "Car Conveyance",
    "bus_travel":     "Bus / Train Travel",
    "fasttag":        "FASTag / Toll",
    "food":           "Food / Meals",
    "hotel":          "Hotel / Accommodation",
    "site_expenses":  "Site Expenses",
    "other":          "Other Expenses",
}

_DECISION_COLORS = {
    "full_approval":    (34,  197, 94),   # green
    "partial_approval": (234, 179, 8),    # amber
    "rejected":         (239, 68,  68),   # red
    "pending_review":   (148, 163, 184),  # slate
}

_UNICODE_MAP = {
    "’": "'",  "‘": "'",  "“": '"',  "”": '"',
    "–": "-",  "—": "--", "…": "...", "→": "->",
    "•": "*",  "·": ".",  "₹": "Rs.", "≤": "<=",
    "≥": ">=", "×": "x",  "÷": "/",  " ": " ",
    "°": " deg", "®": "(R)", "‐": "-", "‑": "-",
    "●": "*",  "▶": ">",  "✔": "[OK]", "✘": "[X]",
    "⚠": "[!]", "✅": "[OK]",
}

PAGE_W = 170   # usable text width mm (A4 210 - 20 left - 20 right)
PAGE_H = 297


# ── Text sanitiser ─────────────────────────────────────────────────────────────

def _s(v) -> str:
    """Sanitise any value to Latin-1 safe string."""
    text = str(v) if v is not None else ""
    for ch, rep in _UNICODE_MAP.items():
        text = text.replace(ch, rep)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _trunc(v, n: int) -> str:
    s = _s(v)
    return s[:n] + "..." if len(s) > n else s


# ── PDF class ──────────────────────────────────────────────────────────────────

class _PDF(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(20, 20, 20)

    # ── Decorators ─────────────────────────────────────────────────────────────

    def header(self):
        if self.page_no() == 1:
            return
        # Navy header bar
        self.set_fill_color(22, 45, 85)
        self.rect(0, 0, 210, 10, "F")
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(255, 255, 255)
        self.set_y(1.5)
        self.cell(0, 7,
                  "RITE AUDIT SYSTEM  |  Rite Water Solutions (India) Pvt. Ltd.",
                  align="C")
        # Gold underline
        self.set_fill_color(200, 160, 40)
        self.rect(0, 10, 210, 1.5, "F")
        self.set_y(16)
        self._rst()

    def footer(self):
        self.set_y(-14)
        # Thin gold bar before footer text
        self.set_fill_color(200, 160, 40)
        self.rect(0, self.get_y() - 1, 210, 1, "F")
        self.set_fill_color(22, 45, 85)
        self.rect(0, self.get_y(), 210, 10, "F")
        self.set_font("Helvetica", size=8)
        self.set_text_color(200, 210, 230)
        self.cell(0, 10, f"CONFIDENTIAL  |  Page {self.page_no()}  |  "
                         "Rite Audit System", align="C")
        self.set_text_color(0, 0, 0)

    def _rst(self):
        self.set_draw_color(0, 0, 0)
        self.set_line_width(0.2)
        self.set_text_color(0, 0, 0)
        self.set_fill_color(255, 255, 255)

    # ── Title block ────────────────────────────────────────────────────────────

    def title_block(self, company, title, subtitle, context):
        # Deep navy top bar
        self.set_fill_color(22, 45, 85)
        self.rect(0, 0, 210, 18, "F")
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(255, 255, 255)
        self.set_y(5)
        self.cell(0, 8, _s(company.upper()), align="C")
        self.ln(20)

        # Gold accent bar
        self.set_fill_color(200, 160, 40)
        self.rect(0, 18, 210, 2, "F")
        self.ln(4)

        # Main title
        self.set_font("Helvetica", "B", 22)
        self.set_text_color(22, 45, 85)
        self.cell(0, 14, _s(title.upper()), align="C", new_x="LMARGIN", new_y="NEXT")

        # Subtitle
        self.set_font("Helvetica", "I", 11)
        self.set_text_color(80, 80, 80)
        self.cell(0, 7, _s(subtitle), align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

        # Double rule
        self.set_draw_color(22, 45, 85)
        self.set_line_width(1.2)
        self.line(20, self.get_y(), 190, self.get_y())
        self.set_line_width(0.4)
        self.line(20, self.get_y() + 2, 190, self.get_y() + 2)
        self.ln(5)

        # Context line
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(60, 60, 60)
        self.cell(0, 7, _s(context), align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(10)
        self._rst()

    # ── Metadata table ─────────────────────────────────────────────────────────

    def meta_table(self, rows: list):
        # Table header bar
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(22, 45, 85)
        self.set_text_color(255, 255, 255)
        self.cell(170, 8, "  REPORT DETAILS", border=0, fill=True,
                  new_x="LMARGIN", new_y="NEXT")
        self._rst()
        for i, (label, value) in enumerate(rows):
            # Alternate row backgrounds
            bg = (240, 244, 250) if i % 2 == 0 else (252, 252, 255)
            self.set_fill_color(*bg)
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(22, 45, 85)
            self.cell(58, 8, f"  {_s(label)}", border=1, fill=True)
            self.set_font("Helvetica", size=9)
            self.set_text_color(30, 30, 30)
            # Highlight the Classification row
            if "confidential" in str(value).lower():
                self.set_text_color(180, 30, 30)
                self.set_font("Helvetica", "B", 9)
            self.cell(112, 8, f"  {_s(str(value))}", border=1, fill=True,
                      new_x="LMARGIN", new_y="NEXT")
        self.ln(10)
        self._rst()

    # ── Section / sub-section headings ─────────────────────────────────────────

    def h1(self, number: int, title: str):
        if self.get_y() > 255:
            self.add_page()
        else:
            self.ln(4)
        # Navy background
        self.set_font("Helvetica", "B", 13)
        self.set_fill_color(22, 45, 85)
        self.set_draw_color(200, 160, 40)
        self.set_text_color(255, 255, 255)
        self.cell(0, 11, f"   {number}. {_s(title).upper()}", border=0, fill=True,
                  new_x="LMARGIN", new_y="NEXT")
        # Gold underline
        self.set_line_width(1.0)
        self.line(20, self.get_y(), 190, self.get_y())
        self.ln(5)
        self._rst()

    def h2(self, title: str):
        if self.get_y() > 258:
            self.add_page()
        else:
            self.ln(3)
        # Blue-tinted band
        self.set_fill_color(235, 241, 252)
        self.set_draw_color(59, 100, 180)
        self.set_line_width(0.8)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(22, 45, 85)
        self.cell(0, 9, f"   {_s(title)}", border="LB", fill=True,
                  new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        self._rst()

    def h3(self, title: str):
        self.ln(2)
        self.set_font("Helvetica", "BI", 10)
        self.set_text_color(59, 100, 180)
        self.cell(5, 7, "")          # small indent
        self.cell(0, 7, _s(title), new_x="LMARGIN", new_y="NEXT")
        # Thin colored underline
        self.set_draw_color(180, 200, 240)
        self.set_line_width(0.3)
        self.line(20, self.get_y(), 120, self.get_y())
        self.ln(3)
        self._rst()

    # ── Body text ──────────────────────────────────────────────────────────────

    def para(self, text: str):
        self.set_font("Helvetica", size=10)
        self.set_text_color(35, 35, 35)
        self.multi_cell(0, 5.5, _s(text))
        self.ln(3)
        self._rst()

    def bullets(self, items: list, indent: int = 5):
        self.set_font("Helvetica", size=10)
        self.set_text_color(35, 35, 35)
        for item in items:
            self.set_x(20 + indent)
            self.set_text_color(59, 100, 180)
            self.cell(5, 6, ">")
            self.set_text_color(35, 35, 35)
            self.multi_cell(PAGE_W - indent - 5, 6, _s(str(item)))
        self.ln(2)
        self._rst()

    def note_box(self, text: str, bg=(255, 252, 230), border_color=(200, 160, 0)):
        """A coloured info / warning / success box."""
        self.set_font("Helvetica", size=9)
        self.set_fill_color(*bg)
        self.set_draw_color(*border_color)
        self.set_line_width(0.6)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 5.5, f"  {_s(text)}", border=1, fill=True)
        self.ln(3)
        self._rst()

    # ── kv table (Field | Details — exactly like reference) ───────────────────

    def kv_table(self, rows: list):
        ROW_H  = 7
        KEY_W  = 55
        VAL_W  = 115
        CHARS  = 60          # conservative chars-per-line at 9pt / 115 mm
        BOTTOM = self.h - 22   # matches set_auto_page_break(margin=22)

        def _wrap(text: str) -> list:
            if not text:
                return [""]
            result, current = [], ""
            for word in text.split(" "):
                while len(word) > CHARS:
                    if current:
                        result.append(current)
                        current = ""
                    result.append(word[:CHARS])
                    word = word[CHARS:]
                joined = (current + " " + word).strip() if current else word
                if len(joined) <= CHARS:
                    current = joined
                else:
                    result.append(current)
                    current = word
            if current:
                result.append(current)
            lines = result if result else [""]
            if len(lines) > 25:
                lines = lines[:24] + [lines[24][:CHARS - 3] + "..."]
            return lines

        def _draw_header():
            self.set_font("Helvetica", "B", 9)
            self.set_fill_color(22, 45, 85)
            self.set_text_color(255, 255, 255)
            self.cell(KEY_W, 8, "   Field", border=1, fill=True)
            self.cell(VAL_W, 8, "   Details", border=1, fill=True,
                      new_x="LMARGIN", new_y="NEXT")
            self._rst()

        _draw_header()

        for i, (key, value) in enumerate(rows):
            bg      = (240, 244, 250) if i % 2 == 0 else (252, 252, 255)
            val_str = _s(str(value))
            lines   = _wrap(val_str)
            n       = len(lines)
            total_h = ROW_H * n

            # Pre-flight: if the full row won't fit, start a fresh page first.
            # This guarantees set_xy() always operates within the current page.
            if self.get_y() + total_h > BOTTOM - 2:
                self.add_page()
                _draw_header()

            y0 = self.get_y()
            x0 = self.l_margin   # 20 mm

            # Key cell spans the full row height
            self.set_fill_color(*bg)
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(22, 45, 85)
            self.cell(KEY_W, total_h, f"   {_s(str(key))}", border=1, fill=True)

            # Value column: one fixed-height cell per wrapped line (no multi_cell)
            self.set_font("Helvetica", size=9)
            self.set_text_color(30, 30, 30)
            for li, line_txt in enumerate(lines):
                if n == 1:
                    bdr = 1
                elif li == 0:
                    bdr = "LTR"
                elif li == n - 1:
                    bdr = "LBR"
                else:
                    bdr = "LR"
                self.set_xy(x0 + KEY_W, y0 + ROW_H * li)
                self.cell(VAL_W, ROW_H, f"   {line_txt}", border=bdr, fill=True)

            # Advance cursor safely — no page-break risk since we pre-checked.
            self.set_xy(x0, y0 + total_h)

        self.ln(5)
        self._rst()

    # ── Data table ─────────────────────────────────────────────────────────────

    def table(self, headers: list, rows: list, col_widths: list = None,
              header_bg=(22, 45, 85), header_fg=(255, 255, 255)):
        ROW_H  = 7
        BOTTOM = self.h - 22

        n = len(headers)
        if col_widths is None:
            col_w = [PAGE_W // n] * n
        else:
            scale = PAGE_W / sum(col_widths)
            col_w = [max(8, int(w * scale)) for w in col_widths]

        def _wrap(text, cw):
            max_ch = max(6, int((cw - 2) * 0.56))
            if not text:
                return [""]
            result, current = [], ""
            for word in text.split(" "):
                while len(word) > max_ch:
                    if current:
                        result.append(current)
                        current = ""
                    result.append(word[:max_ch])
                    word = word[max_ch:]
                joined = (current + " " + word).strip() if current else word
                if len(joined) <= max_ch:
                    current = joined
                else:
                    result.append(current)
                    current = word
            if current:
                result.append(current)
            return result or [""]

        def _draw_header():
            self.set_font("Helvetica", "B", 9)
            self.set_fill_color(*header_bg)
            self.set_text_color(*header_fg)
            for i, h in enumerate(headers):
                self.cell(col_w[i], 8, f"  {_s(h)}", border=1, fill=True)
            self.ln()
            self._rst()

        _draw_header()

        for ri, row_data in enumerate(rows):
            first = _s(str(row_data[0])).upper() if row_data else ""
            is_total    = any(first.startswith(t) for t in
                              ("TOTAL", "GRAND", "ESTIMATED", "NET", "SUBTOTAL"))
            is_rejected = any(
                kw in _s(str(row_data[-1])).upper()
                for kw in ("REJECT", "[X]")
            ) if len(row_data) > 1 else False

            # Pre-wrap every cell
            wrapped = [
                _wrap(_s(str(row_data[i] if i < len(row_data) else "")),
                      col_w[i] if i < len(col_w) else col_w[-1])
                for i in range(len(col_w))
            ]
            n_lines = max(len(w) for w in wrapped)
            total_h = ROW_H * n_lines

            # Pre-flight: ensure whole row fits on this page
            if self.get_y() + total_h > BOTTOM - 2:
                self.add_page()
                _draw_header()

            y0 = self.get_y()
            x0 = self.l_margin

            # Row background & font
            if is_total:
                self.set_font("Helvetica", "B", 9)
                self.set_fill_color(220, 228, 242)
                row_fg = (22, 45, 85)
            elif is_rejected:
                self.set_font("Helvetica", size=9)
                self.set_fill_color(255, 240, 240)
                row_fg = (160, 30, 30)
            else:
                self.set_font("Helvetica", size=9)
                if ri % 2 == 0:
                    self.set_fill_color(247, 249, 253)
                else:
                    self.set_fill_color(237, 242, 252)
                row_fg = (35, 35, 35)

            x_cur = x0
            for ci, lines in enumerate(wrapped):
                cw = col_w[ci] if ci < len(col_w) else col_w[-1]

                # Per-column colour overrides
                if not is_total and not is_rejected and ci < len(headers):
                    h_lower = headers[ci].lower()
                    raw = lines[0].replace(" ", "").replace("Rs.", "").replace(",", "")
                    try:
                        is_pos = float(raw) > 0
                    except ValueError:
                        is_pos = False
                    if any(k in h_lower for k in ("deduct", "excess", "reject")) and is_pos:
                        fg = (180, 30, 30)
                    elif any(k in h_lower for k in ("approv",)):
                        fg = (30, 130, 60)
                    else:
                        fg = row_fg
                else:
                    fg = row_fg

                self.set_text_color(*fg)
                for li, line_txt in enumerate(lines):
                    if n_lines == 1:
                        bdr = 1
                    elif li == 0:
                        bdr = "LTR"
                    elif li == n_lines - 1:
                        bdr = "LBR"
                    else:
                        bdr = "LR"
                    self.set_xy(x_cur, y0 + ROW_H * li)
                    self.cell(cw, ROW_H, f"  {line_txt}", border=bdr, fill=True)

                # Pad shorter columns to fill row height
                for li in range(len(lines), n_lines):
                    bdr = "LR" if li < n_lines - 1 else "LBR"
                    self.set_xy(x_cur, y0 + ROW_H * li)
                    self.cell(cw, ROW_H, "", border=bdr, fill=True)

                x_cur += cw

            # Advance cursor safely — row fits by pre-flight guarantee
            self.set_xy(x0, y0 + total_h)

        # Thin rule after table
        self.set_draw_color(150, 170, 210)
        self.set_line_width(0.4)
        self.line(20, self.get_y(), 190, self.get_y())
        self.ln(5)
        self._rst()

    # ── Decision badge ──────────────────────────────────────────────────────────

    def decision_badge(self, decision: str, approved: float, claimed: float,
                       voucher_appr: float = None):
        color = _DECISION_COLORS.get(decision, (148, 163, 184))
        label = decision.replace("_", " ").upper()

        # Top strip with decision color
        self.set_fill_color(*color)
        self.rect(20, self.get_y(), 170, 3, "F")
        self.ln(4)

        # Main badge cell
        self.set_font("Helvetica", "B", 14)
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        self.cell(0, 13, f"   {label}", border=0, fill=True,
                  new_x="LMARGIN", new_y="NEXT")

        # Detail strip (slightly darker shade) — two lines to avoid overflow
        r, g, b = color
        dark = (max(0, r - 40), max(0, g - 40), max(0, b - 40))
        self.set_fill_color(*dark)
        self.set_font("Helvetica", size=12)
        if voucher_appr is not None:
            ded_from_ph = max(round(voucher_appr - approved, 2), 0)
            line1 = (f"   Claimed: Rs.{claimed:,.2f}   |   "
                     f"Project Head Approved: Rs.{voucher_appr:,.2f}")
            line2 = (f"   Rite Audit Approved: Rs.{approved:,.2f}   |   "
                     f"Deduction from PH: Rs.{ded_from_ph:,.2f}")
        else:
            rate  = (approved / claimed * 100) if claimed > 0 else 0
            ded   = claimed - approved
            line1 = (f"   Claimed: Rs.{claimed:,.2f}   |   "
                     f"Rite Audit Approved: Rs.{approved:,.2f}")
            line2 = (f"   Deduction: Rs.{ded:,.2f}   |   "
                     f"Approval Rate: {rate:.1f}%")
        self.cell(0, 7, _s(line1), border=0, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 7, _s(line2), border=0, fill=True, new_x="LMARGIN", new_y="NEXT")

        # Bottom strip
        self.set_fill_color(*color)
        self.rect(20, self.get_y(), 170, 2, "F")
        self.ln(7)
        self._rst()

    # ── End of report ──────────────────────────────────────────────────────────

    def end_marker(self, disclaimer: str = ""):
        self.ln(10)
        # Decorative rule
        self.set_fill_color(22, 45, 85)
        self.rect(20, self.get_y(), 170, 1.5, "F")
        self.ln(4)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(22, 45, 85)
        self.cell(0, 8, "-- End of Report --", align="C",
                  new_x="LMARGIN", new_y="NEXT")
        self.set_fill_color(22, 45, 85)
        self.rect(20, self.get_y(), 170, 1.5, "F")
        self.ln(4)
        if disclaimer:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(110, 110, 110)
            self.multi_cell(0, 5, _s(disclaimer))
        self._rst()


# ── Rejected-item card helper ─────────────────────────────────────────────────

def _draw_reject_card(pdf, idx: int, desc: str, dt: str, col3: str,
                      amt: float, reason: str,
                      col_a: int = 82, col_b: int = 22,
                      col_c: int = 20, col_d: int = 38):
    """
    Draw one rejected-item card (2-row layout):
      Row 1: # | description (col_a) | col_b | col_c | amount (col_d)
      Row 2: "Reason:" label + full reason text (wraps freely)

    Pre-calculates total card height and forces a page break BEFORE drawing
    so multi_cell never crosses a page boundary mid-card.
    """
    REASON_W   = 142        # mm available for reason text
    REASON_LH  = 6          # line height for reason
    CHARS_RSN  = max(6, int((REASON_W - 2) * 0.56))
    BOTTOM     = pdf.h - 22

    # Sanitise all string inputs
    desc   = _s(desc)
    dt     = _s(dt)
    col3   = _s(col3)
    reason = _s(reason)

    # Pre-wrap reason to count lines accurately
    words, result, current = reason.split(" "), [], ""
    for word in words:
        while len(word) > CHARS_RSN:
            if current:
                result.append(current)
                current = ""
            result.append(word[:CHARS_RSN])
            word = word[CHARS_RSN:]
        joined = (current + " " + word).strip() if current else word
        if len(joined) <= CHARS_RSN:
            current = joined
        else:
            result.append(current)
            current = word
    if current:
        result.append(current)
    reason_lines = len(result) if result else 1

    card_h = 7 + reason_lines * REASON_LH   # header row + reason rows

    # Force page break BEFORE drawing so no cell splits across pages
    if pdf.get_y() + card_h > BOTTOM - 2:
        pdf.add_page()

    bg = (255, 242, 242) if idx % 2 == 1 else (255, 250, 250)

    # ── Header row ────────────────────────────────────────────────────────────
    pdf.set_fill_color(*bg)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(160, 30, 30)
    pdf.cell(8, 7, f" {idx}.", border="LTB", fill=True)
    pdf.set_text_color(22, 45, 85)
    pdf.cell(col_a, 7, f"  {desc}", border="TB", fill=True)
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(col_b, 7, f"  {dt}", border="TB", fill=True)
    pdf.cell(col_c, 7, f"  {col3}", border="TB", fill=True)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(22, 45, 85)
    pdf.cell(col_d, 7, f"  Rs.{amt:,.2f}", border="TBR", fill=True,
             new_x="LMARGIN", new_y="NEXT")

    # ── Reason row ────────────────────────────────────────────────────────────
    # Draw each pre-wrapped reason line as a plain cell (no multi_cell = no surprise page breaks)
    pdf.set_fill_color(*bg)
    y0 = pdf.get_y()
    x0 = pdf.l_margin
    total_rsn_h = reason_lines * REASON_LH

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(100, 40, 40)
    pdf.cell(28, total_rsn_h, "   Reason:", border="LB", fill=True)

    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(50, 50, 50)
    for li, line_txt in enumerate(result if result else [reason[:CHARS_RSN]]):
        if reason_lines == 1:
            bdr = "BR"
        elif li == 0:
            bdr = "TR"
        elif li == reason_lines - 1:
            bdr = "BR"
        else:
            bdr = "R"
        pdf.set_xy(x0 + 28, y0 + REASON_LH * li)
        pdf.cell(REASON_W, REASON_LH, f" {line_txt}", border=bdr, fill=True)

    pdf.set_xy(x0, y0 + total_rsn_h)
    pdf._rst()


# ══════════════════════════════════════════════════════════════════════════════
# Main generator
# ══════════════════════════════════════════════════════════════════════════════

def generate_audit_pdf(state: dict, form_snapshot: dict = None) -> bytes:
    """
    Generate a detailed audit-style PDF from the LangGraph claim pipeline state.
    Returns raw .pdf bytes.
    """
    form_snapshot = form_snapshot or {}
    pdf = _PDF()
    pdf.add_page()

    # ── Unpack state ───────────────────────────────────────────────────────────
    claim_id        = state.get("claim_id", "N/A")
    emp_name        = state.get("employee_name", "N/A")
    emp_id          = state.get("employee_id", "N/A")
    claimed         = float(state.get("claimed_amount") or 0)
    approved        = float(state.get("approved_amount") or 0)
    decision        = state.get("decision", "pending_review")
    description     = state.get("claim_description", "")

    cat_elig        = state.get("category_eligible") or {}
    violations      = state.get("policy_violations") or []
    data_issues     = state.get("data_validation_issues") or []
    calc_issues     = state.get("calculation_validation_issues") or []
    calc_warnings   = state.get("calculation_validation_warnings") or []
    report_issues   = state.get("report_validation_issues") or []
    all_issues      = violations + data_issues

    expenses        = state.get("expenses") or []
    rejected_exps   = state.get("rejected_expenses") or []
    dups_removed    = state.get("duplicates_removed") or []
    extracted_text  = state.get("extracted_text") or []
    ocr_conf        = float(state.get("ocr_confidence") or 0)
    total_extracted = float(state.get("total_extracted_amount") or 0)
    cat_claimed_tot = float(state.get("category_claimed_total") or 0)
    extraction_gap  = float(state.get("extraction_gap") or 0)
    recon_note      = state.get("reconciliation_note", "")
    unolo_km        = state.get("unolo_distance_km")
    eligible_km     = state.get("eligible_distance_km")
    emp_dist_km     = state.get("emp_distance_km")

    emp_summary     = state.get("employee_summary") or {}
    has_voucher     = bool(emp_summary.get("is_summary"))
    voucher_no      = emp_summary.get("voucher_no", "")
    voucher_period  = emp_summary.get("period", "")
    voucher_emp     = emp_summary.get("employee_name", "")
    voucher_total   = float(emp_summary.get("summary_total") or 0)
    voucher_approved = float(emp_summary.get("summary_approved") or 0)
    line_decisions  = state.get("voucher_line_decisions") or []
    ai_voucher_rev  = bool(line_decisions)
    has_any_ph_approval = any(
        float(d.get("approved_amount") or 0) > 0
        for d in line_decisions
    )

    judg_note       = state.get("admin_judgment_note", "")
    judg_applied    = state.get("admin_judgment_applied", False)

    period_start = (form_snapshot.get("period_start")
                    or state.get("claim_period_start", ""))
    period_end   = (form_snapshot.get("period_end")
                    or state.get("claim_period_end", ""))

    sub_date = state.get("submission_date", "")
    if sub_date:
        try:
            sub_date = datetime.fromisoformat(sub_date).strftime("%d %b %Y")
        except Exception:
            pass

    today       = datetime.now().strftime("%d %B %Y")
    deduction   = round(claimed - approved, 2)
    period_str  = f"{period_start}  to  {period_end}" if period_start else "—"
    n_cats      = len(cat_elig) or len({e.get("category") for e in expenses if e.get("category")})
    n_docs      = len(extracted_text) or len(expenses)

    evidence_src = (
        "an official SpineHR expense voucher (pre-approved by admin)"
        if (has_voucher and not ai_voucher_rev)
        else ("an AI-reviewed SpineHR expense voucher"
              if ai_voucher_rev
              else f"{max(1, n_docs)} uploaded receipt(s) / document(s)")
    )

    # ── Title block ────────────────────────────────────────────────────────────
    pdf.title_block(
        company  = "Rite Water Solutions (India) Pvt. Ltd.",
        title    = "Expense Audit Report",
        subtitle = "Rite Audit Detailed Analysis of Employee Expense Submission",
        context  = f"{emp_name}  |  {period_str}",
    )

    # ── Metadata table ─────────────────────────────────────────────────────────
    meta = [
        ("Prepared For",    "Management, Rite Water Solutions (India) Pvt. Ltd."),
        ("Employee",        f"{emp_name}  ({emp_id})"),
        ("Claim ID",        claim_id),
        ("Claim Period",    period_str),
        ("Submission Date", sub_date or today),
        ("Date of Report",  today),
        ("Classification",  "CONFIDENTIAL - FOR MANAGEMENT USE ONLY"),
    ]
    if description:
        meta.insert(3, ("Description", _trunc(description, 90)))
    if has_voucher and voucher_no:
        meta.insert(3, ("Expense Voucher No.", voucher_no))
    if has_voucher and voucher_period:
        meta.insert(4, ("Voucher Period", voucher_period))
    pdf.meta_table(meta)

    # ── Decision badge ─────────────────────────────────────────────────────────
    pdf.decision_badge(decision, approved, claimed,
                       voucher_appr=voucher_approved if (has_voucher and has_any_ph_approval) else None)

    # ══════════════════════════════════════════════════════════════════════════
    # 1. Executive Summary
    # ══════════════════════════════════════════════════════════════════════════
    pdf.h1(1, "Executive Summary")

    pdf.para(
        f"This report presents the detailed findings of an AI-assisted review of expense "
        f"claims submitted by {emp_name} (Employee ID: {emp_id}) covering the period "
        f"{period_str}. The claim was submitted on {sub_date or today} with a total claimed "
        f"amount of Rs. {claimed:,.2f}."
    )
    pdf.para(
        f"The review was conducted by the Rite Audit System, "
        f"which analyzed {n_cats} expense categor{'ies' if n_cats != 1 else 'y'} from "
        f"{evidence_src}, cross-referencing each item against the company reimbursement policy."
        + (f" A total of {len(expenses)} approved expense item(s) and "
           f"{len(rejected_exps)} rejected item(s) were processed."
           if expenses or rejected_exps else "")
    )

    if decision == "full_approval":
        pdf.para(
            f"OUTCOME: All submitted expenses were found to be valid and within policy limits. "
            f"The full claimed amount of Rs. {approved:,.2f} is approved for processing."
        )
    elif decision == "partial_approval":
        rate = (approved / claimed * 100) if claimed > 0 else 0
        pdf.para(
            f"OUTCOME: Partial approval granted. Rs. {approved:,.2f} ({rate:.1f}%) of the "
            f"Rs. {claimed:,.2f} claimed is recommended for approval. A deduction of "
            f"Rs. {deduction:,.2f} applies due to policy limit breaches or documentation "
            f"deficiencies. Full details are in Section 2."
        )
    else:
        pdf.para(
            f"OUTCOME: The claim has been rejected in full. No amount is approved for "
            f"processing. Detailed reasons are provided in the analysis below."
        )

    if judg_note:
        pdf.note_box(f"AI Judgment: {judg_note}")
    if recon_note:
        pdf.note_box(f"Reconciliation: {recon_note}", bg=(220, 235, 255),
                     border_color=(0, 100, 200))

    # ══════════════════════════════════════════════════════════════════════════
    # 2. Expense-by-Expense Analysis
    # ══════════════════════════════════════════════════════════════════════════
    pdf.h1(2, "Expense-by-Expense Analysis")

    # ── 3.0  Document Extraction Summary ──────────────────────────────────────
    if extracted_text:
        pdf.h2("2.0  Documents Scanned and Extracted")
        doc_rows = []
        for i, doc in enumerate(extracted_text, 1):
            src       = _s(doc.get("source") or f"Document {i}")
            rtype     = (doc.get("receipt_type") or "").strip().lower()
            if not rtype or rtype == "unknown":
                ext   = src.rsplit(".", 1)[-1].lower() if "." in src else "unknown"
                typ   = _s(ext)
            else:
                typ   = _s(rtype)
            amt  = doc.get("extracted_amount") or doc.get("amount", "")
            amt_str = f"Rs. {float(amt):,.2f}" if amt else "—"
            conf = doc.get("confidence", "")
            conf_str = f"{float(conf) * 100:.0f}%" if conf else "—"
            doc_rows.append([str(i), src, typ, amt_str, conf_str])
        pdf.table(
            headers=["#", "Document / Source", "Type", "Amount Extracted", "OCR Confidence"],
            rows=doc_rows,
            col_widths=[8, 65, 32, 35, 30],
        )
        if total_extracted > 0:
            pdf.para(
                f"Total amount extracted from all documents: Rs. {total_extracted:,.2f}  |  "
                f"Amount categorised: Rs. {cat_claimed_tot:,.2f}"
                + (f"  |  Gap: Rs. {abs(extraction_gap):,.2f}"
                   f" ({'over' if extraction_gap > 0 else 'under'}-categorised)"
                   if abs(extraction_gap) > 0.01 else "  |  No extraction gap.")
            )

    # ── Per-category sub-sections ──────────────────────────────────────────────
    if not cat_elig and not expenses:
        pdf.para("No itemised expense data was extracted from the submitted documents.")
    else:
        # Group expenses and rejected_expenses by category
        items_by_cat: dict = {}
        for exp in expenses:
            cat = exp.get("category", "other")
            items_by_cat.setdefault(cat, {"approved": [], "partial": []})
            items_by_cat[cat]["approved"].append(exp)

        rej_by_cat: dict = {}
        for exp in rejected_exps:
            cat = exp.get("category", "other")
            rej_by_cat.setdefault(cat, []).append(exp)

        # Merge all known categories
        all_cats = sorted(
            set(list(cat_elig.keys()) + list(items_by_cat.keys()) + list(rej_by_cat.keys())),
            key=lambda k: list(_CAT_LABELS.keys()).index(k)
            if k in _CAT_LABELS else 99
        )
        if not all_cats and items_by_cat:
            all_cats = list(items_by_cat.keys())

        sub_num = 1
        for cat_key in all_cats:
            cat_data    = cat_elig.get(cat_key, {})
            cat_name    = _CAT_LABELS.get(cat_key, cat_key.replace("_", " ").title())
            approved_items = items_by_cat.get(cat_key, {}).get("approved", [])
            rejected_items = rej_by_cat.get(cat_key, [])

            cat_claimed_v = float(cat_data.get("claimed") or
                                  sum(i.get("amount", 0) for i in approved_items))
            cat_elig_v    = float(cat_data.get("eligible") or 0)
            cap_v         = float(cat_data.get("policy_limit") or 0)
            reasoning_v   = cat_data.get("reasoning", "")
            item_count    = int(cat_data.get("items") or
                                len(approved_items) + len(rejected_items))

            pdf.h2(f"2.{sub_num}  {cat_name}")

            # ── Bill details kv table ──────────────────────────────────────────
            dates = sorted({i.get("date", "") for i in (approved_items + rejected_items)
                            if i.get("date")})
            date_range = (f"{dates[0]}  to  {dates[-1]}" if len(dates) > 1
                          else (dates[0] if dates else "—"))

            kv = [
                ("Category",         cat_name),
                ("Date Range",        date_range),
                ("Total Items",       f"{item_count} submitted  "
                                      f"({len(approved_items)} approved, "
                                      f"{len(rejected_items)} rejected)"),
                ("Total Claimed",     f"Rs. {cat_claimed_v:,.2f}"),
                ("Amount Approved",   f"Rs. {cat_elig_v:,.2f}"),
                ("Deduction",         f"Rs. {max(cat_claimed_v - cat_elig_v, 0):,.2f}"),
                ("Policy Cap",        f"Rs. {cap_v:,.2f}" if cap_v else "Per policy rules"),
                ("Approval Rate",     f"{(cat_elig_v / cat_claimed_v * 100):.1f}%"
                                      if cat_claimed_v > 0 else "—"),
            ]
            if cat_key == "two_wheeler":
                dist_used = eligible_km or unolo_km or emp_dist_km
                if dist_used:
                    kv.append(("Distance Used", f"{dist_used:,.1f} km"))
                if unolo_km:
                    kv.append(("GPS Verified (Unolo)", f"{unolo_km:,.1f} km"))
            if reasoning_v:
                kv.append(("Policy Basis", reasoning_v))
            pdf.kv_table(kv)

            # ── Approved / partial items table ─────────────────────────────────
            if approved_items:
                pdf.h3(f"Items Approved / Partially Approved")
                cat_ratio = (cat_elig_v / cat_claimed_v) if cat_claimed_v > 0 else 0
                tbl_rows = []
                for exp in approved_items:
                    amt      = float(exp.get("amount") or 0)
                    appr_amt = round(amt * min(cat_ratio, 1.0), 2)
                    desc     = _s(exp.get("description") or "Expense")
                    dt       = _s(exp.get("date") or "—")
                    src      = _trunc(exp.get("source_document") or "—", 20)
                    conf     = exp.get("system_confidence") or exp.get("confidence")
                    conf_str = f"{float(conf) * 100:.0f}%" if conf else "—"
                    notes    = _s(exp.get("validation_notes") or "OK")
                    tbl_rows.append([desc, dt, f"Rs.{amt:,.2f}",
                                     f"Rs.{appr_amt:,.2f}", conf_str, notes])
                # Totals
                total_claimed_cat = sum(float(e.get("amount") or 0) for e in approved_items)
                total_appr_cat    = round(total_claimed_cat * min(cat_ratio, 1.0), 2)
                tbl_rows.append(["TOTAL", "",
                                  f"Rs.{total_claimed_cat:,.2f}",
                                  f"Rs.{total_appr_cat:,.2f}", "", ""])
                pdf.table(
                    headers=["Description", "Date", "Claimed", "Approved",
                              "AI Conf.", "Notes"],
                    rows=tbl_rows,
                    col_widths=[48, 24, 25, 25, 22, 26],
                )

            # ── Rejected items table ───────────────────────────────────────────
            if rejected_items:
                pdf.h3(f"Items Rejected")
                rej_rows = []
                for j, exp in enumerate(rejected_items, 1):
                    amt    = float(exp.get("amount") or 0)
                    desc   = _s(exp.get("description") or "Expense")
                    dt     = _s(exp.get("date") or "—")
                    reason = _s(exp.get("system_reason") or
                                exp.get("validation_notes") or "Policy violation")
                    conf   = exp.get("system_confidence")
                    conf_s = f"{float(conf)*100:.0f}%" if conf else "—"
                    _draw_reject_card(pdf, j, desc, dt, conf_s, amt, reason,
                                      col_a=82, col_b=22, col_c=20, col_d=38)
                pdf._rst()

            # ── Voucher line decisions (AI voucher review mode) ────────────────
            if ai_voucher_rev and not approved_items and not rejected_items:
                cat_decs = [d for d in line_decisions
                            if _map_cat(d.get("expense_head", "")) == cat_key]
                if cat_decs:
                    pdf.h3("Voucher Line Items")
                    vl_rows = []
                    for d in cat_decs:
                        head  = _s(d.get("expense_head") or "")
                        dt    = _s(d.get("date", "—"))
                        amt   = float(d.get("claimed_amount") or d.get("amount") or 0)
                        appr  = float(d.get("approved_amount") or amt)
                        dec   = _s(d.get("decision", "approve")).upper()
                        rsn   = _s(d.get("reason") or "--")
                        vl_rows.append([head, dt, f"Rs.{amt:,.2f}",
                                         f"Rs.{appr:,.2f}", dec, rsn])
                    vl_rows.append(["TOTAL", "",
                                     f"Rs.{sum(float(d.get('claimed_amount') or 0) for d in cat_decs):,.2f}",
                                     f"Rs.{sum(float(d.get('approved_amount') or d.get('claimed_amount') or 0) for d in cat_decs):,.2f}",
                                     "", ""])
                    pdf.table(
                        headers=["Expense Head", "Date", "Claimed",
                                  "Approved", "Decision", "Reason"],
                        rows=vl_rows,
                        col_widths=[45, 22, 25, 25, 22, 31],
                    )

            # ── Key findings bullet list ───────────────────────────────────────
            cat_findings = [v for v in all_issues
                            if cat_name.lower().split("/")[0].strip() in v.lower()
                            or cat_key.replace("_", " ") in v.lower()]
            if not cat_findings and reasoning_v and "cap" in reasoning_v.lower():
                cat_findings = [reasoning_v]
            if not cat_findings and cat_elig_v < cat_claimed_v - 0.01:
                cat_findings = [
                    f"Claimed Rs.{cat_claimed_v:,.2f} exceeds policy cap of "
                    f"Rs.{cap_v:,.2f}; eligible amount adjusted to Rs.{cat_elig_v:,.2f}."
                ]
            if rejected_items:
                cat_findings.append(
                    f"{len(rejected_items)} item(s) rejected by AI judgment — "
                    "see rejection table above for specific reasons."
                )

            pdf.h3(f"Key Findings — {cat_name}")
            if cat_findings:
                pdf.bullets(cat_findings)
            else:
                pdf.bullets([
                    f"All {cat_name} expenses are within policy limits. "
                    f"Rs.{cat_claimed_v:,.2f} claimed; Rs.{cat_elig_v:,.2f} approved."
                ])

            sub_num += 1

    # ── 3.x  Duplicates removed ────────────────────────────────────────────────
    if dups_removed:
        pdf.h2(f"2.{sub_num if 'sub_num' in dir() else '?'}  "
               "Duplicate Receipts Identified and Removed")
        pdf.para(
            f"{len(dups_removed)} receipt(s) were automatically identified as duplicates "
            "and excluded from calculations. UPI screenshots are removed when a matching "
            "vendor receipt exists for the same transaction. Identical submissions are "
            "deduplicated, keeping one copy."
        )
        dup_rows = [[str(i + 1), _s(d)] for i, d in enumerate(dups_removed)]
        pdf.table(
            headers=["#", "Excluded Item"],
            rows=dup_rows,
            col_widths=[10, 160],
        )

    # ══════════════════════════════════════════════════════════════════════════
    # 4. Pattern Analysis and Risk Assessment
    # ══════════════════════════════════════════════════════════════════════════
    pdf.h1(3, "Pattern Analysis and Risk Assessment")

    # ── 4.1  Financial Exposure Summary ───────────────────────────────────────
    pdf.h2("3.1  Financial Exposure Summary")
    if cat_elig:
        fin_rows = []
        for ck, cd in cat_elig.items():
            cname   = _CAT_LABELS.get(ck, ck.replace("_", " ").title())
            cclaim  = float(cd.get("claimed") or 0)
            celig   = float(cd.get("eligible") or 0)
            cexcess = round(cclaim - celig, 2)
            ccap    = float(cd.get("policy_limit") or 0)
            creason = _s(cd.get("reasoning") or "—")
            fin_rows.append([
                cname,
                f"Rs.{cclaim:,.0f}",
                f"Rs.{celig:,.0f}",
                f"Rs.{max(cexcess,0):,.0f}",
                f"Rs.{ccap:,.0f}" if ccap else "—",
                creason,
            ])
        fin_rows.append([
            "TOTAL",
            f"Rs.{claimed:,.0f}",
            f"Rs.{approved:,.0f}",
            f"Rs.{max(deduction,0):,.0f}",
            "", "",
        ])
        pdf.table(
            headers=["Category", "Claimed", "Approved", "Deduction",
                      "Policy Cap", "Policy Basis"],
            rows=fin_rows,
            col_widths=[40, 25, 25, 25, 25, 30],
        )
    else:
        pdf.para("No category-level financial data available.")

    # ── 4.2  Inflation / Anomaly Analysis ─────────────────────────────────────
    pdf.h2("3.2  Consistent Issues / Anomaly Analysis")
    if not all_issues and not calc_warnings:
        pdf.para(
            "No policy violations, anomalies, or documentation deficiencies were "
            "identified in this claim. All expense items are consistent with the "
            "company's reimbursement policy and supported by submitted documentation."
        )
    else:
        if all_issues:
            pdf.para(f"The following {len(all_issues)} issue(s) were identified:")
            issue_rows = [[str(i+1), _s(issue)] for i, issue in enumerate(all_issues)]
            pdf.table(
                headers=["#", "Issue"],
                rows=issue_rows,
                col_widths=[10, 160],
                header_bg=(160, 60, 0),
            )
        if calc_warnings:
            pdf.h3("Calculation Warnings")
            pdf.bullets([_s(w) for w in calc_warnings])
        if calc_issues:
            pdf.h3("Calculation Validation Issues")
            pdf.bullets([_s(w) for w in calc_issues])

    # ── 4.3  Risk Assessment ───────────────────────────────────────────────────
    pdf.h2("3.3  Risk Assessment")
    if claimed > 0:
        ded_pct = deduction / claimed * 100
        if decision == "rejected":
            risk, bg = "HIGH", (255, 220, 220)
            risk_text = (
                f"The entire claim of Rs.{claimed:,.2f} has been rejected. "
                f"This indicates significant policy non-compliance or insufficient documentation."
            )
        elif ded_pct > 30:
            risk, bg = "HIGH", (255, 220, 220)
            risk_text = (
                f"The deduction of Rs.{deduction:,.2f} represents {ded_pct:.1f}% of the "
                f"total claimed amount — indicating substantial policy non-compliance."
            )
        elif ded_pct > 0:
            risk, bg = "MODERATE", (255, 250, 200)
            risk_text = (
                f"A deduction of Rs.{deduction:,.2f} ({ded_pct:.1f}%) was applied due to "
                f"policy limit breaches or documentation gaps."
            )
        else:
            risk, bg = "LOW", (220, 255, 220)
            risk_text = (
                "All expenses are within policy limits and supported by documentation. "
                "No significant risk factors identified."
            )
        pdf.note_box(f"Risk Level: {risk}  |  {risk_text}", bg=bg,
                     border_color=(150, 100, 0) if risk != "LOW" else (0, 150, 0))
    if all_issues:
        pdf.para(
            f"A total of {len(violations)} policy violation(s) and "
            f"{len(data_issues)} data validation issue(s) were recorded. "
            "See the full issue list in Section 3.2."
        )

    # ── 4.4  Reconciliation Analysis ──────────────────────────────────────────
    if total_extracted > 0 or cat_claimed_tot > 0:
        pdf.h2("3.4  Reconciliation Analysis")
        recon_rows = [
            ["Total Amount Claimed (by Employee)",
             f"Rs.{claimed:,.2f}", "—"],
            ["Total Extracted from Documents (OCR)",
             f"Rs.{total_extracted:,.2f}",
             f"{'OK' if abs(total_extracted - claimed) < 1 else 'GAP: Rs.' + f'{abs(total_extracted - claimed):,.2f}'}"],
            ["Total Categorised Amount",
             f"Rs.{cat_claimed_tot:,.2f}",
             f"{'OK' if abs(extraction_gap) < 1 else 'Gap: Rs.' + f'{abs(extraction_gap):,.2f}'}"],
            ["Total Approved (this decision)",
             f"Rs.{approved:,.2f}", "—"],
            ["Total Deduction",
             f"Rs.{deduction:,.2f}", "—"],
        ]
        if unolo_km:
            recon_rows.append([
                "GPS Distance (Unolo)",
                f"{unolo_km:,.1f} km", "—"])
        if emp_dist_km:
            recon_rows.append([
                "Employee-Reported Distance",
                f"{emp_dist_km:,.1f} km", "—"])
        pdf.table(
            headers=["Item", "Value", "Status"],
            rows=recon_rows,
            col_widths=[85, 50, 35],
        )
        if recon_note:
            pdf.note_box(recon_note, bg=(220, 235, 255), border_color=(0, 100, 200))

    # ── 4.5  Voucher vs Rite Audit System Comparison ──────────────────────────
    if line_decisions or cat_elig:
        pdf.h2("3.5  Voucher vs Rite Audit System Comparison")

        # Aggregate claimed & voucher-approved per category from line_decisions
        cat_claimed_agg: dict = {}
        cat_voucher_agg: dict = {}
        for d in line_decisions:
            ck   = _map_cat(d.get("expense_head", ""))
            v_cl = float(d.get("claimed_amount") or 0)
            v_ap_raw = d.get("approved_amount")
            v_ap = float(v_cl if v_ap_raw is None else v_ap_raw)
            cat_claimed_agg[ck] = cat_claimed_agg.get(ck, 0) + v_cl
            cat_voucher_agg[ck] = cat_voucher_agg.get(ck, 0) + v_ap

        # All known categories (from both line_decisions and cat_elig)
        all_cmp_cats = sorted(
            set(list(cat_claimed_agg.keys()) + list(cat_elig.keys())),
            key=lambda k: list(_CAT_LABELS.keys()).index(k) if k in _CAT_LABELS else 99
        )

        ph_col_label = "Voucher Approved" if has_any_ph_approval else "Claimed Amt"
        pdf.para(
            f"The table below compares each expense category claimed against the amount "
            f"calculated by the Rite Audit System using company reimbursement policy. "
            + ("Voucher column shows SpineHR admin-approved amounts."
               if has_any_ph_approval else
               "SpineHR shows no admin approval yet — claimed amounts used as baseline.")
        )

        cmp_rows        = []
        total_voucher_appr = 0.0
        total_system_appr  = 0.0

        for ck in all_cmp_cats:
            cat_name  = _CAT_LABELS.get(ck, ck.replace("_", " ").title())
            v_cl      = cat_claimed_agg.get(ck, 0)
            v_ap_raw  = cat_voucher_agg.get(ck, 0)
            # When SpineHR has no approvals, use claimed as the comparison baseline
            v_ap      = v_ap_raw if has_any_ph_approval else v_cl
            sys_elig  = float((cat_elig.get(ck) or {}).get("eligible") or 0)
            # Use system eligible if category was analyzed; else match baseline
            sys_line  = sys_elig if ck in cat_elig else v_ap
            sys_line  = min(sys_line, v_ap)       # never approve more than baseline
            diff      = round(sys_line - v_ap, 2)
            status    = ("Match"    if abs(diff) < 0.01
                         else ("Deducted" if diff < 0 else "Excess"))
            if v_cl == 0 and sys_elig == 0:
                continue
            cmp_rows.append([
                cat_name,
                f"Rs.{v_cl:,.0f}",
                f"Rs.{v_ap:,.0f}",
                f"Rs.{sys_line:,.0f}",
                f"Rs.{abs(diff):,.0f}",
                status,
            ])
            total_voucher_appr += v_ap
            total_system_appr  += sys_line

        total_diff = round(total_system_appr - total_voucher_appr, 2)
        cmp_rows.append([
            "TOTAL",
            f"Rs.{claimed:,.0f}",
            f"Rs.{total_voucher_appr:,.0f}",
            f"Rs.{total_system_appr:,.0f}",
            f"Rs.{abs(total_diff):,.0f}",
            "Match" if abs(total_diff) < 0.01 else
            ("Deducted" if total_diff < 0 else "Excess"),
        ])
        pdf.table(
            headers=["Category", "Claimed", ph_col_label,
                     "System Approved", "Difference", "Status"],
            rows=cmp_rows,
            col_widths=[50, 26, 30, 28, 22, 20],
        )

        if abs(total_diff) < 0.01:
            pdf.note_box(
                "Voucher and Rite Audit System are fully aligned — no discrepancy in totals.",
                bg=(220, 255, 220), border_color=(0, 150, 0),
            )
        elif total_diff > 0:
            pdf.note_box(
                f"The Rite Audit System calculated Rs.{total_diff:,.2f} MORE than the voucher "
                f"approved amount. This may indicate the voucher was conservative or policy "
                f"caps were not fully applied in SpineHR.",
                bg=(255, 250, 220), border_color=(180, 130, 0),
            )
        else:
            pdf.note_box(
                f"The Rite Audit System calculated Rs.{abs(total_diff):,.2f} LESS than the "
                f"voucher approved amount. Deductions were applied based on policy limits "
                f"(distance caps, daily food limits, missing documentation).",
                bg=(255, 235, 220), border_color=(200, 80, 0),
            )

    # ── 4.6  Full Rejected Items Register ─────────────────────────────────────
    if rejected_exps:
        pdf.h2("3.6  Rejected Items Register")
        pdf.para(
            f"The following {len(rejected_exps)} item(s) were rejected and are NOT "
            "included in the approved amount."
        )
        for i, exp in enumerate(rejected_exps, 1):
            desc   = _s(exp.get("description") or "Expense")
            dt     = _s(exp.get("date") or "—")
            cat    = _s(_CAT_LABELS.get(exp.get("category", ""), exp.get("category", "—")))
            amt    = float(exp.get("amount") or 0)
            reason = _s(exp.get("system_reason") or exp.get("reason") or "—")
            # col order: desc(74) | cat(30) | dt(22) | amt(36)  →  total 8+74+30+22+36=170
            _draw_reject_card(pdf, i, desc, cat, dt, amt, reason,
                              col_a=74, col_b=30, col_c=22, col_d=36)
        total_rej = sum(float(e.get("amount") or 0) for e in rejected_exps)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(22, 45, 85)
        pdf.cell(0, 7, f"   Total value of rejected items: Rs.{total_rej:,.2f}",
                 new_x="LMARGIN", new_y="NEXT")
        pdf._rst()

    # ── 4.7  Documentation Status ──────────────────────────────────────────────
    pdf.h2("3.7  Documentation Status")
    missing_docs = [i for i in all_issues
                    if any(kw in i.lower() for kw in
                           ["missing", "proof", "attach", "upload", "required",
                            "not provided", "no gps", "no distance"])]
    if missing_docs:
        pdf.para("The following documentation gaps were identified:")
        pdf.bullets(missing_docs)
    else:
        pdf.para(
            "All required supporting documentation was present for the approved expense items."
            + (" The official SpineHR expense voucher serves as the primary evidence document."
               if has_voucher else
               " Individual receipt scans were accepted as supporting evidence.")
        )
    # AI judgment detail
    if judg_applied and judg_note:
        pdf.h3("AI Judgment System Details")
        pdf.para(judg_note)
    if report_issues:
        pdf.h3("Report Quality Checks")
        pdf.bullets([_s(i) for i in report_issues])

    # ══════════════════════════════════════════════════════════════════════════
    # 5. Recommendations
    # ══════════════════════════════════════════════════════════════════════════
    pdf.h1(4, "Recommendations")

    # ── 5.1  Immediate Actions ─────────────────────────────────────────────────
    pdf.h2("4.1  Immediate Actions")
    immediate = []
    if decision == "rejected":
        immediate += [
            f"Do not process Claim {claim_id} in the current form. Return the submission "
            "to the employee with specific reasons for rejection.",
            "Inform the employee of all policy requirements that were not met so they can "
            "resubmit with the correct documentation.",
            "Log this claim in the internal audit system for tracking purposes.",
        ]
    elif decision == "partial_approval":
        immediate += [
            f"Process Claim {claim_id} for the approved amount of Rs.{approved:,.2f}. "
            f"A deduction of Rs.{deduction:,.2f} applies.",
            "Communicate the deduction reason(s) to the employee (see Section 2 and Section 3.2).",
            "Advise the employee to resubmit the disallowed portion (Rs.{:,.2f}) with corrected "
            "documentation if they wish to claim the balance.".format(deduction),
        ]
    else:  # full
        immediate += [
            f"Process Claim {claim_id} for the full approved amount of Rs.{approved:,.2f}.",
            "File the supporting documents (receipts, GPS screenshot, expense voucher) with "
            "the payment record for audit purposes.",
        ]
    if not has_voucher:
        immediate.append(
            "Request the official SpineHR expense voucher from the employee (if not yet "
            "submitted) to complete the approval record."
        )
    if unolo_km is None and any(k == "two_wheeler" for k in cat_elig):
        immediate.append(
            "Request Unolo GPS tracking screenshot from the employee to validate "
            "the two-wheeler distance claimed."
        )
    pdf.bullets(immediate)

    # ── 5.2  Documentation Requirements ───────────────────────────────────────
    pdf.h2("4.2  Documentation Requirements")
    doc_req = []
    if missing_docs:
        doc_req += [_s(d) for d in missing_docs]
    if not has_voucher:
        doc_req.append(
            "Upload the official SpineHR Expense Voucher PDF to confirm admin-level "
            "approval breakdown and enable final verification."
        )
    if any("hotel" in k for k in cat_elig):
        doc_req.append(
            "Hotel / accommodation receipts must include the official GST invoice with "
            "check-in / check-out dates and the establishment's letterhead or stamp."
        )
    if any("food" in k for k in cat_elig):
        doc_req.append(
            "Food receipts must clearly show the vendor name, date, and itemised total. "
            "UPI screenshots alone are insufficient — pair with the physical bill."
        )
    if not doc_req:
        doc_req.append("No additional documentation is required for this claim.")
    pdf.bullets(doc_req)

    # ── 5.3  Investigation Actions (if risk is high) ───────────────────────────
    if deduction > claimed * 0.25 or decision == "rejected":
        pdf.h2("4.3  Investigation Actions")
        pdf.bullets([
            f"Conduct a wider review of claims submitted by {emp_name} for the current "
            "financial year to determine whether similar patterns recur.",
            "Cross-check the vendor receipts submitted against vendor GST filings "
            "or direct vendor confirmation if amounts appear inflated.",
            "If a travel vendor is involved, verify the vehicle registration, route, "
            "and toll records independently.",
            "Obtain GPS tracking logs or FASTag transaction records for the claimed period.",
            "Escalate to HR and internal audit if fraud indicators are confirmed.",
        ])
    else:
        pdf.h2("4.3  Process Improvements")
        pdf.bullets([
            "Require Unolo GPS screenshots for all two-wheeler claims above Rs. 1,000.",
            "Enforce a 7-day submission window from the end of the claim period.",
            "Require supervisor co-sign on expense vouchers above Rs. 10,000.",
        ])

    # ── 5.4  Systemic Controls ─────────────────────────────────────────────────
    pdf.h2("4.4  Systemic Controls")
    pdf.bullets([
        "All travel reimbursement claims above Rs. 5,000 should be supported by GPS "
        "route evidence (Unolo tracking) in addition to fuel / toll receipts.",
        "Implement a per-trip distance validation step: claimed distance should be "
        "verified against the employee's visit report and GPS data before approval.",
        "Use the Rite Audit System's feedback loop — admin overrides are automatically "
        "saved to the training database to improve future AI judgments.",
        "Conduct quarterly audits of top-10 expense claimants to identify systematic "
        "inflation or vendor-pattern anomalies.",
        "Consider vendor empanelment for travel services to eliminate manual odometer "
        "readings and require GPS-tracked vehicles.",
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # 6. Conclusion
    # ══════════════════════════════════════════════════════════════════════════
    pdf.h1(5, "Conclusion")

    pdf.para(
        f"The AI-assisted review of Claim {claim_id} submitted by {emp_name} "
        f"(Employee ID: {emp_id}) for the period {period_str} has been completed. "
        f"{n_cats} expense categor{'ies were' if n_cats != 1 else 'y was'} analyzed "
        f"across {len(expenses) + len(rejected_exps)} submitted item(s) against Rite "
        f"Water Solutions' expense reimbursement policy."
    )

    if decision == "full_approval":
        pdf.para(
            f"All submitted expenses totalling Rs.{claimed:,.2f} are within policy limits "
            f"and supported by adequate documentation. The full amount of Rs.{approved:,.2f} "
            f"is approved for processing."
        )
    elif decision == "partial_approval":
        pdf.para(
            f"The total claimed amount of Rs.{claimed:,.2f} includes Rs.{deduction:,.2f} in "
            f"expenses that exceed policy limits or lack required documentation. "
            f"Rs.{approved:,.2f} is recommended for approval ({(approved/claimed*100):.1f}%). "
            f"The disallowed Rs.{deduction:,.2f} may be resubmitted with corrected documentation."
        )
    else:
        pdf.para(
            f"The total claimed amount of Rs.{claimed:,.2f} could not be approved due to "
            f"policy non-compliance and/or insufficient documentation. "
            f"The claim has been rejected in full. The employee should review the rejection "
            f"reasons detailed in Sections 2 and 3, address each point, and resubmit."
        )

    if all_issues:
        pdf.para(
            f"A total of {len(all_issues)} policy violation(s) or data issue(s) were recorded. "
            "These are detailed in Section 3.2. The AI judgment was cross-checked against "
            f"the training database of prior admin decisions to ensure consistency."
        )

    pdf.para(
        "This AI-generated recommendation must be reviewed and confirmed by an authorized "
        "finance officer or HR representative before any payment is processed or communicated "
        "to the employee. The findings should be filed with the company's internal audit records "
        "as per the applicable expense reimbursement policy."
    )

    # ── End marker ─────────────────────────────────────────────────────────────
    pdf.end_marker(
        "This report was generated by the Rite Audit System. "
        "All figures are based on OCR-extracted receipt data, company policy as configured, "
        "and the AI judgment engine. Human review is mandatory before final disbursement."
    )

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


# ── Helper ─────────────────────────────────────────────────────────────────────

def _map_cat(expense_head: str) -> str:
    h = expense_head.lower()
    if any(x in h for x in ("bus", "train", "auto", "sleeper", "ac")):
        return "bus_travel"
    if any(x in h for x in ("fuel", "bike", "two", "2 wheel", "petrol")):
        return "two_wheeler"
    if any(x in h for x in ("food", "meal", "da", "allowance")):
        return "food"
    if any(x in h for x in ("hotel", "lodge", "stay", "accommodation")):
        return "hotel"
    if any(x in h for x in ("toll", "fasttag", "fast tag")):
        return "fasttag"
    if any(x in h for x in ("site", "material", "misc")):
        return "site_expenses"
    return "other"
