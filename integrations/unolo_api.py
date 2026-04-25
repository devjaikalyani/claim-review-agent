"""
Unolo API Integration
Fetches verified GPS distance data for an employee over a date range.
"""
import os
import requests
from pathlib import Path

_BASE_URL = "https://api-lb-ext.unolo.com/api/protected"


def _load_env_once():
    """Load .env lazily so module-level import order doesn't matter."""
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass


def fetch_unolo_distance(
    employee_id: str,
    start_date:  str,
    end_date:    str,
) -> dict:
    _load_env_once()
    api_key = os.getenv("UNOLO_API_KEY", "")
    api_id  = os.getenv("UNOLO_API_ID", "")
    base_url = os.getenv("UNOLO_BASE_URL", _BASE_URL).strip()

    if not api_key or not api_id:
        return _error_response("Unolo API credentials not configured (UNOLO_API_KEY / UNOLO_API_ID missing)")

    try:
        response = requests.get(
            f"{base_url}/eodSummary",
            headers={
                "id":    api_id,
                "token": api_key,
            },
            params={
                "start":      start_date,
                "end":        end_date,
                "employeeId": employee_id,   # filter by specific employee
            },
            timeout=10,
        )
        response.raise_for_status()
        data        = response.json()
        distance_km = _extract_total_distance(data)

        return {
            "distance_km":  distance_km if distance_km > 0 else None,
            "verified":     distance_km > 0,
            "gps_accuracy": "N/A",
            "source":       "api",
            "error":        None if distance_km > 0 else f"API returned 0 km — raw: {str(data)[:300]}",
        }

    except requests.exceptions.Timeout:
        return _error_response("Unolo API timed out")
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "unknown"
        return _error_response(f"Unolo API error: {status}")
    except Exception as e:
        return _error_response(str(e))


def _extract_total_distance(data) -> float:
    """
    Extract total distance from Unolo eodSummary response.
    Handles both list and dict response formats with multiple field name variants.
    """
    _DISTANCE_KEYS = (
        "totalDistance", "total_distance", "distanceKm", "distance_km",
        "distance", "travelledDistance", "travelled_distance",
        "kmTravelled", "km_travelled", "totalKm", "total_km",
    )

    def _extract_one(obj: dict) -> float:
        for key in _DISTANCE_KEYS:
            val = obj.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass
        return 0.0

    if isinstance(data, list):
        return sum(_extract_one(day) for day in data if isinstance(day, dict))

    if isinstance(data, dict):
        # Top-level dict — try direct keys first, then look for nested "data" list
        direct = _extract_one(data)
        if direct > 0:
            return direct
        nested = data.get("data") or data.get("result") or data.get("records") or []
        if isinstance(nested, list):
            return sum(_extract_one(d) for d in nested if isinstance(d, dict))
        return 0.0

    return 0.0


def _error_response(message: str) -> dict:
    return {
        "distance_km":  None,
        "verified":     False,
        "gps_accuracy": "N/A",
        "source":       "api",
        "error":        message,
    }