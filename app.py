"""
Streamlit Application for Employee Rite Audit System.

Two-step UX:
1. Claim submission page
2. Dedicated results dashboard
"""
import os
import sys
import uuid
from datetime import datetime, timedelta

import logging
import streamlit as st

logging.getLogger("tornado.websocket").setLevel(logging.ERROR)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from admin_dashboard import render_dashboard_page, render_admin_review_page
from utils.report_renderer import render_structured_report as _render_structured_report
from config.policy import GENERAL_POLICY
from graph import review_claim_stream
from integrations.spinehr_api import submit_claim, SPINEHR_API_KEY as _SPINEHR_KEY
from integrations.unolo_api import fetch_unolo_distance
from integrations.vision_ai import scan_receipts
from utils.db import get_db
from utils.llm import validate_api_key
from utils.auth import (
    init_auth_db,
    migrate_auth_db,
    sync_admin_flags,
    get_user_by_session,
    logout_session,
    update_user as _auth_update_user,
    register_user as _auth_register,
    complete_oauth_registration as _auth_complete_oauth,
    login_password as _auth_login_password,
    send_email_otp as _auth_send_email_otp,
    login_email_otp as _auth_login_email_otp,
    send_phone_otp as _auth_send_phone_otp,
    login_phone_otp as _auth_login_phone_otp,
    google_auth_url as _auth_google_url,
    google_callback as _auth_google_callback,
    zoho_auth_url as _auth_zoho_url,
    zoho_callback as _auth_zoho_callback,
)


# ── PDF helpers ───────────────────────────────────────────────────────────────

def _sanitize_for_pdf(text: str) -> str:
    """Replace Unicode characters unsupported by core PDF fonts with ASCII equivalents."""
    replacements = {
        "₹": "Rs", "\u20b9": "Rs",
        "─": "-", "━": "-", "═": "=", "╌": "-", "╍": "-",
        "│": "|", "┃": "|", "║": "|",
        "┌": "+", "┐": "+", "└": "+", "┘": "+",
        "├": "+", "┤": "+", "┬": "+", "┴": "+", "┼": "+",
        "╔": "+", "╗": "+", "╚": "+", "╝": "+",
        "╠": "+", "╣": "+", "╦": "+", "╩": "+", "╬": "+",
        "•": "*", "·": ".", "◦": "o",
        "→": "->", "←": "<-", "↑": "^", "↓": "v",
        "✓": "OK", "✗": "X", "✘": "X",
        "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "--",
        "\u2026": "...",
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def build_pdf_report(report_text: str, title: str = "Rite Audit System Report") -> bytes:
    """Generate a PDF using fpdf2 with proper Unicode and auto page breaks."""
    from fpdf import FPDF

    safe_text  = _sanitize_for_pdf(report_text)
    safe_title = _sanitize_for_pdf(title)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, safe_title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(200, 200, 200)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)

    pdf.set_font("Helvetica", size=10)
    pdf.multi_cell(0, 5.5, safe_text)

    return bytes(pdf.output())


def _cleanup_temp_files(image_paths: list[str]) -> None:
    """Delete uploaded temp files after the pipeline completes."""
    for path in image_paths:
        try:
            os.remove(path)
        except OSError:
            pass
    try:
        os.rmdir("temp_uploads")
    except OSError:
        pass


# ── Vision scan disk cache ─────────────────────────────────────────────────────
# Survives laptop sleep / WebSocket reconnects.  Cache is keyed by a SHA-256
# hash of all uploaded file bytes, stored as JSON in temp_uploads/.scan_cache/

import hashlib, json as _json

_SCAN_CACHE_DIR = os.path.join("temp_uploads", ".scan_cache")


def _vision_cache_key(image_paths: list[str]) -> str:
    h = hashlib.sha256()
    for p in sorted(image_paths):          # sorted so order doesn't matter
        try:
            with open(p, "rb") as f:
                h.update(f.read())
        except OSError:
            h.update(p.encode())
    return h.hexdigest()


