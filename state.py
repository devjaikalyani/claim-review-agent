"""
State definition for the Rite Audit System pipeline.
Uses TypedDict for LangGraph state management.
"""
from typing import TypedDict, List, Optional, Dict, Any, Literal
from dataclasses import dataclass, field
from enum import Enum


class ExpenseCategory(str, Enum):
    """Categories of expenses that can be claimed."""
    TWO_WHEELER    = "two_wheeler"
    CAR_CONVEYANCE = "car_conveyance"
    BUS_TRAVEL     = "bus_travel"
    FASTTAG        = "fasttag"
    FOOD           = "food"
    HOTEL          = "hotel"
    SITE_EXPENSES  = "site_expenses"
    OTHER          = "other"


class DecisionType(str, Enum):
    """Types of claim decisions."""
    FULL_APPROVAL    = "full_approval"
    PARTIAL_APPROVAL = "partial_approval"
    REJECTED         = "rejected"
    PENDING_REVIEW   = "pending_review"


@dataclass
class ExtractedExpense:
    """Single expense item extracted from documents."""
    category:         ExpenseCategory
    amount:           float
    date:             str
    description:      str
    source_document:  str
    confidence:       float = 1.0
    is_valid:         bool  = True
    validation_notes: str   = ""


@dataclass
class CategorySummary:
    """Summary of expenses per category."""
    category:       ExpenseCategory
    total_claimed:  float
    total_eligible: float
    items:          List[ExtractedExpense] = field(default_factory=list)
    policy_limit:   float                  = 0.0
    exceeded_limit: bool                   = False
    missing_proofs: List[str]              = field(default_factory=list)


@dataclass
class ClaimDecision:
    """Final decision on the claim."""
    decision_type:      DecisionType
    claimed_amount:     float
    approved_amount:    float
    rejection_reasons:  List[str]                 = field(default_factory=list)
    partial_reasons:    List[str]                 = field(default_factory=list)
    category_breakdown: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    recommendations:    List[str]                 = field(default_factory=list)


class ClaimState(TypedDict, total=False):
    """
    Main state object flowing through the LangGraph pipeline.

    This state is passed between all agents and accumulates
    information as the claim is processed.
    """
    # ── Claim identification ──────────────────────────────────────────────
    claim_id:           str
    employee_id:        str
    employee_name:      str
    submission_date:    str
    claim_period_start: str
    claim_period_end:   str

    # ── Input data ────────────────────────────────────────────────────────
    claimed_amount:    float
    claim_description: str
    images:            List[str]               # image file paths or base64
    documents:         List[str]               # document file paths
    vision_data:       Optional[Dict[str, Any]]
    emp_distance_km:   Optional[float]
    eligible_distance_km: Optional[float]
    unolo_distance_km: Optional[float]         # GPS-verified distance
    spine_hr_data:     Optional[Dict[str, Any]]
    employee_summary:  Optional[Dict[str, Any]]  # Parsed expense voucher PDF — for Critic 2

    # ── Extracted data (populated by ingestion agent) ─────────────────────
    extracted_text: List[Dict[str, str]]       # [{source: str, text: str}]
    ocr_confidence: float

    # ── Structured data (populated by data agent) ─────────────────────────
    expenses:               List[Dict[str, Any]]
    categories:             Dict[str, Dict[str, Any]]
    total_extracted_amount: float               # sum of individual receipt amounts
    duplicates_removed:     List[str]           # human-readable list of auto-removed duplicates
    rejected_expenses:      List[Dict[str, Any]]  # structured rejected items for admin review

    # ── Validation (populated by critic agents) ───────────────────────────
    data_validation_passed:  bool
    data_validation_issues:  List[str]

    calculation_validation_passed:   bool
    calculation_validation_issues:   List[str]
    calculation_validation_warnings: List[str]

    report_validation_passed: bool
    report_validation_issues: List[str]

    # ── Calculations (populated by calculator agent) ───────────────────────
    eligible_amount:   float
    category_eligible: Dict[str, Dict[str, Any]]
    policy_violations: List[str]

    # Reconciliation data (set by calculator, read by critic2)
    category_claimed_total: float
    extraction_gap:         float
    reconciliation_note:    str

    # ── Decision (populated by writer agent) ──────────────────────────────
    decision:           str
    approved_amount:    float
    decision_reasoning: str
    category_breakdown: Dict[str, Dict[str, Any]]

    # ── Report (populated by writer agent) ────────────────────────────────
    final_report: str

    # ── Voucher pipeline ──────────────────────────────────────────────────────
    # Per-item decisions from voucher_judgment_agent — set in initial state so
    # admin_judgment_agent applies them directly instead of re-running LLM.
    voucher_line_decisions: Optional[List[Dict[str, Any]]]

    # ── Control flow ──────────────────────────────────────────────────────
    current_agent:         str
    revision_count:        int
    max_revisions:         int
    data_revision_count:   int
    calc_revision_count:   int
    report_revision_count: int
    error_message:         Optional[str]
    processing_complete:   bool
    test_mode:             bool
    admin_judgment_failed: bool  # True when LLM call failed — forces pending_review


