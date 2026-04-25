"""
SpineHR API Integration

Handles two operations:
  1. fetch_employee()     — pull employee profile (department, claim limit, etc.)
  2. submit_claim()       — push the approved claim result back into SpineHR

Falls back to demo mode when SPINEHR_API_KEY is not set, so the app works
end-to-end without real credentials.
"""

import os
import requests

SPINEHR_API_KEY  = os.getenv("SPINEHR_API_KEY", "")
SPINEHR_BASE_URL = os.getenv("SPINEHR_BASE_URL", "https://api.spinehr.com/v1")


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_employee(employee_id: str) -> dict:
    """
    Fetch employee profile from SpineHR.

    Returns:
        {
            "id":           str,
            "name":         str,
            "department":   str,
            "designation":  str,
            "claim_limit":  float,
            "manager_id":   str | None,
            "source":       "api" | "demo",
            "error":        str | None
        }
    """
    if not SPINEHR_API_KEY:
        return _demo_employee(employee_id)

    try:
        resp = requests.get(
            f"{SPINEHR_BASE_URL}/employees/{employee_id}",
            headers={"Authorization": f"Bearer {SPINEHR_API_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "id":          data.get("id", employee_id),
            "name":        data.get("name", ""),
            "department":  data.get("department", ""),
            "designation": data.get("designation", ""),
            "claim_limit": float(data.get("claim_limit", 20000)),
            "manager_id":  data.get("manager_id"),
            "source":      "api",
            "error":       None,
        }
    except requests.exceptions.Timeout:
        return _employee_error(employee_id, "SpineHR API timed out")
    except requests.exceptions.HTTPError as e:
        return _employee_error(employee_id, f"SpineHR HTTP {e.response.status_code}")
    except Exception as e:
        return _employee_error(employee_id, str(e))


def submit_claim(
    claim_id: str,
    employee_id: str,
    claimed_amount: float,
    approved_amount: float,
    category_breakdown: dict,
    period_start: str,
    period_end: str,
) -> dict:
    """
    Push the approved claim result into SpineHR for payroll processing.

    Returns:
        {
            "submission_id":  str,
            "status":         "submitted" | "failed",
            "payroll_cycle":  str,
            "source":         "api" | "demo",
            "error":          str | None
        }
    """
    if not SPINEHR_API_KEY:
        return _demo_submission(claim_id, approved_amount)

    payload = {
        "claim_id":         claim_id,
        "employee_id":      employee_id,
        "claimed_amount":   claimed_amount,
        "approved_amount":  approved_amount,
        "categories":       {k: v.get("eligible", 0) for k, v in category_breakdown.items()},
        "period_start":     period_start,
        "period_end":       period_end,
    }

    try:
        resp = requests.post(
            f"{SPINEHR_BASE_URL}/claims",
            headers={
                "Authorization": f"Bearer {SPINEHR_API_KEY}",
                "Content-Type":  "application/json",
            },
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "submission_id": data.get("id", claim_id),
            "status":        "submitted",
            "payroll_cycle": data.get("payroll_cycle", "current"),
            "source":        "api",
            "error":         None,
        }
    except requests.exceptions.Timeout:
        return _submission_error("SpineHR API timed out")
    except requests.exceptions.HTTPError as e:
        return _submission_error(f"SpineHR HTTP {e.response.status_code}")
    except Exception as e:
        return _submission_error(str(e))


# ── Demo helpers ──────────────────────────────────────────────────────────────

def _demo_employee(employee_id: str) -> dict:
    return {
        "id":          employee_id,
        "name":        "Demo Employee",
        "department":  "Sales",
        "designation": "Sales Executive",
        "claim_limit": 20000.0,
        "manager_id":  "MGR-001",
        "source":      "demo",
        "error":       None,
    }

def _demo_submission(claim_id: str, approved_amount: float) -> dict:
    from datetime import datetime
    month = datetime.now().strftime("%B %Y")
    return {
        "submission_id": f"SHR-{claim_id}",
        "status":        "submitted",
        "payroll_cycle": month,
        "source":        "demo",
        "error":         None,
    }

def _employee_error(employee_id: str, message: str) -> dict:
    return {
        "id":          employee_id,
        "name":        "",
        "department":  "",
        "designation": "",
        "claim_limit": 20000.0,
        "manager_id":  None,
        "source":      "api",
        "error":       message,
    }

def _submission_error(message: str) -> dict:
    return {
        "submission_id": None,
        "status":        "failed",
        "payroll_cycle": None,
        "source":        "api",
        "error":         message,
    }