def _load_vision_cache(key: str):
    path = os.path.join(_SCAN_CACHE_DIR, f"{key}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return _json.load(f)
    except (OSError, _json.JSONDecodeError):
        return None


def _save_vision_cache(key: str, result: dict) -> None:
    os.makedirs(_SCAN_CACHE_DIR, exist_ok=True)
    path = os.path.join(_SCAN_CACHE_DIR, f"{key}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(result, f)
    except OSError:
        pass


def _delete_vision_cache(key: str) -> None:
    path = os.path.join(_SCAN_CACHE_DIR, f"{key}.json")
    try:
        os.remove(path)
    except OSError:
        pass


# ── Theme CSS ─────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def _theme_css(theme: str) -> str:
    """
    Return theme-specific CSS overrides.

    config.toml sets base="dark" so the loading screen and native Streamlit
    widgets (inputs, file uploader, expanders) are dark by default — no flash
    for dark-theme users.

    Dark  — only needs app-shell gradient + custom HTML elements.
            Native widgets are already correct from config.toml.
    Light — must explicitly override EVERY native widget to light colours
            (fighting config.toml's dark defaults).
    """

    dark = """
        /* ── App shell ────────────────────────────────────────────── */
        .stApp {
            background:
                radial-gradient(circle at top right, rgba(0,175,239,0.18), transparent 30%),
                radial-gradient(circle at bottom left, rgba(3,57,108,0.40), transparent 40%),
                linear-gradient(180deg, #040e1f 0%, #061525 100%) !important;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #030d1e 0%, #051222 100%) !important;
            border-right: 1px solid rgba(0,175,239,0.12) !important;
        }
        [data-testid="stHeader"] {
            background: rgba(12,16,24,0.82) !important;
            backdrop-filter: blur(8px) !important;
        }

        /* ── Custom HTML elements ──────────────────────────────────── */
        .hero-card {
            background: linear-gradient(135deg, rgba(255,255,255,0.06), rgba(255,255,255,0.03));
            border: 1px solid rgba(255,255,255,0.08);
            box-shadow: 0 24px 70px rgba(0,0,0,0.28);
        }
        .hero-title  { color: #f7f4ed; }
        .hero-kicker { color: #00AFEF; }
        .hero-copy   { color: #cdd6e3; }
        .section-card {
            background: rgba(12,18,29,0.86);
            border: 1px solid rgba(255,255,255,0.08);
            box-shadow: 0 18px 48px rgba(0,0,0,0.24);
        }
        .section-label { color: #9cc2ff; }
        .step-card {
            background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
            border: 1px solid rgba(255,255,255,0.08);
        }
        .step-num  { color: #00AFEF; }
        .step-copy { color: #cbd5e1; }
        .reasoning-card, .report-card {
            background: rgba(12,18,29,0.92);
            border: 1px solid rgba(255,255,255,0.08);
            box-shadow: 0 18px 48px rgba(0,0,0,0.24);
        }
        .summary-chip { background: rgba(255,255,255,0.08); color: #dce7f7; }
        .policy-mini  { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.07); }
        .policy-mini strong { color: #f8fafc; }
        div[data-testid="stMetric"] {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.06);
        }
        .stDownloadButton button {
            background: rgba(255,255,255,0.05) !important;
            color: #f8fafc !important;
            border: 1px solid rgba(255,255,255,0.08) !important;
        }
        [data-testid="stBaseButton-secondary"] {
            background: rgba(0,175,239,0.10) !important;
            color: #29c0f0 !important;
            border: 1px solid rgba(0,175,239,0.30) !important;
        }
        [data-testid="stBaseButton-secondary"]:hover {
            background: rgba(0,175,239,0.20) !important;
            border-color: rgba(0,175,239,0.55) !important;
            color: #7ddff8 !important;
        }
        .report-pre {
            background: rgba(0,0,0,0.38) !important;
            color: #cdd9e5 !important;
            border: 1px solid rgba(255,255,255,0.07) !important;
        }
        .rpt-header-bar {
            border-color: rgba(255,255,255,0.08) !important;
        }
        .rpt-company { color: #9ca3af; }
        .rpt-doc-label { color: #f1f5f9; }
        .rpt-block-title { color: #7eb3ff; }
        .rpt-kv td { color: #dce7f7; }
        .rpt-kv td:first-child { color: #8fa8c8; }
        .rpt-kv code { background: rgba(255,255,255,0.07); color: #f1c97a; }
        .rpt-body {
            border-color: rgba(255,255,255,0.08) !important;
        }
        .rpt-table th { color: #8fa8c8; border-bottom: 1px solid rgba(255,255,255,0.07); }
        .rpt-table td { color: #dce7f7; border-bottom: 1px solid rgba(255,255,255,0.05); }
        .rpt-td-ok { color: #4ade80 !important; font-weight: 600; }
        .rpt-td-reduced { color: #fbbf24 !important; font-weight: 600; }
        .rpt-capped { background: rgba(251,191,36,0.15); color: #fbbf24; }

        /* ── Dialog (st.dialog modal) ──────────────────────────────── */
        /* Backdrop: blur the dark page behind */
        [data-baseweb="modal"] > div {
            background:              rgba(2,8,20,0.60) !important;
            backdrop-filter:         blur(8px) !important;
            -webkit-backdrop-filter: blur(8px) !important;
        }
        /* Dialog box itself */
        [role="dialog"],
        [role="dialog"] > div,
        [data-testid="stDialogContent"] {
            background-color: #0c1829 !important;
            background:       #0c1829 !important;
            border:           1px solid rgba(255,255,255,0.08) !important;
            border-radius:    20px !important;
        }

        /* ── Popover trigger button ────────────────────────────────── */
        [data-testid="stPopover"] button,
        [data-testid="stPopover"] > div > button,
        [data-testid="stPopover"] > button {
            background:       #0c1e38 !important;
            background-color: #0c1e38 !important;
            color:            #d1dae8 !important;
            border:           1px solid rgba(255,255,255,0.18) !important;
            box-shadow:       none !important;
            min-height:       2.4rem !important;
            font-size:        0.92rem !important;
        }
        [data-testid="stPopover"] button:hover {
            background:       #122240 !important;
            background-color: #122240 !important;
            color:            #f7f4ed !important;
        }

        /* ── Top-nav active page button ─────────────────────────────── */
        #topnav_submit [data-testid="stBaseButton-secondary"],
        #topnav_admin [data-testid="stBaseButton-secondary"],
        #topnav_profile [data-testid="stBaseButton-secondary"] {
            transition: background 0.15s, border-color 0.15s;
        }

        /* ── Top-nav: all 5 buttons uniform height & font ──────────── */
        #topnav_submit button,
        #topnav_admin button,
        #topnav_profile button,
        #topnav_signout button,
        [data-testid="stPopover"] button {
            height: 38px !important;
            min-height: 38px !important;
            max-height: 38px !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            font-size: 0.875rem !important;
            width: 100% !important;
            box-sizing: border-box !important;
        }

        /* ── Portal overlays (calendar, tooltip, dropdowns) — dark ─── */
        /* Mirror of light section so dark mode wins regardless of any
           CSS bleed when themes are switched without full page reload.  */
        [data-layer="true"],
        [data-layer="true"] * {
            background-color: #071629 !important;
            background:       #071629 !important;
            color:            #f7f4ed !important;
        }
        [data-baseweb="calendar"] button {
            background-color: transparent !important;
            background:       transparent !important;
            color:            #e2e8f0 !important;
            border:           none !important;
        }
        [data-baseweb="calendar"] button:hover {
            background-color: rgba(255,255,255,0.08) !important;
            background:       rgba(255,255,255,0.08) !important;
        }
        [data-baseweb="calendar"] [aria-selected="true"],
        [data-baseweb="calendar"] [aria-selected="true"] * {
            background-color: #00AFEF !important;
            background:       #00AFEF !important;
            color:            #ffffff !important;
        }
        [data-baseweb="calendar"] [role="columnheader"],
        [data-baseweb="calendar"] [role="columnheader"] * {
            color: rgba(255,255,255,0.45) !important;
        }
        [data-baseweb="calendar"] select {
            background-color: rgba(255,255,255,0.08) !important;
            color:            #e2e8f0 !important;
        }
        [data-layer="true"] [role="option"]:hover,
        [data-layer="true"] [data-baseweb="menu-item"]:hover {
            background-color: rgba(255,255,255,0.08) !important;
            background:       rgba(255,255,255,0.08) !important;
        }
        [data-layer="true"] [role="option"][aria-selected="true"],
        [data-layer="true"] [data-baseweb="menu-item"][aria-selected="true"] {
            background-color: rgba(0,175,239,0.20) !important;
            background:       rgba(0,175,239,0.20) !important;
            color:            #29c0f0 !important;
        }
    """

    light = """

        /* ════════════════════════════════════════════════════════════
           LIGHT MODE — full rewrite.
           config.toml sets base="dark" so every Streamlit widget
           defaults dark. Every rule here must use !important to win.
           ════════════════════════════════════════════════════════════ */

        /* ── 1. APP SHELL ─────────────────────────────────────────── */
        html, body {
            background-color: #f0f7ff !important;
            color: #061525 !important;
        }
        .stApp, [data-testid="stAppViewContainer"] {
            background: linear-gradient(160deg, #f0f7ff 0%, #daf0fb 100%) !important;
            color: #061525 !important;
        }
        [data-testid="stMain"], [data-testid="stMainBlockContainer"],
        [data-testid="block-container"] {
            background: transparent !important;
            color: #061525 !important;
        }
        [data-testid="stSidebar"], [data-testid="stSidebar"] > div {
            background: linear-gradient(180deg, #f0f7ff 0%, #e4f3fc 100%) !important;
            border-right: 1px solid rgba(0,175,239,0.15) !important;
        }
        [data-testid="stSidebar"] * { color: #061525 !important; }
        [data-testid="stHeader"] {
            background: rgba(240,247,255,0.92) !important;
            backdrop-filter: blur(8px) !important;
        }
        [data-testid="stToolbar"], [data-testid="stDecoration"] {
            background: transparent !important;
        }

        /* ── 2. TYPOGRAPHY ────────────────────────────────────────── */
        .stApp *, .stMarkdown * {
            color: #061525;
        }
        h1, h2, h3, h4, h5, h6 { color: #0f172a !important; }
        p, li, span { color: #061525 !important; }
        label, .stWidgetLabel, [data-testid="stWidgetLabel"] {
            color: #374151 !important;
        }
        label p { color: #374151 !important; }
        small, .stCaption, [data-testid="stCaptionContainer"] p {
            color: #6b7280 !important;
        }
        code { background: #f1f5f9 !important; color: #1e3a5f !important; }
        [data-testid="stCode"],
        [data-testid="stCode"] pre,
        [data-testid="stCode"] code,
        [data-testid="stCodeBlock"],
        [data-testid="stCodeBlock"] pre,
        [data-testid="stCodeBlock"] code {
            background-color: #f1f5f9 !important;
            background:       #f1f5f9 !important;
            color:            #1e3a5f !important;
            border:           1px solid rgba(0,0,0,0.08) !important;
        }
        a { color: #2563eb !important; }

        /* ── 3. TEXT INPUTS ───────────────────────────────────────── */
        [data-baseweb="base-input"],
        [data-baseweb="input"],
        [data-baseweb="input"] > div,
        [data-testid="stTextInput"] > div,
        [data-testid="stNumberInput"] > div > div,
        [data-testid="stDateInput"] > div > div {
            background-color: #ffffff !important;
            background:       #ffffff !important;
            border-color:     rgba(0,0,0,0.20) !important;
        }
        input,
        [data-baseweb="input"] input,
        [data-baseweb="base-input"] input,
        [data-testid="stTextInput"] input,
        [data-testid="stNumberInput"] input,
        [data-testid="stDateInput"] input {
            background-color: transparent !important;
            color:            #061525 !important;
            caret-color:      #000000 !important;
            -webkit-text-fill-color: #061525 !important;
        }
        input::placeholder { color: rgba(17,24,39,0.35) !important; }
        /* Browser autofill — Chrome ignores color; must use fill-color + inset shadow */
        input:-webkit-autofill,
        input:-webkit-autofill:hover,
        input:-webkit-autofill:focus,
        input:-webkit-autofill:active {
            -webkit-text-fill-color: #061525 !important;
            -webkit-box-shadow: 0 0 0px 1000px #ffffff inset !important;
            box-shadow:         0 0 0px 1000px #ffffff inset !important;
            caret-color: #000000 !important;
            transition: background-color 5000s ease-in-out 0s;
        }

        /* ── 4. TEXTAREA ──────────────────────────────────────────── */
        [data-baseweb="textarea"],
        [data-baseweb="textarea"] > div,
        [data-testid="stTextArea"] > div {
            background-color: #ffffff !important;
            background:       #ffffff !important;
            border-color:     rgba(0,0,0,0.20) !important;
        }
        textarea,
        [data-baseweb="textarea"] textarea,
        [data-testid="stTextArea"] textarea {
            background-color: transparent !important;
            color:            #061525 !important;
            caret-color:      #000000 !important;
            -webkit-text-fill-color: #061525 !important;
        }
        textarea::placeholder { color: rgba(17,24,39,0.35) !important; }
        textarea:-webkit-autofill { -webkit-text-fill-color: #061525 !important; }

        /* ── 5. SELECT / MULTISELECT (inline box) ─────────────────── */
        [data-baseweb="select"],
        [data-baseweb="select"] > div,
        [data-baseweb="select"] [data-baseweb="input"],
        [data-testid="stSelectbox"] > div > div,
        [data-testid="stMultiSelect"] > div > div {
            background-color: #ffffff !important;
            background:       #ffffff !important;
            border-color:     rgba(0,0,0,0.20) !important;
            color:            #061525 !important;
        }
        [data-baseweb="select"] span,
        [data-baseweb="select"] input { color: #061525 !important; }
        /* Selected tag chips in multiselect */
        [data-baseweb="tag"] {
            background-color: #deeeff !important;
            color:            #061525 !important;
        }

        /* ── 6. BUTTONS ───────────────────────────────────────────── */
        .stButton > button {
            background-color: #f3f4f6 !important;
            color:            #061525 !important;
            border:           1px solid rgba(0,0,0,0.14) !important;
        }
        .stButton > button:hover {
            background-color: #e5e7eb !important;
            color:            #0f172a !important;
        }
        [data-testid="stBaseButton-primary"],
        [data-testid="stBaseButton-primary"]:hover {
            background-color: #00AFEF !important;
            color:            #ffffff !important;
            border:           none !important;
        }
        [data-testid="stBaseButton-secondary"] {
            background: rgba(0,175,239,0.08) !important;
            color: #0080bb !important;
            border: 1px solid rgba(0,175,239,0.38) !important;
        }
        [data-testid="stBaseButton-secondary"]:hover {
            background: rgba(0,175,239,0.16) !important;
            border-color: rgba(0,175,239,0.58) !important;
            color: #006fa3 !important;
        }
        .stDownloadButton button {
            background-color: #f3f4f6 !important;
            color:            #061525 !important;
            border:           1px solid rgba(0,0,0,0.12) !important;
        }
        .stNumberInput button {
            background-color: #f3f4f6 !important;
            color:            #374151 !important;
            border-color:     rgba(0,0,0,0.14) !important;
        }

        /* ── 7. FILE UPLOADER ─────────────────────────────────────── */
        [data-testid="stFileUploader"],
        [data-testid="stFileUploader"] > div,
        [data-testid="stFileUploader"] section,
        [data-testid="stFileUploaderDropzone"],
        [data-testid="stFileUploaderDropzone"] > div,
        [data-testid="stFileUploaderDropzone"] > div > div {
            background:       #f8fafc !important;
            background-color: #f8fafc !important;
        }
        [data-testid="stFileUploaderDropzone"] {
            border: 1.5px dashed rgba(37,99,235,0.40) !important;
        }
        /* Force ALL elements inside the uploader to light —
           this covers the uploaded-file preview cards which have
           their own dark background set by the BaseUI dark theme */
        [data-testid="stFileUploader"] *,
        [data-testid="stFileUploaderFileData"],
        [data-testid="stFileUploaderFileData"] *,
        [data-testid="stUploadedFile"],
        [data-testid="stUploadedFile"] * {
            background-color: #f0f7ff !important;
            background:       #f0f7ff !important;
            color:            #374151 !important;
        }
        /* Restore white for the dropzone button and icons */
        [data-testid="stFileUploader"] button {
            background:       #ffffff !important;
            background-color: #ffffff !important;
            color:            #374151 !important;
            border:           1px solid rgba(0,0,0,0.15) !important;
        }
        [data-testid="stFileUploader"] svg {
            background: transparent !important;
        }

        /* ── 8. EXPANDERS ─────────────────────────────────────────── */
        [data-testid="stExpander"],
        [data-testid="stExpander"] > div,
        [data-testid="stExpander"] details,
        [data-testid="stExpander"] details > div,
        [data-testid="stExpander"] [data-baseweb="accordion"],
        [data-testid="stExpander"] [data-baseweb="accordion"] > div,
        [data-testid="stExpander"] [data-baseweb="accordion"] > div > div,
        [data-testid="stExpanderDetails"],
        [data-testid="stExpanderDetails"] > div,
        [data-testid="stExpanderDetails"] > div > div {
            background:       #ffffff !important;
            background-color: #ffffff !important;
            border-radius: 12px !important;
        }
        [data-testid="stExpander"] {
            border: 1px solid rgba(0,0,0,0.08) !important;
        }
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] button,
        [data-testid="stExpander"] button:hover,
        [data-testid="stExpander"] button:active,
        [data-testid="stExpander"] button:focus,
        [data-testid="stExpander"] button:focus-visible {
            background:       #ffffff !important;
            background-color: #ffffff !important;
            outline: none !important;
            box-shadow: none !important;
        }
        [data-testid="stExpander"] summary * { color: #061525 !important; }
        [data-testid="stExpander"] [data-testid="stExpanderDetails"] * {
            color: #374151 !important;
        }

        /* ── 9. CHECKBOXES & RADIO BUTTONS ───────────────────────── */
        [data-testid="stCheckbox"] label span,
        [data-testid="stRadio"] label span { color: #061525 !important; }
        [data-baseweb="checkbox"] div,
        [data-baseweb="radio"] div { border-color: rgba(0,0,0,0.30) !important; }

        /* ── 10. SLIDER ───────────────────────────────────────────── */
        [data-testid="stSlider"] * { color: #061525 !important; }
        [data-testid="stSlider"] [role="slider"] {
            background: #00AFEF !important;
            border-color: #00AFEF !important;
        }

        /* ── 11. TABS ─────────────────────────────────────────────── */
        [data-testid="stTabs"] [role="tablist"] {
            border-bottom: 2px solid rgba(0,0,0,0.10) !important;
        }
        [data-testid="stTabs"] button[role="tab"] {
            color: #6b7280 !important;
            background: transparent !important;
        }
        [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            color: #00AFEF !important;
            border-bottom-color: #00AFEF !important;
        }

        /* ── 12. METRICS ──────────────────────────────────────────── */
        div[data-testid="stMetric"] {
            background: rgba(0,0,0,0.03) !important;
            border: 1px solid rgba(0,0,0,0.07) !important;
        }
        [data-testid="stMetricLabel"] p { color: #6b7280 !important; }
        [data-testid="stMetricValue"]   { color: #0f172a !important; }
        [data-testid="stMetricDelta"] * { color: #374151 !important; }

        /* ── 13. ALERTS / INFO BOXES ──────────────────────────────── */
        [data-testid="stAlert"] { color: #061525 !important; }
        [data-testid="stAlert"] * { color: #061525 !important; }

        /* ── 14. PROGRESS BAR ─────────────────────────────────────── */
        [data-testid="stProgressBar"] > div { background: #e5e7eb !important; }

        /* ── 15. POPOVER TRIGGER BUTTON ───────────────────────────── */
        [data-testid="stPopover"] button,
        [data-testid="stPopover"] > div > button {
            background:       #ffffff !important;
            background-color: #ffffff !important;
            color:            #374151 !important;
            border:           1px solid rgba(0,0,0,0.14) !important;
            box-shadow:       0 1px 4px rgba(0,0,0,0.08) !important;
        }
        [data-testid="stPopover"] button:hover {
            background: #f3f4f6 !important; color: #061525 !important;
        }

        /* ── 16. POPOVER BODY (st.popover content) ────────────────── */
        [data-testid="stPopoverBody"],
        [data-testid="stPopoverBody"] > div,
        [data-testid="stPopoverBody"] > div > div {
            background:       #ffffff !important;
            background-color: #ffffff !important;
            border:           1px solid rgba(0,0,0,0.10) !important;
            box-shadow:       0 4px 16px rgba(0,0,0,0.12) !important;
        }
        [data-testid="stPopoverBody"] * { color: #061525 !important; }

        /* ══════════════════════════════════════════════════════════════
           17. PORTAL OVERLAYS
           BaseUI portals every floating element (calendar, dropdown,
           tooltip) as a direct child of <body>. The wrapper attribute
           varies by Streamlit/BaseUI version — [data-layer="true"],
           [data-layer], [data-baseweb="layer"], or a plain div.

           Strategy: use CSS :has() to target the portal wrapper
           by what it CONTAINS rather than its own attributes. This
           works regardless of version. Fallback [data-layer] rules
           cover older browsers.
           ══════════════════════════════════════════════════════════════ */

        /* ── Nuclear base: portal wrapper + every descendant → white ── */
        /* :has() targets the direct <body> child that contains
           the calendar / dropdown / tooltip, no matter its attributes */
        body > div:has([data-baseweb="calendar"]),
        body > div:has([data-baseweb="calendar"]) *,
        body > div:has([role="listbox"]),
        body > div:has([role="listbox"]) *,
        body > div:has([data-baseweb="menu"]),
        body > div:has([data-baseweb="menu"]) *,
        body > div:has([data-baseweb="tooltip"]),
        body > div:has([data-baseweb="tooltip"]) *,
        body > div:has([data-baseweb="popover"]),
        body > div:has([data-baseweb="popover"]) * {
            background-color: #ffffff !important;
            background:       #ffffff !important;
            color:            #061525 !important;
        }
        /* Fallback for older browsers that don't support :has() */
        [data-layer="true"],  [data-layer="true"] *,
        [data-layer],         [data-layer] *,
        [data-baseweb="layer"],[data-baseweb="layer"] * {
            background-color: #ffffff !important;
            background:       #ffffff !important;
            color:            #061525 !important;
        }

        /* ── Floating card polish ──────────────────────────────────── */
        [data-baseweb="popover"] > div,
        [data-baseweb="tooltip"] > div {
            border:        1px solid rgba(0,0,0,0.10) !important;
            box-shadow:    0 6px 20px rgba(0,0,0,0.12) !important;
            border-radius: 10px !important;
        }

        /* ── Calendar: day buttons transparent → white parent shows ── */
        [data-baseweb="calendar"] button {
            background-color: transparent !important;
            background:       transparent !important;
            color:            #061525 !important;
            border:           none !important;
        }
        [data-baseweb="calendar"] button:hover {
            background-color: #deeeff !important;
            background:       #deeeff !important;
        }
        /* Selected date — orange pill */
        [data-baseweb="calendar"] [aria-selected="true"],
        [data-baseweb="calendar"] [aria-selected="true"] * {
            background-color: #00AFEF !important;
            background:       #00AFEF !important;
            color:            #ffffff !important;
        }
        /* Day-of-week column headers */
        [data-baseweb="calendar"] [role="columnheader"],
        [data-baseweb="calendar"] [role="columnheader"] * {
            color: #9ca3af !important;
        }
        /* Month / year native selects */
        [data-baseweb="calendar"] select,
        body > div:has([data-baseweb="calendar"]) select {
            background-color: #f3f4f6 !important;
            color:            #061525 !important;
            border-color:     rgba(0,0,0,0.15) !important;
        }

        /* ── Dropdown list option hover / selected states ──────────── */
        body > div:has([role="listbox"]) [role="option"]:hover,
        body > div:has([data-baseweb="menu"]) [data-baseweb="menu-item"]:hover,
        [data-layer] [role="option"]:hover {
            background-color: #deeeff !important;
            background:       #deeeff !important;
        }
        body > div:has([role="listbox"]) [role="option"][aria-selected="true"],
        body > div:has([data-baseweb="menu"]) [data-baseweb="menu-item"][aria-selected="true"],
        [data-layer] [role="option"][aria-selected="true"] {
            background-color: rgba(0,175,239,0.12) !important;
            background:       rgba(0,175,239,0.12) !important;
            color:            #0090cc !important;
        }

        /* ── 19. DIALOG — light theme, blurred backdrop ─────────────── */
        /* Backdrop */
        [data-baseweb="modal"] > div {
            background:              rgba(100,120,150,0.35) !important;
            backdrop-filter:         blur(8px) !important;
            -webkit-backdrop-filter: blur(8px) !important;
        }
        /* Dialog box */
        [role="dialog"],
        [role="dialog"] > div,
        [data-testid="stDialogContent"] {
            background-color: #ffffff !important;
            background:       #ffffff !important;
            border:           1px solid rgba(0,0,0,0.08) !important;
            border-radius:    20px !important;
            box-shadow:       0 8px 32px rgba(0,0,0,0.12) !important;
            color:            #0f172a !important;
        }
        [data-testid="stDialog"] *,
        [data-testid="stDialogContent"] * {
            color: #0f172a !important;
        }
        /* Close button */
        [data-testid="stDialog"] [data-testid="stBaseButton-headerNoPadding"],
        [data-testid="stDialog"] [data-testid="stBaseButton-headerNoPadding"] * {
            color: #6b7280 !important;
            background: transparent !important;
        }
        /* Primary button — let gradient apply */
        [data-testid="stDialog"] [data-testid="stBaseButton-primary"] {
            color: #ffffff !important;
        }
        /* Secondary (Cancel) button */
        [data-testid="stDialog"] [data-testid="stBaseButton-secondary"] {
            background: #f3f4f6 !important;
            color:      #374151 !important;
            border:     1px solid rgba(0,0,0,0.12) !important;
        }
        [data-testid="stDialog"] [data-testid="stBaseButton-secondary"]:hover {
            background: #e5e7eb !important;
        }
        /* Input fields */
        [data-testid="stDialog"] input {
            background-color:        #ffffff !important;
            color:                   #0f172a !important;
            -webkit-text-fill-color: #0f172a !important;
            caret-color:             #000000 !important;
        }
        [data-testid="stDialog"] [data-baseweb="base-input"],
        [data-testid="stDialog"] [data-baseweb="input"],
        [data-testid="stDialog"] [data-baseweb="input"] > div {
            background-color: #ffffff !important;
            background:       #ffffff !important;
            border-color:     rgba(0,0,0,0.20) !important;
        }
        [data-testid="stDialog"] input::placeholder {
            color: rgba(0,0,0,0.35) !important;
        }
        [data-testid="stDialog"] label,
        [data-testid="stDialog"] [data-testid="stWidgetLabel"] * {
            color: #374151 !important;
        }

        /* ── 18. CUSTOM HTML CARDS ────────────────────────────────── */
        .hero-card {
            background: rgba(255,255,255,0.95);
            border: 1px solid rgba(0,0,0,0.08);
            box-shadow: 0 4px 24px rgba(0,0,0,0.08);
        }
        .hero-title  { color: #0f172a; }
        .hero-kicker { color: #0090cc; }
        .hero-copy   { color: #4b5868; }
        .section-card {
            background: #ffffff;
            border: 1px solid rgba(0,0,0,0.08);
            box-shadow: 0 4px 16px rgba(0,0,0,0.06);
        }
        .section-label { color: #2563eb; }
        .step-card { background: #ffffff; border: 1px solid rgba(0,0,0,0.08); }
        .step-num  { color: #0090cc; }
        .step-copy { color: #4b5868; }
        .reasoning-card, .report-card {
            background: #ffffff;
            border: 1px solid rgba(0,0,0,0.08);
            box-shadow: 0 4px 16px rgba(0,0,0,0.06);
        }
        .summary-chip { background: rgba(0,0,0,0.06); color: #061525; }
        .policy-mini  { background: rgba(0,0,0,0.02); border: 1px solid rgba(0,0,0,0.07); }
        .policy-mini strong { color: #061525; }
        .report-pre {
            background: #f5f0e8 !important;
            color: #1f2937 !important;
            border: 1px solid rgba(0,0,0,0.09) !important;
        }
        .rpt-header-bar {
            border-color: rgba(0,0,0,0.10) !important;
            background: linear-gradient(135deg,rgba(0,175,239,0.09) 0%,rgba(97,206,112,0.06) 100%) !important;
        }
        .rpt-company { color: #6b7280; }
        .rpt-doc-label { color: #0f172a; }
        .rpt-block-title { color: #2563eb; }
        .rpt-kv td { color: #1f2937; }
        .rpt-kv td:first-child { color: #6b7280; }
        .rpt-kv code { background: #f1f5f9; color: #1e3a5f; }
        .rpt-body {
            border-color: rgba(0,0,0,0.10) !important;
        }
        .rpt-table th { color: #6b7280; border-bottom: 1px solid rgba(0,0,0,0.08); }
        .rpt-table td { color: #1f2937; border-bottom: 1px solid rgba(0,0,0,0.05); }
        .rpt-td-ok { color: #16a34a !important; font-weight: 600; }
        .rpt-td-reduced { color: #d97706 !important; font-weight: 600; }
        .rpt-capped { background: rgba(217,119,6,0.12); color: #b45309; }
    """

    system = f"""
        @media (prefers-color-scheme: dark)  {{ {dark} }}
        @media (prefers-color-scheme: light) {{ {light} }}
    """

    return {"Dark": dark, "Light": light, "System": system}.get(theme, dark)


# ── Style injection ───────────────────────────────────────────────────────────

def inject_loading_theme() -> None:
    """
    Apply theme background and inject calendar portal CSS.
    Theme is read directly from session state (Python) so it's always correct.
    """
    theme    = st.session_state.get("theme", "Dark")
    dark_bg  = "#040e1f"
    light_bg = "#f0f7ff"
    bg       = light_bg if theme == "Light" else dark_bg

    # NOTE: st.markdown() uses React dangerouslySetInnerHTML which does NOT
    # execute <script> tags, so the JS below never runs.  All portal/overlay
    # CSS is applied via inject_styles() → _theme_css() instead.
    # light_cal_css is kept here only as a reference mirror of that CSS.
    light_cal_css = """
        [data-layer="true"], [data-layer="true"] * {
            background-color: #ffffff !important;
            background: #ffffff !important;
            color: #1a2332 !important;
        }
        [data-baseweb="calendar"] button {
            background-color: transparent !important; background: transparent !important;
            border: none !important;
        }
        [data-baseweb="calendar"] button:hover {
            background-color: #deeeff !important;
        }
        [data-baseweb="calendar"] [aria-selected="true"],
        [data-baseweb="calendar"] [aria-selected="true"] * {
            background-color: #00AFEF !important; background: #00AFEF !important;
            color: #ffffff !important;
        }
        [data-layer="true"] [role="option"]:hover { background-color: #deeeff !important; }
        [data-layer="true"] [role="option"][aria-selected="true"] {
            background-color: rgba(0,175,239,0.12) !important; color: #0090cc !important;
        }
    """ if theme == "Light" else ""

    is_light = "true" if theme == "Light" else "false"

    st.markdown(
        f"""
        <script>
        (function(){{
            try {{
                // ── Background colour ────────────────────────────────────────
                document.documentElement.style.backgroundColor = '{bg}';
                if (document.body) document.body.style.backgroundColor = '{bg}';

                // ── <head> CSS (covers hover via pseudo-selector) ────────────
                var sid = 'cr-cal-fix';
                var s = document.getElementById(sid);
                if (!s) {{ s = document.createElement('style'); s.id = sid; document.head.appendChild(s); }}
                s.textContent = `{light_cal_css}`;

                // ── MutationObserver ─────────────────────────────────────────
                // Always disconnect + recreate so isLight closure is always current.
                // Bug if guarded with `if (!_crCalObs)`: observer created in Dark mode
                // captures isLight=false; switching to Light skips the block entirely.
                if (window._crCalObs) {{ window._crCalObs.disconnect(); window._crCalObs = null; }}

                var isLight = {is_light};
                if (!isLight) return;   // nothing to do in dark mode

                var _t = null;

                function sp(el, p, v) {{ el.style.setProperty(p, v, 'important'); }}

                function applyLight() {{
                    _t = null;

                    // ── Calendar date-grid ───────────────────────────────────
                    document.querySelectorAll('[data-baseweb="calendar"]').forEach(function(cal) {{

                        // Walk UP from calendar to body, whitening every ancestor.
                        // Necessary because the portal wrapper div (which sits directly
                        // under <body>) and [data-baseweb="layer"] / [data-baseweb="popover"]
                        // all inherit Streamlit's dark base theme and must be overridden.
                        var anc = cal.parentElement;
                        while (anc && anc !== document.body) {{
                            sp(anc, 'background-color', '#ffffff');
                            sp(anc, 'background',       '#ffffff');
                            sp(anc, 'color',            '#1a2332');
                            anc = anc.parentElement;
                        }}

                        // Calendar container itself
                        sp(cal, 'background-color', '#ffffff');
                        sp(cal, 'background',       '#ffffff');
                        sp(cal, 'color',            '#1a2332');

                        // Every element inside the calendar
                        cal.querySelectorAll('*').forEach(function(el) {{
                            var ariaSel = el.getAttribute('aria-selected');
                            var role    = el.getAttribute('role');
                            if (ariaSel === 'true') {{
                                // Selected date — orange highlight
                                sp(el, 'background-color', '#00AFEF');
                                sp(el, 'background',       '#00AFEF');
                                sp(el, 'color',            '#ffffff');
                            }} else if (role === 'columnheader') {{
                                // Su Mo Tu We Th Fr Sa headers
                                sp(el, 'background-color', '#ffffff');
                                sp(el, 'background',       '#ffffff');
                                sp(el, 'color',            '#9ca3af');
                            }} else if (el.tagName === 'BUTTON') {{
                                // Nav arrows + day cells
                                sp(el, 'background-color', 'transparent');
                                sp(el, 'background',       'transparent');
                                sp(el, 'color',            '#1a2332');
                                el.onmouseenter = function() {{ sp(this, 'background-color', '#deeeff'); }};
                                el.onmouseleave = function() {{ sp(this, 'background-color', 'transparent'); }};
                            }} else if (el.tagName === 'SELECT') {{
                                // Month / year native selects
                                sp(el, 'background-color', '#f3f4f6');
                                sp(el, 'color',            '#1a2332');
                            }} else {{
                                sp(el, 'background-color', '#ffffff');
                                sp(el, 'background',       '#ffffff');
                                sp(el, 'color',            '#1a2332');
                            }}
                        }});
                    }});

                    // ── Month / year dropdown listboxes (separate portal) ────
                    document.querySelectorAll('[role="listbox"]').forEach(function(lb) {{
                        var anc = lb.parentElement;
                        while (anc && anc !== document.body) {{
                            sp(anc, 'background-color', '#ffffff');
                            sp(anc, 'background',       '#ffffff');
                            anc = anc.parentElement;
                        }}
                        sp(lb, 'background-color', '#ffffff');
                        sp(lb, 'background',       '#ffffff');
                        sp(lb, 'color',            '#1a2332');
                        lb.querySelectorAll('[role="option"]').forEach(function(opt) {{
                            if (opt.getAttribute('aria-selected') === 'true') {{
                                sp(opt, 'background-color', 'rgba(0,175,239,0.12)');
                                sp(opt, 'color',            '#0090cc');
                            }} else {{
                                sp(opt, 'background-color', '#ffffff');
                                sp(opt, 'color',            '#1a2332');
                                opt.onmouseenter = function() {{ sp(this, 'background-color', '#deeeff'); }};
                                opt.onmouseleave = function() {{ sp(this, 'background-color', '#ffffff'); }};
                            }}
                        }});
                    }});
                }}

                // Observe ANY child-list change anywhere in body.
                // On each change: debounce 80 ms, then run applyLight().
                // We deliberately do NOT inspect individual added nodes here — doing so
                // causes the "empty shell" timing bug where the calendar container is
                // found before React has rendered its children into it.
                window._crCalObs = new MutationObserver(function() {{
                    if (_t) clearTimeout(_t);
                    _t = setTimeout(applyLight, 80);
                }});
                window._crCalObs.observe(document.body, {{ childList: true, subtree: true }});

            }} catch(e) {{}}
        }})();
        </script>
        """,
        unsafe_allow_html=True,
    )



def inject_styles() -> None:
    theme = st.session_state.get("theme", "Dark")
    # Persist theme in URL so it survives page refresh
    try:
        if st.query_params.get("theme") != theme:
            st.query_params["theme"] = theme
    except Exception:
        pass
    st.markdown(
        f"<script>try{{localStorage.setItem('crTheme','{theme}');}}catch(e){{}}</script>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Space+Grotesk:wght@400;500;700&family=DM+Sans:wght@400;500;700&display=swap');

            html, body, [class*="css"] {{
                font-family: 'Plus Jakarta Sans', 'DM Sans', sans-serif;
            }}

            h1, h2, h3 {{
                font-family: 'Plus Jakarta Sans', 'Space Grotesk', sans-serif;
                letter-spacing: -0.03em;
            }}

            /* ── Remove Streamlit's default top padding ────────── */
            [data-testid="stAppViewContainer"] > section > div:first-child,
            .main > div:first-child,
            [data-testid="stMainBlockContainer"],
            [data-testid="block-container"] {{
                padding-top: 0.5rem !important;
            }}

            /* ── Shared structural styles ───────────────────────── */
            .hero-card {{
                border-radius: 28px;
                padding: 28px 30px;
                margin-bottom: 22px;
                backdrop-filter: blur(10px);
            }}
            .hero-kicker {{
                font-size: 0.84rem;
                font-weight: 700;
                letter-spacing: 0.16em;
                text-transform: uppercase;
                margin-bottom: 10px;
            }}
            .hero-title {{
                font-size: 4.3rem;
                line-height: 1;
                margin: 0 0 12px 0;
            }}
            .hero-copy {{
                font-size: 1rem;
                max-width: 700px;
                margin: 0;
            }}
            .section-card {{
                border-radius: 24px;
                padding: 22px;
                margin-bottom: 18px;
            }}
            .section-label {{
                font-size: 0.82rem;
                font-weight: 700;
                letter-spacing: 0.12em;
                text-transform: uppercase;
                margin-bottom: 12px;
            }}
            .step-card {{
                border-radius: 20px;
                padding: 18px;
                min-height: 150px;
            }}
            .step-num {{
                font-size: 0.78rem;
                font-weight: 700;
                letter-spacing: 0.12em;
                text-transform: uppercase;
            }}
            .step-title {{
                font-family: 'Space Grotesk', sans-serif;
                font-size: 1.2rem;
                font-weight: 700;
                margin: 8px 0 10px 0;
            }}
            .step-copy {{
                font-size: 0.95rem;
                margin: 0;
            }}
            .result-banner {{
                border-radius: 26px;
                padding: 26px 28px;
                color: #0f172a;
                box-shadow: 0 24px 70px rgba(0,0,0,0.30);
                margin-bottom: 18px;
            }}
            .result-full    {{ background: linear-gradient(135deg, #b8ffce 0%, #7ff1ba 100%); }}
            .result-partial {{ background: linear-gradient(135deg, #ffe3a3 0%, #ffbf66 100%); }}
            .result-title {{
                font-family: 'Space Grotesk', sans-serif;
                font-size: 2.5rem;
                line-height: 1;
                margin: 0 0 10px 0;
            }}
            .result-subtitle {{
                font-size: 1.05rem;
                margin: 0;
                color: rgba(15,23,42,0.82);
            }}
            .reasoning-card, .report-card {{
                border-radius: 24px;
                padding: 22px;
            }}
            .report-pre {{
                white-space: pre-wrap;
                word-break: break-word;
                border-radius: 16px;
                padding: 20px 22px;
                font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
                font-size: 0.86rem;
                line-height: 1.65;
                overflow-x: auto;
                margin: 0;
            }}
            /* ── Structured report card ────────────────────────── */
            .rpt-header-bar {{
                border-radius: 16px 16px 0 0;
                padding: 18px 22px 16px;
                background: linear-gradient(135deg,rgba(0,175,239,0.14) 0%,rgba(97,206,112,0.09) 100%);
                border: 1px solid rgba(255,255,255,0.08);
                border-bottom: none;
                margin-top: 4px;
            }}
            .rpt-company {{
                font-size: 0.70rem;
                font-weight: 700;
                letter-spacing: 0.16em;
                text-transform: uppercase;
                opacity: 0.55;
                margin-bottom: 3px;
            }}
            .rpt-doc-label {{
                font-family: 'Space Grotesk', sans-serif;
                font-size: 1.22rem;
                font-weight: 700;
            }}
            .rpt-body {{
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 0 0 16px 16px;
                border-top: none;
                padding: 18px 22px 20px;
            }}
            .rpt-block-title {{
                font-size: 0.74rem;
                font-weight: 700;
                letter-spacing: 0.13em;
                text-transform: uppercase;
                margin-bottom: 10px;
                margin-top: 6px;
            }}
            .rpt-kv {{
                width: 100%;
                border-collapse: collapse;
                font-size: 0.92rem;
                line-height: 1.7;
            }}
            .rpt-kv td:first-child {{
                opacity: 0.58;
                padding-right: 14px;
                white-space: nowrap;
                font-size: 0.84rem;
            }}
            .rpt-kv code {{
                font-size: 0.82rem;
                border-radius: 6px;
                padding: 1px 6px;
            }}
            .rpt-decision-badge {{
                border-radius: 12px;
                padding: 13px 18px;
                color: #ffffff;
                font-family: 'Space Grotesk', sans-serif;
                font-size: 1.1rem;
                font-weight: 700;
                letter-spacing: 0.04em;
                margin: 16px 0 6px 0;
                text-align: center;
            }}
            .rpt-table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 0.89rem;
                margin-top: 6px;
            }}
            .rpt-table th {{
                text-align: left;
                padding: 7px 12px;
                font-size: 0.72rem;
                font-weight: 700;
                letter-spacing: 0.09em;
                text-transform: uppercase;
                opacity: 0.5;
            }}
            .rpt-table td {{
                padding: 9px 12px;
            }}
            .rpt-table tbody tr:last-child td {{ border-bottom: none; }}
            .rpt-note-row td {{
                font-size: 0.80rem;
                padding: 2px 12px 9px;
                opacity: 0.6;
                font-style: italic;
            }}
            .rpt-capped {{
                font-size: 0.68rem;
                border-radius: 4px;
                padding: 1px 5px;
                margin-left: 5px;
                vertical-align: middle;
            }}

            .summary-chip {{
                display: inline-block;
                padding: 9px 12px;
                border-radius: 999px;
                font-size: 0.88rem;
                margin: 6px 10px 0 0;
            }}
            .policy-mini {{
                border-radius: 16px;
                padding: 12px 14px;
                margin-bottom: 10px;
            }}
            .policy-mini strong {{ display: block; margin-bottom: 4px; }}
            div[data-testid="stMetric"] {{
                border-radius: 18px;
                padding: 8px 12px;
            }}
            .stButton button, .stDownloadButton button {{
                border-radius: 16px !important;
                height: 3.1rem;
                font-weight: 700 !important;
                border: 0 !important;
            }}
            .stButton button[kind="primary"] {{
                background: linear-gradient(135deg, #00AFEF 0%, #ff8f3d 100%) !important;
                color: white !important;
                box-shadow: 0 16px 40px rgba(0,175,239,0.35);
            }}

            /* ── Popover trigger button — shape only ────────────── */
            [data-testid="stPopover"] button,
            [data-testid="stPopover"] > button {{
                border-radius: 12px !important;
                height: 2.2rem !important;
                font-size: 0.82rem !important;
                font-weight: 600 !important;
                padding: 0 14px !important;
            }}

            /* ── Popover body — size ────────────────────────────── */
            [data-testid="stPopoverBody"] {{
                min-width: 180px !important;
                padding: 16px 20px !important;
            }}
            [data-testid="stPopoverBody"] label {{
                padding: 6px 0 !important;
            }}
            /* ── Shift radio options right inside the inner box ── */
            [data-testid="stPopoverBody"] [data-testid="stRadio"] > div {{
                padding-left: 14px !important;
            }}

            @media (max-width: 900px) {{
                .hero-title {{ font-size: 3rem; }}
            }}

            /* ── Theme-specific overrides ───────────────────────── */
            {_theme_css(theme)}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── Theme selector ────────────────────────────────────────────────────────────

def _theme_popover() -> None:
    """Shared theme radio inside a popover — works in sidebar or main area."""
    with st.popover("Theme", width="stretch"):
        st.radio("Theme", options=["Dark", "Light", "System"],
                 key="theme", label_visibility="collapsed")


def render_theme_selector() -> None:
    """Top-right nav bar: Submit Claim · Theme · My Profile · Sign out."""
    current = st.session_state.get("page", "form")

    # Inject active-page highlight style + JS to apply it by button text
    active_text = (
        "Admin Dashboard" if current in ("dashboard", "admin_review") else
        "Submit Claim" if current == "form" else
        "My Profile"
    )
    st.markdown(f"""
        <style>
        button.topnav-active,
        button.topnav-active:hover {{
            background:       #00AFEF !important;
            background-color: #00AFEF !important;
            color:            #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            border:           none !important;
            box-shadow:       0 2px 10px rgba(0,175,239,0.35) !important;
        }}
        [data-testid="stBaseButton-primary"]:has(div:contains("Sign out")) {{
            background:       #00AFEF !important;
            background-color: #00AFEF !important;
            color:            #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            border:           none !important;
            box-shadow:       0 2px 10px rgba(0,175,239,0.35) !important;
        }}
        [data-testid="stBaseButton-primary"]:has(div:contains("Sign out")):hover {{
            background:       #0099d4 !important;
            background-color: #0099d4 !important;
            color:            #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }}
        </style>
        <script>
        (function() {{
            function applyActive() {{
                document.querySelectorAll('[data-testid="stBaseButton-secondary"]').forEach(function(btn) {{
                    btn.classList.remove('topnav-active');
                    if (btn.innerText.trim() === '{active_text}') {{
                        btn.classList.add('topnav-active');
                    }}
                }});
            }}
            applyActive();
            setTimeout(applyActive, 200);
            setTimeout(applyActive, 600);
        }})();
        </script>
    """, unsafe_allow_html=True)

    auth_user = st.session_state.get("auth_user") or {}
    is_admin  = bool(auth_user.get("is_admin"))

    if is_admin:
        _, c_submit, c_admin, c_theme, c_profile, c_signout = st.columns([1.0, 1.4, 2.2, 1.3, 1.3, 1.1])
    else:
        _, c_submit, c_theme, c_profile, c_signout = st.columns([2.5, 1.4, 1.3, 1.3, 1.1])

    with c_submit:
        if st.button(
            "Submit Claim",
            key="topnav_submit",
            type="secondary",
            width="stretch",
        ):
            st.session_state["page"] = "form"
            st.rerun()

    if is_admin:
        with c_admin:
            if st.button(
                "Admin Dashboard",
                key="topnav_admin",
                type="secondary",
                width="stretch",
            ):
                st.session_state["page"] = "dashboard"
                st.rerun()

    with c_theme:
        _theme_popover()

    with c_profile:
        if st.button(
            "My Profile",
            key="topnav_profile",
            type="secondary",
            width="stretch",
        ):
            st.session_state["page"] = "profile"
            st.rerun()

    with c_signout:
        if st.button("Sign out", key="topnav_signout", width="stretch", type="primary"):
            logout_session(st.session_state.get("auth_token"))
            st.session_state.update({
                "auth_token": None, "auth_user": None,
                "auth_mode": "login", "auth_error": "",
                "pending_oauth": None,
                "email_otp_sent": False, "email_otp_to": "",
                "phone_otp_sent": False, "phone_otp_to": "",
                "page": "form",
            })
            try:
                st.query_params.pop("sid", None)
            except Exception:
                pass
            st.rerun()


# ── Session state ─────────────────────────────────────────────────────────────

def init_session_state() -> None:
    defaults = {
        "page":               "form",
        "last_result":            None,
        "last_employee_id":       "",
        "last_employee_name":     "",
        "last_claimed":           0.0,
        "last_approved":          0.0,
        "last_distance":          None,
        "last_odometer_readings": [],
        "last_vision":            {},
        "last_claim_id":          "",
        "last_form_snapshot":     {},
        "last_voucher_pdf":       None,
        "last_voucher_pdf_name":  "",
        "theme":              "Dark",
        # ── auth ──────────────────────────────────────────────────────
        "auth_token":         None,   # session token stored in DB
        "auth_user":          None,   # {id, employee_id, name, email, phone, ...}
        "auth_mode":          "login",  # "login" | "register" | "complete_oauth"
        "auth_error":         "",
        "pending_oauth":      None,   # {google_id, zoho_id, email, name} after OAuth
        "email_otp_sent":     False,
        "email_otp_to":       "",
        "phone_otp_sent":     False,
        "phone_otp_to":       "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


# ── Sidebar ───────────────────────────────────────────────────────────────────

_LOGO_URL = "https://ritewater.in/wp-content/uploads/2023/10/Group-45541@2x.png"


def render_sidebar() -> None:
    with st.sidebar:
        # ── Brand logo ────────────────────────────────────────────────
        st.markdown(
            f"""
            <div style="padding:10px 4px 4px;text-align:center">
                <img src="{_LOGO_URL}"
                     style="max-width:90px;width:100%;height:auto;object-fit:contain"
                     alt="Rite Water Solutions">
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.divider()

        # ── Logged-in user info ───────────────────────────────────────
        user = st.session_state.get("auth_user")
        if user:
            contact = user.get("email") or user.get("phone") or ""
            emp_id  = user.get("employee_id", "")
            st.markdown(
                f"""
                <div style="text-align:center;margin-bottom:4px">
                    <div style="font-size:1.1rem;margin-bottom:4px"><strong>{user.get('name','')}</strong></div>
                    {'<div style="font-size:0.95rem;opacity:.7">'+contact+'</div>' if contact else ''}
                    {'<div style="font-size:0.88rem;opacity:.5">Employee ID: '+emp_id+'</div>' if emp_id else ''}
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.divider()

        st.markdown("## Reimbursement Policy")
        st.caption("Rite Water Solutions (India) Pvt. Ltd. — Effective Nov 2023")

        with st.expander("Two Wheeler / Bike"):
            st.write("**Rate:** Rs.3 per km")
            st.write("**Proof required:** Fuel bill + Unolo GPS screenshot")
            st.caption("Car conveyance: Rs.9/km (Manager and above)")

        with st.expander("Food / Meals"):
            st.write("**With overnight stay (per day):**")
            st.write("· Technician / Sr. Executive — **Rs.400**")
            st.write("· Manager / Asst. Manager — Rs.500")
            st.write("· Sr. Manager — Rs.600")
            st.divider()
            st.write("**Without overnight stay (>12 hrs, per day):**")
            st.write("· Technician / Sr. Executive — **Rs.200**")
            st.write("· Manager / Asst. Manager — Rs.250")
            st.write("· Sr. Manager — Rs.300")
            st.caption("Max Rs.7,000/month if travel exceeds 15 days")

        with st.expander("Bus / Train Travel"):
            st.write("**Technician / Sr. Executive:**")
            st.write("· Sleeper Class Train / Non-AC Bus")
            st.divider()
            st.write("**Manager / Asst. Manager:**")
            st.write("· 3rd AC Train / AC Bus")
            st.divider()
            st.write("**Sr. Manager:**")
            st.write("· 2nd AC Train / Bus AC")

        with st.expander("Hotel / Accommodation"):
            st.write("**Technician** (per night):")
            st.write("· Grade A city — Rs.1,000")
            st.write("· Grade B city — Rs.900")
            st.write("· Grade C city — Rs.700")
            st.caption("Grade A: Metros (Mumbai/Delhi/Bengaluru/Pune etc.)")
            st.caption("Grade B: State Capitals + Indore/Nagpur/Surat etc.")
            st.caption("Grade C: All other cities")

        with st.expander("FASTag / Toll"):
            st.write("Actual toll charges (work travel only)")
            st.write("**Proof:** FASTag bank statement / NHAI screenshot")
            st.caption("Monthly limit: Rs.3,000")

        with st.expander("Site Expenses"):
            st.write("Actual operational costs at site:")
            st.write("· Materials, tools, dispatch charges")
            st.write("· Porter / handling / parcel / courier")
            st.write("**Proof:** Receipt mandatory for each item")
            st.caption("Subject to admin approval | Monthly limit: Rs.50,000")

        with st.expander("Site Deputation (>30 days)"):
            st.write("**Where no Guest House is available:**")
            st.write("Technician — Lodging up to Rs.4,000–7,000")
            st.write("(varies by city grade)")
            st.write("Fooding — up to Rs.4,000/month")
            st.caption("Project Manager: Lodging Rs.8,000–12,000 | Fooding Rs.7,000")

        st.markdown("---")
        st.markdown("### Quick Rules")
        st.caption(f"Max single claim: Rs{GENERAL_POLICY['max_single_claim']:,.0f}")
        st.caption(f"Max claim period: {GENERAL_POLICY['max_claim_period_days']} days")
        st.caption(f"Manager approval required above: Rs{GENERAL_POLICY['require_manager_approval_above']:,.0f}")
        st.markdown("---")
        st.markdown("### Tech Stack")
        st.caption("**UI:** Streamlit")
        st.caption("**Powered by:** Rite Audit Agent (judgment) · Rite Audit Agent (OCR/vision)")
        st.caption("**AI Framework:** LangGraph + LangChain (9-node workflow)")
        st.caption("**Prompt Caching:** Anthropic cache_control (cost optimisation)")
        st.caption("**Database:** SQLite (claims · auth · training)")
        st.caption("**GPS Verification:** Unolo API (distance validation)")
        st.caption("**HR Integration:** SpineHR API (employee profiles)")
        st.caption("**Auth:** Password · Email OTP · Phone OTP (Twilio) · Google OAuth2 · Zoho OAuth2")
        st.caption("**Language:** Python 3.11+")



# ── File helpers ──────────────────────────────────────────────────────────────

def save_uploaded_files(uploaded_files) -> list[str]:
    image_paths = []
    if not uploaded_files:
        return image_paths
    upload_dir = "temp_uploads"
    os.makedirs(upload_dir, exist_ok=True)
    for uploaded_file in uploaded_files:
        file_path = os.path.join(upload_dir, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        image_paths.append(file_path)
    return image_paths


# ── Submission page ───────────────────────────────────────────────────────────

def render_submission_page() -> None:
    st.markdown(
        f"""
        <div class="hero-card">
            <div class="hero-kicker">AI Expense Review</div>
            <div class="hero-title">Rite Audit System</div>
            <p class="hero-copy">
                Submit once. Review on the next screen.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _render_manual_form()


def _render_manual_form() -> None:
    """Original manual entry form — extracted for tab structure."""

    with st.form("claim_submission_form", clear_on_submit=False):
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-label">Employee</div>', unsafe_allow_html=True)
        employee_col1, employee_col2 = st.columns(2)
        _u = st.session_state.get("auth_user") or {}
        with employee_col1:
            employee_name = st.text_input(
                "Employee Name",
                value=_u.get("name", ""),
                placeholder="e.g. Pawan Pawar",
            )
        with employee_col2:
            employee_id = st.text_input(
                "Employee ID",
                value=_u.get("employee_id", ""),
                placeholder="e.g. EMP-001",
            )
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-label">Claim</div>', unsafe_allow_html=True)
        claim_col1, claim_col2 = st.columns(2)
        with claim_col1:
            claimed_amount = st.number_input(
                "Total Claimed Amount (Rs)",
                min_value=0.0,
                max_value=float(GENERAL_POLICY.get("max_single_claim", 100000)),
                value=5000.0,
                step=100.0,
            )
        with claim_col2:
            emp_distance = st.number_input(
                "Total Distance Travelled (km)",
                min_value=0.0,
                max_value=10000.0,
                value=0.0,
                step=10.0,
                help="Required only for two-wheeler / fuel claims",
            )

        date_col1, date_col2 = st.columns(2)
        today = datetime.today().date()
        with date_col1:
            period_start = st.date_input("Claim Period Start", value=today - timedelta(days=30))
        with date_col2:
            period_end = st.date_input("Claim Period End", value=today)

        claim_description = st.text_area(
            "Claim Description",
            placeholder="Purpose of travel, meals, tolls, reimbursements, or other notes",
            height=110,
        )
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-label">Documents</div>', unsafe_allow_html=True)
        uploaded_files = st.file_uploader(
            "Upload receipts, bills, screenshots, or summary PDFs",
            type=["jpg", "jpeg", "png", "pdf", "webp"],
            accept_multiple_files=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)

        test_mode = st.checkbox(
            "Test mode (skip LLM judgment — rule-based only, no training DB)",
            value=False,
        )

        submitted = st.form_submit_button(
            "Submit for AI Review",
            type="primary",
            width="stretch",
        )

    if submitted:
        _process_submission(
            employee_name, employee_id, claimed_amount, emp_distance,
            period_start, period_end, claim_description, uploaded_files,
            test_mode=test_mode,
        )


def _build_line_items(result: dict) -> list:
    """Build structured line items for admin review from pipeline result."""
    cat_eligible = result.get("category_eligible", {})
    items = []

    for exp in result.get("expenses", []):
        cat      = exp.get("category", "other")
        cat_data = cat_eligible.get(cat, {})
        claimed  = float(cat_data.get("claimed") or 0)
        eligible = float(cat_data.get("eligible") or 0)
        amt      = float(exp.get("amount") or 0)

        if claimed > 0:
            ratio = min(eligible / claimed, 1.0)
            sys_approved = round(amt * ratio, 2)
        else:
            sys_approved = amt

        notes       = exp.get("validation_notes", "") or ""
        is_partial  = "partial" in notes.lower()
        sys_decision = "partial" if is_partial or (sys_approved < amt * 0.99) else "approve"

        items.append({
            "description":            exp.get("description", ""),
            "date":                   exp.get("date", ""),
            "category":               cat,
            "claimed_amount":         amt,
            "system_decision":        sys_decision,
            "system_approved_amount": sys_approved,
            "system_reason":          notes,
            "system_confidence":      exp.get("system_confidence"),
            "source_type":            exp.get("source_type", "receipt"),
        })

    for rej in result.get("rejected_expenses", []):
        items.append({
            "description":            rej.get("description", ""),
            "date":                   rej.get("date", ""),
            "category":               rej.get("category", "other"),
            "claimed_amount":         float(rej.get("amount") or 0),
            "system_decision":        "reject",
            "system_approved_amount": 0.0,
            "system_reason":          rej.get("system_reason", ""),
            "system_confidence":      rej.get("system_confidence"),
            "source_type":            rej.get("source_type", "receipt"),
        })

    return items


def _save_claim_to_db(
    result: dict,
    employee_name: str,
    claimed_amount: float,
    period_start: str,
    period_end: str,
) -> None:
    """Persist the completed claim and its line items to the claims DB."""
    db         = get_db()
    line_items = _build_line_items(result)
    claim_data = {
        **result,
        "employee_name":      employee_name,
        "claimed_amount":     claimed_amount,
        "claim_period_start": period_start,
        "claim_period_end":   period_end,
        "submission_date":    datetime.now().isoformat(),
        "processing_complete": True,
    }
    db.save_full_claim(claim_data, line_items)


def _process_submission(
    employee_name, employee_id, claimed_amount, emp_distance,
    period_start, period_end, claim_description, uploaded_files,
    test_mode: bool = False,
) -> None:
    if not employee_name.strip() or not employee_id.strip():
        st.error("Please enter both employee name and ID.")
        return

    image_paths = save_uploaded_files(uploaded_files)
    if not image_paths:
        st.error("Please upload at least one supporting document.")
        return

    prefix   = "TEST" if test_mode else "CLM"
    claim_id = f"{prefix}-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    progress    = st.progress(0)
    status      = st.empty()

    try:
        # Step 1: Vision scan — resume from disk cache if laptop slept mid-scan
        total_files    = len(image_paths)
        _cache_key     = _vision_cache_key(image_paths)
        vision_result  = _load_vision_cache(_cache_key)

        scan_label = st.empty()

        if vision_result is not None:
            # Restored from cache — skip all API calls
            _r_ok  = len(vision_result.get("receipts", []))
            _r_err = len(vision_result.get("errors", []))
            _r_amt = vision_result.get("total_extracted", 0)
            _summary_parts = [f"**{_r_ok}** receipt{'s' if _r_ok != 1 else ''} scanned"]
            if _r_ok:
                _summary_parts.append(f"Rs.{_r_amt:,.2f} extracted")
            if _r_err:
                _summary_parts.append(f"⚠️ {_r_err} file{'s' if _r_err != 1 else ''} could not be read")
            scan_label.markdown(
                "Scan restored from cache — " + "  ·  ".join(_summary_parts),
                unsafe_allow_html=True,
            )
            progress.progress(40)
        else:
            scan_label.markdown(
                f"**Scanning documents…** &nbsp; 0 / {total_files} files processed",
                unsafe_allow_html=True,
            )
            progress.progress(5)

            import math as _math
            _pdf_count    = sum(1 for p in image_paths if p.lower().endswith(".pdf"))
            _img_count    = total_files - _pdf_count
            _total_jobs   = max(1, _math.ceil(_img_count / 4) + _math.ceil(_pdf_count / 2))
            _files_per_job = max(1, total_files / _total_jobs)

            def _on_scan_progress(done, total, label):
                approx_files = min(total_files, round(done * _files_per_job))
                pct = 5 + int(35 * done / max(1, total))
                progress.progress(pct)
                scan_label.markdown(
                    f"**Scanning documents…** &nbsp;"
                    f"<span style='color:#94a3b8'>{approx_files} / {total_files} files</span>"
                    f"<br><span style='font-size:0.8rem;color:#64748b'>Processing: {label}</span>",
                    unsafe_allow_html=True,
                )

            vision_result = scan_receipts(image_paths, on_progress=_on_scan_progress)
            _save_vision_cache(_cache_key, vision_result)   # persist so sleep won't force rescan

            _r_ok  = len(vision_result.get("receipts", []))
            _r_err = len(vision_result.get("errors", []))
            _r_amt = vision_result.get("total_extracted", 0)
            _summary_parts = [f"**{_r_ok}** receipt{'s' if _r_ok != 1 else ''} scanned"]
            if _r_ok:
                _summary_parts.append(f"Rs.{_r_amt:,.2f} extracted")
            if _r_err:
                _summary_parts.append(f"⚠️ {_r_err} file{'s' if _r_err != 1 else ''} could not be read")
            scan_label.markdown(
                "Scan complete — " + "  ·  ".join(_summary_parts),
                unsafe_allow_html=True,
            )
            progress.progress(40)

        needs_unolo         = vision_result.get("needs_unolo", False)
        odometer_readings   = vision_result.get("odometer_readings", [])
        odometer_km         = vision_result.get("odometer_distance_km")

        # Odometer info message
        if odometer_readings:
            readable = [r for r in odometer_readings if r.get("distance_km") is not None]
            unreadable = len(odometer_readings) - len(readable)
            msg_parts = [f"**{len(odometer_readings)}** odometer screenshot(s) found"]
            if odometer_km:
                msg_parts.append(f"total **{odometer_km:.0f} km** from odometer")
            if unreadable:
                msg_parts.append(f"⚠ {unreadable} screenshot(s) unreadable — Unolo will fill gap")
            scan_label.markdown("Odometer scan — " + "  ·  ".join(msg_parts), unsafe_allow_html=True)

        # Step 2: Unolo distance cross-check
        # Primary source: odometer screenshots; fallback: employee-reported km
        primary_km     = odometer_km if odometer_km else (emp_distance if emp_distance > 0 else None)
        unolo_distance = None
        if needs_unolo:
            status.text("Fetching Unolo GPS distance for cross-check...")
            progress.progress(45)
            unolo_result = fetch_unolo_distance(
                employee_id=employee_id,
                start_date=period_start.isoformat(),
                end_date=period_end.isoformat(),
            )
            unolo_error = unolo_result.get("error")
            if unolo_error:
                st.warning(f"Unolo API: {unolo_error} — using odometer/reported distance.")
                unolo_distance = primary_km
            else:
                api_km = unolo_result.get("distance_km")
                if primary_km and api_km:
                    unreadable_trips = sum(
                        1 for r in odometer_readings if r.get("distance_km") is None
                    )
                    if unreadable_trips > 0:
                        # Partial odometer — Unolo covers the full period without gaps
                        unolo_distance = api_km
                        st.info(
                            f"Odometer partial ({unreadable_trips} unreadable)  ·  "
                            f"Unolo GPS: **{api_km:.0f} km** used for full period"
                        )
                    else:
                        unolo_distance = min(primary_km, api_km)
                        source_label = "odometer" if odometer_km else "reported"
                        st.info(
                            f"Odometer: **{primary_km:.0f} km** ({source_label})  ·  "
                            f"Unolo GPS: **{api_km:.0f} km**  ·  "
                            f"Verified (lower): **{unolo_distance:.0f} km**"
                        )
                else:
                    unolo_distance = api_km or primary_km
                    if api_km:
                        st.info(f"Unolo GPS: **{api_km:.0f} km** (no odometer data)")
        else:
            progress.progress(45)
            unolo_distance = primary_km

        # Step 3: AI pipeline
        status.text("Running AI agent pipeline...")
        progress.progress(50)

        result = None
        for _, _, state in review_claim_stream(
            claim_id=claim_id,
            employee_id=employee_id,
            employee_name=employee_name,
            claimed_amount=claimed_amount,
            images=image_paths,
            vision_data=vision_result,          # ← pass pre-scanned data so
                                                #   ingestion_agent skips the
                                                #   redundant scan + per-image calls
            unolo_distance_km=unolo_distance if unolo_distance and unolo_distance > 0 else None,
            claim_period_start=period_start.isoformat(),
            claim_period_end=period_end.isoformat(),
            claim_description=claim_description,
            test_mode=test_mode,
        ):
            agent = state.get("current_agent", "")
            if agent:
                status.text(f"Agent running: {agent}...")
            result = state

        progress.progress(90)

        # Step 3b: Persist claim to DB for admin dashboard
        try:
            _save_claim_to_db(
                result=result,
                employee_name=employee_name,
                claimed_amount=claimed_amount,
                period_start=period_start.isoformat(),
                period_end=period_end.isoformat(),
            )
        except Exception:
            pass  # DB save failure must never block the user-facing result

        # Step 4: SpineHR submission (only when API key is configured)
        if _SPINEHR_KEY:
            status.text("Submitting to SpineHR...")
            spinehr_submission = submit_claim(
                claim_id=claim_id,
                employee_id=employee_id,
                claimed_amount=claimed_amount,
                approved_amount=result.get("approved_amount", 0),
                category_breakdown=result.get("category_eligible", {}),
                period_start=period_start.isoformat(),
                period_end=period_end.isoformat(),
            )
            if result:
                result["spinehr_submission"] = spinehr_submission

        progress.progress(100)
        status.text("Processing complete.")

        if not result or not result.get("final_report"):
            st.error("Report generation failed — the writer agent produced no output.")
            return

        # Persist to session state and navigate to results
        st.session_state["last_result"]        = result
        st.session_state["last_claim_id"]      = claim_id
        st.session_state["last_employee_id"]   = employee_id
        st.session_state["last_employee_name"] = employee_name
        st.session_state["last_claimed"]       = claimed_amount
        st.session_state["last_approved"]      = result.get("approved_amount", 0)
        st.session_state["last_distance"]          = unolo_distance
        st.session_state["last_odometer_readings"] = odometer_readings
        st.session_state["last_vision"]            = vision_result
        st.session_state["last_form_snapshot"] = {
            "period_start": period_start.isoformat(),
            "period_end":   period_end.isoformat(),
        }
        st.session_state["page"] = "result"
        _cleanup_temp_files(image_paths)
        _delete_vision_cache(_cache_key)   # pipeline done — cache no longer needed
        st.rerun()

    except Exception as exc:
        status.text("Processing failed.")
        progress.progress(0)
        st.error(f"Error: {exc}")
        st.exception(exc)


# ── Structured report renderer ───────────────────────────────────────────────

# ── Result page ───────────────────────────────────────────────────────────────

def render_result_page() -> None:
    result = st.session_state.get("last_result")
    if not result:
        st.session_state["page"] = "form"
        st.rerun()
        return

    claimed_amount     = st.session_state.get("last_claimed", 0.0)
    approved_amount    = st.session_state.get("last_approved", 0.0)
    employee_name      = st.session_state.get("last_employee_name", "")
    employee_id        = st.session_state.get("last_employee_id", "")
    claim_id           = st.session_state.get("last_claim_id", "")
    unolo_distance     = st.session_state.get("last_distance")
    odometer_readings  = st.session_state.get("last_odometer_readings", [])
    vision_data        = st.session_state.get("last_vision", {})
    decision           = result.get("decision", "")
    reasoning          = result.get("decision_reasoning", "")
    report_text        = result.get("final_report", "")
    category_eligible  = result.get("category_eligible", {})
    policy_violations  = result.get("policy_violations", [])
    duplicates_removed = result.get("duplicates_removed", [])
    spinehr_sub        = result.get("spinehr_submission", {})

    is_full = "FULL" in decision.upper()
    banner_cls   = "result-full" if is_full else "result-partial"
    banner_title = "Full Approval" if is_full else "Partial Approval"
    deduction    = claimed_amount - approved_amount

    # ── Decision banner ───────────────────────────────────────────────────────
    deduction_html = "" if is_full else f" &nbsp;&middot;&nbsp; Deduction Rs.{deduction:,.2f}"
    st.markdown(
        f'<div class="result-banner {banner_cls}">'
        f'<div class="result-title">{banner_title}</div>'
        f'<div class="result-subtitle">Approved Rs.{approved_amount:,.2f} of Rs.{claimed_amount:,.2f} claimed{deduction_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Metrics row ───────────────────────────────────────────────────────────
    mc1, mc2, mc3, mc4 = st.columns(4)
    with mc1:
        st.metric("Claimed",  f"Rs.{claimed_amount:,.0f}")
    with mc2:
        st.metric("Approved", f"Rs.{approved_amount:,.0f}")
    with mc3:
        pct = (approved_amount / claimed_amount * 100) if claimed_amount > 0 else 0
        st.metric("Approval %", f"{pct:.1f}%")
    with mc4:
        receipt_count = len(vision_data.get("receipts", []))
        st.metric("Documents", str(receipt_count))

    # ── Summary chips ─────────────────────────────────────────────────────────
    chips_html = (
        f'<span class="summary-chip">Claim {claim_id}</span>'
        f'<span class="summary-chip">{employee_name} [{employee_id}]</span>'
    )
    if unolo_distance:
        chips_html += f'<span class="summary-chip">Unolo: {unolo_distance:.0f} km</span>'
    if duplicates_removed:
        chips_html += f'<span class="summary-chip">{len(duplicates_removed)} duplicate(s) removed</span>'
    st.markdown(chips_html, unsafe_allow_html=True)
    st.markdown("")

    # ── Navigation buttons ────────────────────────────────────────────────────
    nav1, nav2, _ = st.columns([1, 1, 4])
    with nav1:
        if st.button("New Claim", key="nav_new_claim", width="stretch", type="primary"):
            st.session_state["page"] = "form"
            st.rerun()
    with nav2:
        if st.button("Back to Form", key="nav_back", width="stretch"):
            st.session_state["page"] = "form"
            st.rerun()

    # ── AI Reasoning ──────────────────────────────────────────────────────────
    if reasoning:
        st.markdown('<div class="reasoning-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-label">AI Decision Reasoning</div>', unsafe_allow_html=True)
        st.info(reasoning)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Structured report card ────────────────────────────────────────────────
    form_snap    = st.session_state.get("last_form_snapshot", {})
    period_start = form_snap.get("period_start", "N/A")
    period_end   = form_snap.get("period_end",   "N/A")

    st.markdown('<div class="section-label" style="margin-top:18px">Complete Review Report</div>', unsafe_allow_html=True)
    _render_structured_report(
        result=result,
        claim_id=claim_id,
        employee_name=employee_name,
        employee_id=employee_id,
        claimed_amount=claimed_amount,
        approved_amount=approved_amount,
        decision=decision,
        category_eligible=category_eligible,
        policy_violations=policy_violations,
        duplicates_removed=duplicates_removed,
        unolo_distance=unolo_distance,
        period_start=period_start,
        period_end=period_end,
    )

    # ── Download PDF ──────────────────────────────────────────────────────────
    dl_col, _ = st.columns([1, 3])
    with dl_col:
        try:
            from utils.audit_pdf import generate_audit_pdf
            form_snap = st.session_state.get("last_form_snapshot", {})
            pdf_bytes = generate_audit_pdf(result, form_snap)
            st.download_button(
                "Download Audit Report",
                data=pdf_bytes,
                file_name=f"{claim_id}_audit_report.pdf",
                mime="application/pdf",
                width="stretch",
                type="primary",
            )
        except ImportError:
            st.caption("PDF library not installed (pip install fpdf2)")
        except Exception as _pdf_err:
            st.warning(f"PDF generation failed: {_pdf_err}")

    # ── SpineHR status ────────────────────────────────────────────────────────
    if spinehr_sub:
        st.markdown("---")
        if spinehr_sub.get("error"):
            st.warning(f"SpineHR submission: {spinehr_sub['error']}")
        else:
            src = " (demo)" if spinehr_sub.get("source") == "demo" else ""
            st.success(
                f"SpineHR{src}: Claim submitted — "
                f"ID `{spinehr_sub.get('submission_id', 'N/A')}` | "
                f"Payroll cycle: {spinehr_sub.get('payroll_cycle', 'N/A')}"
            )

    # ── Odometer Readings ─────────────────────────────────────────────────────
    if odometer_readings:
        st.markdown("---")
        st.markdown('<div class="section-label">Odometer Readings</div>', unsafe_allow_html=True)
        for r in odometer_readings:
            in_r   = r.get("in_reading")
            out_r  = r.get("out_reading")
            dist   = r.get("distance_km")
            in_c   = float(r.get("in_confidence") or 0)
            out_c  = float(r.get("out_confidence") or 0)
            notes  = r.get("notes", "")
            fname  = r.get("file", "")

            in_str  = f"{in_r:,} km"  if in_r  is not None else "⚠ Unreadable"
            out_str = f"{out_r:,} km" if out_r is not None else "⚠ Unreadable"
            dist_str = f"**{dist:.0f} km**" if dist is not None else "—"

            c1, c2, c3 = st.columns(3)
            c1.metric("In Reading",  in_str,  delta=None)
            c2.metric("Out Reading", out_str, delta=None)
            c3.metric("Trip Distance", dist_str if dist else "—")
            if notes:
                st.caption(f"⚠ {fname}: {notes}")

        total_odo = sum(r.get("distance_km") or 0 for r in odometer_readings)
        unreadable_count = sum(1 for r in odometer_readings if r.get("distance_km") is None)
        summary_parts = [f"Total odometer distance: **{total_odo:.0f} km**"]
        if unreadable_count:
            summary_parts.append(f"{unreadable_count} screenshot(s) unreadable (Unolo used as fallback)")
        if unolo_distance:
            summary_parts.append(f"Unolo GPS: **{unolo_distance:.0f} km** (verified lower value used)")
        st.info("  ·  ".join(summary_parts))

    # ── Vision AI Scanned Documents ───────────────────────────────────────────
    receipts    = vision_data.get("receipts", [])
    scan_errors = vision_data.get("errors", [])
    emp_summary = vision_data.get("employee_summary")

    if receipts or scan_errors or emp_summary:
        st.markdown("---")
        total_ext = vision_data.get("total_extracted", 0)
        st.markdown(
            '<div class="section-label" style="margin-top:4px">Scanned Documents</div>',
            unsafe_allow_html=True,
        )

        # Summary stats bar
        _ok  = len(receipts)
        _err = len(scan_errors)
        _odo = len(odometer_readings)
        _bar_parts = [f"**{_ok}** receipt{'s' if _ok != 1 else ''} scanned"]
        if _ok:
            _bar_parts.append(f"Rs.{total_ext:,.2f} extracted")
        if _odo:
            _odo_km = sum(r.get("distance_km") or 0 for r in odometer_readings)
            _bar_parts.append(f"**{_odo}** odometer reading{'s' if _odo != 1 else ''} · {_odo_km:.0f} km")
        if _err:
            _bar_parts.append(f"⚠️ {_err} file{'s' if _err != 1 else ''} could not be read")
        st.caption("  ·  ".join(_bar_parts))

        _TYPE_META = {
            "fuel_bill":     ("⛽", "Fuel Bill"),
            "bus_ticket":    ("🚌", "Bus / Train"),
            "fasttag":       ("🛣️",  "FASTag / Toll"),
            "food_bill":     ("🍽️",  "Food"),
            "upi_payment":   ("📱", "UPI Payment"),
            "site_expenses": ("🏗️",  "Site Expense"),
            "unolo":         ("📍", "Unolo Distance"),
            "other":         ("📄", "Other"),
        }

        # ── Expense Voucher card ──────────────────────────────────────────────
        if emp_summary:
            v_total    = float(emp_summary.get("summary_total",    0) or 0)
            v_approved = float(emp_summary.get("summary_approved") or v_total)
            emp_name   = emp_summary.get("employee_name", "")
            v_cats     = emp_summary.get("categories") or {}

            with st.expander("📋  Expense Voucher  (Official PDF)", expanded=True):
                vc1, vc2, vc3 = st.columns(3)
                vc1.metric("Claimed (Voucher)", f"Rs.{v_total:,.2f}")
                vc2.metric("Admin-Approved",    f"Rs.{v_approved:,.2f}")
                if emp_name:
                    vc3.metric("Employee", emp_name)

                if v_cats:
                    st.markdown("**Category Breakdown**")
                    rows_html = ""
                    for cat_key, cat_info in v_cats.items():
                        c_claimed  = float(cat_info.get("claimed",  0) or 0)
                        c_approved = float(cat_info.get("approved", 0) or c_claimed)
                        cat_label  = cat_key.replace("_", " ").title()
                        rows_html += (
                            f"<tr>"
                            f"<td style='padding:5px 12px'>{cat_label}</td>"
                            f"<td style='padding:5px 12px;text-align:right'>"
                            f"Rs.{c_claimed:,.2f}</td>"
                            f"<td style='padding:5px 12px;text-align:right;color:#4ade80'>"
                            f"Rs.{c_approved:,.2f}</td>"
                            f"</tr>"
                        )
                    st.markdown(
                        "<table style='width:100%;border-collapse:collapse;font-size:0.88rem'>"
                        "<thead><tr>"
                        "<th style='padding:5px 12px;text-align:left;"
                        "border-bottom:1px solid #334155'>Category</th>"
                        "<th style='padding:5px 12px;text-align:right;"
                        "border-bottom:1px solid #334155'>Claimed</th>"
                        "<th style='padding:5px 12px;text-align:right;"
                        "border-bottom:1px solid #334155'>Approved</th>"
                        f"</tr></thead><tbody>{rows_html}</tbody></table>",
                        unsafe_allow_html=True,
                    )

        # ── Individual receipt cards — receipt struct is FLAT (not nested) ────
        # Fields: receipt_type, vendor, date, amount, confidence, file, notes
        if receipts:
            from collections import defaultdict
            by_type: dict = defaultdict(list)
            for r in receipts:
                by_type[r.get("receipt_type", "other")].append(r)

            for rtype, rlist in by_type.items():
                icon, label = _TYPE_META.get(rtype, ("📄", rtype.replace("_", " ").title()))
                plural = "s" if len(rlist) > 1 else ""
                st.markdown(
                    f"<div style='margin:14px 0 4px;font-size:0.9rem;font-weight:600;"
                    f"color:#94a3b8'>{icon}&nbsp; {label}"
                    f"<span style='font-weight:400'> · {len(rlist)} document{plural}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                for r in rlist:
                    fname  = r.get("file", "") or "—"
                    amount = float(r.get("amount", 0) or 0)
                    date_  = r.get("date", "") or "—"
                    vendor = r.get("vendor", "") or ""
                    notes  = r.get("notes", "") or ""
                    conf   = r.get("confidence")
                    conf_pct   = f"{float(conf)*100:.0f}%" if conf is not None else "—"
                    conf_color = (
                        "#4ade80" if (conf or 0) >= 0.85
                        else "#facc15" if (conf or 0) >= 0.60
                        else "#f87171"
                    )
                    amt_str = f"Rs.{amount:,.2f}" if amount else "₹—"

                    exp_label = f"{icon} {fname}  —  {amt_str}  ·  {date_}"
                    with st.expander(exp_label, expanded=False):
                        rc1, rc2, rc3 = st.columns(3)
                        rc1.metric("Amount", amt_str)
                        rc2.metric("Date",   date_)
                        rc3.markdown(
                            f"**Confidence**<br>"
                            f"<span style='color:{conf_color};font-size:1.1rem;"
                            f"font-weight:700'>{conf_pct}</span>",
                            unsafe_allow_html=True,
                        )
                        if vendor:
                            st.markdown(f"**Vendor:** {vendor}")
                        if notes:
                            st.caption(f"Note: {notes}")
                        if rtype == "other" and amount == 0 and (conf or 0) == 0:
                            st.info(
                                "This file could not be read as a receipt. "
                                "If it is an odometer reading, rename the file to include "
                                "'odometer' or 'reading' so it is automatically detected.",
                                icon="ℹ️",
                            )

                        # FASTag: show toll transactions if present
                        txns = r.get("transactions", [])
                        if rtype == "fasttag" and txns:
                            st.markdown("**Toll Transactions**")
                            t_rows = ""
                            for t in txns:
                                t_rows += (
                                    f"<tr>"
                                    f"<td style='padding:3px 10px'>{t.get('date','—')}</td>"
                                    f"<td style='padding:3px 10px'>"
                                    f"{t.get('toll_plaza','—')}</td>"
                                    f"<td style='padding:3px 10px;text-align:right'>"
                                    f"Rs.{float(t.get('amount',0)):,.2f}</td>"
                                    f"</tr>"
                                )
                            st.markdown(
                                "<table style='width:100%;border-collapse:collapse;"
                                "font-size:0.85rem'>"
                                "<thead><tr>"
                                "<th style='padding:3px 10px;border-bottom:1px solid "
                                "#334155;text-align:left'>Date</th>"
                                "<th style='padding:3px 10px;border-bottom:1px solid "
                                "#334155;text-align:left'>Toll Plaza</th>"
                                "<th style='padding:3px 10px;border-bottom:1px solid "
                                "#334155;text-align:right'>Amount</th>"
                                f"</tr></thead><tbody>{t_rows}</tbody></table>",
                                unsafe_allow_html=True,
                            )

                        # Any remaining fields (skip already shown + raw text)
                        _SHOWN = {"receipt_type", "vendor", "date", "amount",
                                  "confidence", "file", "notes", "raw_ocr", "transactions"}
                        extras = {k: v for k, v in r.items()
                                  if k not in _SHOWN and v not in (None, "", [], {})}
                        if extras:
                            with st.expander("More fields", expanded=False):
                                st.json(extras)

        # ── Scan errors (collapsed — can be many) ─────────────────────────────
        if scan_errors:
            with st.expander(
                f"⚠️  {len(scan_errors)} file(s) could not be read  "
                f"(click to view)", expanded=False
            ):
                st.caption(
                    "These files were uploaded but could not be parsed. "
                    "PDFs named ExpVouch_* are treated as expense vouchers — "
                    "if the format does not match the company voucher template "
                    "they will appear here."
                )
                for err in scan_errors:
                    # Split "filename: reason" for cleaner display
                    parts = str(err).split(": ", 1)
                    if len(parts) == 2:
                        st.markdown(
                            f"<div style='padding:4px 0;font-size:0.85rem'>"
                            f"<span style='color:#94a3b8'>{parts[0]}</span>"
                            f"<span style='color:#f87171'> — {parts[1]}</span></div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f"<div style='padding:4px 0;font-size:0.85rem;"
                            f"color:#f87171'>{err}</div>",
                            unsafe_allow_html=True,
                        )

        # ── Raw JSON for debugging ────────────────────────────────────────────
        with st.expander("🔧  Raw JSON (debug)", expanded=False):
            clean_receipts = [
                {k: v for k, v in r.items() if k != "raw_ocr"}
                for r in receipts
            ]
            clean_summary = (
                {k: v for k, v in emp_summary.items() if k != "raw_text"}
                if emp_summary else None
            )
            st.json({
                "source":           vision_data.get("source", "claude_vision"),
                "needs_unolo":      vision_data.get("needs_unolo", False),
                "has_summary":      vision_data.get("has_summary", False),
                "total_extracted":  total_ext,
                "receipts":         clean_receipts,
                "by_category":      vision_data.get("by_category", {}),
                "employee_summary": clean_summary,
                "errors":           scan_errors,
            })


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _restore_session() -> None:
    """
    Restore auth token and theme from URL query params after a page refresh.
    Called before init_session_state() so session_state is populated correctly
    from the very first render.
    """
    try:
        qp_theme = st.query_params.get("theme")
        if qp_theme in ("Dark", "Light", "System") and "theme" not in st.session_state:
            st.session_state["theme"] = qp_theme

        sid = st.query_params.get("sid")
        if sid and not st.session_state.get("auth_token"):
            user = get_user_by_session(sid)
            if user:
                st.session_state["auth_token"] = sid
                st.session_state["auth_user"]  = user
    except Exception:
        pass


def _set_auth_success(token: str, user: dict, extra: dict | None = None) -> None:
    """Set session state on successful login/registration and rerun."""
    st.session_state["auth_token"] = token
    st.session_state["auth_user"]  = user
    st.session_state["auth_error"] = ""
    st.session_state["page"]       = "form"
    if extra:
        st.session_state.update(extra)
    # Persist session token and theme in URL so they survive page refresh
    try:
        st.query_params["sid"]   = token
        st.query_params["theme"] = st.session_state.get("theme", "Dark")
    except Exception:
        pass
    st.rerun()


def _render_demo_otp(label: str, otp: str) -> None:
    """Show the OTP in-page when running without real credentials."""
    st.markdown(
        f'<div class="demo-otp-box">'
        f'<div class="demo-otp-label">{label}</div>'
        f'<div class="demo-otp-code">{otp}</div>'
        f'<div class="demo-otp-note">Copy the code above and paste it below</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _get_redirect_uri() -> str:
    """Base URL used as the OAuth redirect_uri.  Override via STREAMLIT_BASE_URL."""
    return os.getenv("STREAMLIT_BASE_URL", "http://localhost:8501").rstrip("/")


def _handle_oauth_callback() -> None:
    """
    Detect an OAuth redirect (Google / Zoho) in the URL query params,
    process it, then clear the params and rerun so the main app loads clean.
    """
    params = st.query_params
    code  = params.get("code", "")
    state = params.get("state", "")
    if not code:
        return

    # Guard: if this exact code was already exchanged in a previous Streamlit
    # re-run (Streamlit can execute the script multiple times on a single page
    # load), skip it — OAuth codes are single-use and expire in ~60 seconds.
    if st.session_state.get("_oauth_last_code") == code:
        st.query_params.clear()
        return
    st.session_state["_oauth_last_code"] = code

    redirect_uri = _get_redirect_uri()
    result: dict = {}

    # Extract theme embedded in state: "google_Dark_TOKEN" or "zoho_Light_TOKEN"
    # Format: {provider}_{theme}_{random} — split on first two underscores
    _state_parts = state.split("_", 2)
    _embedded_theme = _state_parts[1] if len(_state_parts) >= 2 and _state_parts[1] in ("Dark", "Light", "System") else None
    if _embedded_theme:
        st.session_state["theme"] = _embedded_theme

    if state.startswith("google_"):
        with st.spinner("Completing Google sign-in…"):
            result = _auth_google_callback(code, redirect_uri)
    elif state.startswith("zoho_"):
        with st.spinner("Completing Zoho sign-in…"):
            result = _auth_zoho_callback(code, redirect_uri)
    else:
        return  # unknown provider — leave params intact

    st.query_params.clear()
    # Restore theme in URL so it survives the next rerun
    if _embedded_theme:
        try:
            st.query_params["theme"] = _embedded_theme
        except Exception:
            pass

    if result.get("error"):
        st.session_state["auth_error"] = result["error"]
        st.rerun()

    if result.get("new_user"):
        st.session_state["auth_mode"]    = "complete_oauth"
        st.session_state["pending_oauth"] = {
            "google_id": result.get("google_id", ""),
            "zoho_id":   result.get("zoho_id",   ""),
            "email":     result.get("email",      ""),
            "name":      result.get("name",       ""),
        }
        st.rerun()

    if result.get("success") and result.get("user"):
        _set_auth_success(result["token"], result["user"])


def _inject_auth_css() -> None:
    """Auth-page specific CSS injected once per render."""
    theme = st.session_state.get("theme", "Dark")
    is_light = theme == "Light"

    card_bg      = "#ffffff"              if is_light else "rgba(4,20,48,0.92)"
    card_border  = "rgba(0,0,0,0.10)"    if is_light else "rgba(255,255,255,0.08)"
    text_main    = "#0f172a"             if is_light else "#f7f4ed"
    text_sub     = "#6b7280"             if is_light else "#8fa8c8"
    btn_bg       = "#f3f4f6"             if is_light else "rgba(255,255,255,0.06)"
    btn_border   = "rgba(0,0,0,0.14)"   if is_light else "rgba(255,255,255,0.14)"
    inp_bg       = "#ffffff"             if is_light else "rgba(255,255,255,0.05)"
    inp_border   = "rgba(0,0,0,0.18)"   if is_light else "rgba(255,255,255,0.14)"
    demo_bg      = "#fefce8"             if is_light else "rgba(253,224,71,0.10)"
    demo_border  = "#fbbf24"
    demo_col     = "#92400e"             if is_light else "#fcd34d"
    hero_bg      = "linear-gradient(145deg,#dbeefb 0%,#c2e0f5 55%,rgba(0,175,239,0.12) 100%)" if is_light else "linear-gradient(145deg,rgba(0,15,40,0.98) 0%,rgba(0,48,88,0.96) 55%,rgba(0,175,239,0.14) 100%)"
    hero_text    = "#0f172a"             if is_light else "#f0f6fc"
    hero_sub     = "#3d6080"             if is_light else "#8fa8c8"
    hero_feat    = "#1e4f78"             if is_light else "#a8c8e0"
    divider_col  = "rgba(0,0,0,0.10)"   if is_light else "rgba(255,255,255,0.10)"
    otp_link_col = "#0080bb"             if is_light else "#29c0f0"
    back_col     = "#6b7280"             if is_light else "#8fa8c8"

    st.markdown(f"""
    <style>
    /* ── Hero panel ──────────────────────────────────────────── */
    .auth-hero {{
        background: {hero_bg};
        border: 1px solid {card_border};
        border-radius: 24px;
        padding: 52px 44px;
        min-height: 560px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        box-shadow: 0 20px 60px rgba(0,0,0,0.22);
    }}
    .auth-hero-title {{
        font-family: 'Plus Jakarta Sans', 'Space Grotesk', sans-serif;
        font-size: 2.8rem;
        font-weight: 800;
        color: {hero_text};
        line-height: 1.1;
        margin: 8px 0 14px;
    }}
    .auth-hero-sub {{
        color: {hero_sub};
        font-size: 0.97rem;
        line-height: 1.65;
        margin: 0 0 36px;
    }}
    .auth-hero-features {{ display:flex; flex-direction:column; gap:18px; }}
    .auth-hero-feature {{
        display: flex; align-items: flex-start; gap: 12px;
        color: {hero_feat}; font-size: 0.92rem; line-height: 1.45;
    }}
    .auth-hero-icon {{ color:#00AFEF; font-size:0.7rem; margin-top:4px; flex-shrink:0; }}
    .auth-brand-kicker {{
        font-size:0.78rem; font-weight:700; letter-spacing:0.14em;
        text-transform:uppercase; color:#00AFEF; margin-bottom:6px;
    }}

    /* ── Form card ───────────────────────────────────────────── */
    .auth-card {{
        background: {card_bg};
        border: 1px solid {card_border};
        border-radius: 22px;
        padding: 32px 28px 24px;
        box-shadow: 0 16px 48px rgba(0,0,0,0.18);
        margin-bottom: 8px;
    }}
    .auth-card-title {{
        font-family: 'Plus Jakarta Sans', 'Space Grotesk', sans-serif;
        font-size: 1.75rem;
        font-weight: 700;
        color: {text_main};
        margin: 18px 0 6px;
        padding-left: 18px;
        font-size: 2rem;
        line-height: 1.2;
        text-align: left;
    }}
    .auth-card-sub {{
        color: {text_sub};
        font-size: 0.97rem;
        margin: 0 0 22px;
        padding-left: 18px;
        text-align: left;
    }}

    /* ── Divider "or" ────────────────────────────────────────── */
    .auth-divider {{
        display: flex; align-items: center; gap: 10px;
        color: {text_sub}; font-size: 0.78rem;
        margin: 16px 0;
    }}
    .auth-divider::before, .auth-divider::after {{
        content: ''; flex: 1; height: 1px;
        background: {divider_col};
    }}

    /* ── OAuth provider buttons (anchor tags) ────────────────── */
    a.auth-provider-btn {{
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 11px;
        width: 100%;
        padding: 12px 18px;
        border-radius: 12px;
        font-family: 'Plus Jakarta Sans', 'DM Sans', sans-serif;
        font-size: 0.92rem;
        font-weight: 600;
        text-decoration: none !important;
        margin-bottom: 10px;
        cursor: pointer;
        transition: opacity 0.15s, transform 0.12s, box-shadow 0.15s;
        box-sizing: border-box;
        letter-spacing: 0.01em;
    }}
    a.auth-provider-btn:hover {{
        opacity: 0.88;
        transform: translateY(-1px);
    }}
    a.auth-provider-btn-google {{
        background: {btn_bg};
        color: {text_main} !important;
        -webkit-text-fill-color: {text_main} !important;
        border: 1.5px solid {btn_border};
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }}
    a.auth-provider-btn-zoho {{
        background: #e8270a;
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        border: none;
        box-shadow: 0 2px 10px rgba(232,39,10,0.30);
    }}
    a.auth-provider-btn-zoho:hover {{
        box-shadow: 0 4px 16px rgba(232,39,10,0.45) !important;
    }}
    a.auth-provider-btn-unconfigured {{
        background: {btn_bg};
        color: {text_sub} !important;
        -webkit-text-fill-color: {text_sub} !important;
        border: 1px dashed {btn_border};
        cursor: not-allowed;
        opacity: 0.55;
        pointer-events: none;
    }}

    /* ── Input fields inside auth card ──────────────────────── */
    .auth-card [data-baseweb="base-input"],
    .auth-card [data-baseweb="input"],
    .auth-card [data-baseweb="input"] > div {{
        background-color: {inp_bg} !important;
        background:       {inp_bg} !important;
        border-color:     {inp_border} !important;
    }}
    .auth-card input {{
        background-color: transparent !important;
        color: {text_main} !important;
        -webkit-text-fill-color: {text_main} !important;
    }}

    /* ── OTP / back text links row ───────────────────────────── */
    .auth-alt-row {{
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        flex-wrap: wrap;
        margin: 12px 0 4px;
        font-size: 0.84rem;
        color: {text_sub};
    }}
    .auth-alt-row .sep {{ opacity: 0.4; }}
    .auth-alt-link {{
        color: {otp_link_col};
        font-weight: 600;
        cursor: pointer;
        text-decoration: underline;
        text-underline-offset: 2px;
        background: none;
        border: none;
        font-size: inherit;
        font-family: inherit;
        padding: 0;
        line-height: inherit;
    }}
    .auth-alt-link:hover {{ opacity: 0.75; }}

    /* ── Back / switch link row ──────────────────────────────── */
    .auth-back-row {{
        margin-bottom: 16px;
    }}
    .auth-back-link {{
        color: {back_col};
        font-size: 0.84rem;
        cursor: pointer;
        background: none;
        border: none;
        font-family: inherit;
        padding: 0;
        display: inline-flex;
        align-items: center;
        gap: 5px;
    }}
    .auth-back-link:hover {{ color: {text_main}; }}

    /* ── "Other sign-in options" expander inside auth card ──── */
    .auth-card [data-testid="stExpander"] {{
        border:        1px solid {divider_col} !important;
        border-radius: 12px !important;
        margin-top:    14px !important;
        overflow:      hidden !important;
    }}
    /* Force every element in the expander header to card_bg —
       all pseudo-states: default, hover, active, focus, focus-visible */
    .auth-card [data-testid="stExpander"] button,
    .auth-card [data-testid="stExpander"] button:hover,
    .auth-card [data-testid="stExpander"] button:active,
    .auth-card [data-testid="stExpander"] button:focus,
    .auth-card [data-testid="stExpander"] button:focus-visible,
    .auth-card [data-testid="stExpander"] summary,
    .auth-card [data-testid="stExpander"] summary:hover,
    .auth-card [data-testid="stExpander"] summary:active,
    .auth-card [data-testid="stExpander"] details > summary,
    .auth-card [data-testid="stExpander"] details[open] > summary,
    .auth-card [data-testid="stExpander"] [data-baseweb="accordion"],
    .auth-card [data-testid="stExpander"] [data-baseweb="accordion"] > div,
    .auth-card [data-testid="stExpander"] [data-baseweb="accordion"] button,
    .auth-card [data-testid="stExpander"] [data-baseweb="accordion"] button:hover,
    .auth-card [data-testid="stExpander"] [data-baseweb="accordion"] button:active,
    .auth-card [data-testid="stExpander"] [data-baseweb="accordion"] button:focus,
    .auth-card [data-testid="stExpander"] [data-baseweb="accordion"] button:focus-visible {{
        background:       {card_bg} !important;
        background-color: {card_bg} !important;
        outline:          none !important;
        box-shadow:       none !important;
    }}
    .auth-card [data-testid="stExpander"] button:hover,
    .auth-card [data-testid="stExpander"] summary:hover {{
        background:       {btn_bg} !important;
        background-color: {btn_bg} !important;
    }}
    .auth-card [data-testid="stExpander"] button span,
    .auth-card [data-testid="stExpander"] button p,
    .auth-card [data-testid="stExpander"] summary span,
    .auth-card [data-testid="stExpander"] summary p {{
        color:       {text_sub} !important;
        font-size:   0.88rem !important;
        font-weight: 600 !important;
    }}
    .auth-card [data-testid="stExpanderDetails"],
    .auth-card [data-testid="stExpander"] [data-testid="stExpanderDetails"],
    .auth-card [data-testid="stExpander"] [data-testid="stExpanderDetails"] > div,
    .auth-card [data-testid="stExpander"] [data-testid="stExpanderDetails"] > div > div,
    .auth-card [data-testid="stExpander"] details > div,
    .auth-card [data-testid="stExpander"] [data-baseweb="accordion"] > div:last-child,
    .auth-card [data-testid="stExpander"] [data-baseweb="accordion"] > div:last-child > div {{
        background:       {card_bg} !important;
        background-color: {card_bg} !important;
        padding-top:      12px !important;
    }}

    /* ── Setup-account footer ────────────────────────────────── */
    .auth-setup-row {{
        text-align: center;
        font-size: 0.86rem;
        color: {text_sub};
        margin-top: 18px;
        padding-top: 16px;
        border-top: 1px solid {divider_col};
    }}

    /* ── Demo OTP box ────────────────────────────────────────── */
    .demo-otp-box {{
        background: {demo_bg}; border: 1.5px solid {demo_border};
        border-radius: 14px; padding: 14px 18px; margin: 12px 0;
    }}
    .demo-otp-label {{
        font-size:0.75rem; font-weight:700; letter-spacing:0.1em;
        text-transform:uppercase; color:{demo_col}; margin-bottom:6px;
    }}
    .demo-otp-code {{
        font-size:2rem; font-weight:700; letter-spacing:0.3em;
        color:{demo_col}; font-family:'JetBrains Mono',monospace;
    }}
    .demo-otp-note {{ font-size:0.78rem; color:{demo_col}; opacity:0.8; margin-top:4px; }}
    </style>
    """, unsafe_allow_html=True)


# ── Auth helper functions ──────────────────────────────────────────────────────

def _render_back_link(target_mode: str) -> None:
    """Render a ← Back button that switches auth_mode."""
    if st.button("← Back", key=f"back_to_{target_mode}", type="tertiary"):
        st.session_state["auth_mode"] = target_mode
        st.session_state["email_otp_sent"]  = False
        st.session_state["email_otp_to"]    = ""
        st.session_state["phone_otp_sent"]  = False
        st.session_state["phone_otp_to"]    = ""
        st.rerun()


def _provider_btn(label: str, url: str, variant: str, icon_html: str) -> None:
    """Render a full-width provider button anchor."""
    cls = f"auth-provider-btn auth-provider-btn-{variant}"
    if url:
        st.markdown(
            f'<a href="{url}" target="_self" class="{cls}">'
            f'{icon_html}<span>{label}</span></a>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="auth-provider-btn auth-provider-btn-unconfigured">'
            f'{icon_html}<span>{label} (not configured)</span></div>',
            unsafe_allow_html=True,
        )


_GOOGLE_ICON = (
    '<svg width="18" height="18" viewBox="0 0 48 48" style="flex-shrink:0">'
    '<path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>'
    '<path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>'
    '<path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>'
    '<path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>'
    '</svg>'
)

_ZOHO_ICON = (
    '<svg width="18" height="18" viewBox="0 0 64 64" style="flex-shrink:0">'
    '<rect width="64" height="64" rx="8" fill="#fff" opacity=".15"/>'
    '<text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" '
    'font-family="Arial Black,sans-serif" font-size="36" font-weight="900" fill="#fff">Z</text>'
    '</svg>'
)


def _render_main_login() -> None:
    """Main login view: password form + OAuth buttons + OTP text links."""
    theme    = st.session_state.get("theme", "Dark")
    redirect = _get_redirect_uri()
    google_url = _auth_google_url(redirect, theme=theme)
    zoho_url   = _auth_zoho_url(redirect,  theme=theme)

    st.markdown('<div class="auth-card-title">Welcome back</div>'
                '<div class="auth-card-sub">Sign in to access the portal.</div>',
                unsafe_allow_html=True)

    # ── OAuth + OTP buttons ────────────────────────────────────────
    _provider_btn("Continue with Google",    google_url, "google", _GOOGLE_ICON)
    _provider_btn("Continue with Zoho Mail", zoho_url,  "zoho",   _ZOHO_ICON)
    st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
    otp_col1, otp_col2 = st.columns(2)
    with otp_col1:
        if st.button("Email OTP", key="go_email_otp", width="stretch"):
            st.session_state["auth_mode"] = "email_otp"
            st.rerun()
    with otp_col2:
        if st.button("Phone OTP", key="go_phone_otp", width="stretch"):
            st.session_state["auth_mode"] = "phone_otp"
            st.rerun()

    # ── Password form (collapsed by default) ──────────────────────
    with st.expander("Sign in with password"):
        with st.form("auth_pw_form", clear_on_submit=False):
            identifier = st.text_input(
                "Email or Employee ID",
                placeholder="you@ritewater.in  or  RWSIPL007",
            )
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch")

        if submitted:
            if not identifier or not password:
                st.error("Please fill in both fields.")
            else:
                res = _auth_login_password(identifier, password)
                if res.get("error"):
                    st.error(res["error"])
                else:
                    _set_auth_success(res["token"], res["user"])

    # ── First time footer ──────────────────────────────────────────
    st.markdown('<div class="auth-setup-row">First time here?</div>', unsafe_allow_html=True)
    if st.button("Set up my account", key="go_register_btn", width="stretch"):
        st.session_state["auth_mode"] = "register"
        st.rerun()


def _login_form_email_otp() -> None:
    """Email OTP form (standalone view, no tabs)."""
    sent    = st.session_state.get("email_otp_sent", False)
    sent_to = st.session_state.get("email_otp_to", "")

    if not sent:
        with st.form("auth_email_otp_req", clear_on_submit=False):
            email = st.text_input("Email address", placeholder="you@ritewater.in")
            send  = st.form_submit_button("Send OTP", type="primary", width="stretch")
        if send:
            if not email.strip():
                st.error("Please enter your email address.")
                return
            res = _auth_send_email_otp(email.strip().lower())
            if res.get("error"):
                st.error(res["error"])
            else:
                st.session_state["email_otp_sent"] = True
                st.session_state["email_otp_to"]   = email.strip().lower()
                if res.get("demo"):
                    st.session_state["_demo_email_otp"] = res.get("otp", "")
                st.rerun()
    else:
        st.caption(f"OTP sent to **{sent_to}**")
        demo_otp = st.session_state.pop("_demo_email_otp", None)
        if demo_otp:
            _render_demo_otp("Demo mode — no SMTP configured", demo_otp)
        with st.form("auth_email_otp_verify", clear_on_submit=False):
            code = st.text_input("Enter 6-digit OTP", placeholder="123456", max_chars=6)
            c1, c2 = st.columns(2)
            with c1:
                verify = st.form_submit_button("Verify OTP", type="primary", width="stretch")
            with c2:
                resend = st.form_submit_button("Resend", width="stretch")
        if verify:
            if not code.strip():
                st.error("Please enter the OTP.")
                return
            res = _auth_login_email_otp(sent_to, code.strip())
            if res.get("error"):
                st.error(res["error"])
            else:
                _set_auth_success(res["token"], res["user"],
                                  {"email_otp_sent": False, "email_otp_to": ""})
        if resend:
            st.session_state["email_otp_sent"] = False
            st.session_state["email_otp_to"]   = ""
            st.rerun()


def _login_form_phone_otp() -> None:
    """Phone OTP form (standalone view, no tabs)."""
    sent    = st.session_state.get("phone_otp_sent", False)
    sent_to = st.session_state.get("phone_otp_to", "")

    if not sent:
        with st.form("auth_phone_otp_req", clear_on_submit=False):
            phone = st.text_input("Phone number", placeholder="+91 9876543210",
                                  help="Enter with country code, e.g. +91XXXXXXXXXX")
            send = st.form_submit_button("Send OTP", type="primary", width="stretch")
        if send:
            if not phone.strip():
                st.error("Please enter your phone number.")
                return
            res = _auth_send_phone_otp(phone.strip())
            if res.get("error"):
                st.error(res["error"])
            else:
                st.session_state["phone_otp_sent"] = True
                st.session_state["phone_otp_to"]   = phone.strip()
                if res.get("demo"):
                    st.session_state["_demo_phone_otp"] = res.get("otp", "")
                st.rerun()
    else:
        st.caption(f"OTP sent to **{sent_to}**")
        demo_otp = st.session_state.pop("_demo_phone_otp", None)
        if demo_otp:
            _render_demo_otp("Demo mode — Twilio not configured", demo_otp)
        with st.form("auth_phone_otp_verify", clear_on_submit=False):
            code = st.text_input("Enter 6-digit OTP", placeholder="123456", max_chars=6)
            c1, c2 = st.columns(2)
            with c1:
                verify = st.form_submit_button("Verify OTP", type="primary", width="stretch")
            with c2:
                resend = st.form_submit_button("Resend", width="stretch")
        if verify:
            if not code.strip():
                st.error("Please enter the OTP.")
                return
            res = _auth_login_phone_otp(sent_to, code.strip())
            if res.get("error"):
                st.error(res["error"])
            else:
                _set_auth_success(res["token"], res["user"],
                                  {"phone_otp_sent": False, "phone_otp_to": ""})
        if resend:
            st.session_state["phone_otp_sent"] = False
            st.session_state["phone_otp_to"]   = ""
            st.rerun()


# ── Register form ──────────────────────────────────────────────────────────────

def _render_register_form(
    prefill_name: str = "",
    prefill_email: str = "",
    google_id: str = "",
    zoho_id: str = "",
) -> None:
    oauth_mode = bool(google_id or zoho_id)
    heading    = "Complete Registration" if oauth_mode else "Set Up Your Account"
    st.markdown(f"<div style='font-weight:700;font-size:1.05rem;margin-bottom:4px'>{heading}</div>",
                unsafe_allow_html=True)
    if not oauth_mode:
        st.caption("Enter your Employee ID and add your email or phone number. "
                   "Your account is already created — this just links your contact details.")

    with st.form("auth_register_form", clear_on_submit=False):
        name = st.text_input("Full Name", value=prefill_name, placeholder="e.g. Pawan Pawar")
        emp_id = st.text_input("Employee ID", placeholder="e.g. RWSIPL007")
        if not oauth_mode:
            email = st.text_input("Email address",
                                  value=prefill_email,
                                  placeholder="you@ritewater.in")
            phone = st.text_input("Phone number (optional)",
                                  placeholder="+91 9876543210")
            password = st.text_input(
                "Set a password (optional — can also use OTP to sign in)",
                type="password",
                placeholder="Leave blank to use OTP only",
            )
        else:
            email    = prefill_email
            phone    = ""
            password = ""
            st.info(f"Signing in via {'Google' if google_id else 'Zoho'}  ·  {prefill_email}")

        submitted = st.form_submit_button(
            "Set Up Account", type="primary", width="stretch"
        )

    if submitted:
        if oauth_mode:
            res = _auth_complete_oauth(
                name=name, employee_id=emp_id, email=email,
                google_id=google_id, zoho_id=zoho_id,
            )
        else:
            res = _auth_register(
                name=name, employee_id=emp_id,
                email=email, phone=phone, password=password,
            )
        if res.get("error"):
            st.error(res["error"])
        else:
            msg = "Account activated! Signing you in…" if res.get("activated") else "Account created! Signing you in…"
            st.success(msg)
            _set_auth_success(res["token"], res["user"],
                              {"auth_mode": "login", "pending_oauth": None})

    st.markdown(
        '<div class="auth-switch">Already have an account? '
        '</div>',
        unsafe_allow_html=True,
    )
    if st.button("Back to Sign in", key="reg_back_btn", width="content"):
        st.session_state["auth_mode"] = "login"
        st.rerun()


# ── Profile page ───────────────────────────────────────────────────────────────

def render_profile_page() -> None:
    user = st.session_state.get("auth_user") or {}

    st.markdown("## My Profile")
    st.caption("Update your personal details below. Employee ID cannot be changed.")
    st.divider()

    # ── Read-only info ─────────────────────────────────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Employee ID**")
        st.code(user.get("employee_id", "—"), language=None)
    with c2:
        st.markdown("**Account created**")
        created = user.get("created_at", "")
        st.caption(created[:10] if created else "—")

    oauth_linked = []
    if user.get("google_id"):
        oauth_linked.append("Google")
    if user.get("zoho_id"):
        oauth_linked.append("Zoho Mail")
    if oauth_linked:
        st.info(f"Linked via OAuth: {', '.join(oauth_linked)}")

    st.divider()

    # ── Editable fields ────────────────────────────────────────────────────────
    with st.form("profile_form", clear_on_submit=False):
        st.markdown("#### Personal Details")
        new_name  = st.text_input("Full name",  value=user.get("name", ""))
        new_email = st.text_input("Email",       value=user.get("email", "") or "")
        new_phone = st.text_input("Phone",       value=user.get("phone", "") or "",
                                  placeholder="+91 XXXXXXXXXX")

        submitted = st.form_submit_button("Save Changes", type="primary",
                                          width="stretch")

    if submitted:
        fields: dict = {}
        if new_name.strip()  != user.get("name", ""):
            fields["name"]  = new_name.strip()
        if new_email.strip() != (user.get("email") or ""):
            fields["email"] = new_email.strip()
        if new_phone.strip() != (user.get("phone") or ""):
            fields["phone"] = new_phone.strip()

        if not fields:
            st.info("No changes detected.")
        else:
            result = _auth_update_user(user["id"], fields)
            if result.get("error"):
                st.error(result["error"])
            else:
                st.session_state["auth_user"] = result["user"]
                st.success("Profile updated successfully.")
                st.rerun()

    if st.button("Change password", type="secondary", width="stretch"):
        _change_password_dialog(user["id"])


# ── Change Password dialog ────────────────────────────────────────────────────

@st.dialog("Change Password")
def _change_password_dialog(user_id: str) -> None:
    st.caption("Choose a new password for your account.")
    new_pw  = st.text_input("New password",     type="password", key="dlg_new_pw")
    conf_pw = st.text_input("Confirm password", type="password", key="dlg_conf_pw")
    st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)
    save_col, cancel_col = st.columns(2)
    with save_col:
        if st.button("Save password", type="primary", width="stretch", key="dlg_save"):
            if not new_pw:
                st.error("Please enter a new password.")
            elif len(new_pw) < 6:
                st.error("Password must be at least 6 characters.")
            elif new_pw != conf_pw:
                st.error("Passwords do not match.")
            else:
                result = _auth_update_user(user_id, {"password": new_pw})
                if result.get("error"):
                    st.error(result["error"])
                else:
                    st.session_state["auth_user"] = result["user"]
                    st.success("Password updated successfully.")
                    st.rerun()
    with cancel_col:
        if st.button("Cancel", width="stretch", key="dlg_cancel"):
            st.rerun()


# ── Main auth page ─────────────────────────────────────────────────────────────

def render_auth_page() -> None:
    """Renders the login / register / complete-OAuth page."""
    _inject_auth_css()

    error = st.session_state.get("auth_error", "")
    mode  = st.session_state.get("auth_mode", "login")

    # ── Top nav bar: theme button right ───────────────────────
    _, theme_col = st.columns([9, 1])
    with theme_col:
        _theme_popover()

    st.markdown("<div style='margin-bottom:20px'></div>", unsafe_allow_html=True)

    # Two-column: hero branding (left) + form (right)
    hero_col, form_col = st.columns([1.15, 0.85])

    with hero_col:
        st.markdown(
            f'<div class="auth-hero">'
            f'<div style="margin-bottom:28px">'
            f'<img src="{_LOGO_URL}" style="height:90px;width:auto;object-fit:contain" alt="Rite Water Solutions">'
            f'</div>'
            f'<div class="auth-brand-kicker">Employee Portal</div>'
            f'<div class="auth-hero-title">Rite Audit<br>System</div>'
            f'<p class="auth-hero-sub">AI-powered expense claim processing for Rite Water Solutions employees.</p>'
            f'<div class="auth-hero-features">'
            f'<div class="auth-hero-feature"><span class="auth-hero-icon">&#9679;</span><span>Instant receipt scanning with AI Vision</span></div>'
            f'<div class="auth-hero-feature"><span class="auth-hero-icon">&#9679;</span><span>Automated policy cap enforcement per category</span></div>'
            f'<div class="auth-hero-feature"><span class="auth-hero-icon">&#9679;</span><span>Multi-stage AI review with full audit trail</span></div>'
            f'<div class="auth-hero-feature"><span class="auth-hero-icon">&#9679;</span><span>Fast decisions — minutes, not days</span></div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with form_col:
        if error:
            st.error(error)
            st.session_state["auth_error"] = ""

        st.markdown('<div class="auth-card">', unsafe_allow_html=True)

        # ── Complete OAuth registration ────────────────────────────
        if mode == "complete_oauth":
            po = st.session_state.get("pending_oauth") or {}
            _render_register_form(
                prefill_name=po.get("name", ""),
                prefill_email=po.get("email", ""),
                google_id=po.get("google_id", ""),
                zoho_id=po.get("zoho_id", ""),
            )

        # ── Account setup (first-time) ────────────────────────────
        elif mode == "register":
            _render_back_link("login")
            _render_register_form()

        # ── Email OTP ─────────────────────────────────────────────
        elif mode == "email_otp":
            _render_back_link("login")
            st.markdown('<div class="auth-card-title">Sign in with Email OTP</div>'
                        '<div class="auth-card-sub">We\'ll send a one-time code to your email.</div>',
                        unsafe_allow_html=True)
            _login_form_email_otp()

        # ── Phone OTP ─────────────────────────────────────────────
        elif mode == "phone_otp":
            _render_back_link("login")
            st.markdown('<div class="auth-card-title">Sign in with Phone OTP</div>'
                        '<div class="auth-card-sub">We\'ll send a one-time code to your phone.</div>',
                        unsafe_allow_html=True)
            _login_form_phone_otp()

        # ── Main login ────────────────────────────────────────────
        else:
            _render_main_login()

        st.markdown('</div>', unsafe_allow_html=True)  # .auth-card


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="Rite Audit System",
        page_icon="AI",
        layout="wide",
    )

    try:
        validate_api_key()
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    _restore_session()        # restore auth + theme from URL params after refresh
    init_session_state()
    init_auth_db()           # idempotent — creates tables on first run
    migrate_auth_db()       # add is_admin column to existing DBs
    sync_admin_flags()       # promote employee IDs from ADMIN_EMPLOYEE_IDS env var
    _handle_oauth_callback() # process Google / Zoho redirect if present

    # Inject theme styles before the auth gate so auth page and all other
    # pages get identical CSS at the same point in the render cycle.
    inject_loading_theme()
    inject_styles()

    # ── Auth gate ──────────────────────────────────────────────────────────────
    token = st.session_state.get("auth_token")
    user  = get_user_by_session(token) if token else None

    if not user:
        # Session expired or never set — clear stale token and show auth page
        if token:
            st.session_state["auth_token"] = None
            st.session_state["auth_user"]  = None
        # Remove stale sid from URL so login page is clean and
        # _restore_session() doesn't retry an invalid token on next refresh
        try:
            st.query_params.pop("sid", None)
        except Exception:
            pass
        render_auth_page()
        st.stop()

    # Valid session — refresh user in state (picks up name / employee_id changes)
    st.session_state["auth_user"] = user

    render_sidebar()
    render_theme_selector()

    page = st.session_state.get("page")
    if page == "result" and st.session_state.get("last_result"):
        render_result_page()
    elif page == "profile":
        render_profile_page()
    elif page == "dashboard":
        if user.get("is_admin"):
            render_dashboard_page()
        else:
            st.error("Access denied. Admin only.")
            st.session_state["page"] = "form"
            st.rerun()
    elif page == "admin_review":
        if user.get("is_admin"):
            render_admin_review_page()
        else:
            st.error("Access denied. Admin only.")
            st.session_state["page"] = "form"
            st.rerun()
    else:
        render_submission_page()


if __name__ == "__main__":
    main()