def create_initial_state(
    claim_id:           str,
    employee_id:        str,
    employee_name:      str,
    claimed_amount:     float,
    images:             List[str] = None,
    documents:          List[str] = None,
    vision_data:        Optional[Dict[str, Any]] = None,
    emp_distance_km:    float     = None,
    eligible_distance_km: float   = None,
    unolo_distance_km:  float     = None,
    claim_period_start: str       = None,
    claim_period_end:   str       = None,
    claim_description:  str       = "",
) -> ClaimState:
    """
    Create an initial state for a new claim review.

    Args:
        claim_id:           Unique identifier for the claim
        employee_id:        Employee ID from HR system
        employee_name:      Employee name
        claimed_amount:     Total amount being claimed
        images:             List of image paths/base64 strings
        documents:          List of document paths
        unolo_distance_km:  Distance from Unolo tracking
        claim_period_start: Start date of claim period (ISO format)
        claim_period_end:   End date of claim period (ISO format)
        claim_description:  Optional description of the claim

    Returns:
        Initialized ClaimState
    """
    from datetime import datetime

    if not claim_id:
        raise ValueError("claim_id must be non-empty")
    if not employee_id:
        raise ValueError("employee_id must be non-empty")
    if claimed_amount <= 0:
        raise ValueError(f"claimed_amount must be positive, got {claimed_amount}")

    return ClaimState(
        # Identification
        claim_id=claim_id,
        employee_id=employee_id,
        employee_name=employee_name,
        submission_date=datetime.now().isoformat(),
        claim_period_start=claim_period_start or "",
        claim_period_end=claim_period_end or "",

        # Inputs
        claimed_amount=claimed_amount,
        claim_description=claim_description,
        images=images or [],
        documents=documents or [],
        vision_data=vision_data,
        emp_distance_km=emp_distance_km,
        eligible_distance_km=eligible_distance_km,
        unolo_distance_km=unolo_distance_km,
        spine_hr_data=None,
        employee_summary=None,  # Populated by ingestion/data agent from summary PDF

        # Extracted data
        extracted_text=[],
        ocr_confidence=0.0,

        # Structured data
        expenses=[],
        categories={},
        total_extracted_amount=0.0,
        duplicates_removed=[],
        rejected_expenses=[],

        # Validation flags
        data_validation_passed=False,
        data_validation_issues=[],

        calculation_validation_passed=False,
        calculation_validation_issues=[],
        calculation_validation_warnings=[],

        report_validation_passed=False,
        report_validation_issues=[],

        # Calculations
        eligible_amount=0.0,
        category_eligible={},
        policy_violations=[],

        # Reconciliation
        category_claimed_total=0.0,
        extraction_gap=0.0,
        reconciliation_note="",

        # Decision
        decision="pending_review",
        approved_amount=0.0,
        decision_reasoning="",
        category_breakdown={},

        # Report
        final_report="",

        # Voucher pipeline
        voucher_line_decisions=None,

        # Control flow
        current_agent="orchestrator",
        revision_count=0,
        max_revisions=3,
        data_revision_count=0,
        calc_revision_count=0,
        report_revision_count=0,
        error_message=None,
        processing_complete=False,
        test_mode=False,
        admin_judgment_failed=False,
    )


def require_fields(state: "ClaimState", agent_name: str, *fields: str) -> None:
    """Raise ValueError if any required field is absent or None in state.
    Call at the top of each agent node to catch missing upstream data early.
    """
    missing = [f for f in fields if state.get(f) is None]
    if missing:
        raise ValueError(
            f"[{agent_name}] Missing required state fields: {', '.join(missing)}"
        )
