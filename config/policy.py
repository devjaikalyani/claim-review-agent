"""
Reimbursement Policy Configuration
Rite Water Solutions (India) Pvt. Ltd.
Recommended Revised Travel Policy — Effective 1st November 2023
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


@dataclass
class CategoryPolicy:
    """Policy rules for a specific expense category."""
    name: str
    rate_type: str  # "per_km", "actual", "daily_limit"
    rate_per_km: float = 0.0
    daily_limit: float = 0.0
    monthly_limit: float = 0.0
    per_trip_limit: float = 0.0
    required_proofs: List[str] = field(default_factory=list)
    description: str = ""


# ── Reimbursement Policy ───────────────────────────────────────────────────────

REIMBURSEMENT_POLICY: Dict[str, CategoryPolicy] = {

    "two_wheeler": CategoryPolicy(
        name="Two Wheeler / Bike",
        rate_type="per_km",
        rate_per_km=3.0,          # Rs. 3/km local petrol conveyance (policy: Bike @ Rs.3/km)
        monthly_limit=5000.0,
        required_proofs=["fuel_bill", "unolo_distance"],
        description=(
            "Local petrol conveyance — Rs.3/km. "
            "Eligible for: Technician, Sr.Executive, Manager, Asst.Manager. "
            "Unolo GPS tracking screenshot required to verify distance. "
            "Car conveyance: Rs.9/km (Manager and above)."
        )
    ),

    "car_conveyance": CategoryPolicy(
        name="Car Conveyance",
        rate_type="per_km",
        rate_per_km=9.0,          # Rs. 9/km — local petrol conveyance per policy
        monthly_limit=15000.0,
        required_proofs=["fuel_bill"],
        description="Local petrol conveyance for car. Rs.9/km. Manager level and above."
    ),

    "bus_travel": CategoryPolicy(
        name="Bus / Train Travel",
        rate_type="actual",
        per_trip_limit=5000.0,    # Upper bound — VP/GM flight upto Rs. 5000
        monthly_limit=22000.0,
        required_proofs=["ticket", "receipt"],
        description=(
            "Travel class by grade: "
            "Technician/Sr.Exec — Sleeper Class Train / Non-AC Bus; "
            "Manager/Asst.Mgr — 3rd AC Train / AC Bus; "
            "Sr.Manager — 2nd AC Train / Bus AC; "
            "VP/GM — 1st AC / 2nd AC Train or Flight up to Rs.5,000 (distance >500 km, prior approval if more)."
        )
    ),

    "fasttag": CategoryPolicy(
        name="FASTag / Toll",
        rate_type="actual",
        monthly_limit=3000.0,
        required_proofs=["fasttag_screenshot", "toll_receipt"],
        description="Highway tolls paid via FASTag for work travel."
    ),

    "food": CategoryPolicy(
        name="Food / Meals",
        rate_type="daily_limit",
        daily_limit=400.0,        # Default: Technician/Sr.Executive level (most common field employee)
        monthly_limit=7000.0,     # Rs. 7000/month cap for >15 days travel (policy note)
        required_proofs=["food_bill", "receipt"],
        description=(
            "With overnight stay (per day): "
            "Technician/Sr.Exec Rs.400 | Manager/Asst.Mgr Rs.500 | "
            "Sr.Manager Rs.600 | VP/GM Rs.750 | Director/CFO Actual. "
            "Without overnight stay (>12 hrs only): "
            "Technician/Sr.Exec Rs.200 | Manager/Asst.Mgr Rs.250 | "
            "Sr.Manager Rs.300 | VP/GM Rs.375. "
            "Max Rs.7,000/month when travel exceeds 15 days in a month "
            "(applicable to Project Manager and above)."
        )
    ),

    "hotel": CategoryPolicy(
        name="Hotel / Accommodation",
        rate_type="actual",
        daily_limit=1000.0,       # Default: Technician level, Grade C city
        monthly_limit=40000.0,
        required_proofs=["hotel_bill", "receipt"],
        description=(
            "Hotel tariff per night (by city grade): "
            "Technician — Grade A Rs.1,000 | Grade B Rs.900 | Grade C Rs.700. "
            "Sr.Executive — Grade A Rs.1,100 | Grade B Rs.1,000 | Grade C Rs.750. "
            "Manager — Grade A Rs.1,500 | Grade B Rs.1,200 | Grade C Rs.750. "
            "Sr.Manager — Grade A Rs.2,000 | Grade B Rs.1,500 | Grade C Rs.1,000. "
            "VP/GM — Grade A Rs.3,000 | Grade B Rs.2,000 | Grade C Rs.1,500. "
            "Director/CFO — Actual. "
            "Grade A: Metros (Mumbai/Delhi/Bengaluru/Hyderabad/Chennai/Kolkata/Ahmedabad/Jaipur/Pune). "
            "Grade B: State Capitals + Agra/Indore/Nagpur/Surat/Kochi/Vishakapatnam etc. "
            "Grade C: All other cities."
        )
    ),

    "site_expenses": CategoryPolicy(
        name="Site Expenses",
        rate_type="actual",
        monthly_limit=50000.0,
        required_proofs=["receipt"],
        description=(
            "Site-related operational costs: material purchase, dispatch charges, "
            "porter/handling, parcel, courier, tools, on-site installation supplies. "
            "Actual amount subject to admin approval. Receipt mandatory."
        )
    ),

    "other": CategoryPolicy(
        name="Other Expenses",
        rate_type="actual",
        monthly_limit=5000.0,
        required_proofs=["receipt"],
        description="Miscellaneous work-related expenses. Actual amount, receipt required."
    ),
}


# ── General Policy Rules ───────────────────────────────────────────────────────

GENERAL_POLICY = {
    "company":                        "Rite Water Solutions (India) Pvt. Ltd.",
    "policy_effective_date":          "2023-11-01",
    "max_claim_period_days":          90,
    "min_claim_amount":               100.0,
    "max_single_claim":               100000.0,
    "proof_validity_days":            90,
    "allow_backdated_claims":         True,
    "max_backdate_days":              90,
    "require_manager_approval_above": 10000.0,
    "currency":                       "INR",
    "currency_symbol":                "Rs",
    # Flight policy: allowed only for VP/GM and above; distance > 500 km;
    # fare upto Rs. 5000; beyond that requires prior management approval.
    "flight_max_fare":                5000.0,
    "flight_min_distance_km":         500.0,
}


# ── City Grade Classification (Annexure) ──────────────────────────────────────

CITY_GRADES = {
    "grade_a": [
        "Delhi", "Mumbai", "Kolkata", "Chennai",
        "Ahmedabad", "Bangalore", "Hyderabad", "Jaipur", "Pune",
    ],
    "grade_b": [
        # All State Capitals plus the following Tier II cities
        "Agra", "Amritsar", "Baroda", "Faridabad", "Gaziabad",
        "Indore", "Jabalpur", "Jamshedpur", "Kanpur", "Kochi",
        "Mysuru", "Nagpur", "Surat", "Vishakapatnam",
    ],
    "grade_c": ["All other Tier III cities not listed in Grade A or Grade B"],
}


# ── Level-Based Food Allowance (Rs/day) ───────────────────────────────────────

# With overnight stay
FOOD_ALLOWANCE_WITH_STAY: Dict[str, Optional[float]] = {
    "director_cfo":                     None,   # Actual
    "vp_general_manager":               750.0,
    "senior_manager_regional_manager":  600.0,
    "manager":                          500.0,
    "asst_manager_deputy_manager":      500.0,
    "senior_executive_supervisor":      400.0,
    "technician_trainee":               400.0,
}

# Without overnight stay (>12 hrs out)
FOOD_ALLOWANCE_WITHOUT_STAY: Dict[str, Optional[float]] = {
    "director_cfo":                     None,   # Actual
    "vp_general_manager":               375.0,
    "senior_manager_regional_manager":  300.0,
    "manager":                          250.0,
    "asst_manager_deputy_manager":      250.0,
    "senior_executive_supervisor":      200.0,
    "technician_trainee":               200.0,
}


# ── Level-Based Hotel Tariff (Rs/night) by City Grade ─────────────────────────

HOTEL_LIMITS: Dict[str, Dict[str, Optional[float]]] = {
    "director_cfo": {
        "grade_a": None, "grade_b": None, "grade_c": None,  # Actual
    },
    "vp_general_manager": {
        "grade_a": 3000.0, "grade_b": 2000.0, "grade_c": 1500.0,
    },
    "senior_manager_regional_manager": {
        "grade_a": 2000.0, "grade_b": 1500.0, "grade_c": 1000.0,
    },
    "manager": {
        "grade_a": 1500.0, "grade_b": 1200.0, "grade_c": 750.0,
    },
    "asst_manager_deputy_manager": {
        "grade_a": 1200.0, "grade_b": 1000.0, "grade_c": 750.0,
    },
    "senior_executive_supervisor": {
        "grade_a": 1100.0, "grade_b": 1000.0, "grade_c": 750.0,
    },
    "technician_trainee": {
        "grade_a": 1000.0, "grade_b": 900.0,  "grade_c": 700.0,
    },
}


# ── Site Deputation Limits (>30 days, where no Guest House available) ──────────

SITE_DEPUTATION_LIMITS: Dict[str, Dict[str, Dict[str, float]]] = {
    "project_manager": {
        "grade_a": {"lodging": 12000.0, "fooding": 7000.0},
        "grade_b": {"lodging": 10000.0, "fooding": 7000.0},
        "grade_c": {"lodging":  8000.0, "fooding": 7000.0},
    },
    "asst_mgr_deputy_mgr": {
        "grade_a": {"lodging": 10500.0, "fooding": 6000.0},
        "grade_b": {"lodging":  9000.0, "fooding": 6000.0},
        "grade_c": {"lodging":  7000.0, "fooding": 6000.0},
    },
    "engineer": {
        "grade_a": {"lodging": 9000.0, "fooding": 5000.0},
        "grade_b": {"lodging": 7500.0, "fooding": 5000.0},
        "grade_c": {"lodging": 5000.0, "fooding": 5000.0},
    },
    "technician": {
        "grade_a": {"lodging": 7000.0, "fooding": 4000.0},
        "grade_b": {"lodging": 5500.0, "fooding": 4000.0},
        "grade_c": {"lodging": 4000.0, "fooding": 4000.0},
    },
}


# ── Validation Rules ───────────────────────────────────────────────────────────

VALIDATION_RULES = {
    "require_date_on_receipt":    True,
    "require_vendor_name":        True,
    "require_amount_on_receipt":  True,
    "allow_handwritten_receipts": False,
    "min_receipt_quality_score":  0.6,
    "flag_duplicate_receipts":    True,
    "flag_weekend_claims":        True,
    "flag_holiday_claims":        True,
}


# ── Distance Verification Rules ────────────────────────────────────────────────

DISTANCE_RULES = {
    "tolerance_percent":             10.0,
    "min_trip_distance_km":           2.0,
    "max_daily_distance_km":        200.0,
    "require_unolo_for_two_wheeler":  True,
    "trust_unolo_over_odometer":      True,
}


# ── Helper Functions ───────────────────────────────────────────────────────────

def get_category_policy(category: str) -> CategoryPolicy:
    """Get policy for a specific expense category."""
    return REIMBURSEMENT_POLICY.get(category.lower(), REIMBURSEMENT_POLICY["other"])


def get_city_grade(city: str) -> str:
    """Return 'grade_a', 'grade_b', or 'grade_c' for a given city name."""
    city_norm = city.strip().title()
    if city_norm in [c.title() for c in CITY_GRADES["grade_a"]]:
        return "grade_a"
    if city_norm in [c.title() for c in CITY_GRADES["grade_b"]]:
        return "grade_b"
    return "grade_c"


def get_hotel_limit(designation_key: str, city: str) -> Optional[float]:
    """Return the hotel tariff cap (Rs/night) for a designation and city, or None for Actual."""
    grade = get_city_grade(city)
    limits = HOTEL_LIMITS.get(designation_key, HOTEL_LIMITS["technician_trainee"])
    return limits.get(grade)


def calculate_eligible_amount(
    category: str,
    claimed_amount: float,
    distance_km: float = None,
    days_count: int = None,
    trip_count: int = None,
) -> tuple[float, str]:
    """
    Calculate eligible reimbursement amount based on policy.

    Returns:
        (eligible_amount, reasoning)
    """
    policy = get_category_policy(category)
    eligible = 0.0
    reasoning = ""

    if policy.rate_type == "per_km":
        if distance_km:
            calculated = distance_km * policy.rate_per_km
            eligible   = min(calculated, claimed_amount, policy.monthly_limit)
            reasoning  = f"Distance: {distance_km}km x Rs.{policy.rate_per_km}/km = Rs.{calculated:.2f}"
            if eligible < claimed_amount:
                reasoning += f" (capped at monthly limit Rs.{policy.monthly_limit})"
        else:
            reasoning = "Distance proof required for conveyance claims"
            eligible  = 0.0

    elif policy.rate_type == "actual":
        eligible  = min(claimed_amount, policy.monthly_limit)
        reasoning = f"Actual amount Rs.{claimed_amount:.2f}"
        if policy.per_trip_limit and trip_count:
            max_by_trips = trip_count * policy.per_trip_limit
            if claimed_amount > max_by_trips:
                eligible   = min(eligible, max_by_trips)
                reasoning += f" (limited by Rs.{policy.per_trip_limit}/trip x {trip_count} trips)"
        if eligible < claimed_amount:
            reasoning += f" (capped at monthly limit Rs.{policy.monthly_limit})"

    elif policy.rate_type == "daily_limit":
        if days_count:
            max_by_days = days_count * policy.daily_limit
            eligible    = min(claimed_amount, max_by_days, policy.monthly_limit)
            reasoning   = f"Rs.{policy.daily_limit}/day x {days_count} days = Rs.{max_by_days:.2f}"
            if eligible < claimed_amount:
                if eligible == policy.monthly_limit:
                    reasoning += f" (capped at monthly limit Rs.{policy.monthly_limit})"
                else:
                    reasoning += " (exceeds daily limit)"
        else:
            eligible  = min(claimed_amount, policy.monthly_limit)
            reasoning = f"Daily count not provided, using monthly limit Rs.{policy.monthly_limit}"

    return eligible, reasoning


def get_required_proofs(category: str) -> List[str]:
    """Get list of required proofs for a category."""
    return get_category_policy(category).required_proofs


def validate_claim_period(start_date: str, end_date: str) -> tuple[bool, str]:
    """Validate if claim period is within policy limits."""
    from datetime import datetime

    try:
        start  = datetime.fromisoformat(start_date)
        end    = datetime.fromisoformat(end_date)
        today  = datetime.now()

        period_days = (end - start).days
        if period_days > GENERAL_POLICY["max_claim_period_days"]:
            return False, (
                f"Claim period ({period_days} days) exceeds maximum allowed "
                f"({GENERAL_POLICY['max_claim_period_days']} days)"
            )

        if GENERAL_POLICY["allow_backdated_claims"]:
            backdate_days = (today - start).days
            if backdate_days > GENERAL_POLICY["max_backdate_days"]:
                return False, (
                    f"Claim is backdated by {backdate_days} days "
                    f"(max allowed: {GENERAL_POLICY['max_backdate_days']} days)"
                )

        return True, "Claim period is valid"

    except Exception as e:
        return False, f"Invalid date format: {str(e)}"


def get_policy_summary() -> str:
    """Generate a human-readable policy summary."""
    summary = (
        f"## {GENERAL_POLICY['company']} — Reimbursement Policy\n"
        f"Effective: {GENERAL_POLICY['policy_effective_date']}\n\n"
    )
    for key, policy in REIMBURSEMENT_POLICY.items():
        summary += f"### {policy.name}\n"
        summary += f"- **Type**: {policy.rate_type}\n"
        if policy.rate_per_km:
            summary += f"- **Rate**: Rs.{policy.rate_per_km}/km\n"
        if policy.daily_limit:
            summary += f"- **Daily Limit**: Rs.{policy.daily_limit}\n"
        if policy.per_trip_limit:
            summary += f"- **Per Trip Limit**: Rs.{policy.per_trip_limit}\n"
        if policy.monthly_limit:
            summary += f"- **Monthly Limit**: Rs.{policy.monthly_limit}\n"
        summary += f"- **Required Proofs**: {', '.join(policy.required_proofs)}\n"
        summary += f"- {policy.description}\n\n"
    return summary
