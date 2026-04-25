"""
LangGraph Pipeline for Claim Review

Flow:
    orchestrator → ingestion → data → admin_judgment → critic1 → calculator → critic2 → writer → critic3 → END
                                            |               ^           |           ^        |        ^        |
                                            |               └──revise───┘           └─revise─┘        └─revise─┘
                                            └── (skipped when expense voucher is present)

Node responsibilities:
    orchestrator    — validate claim amount, dates, required inputs
    ingestion       — scan receipts via Claude Vision (fast-path if pre-scanned)
    data            — structure receipts into expense categories; deduplicate
    admin_judgment  — LLM judgment using 83+ training examples; skip if voucher present
    critic1         — validate data completeness & OCR confidence; revise → data
    calculator      — apply policy caps per category (voucher path: trust admin amounts)
    critic2         — verify calculations & reconciliation; revise → calculator
    writer          — generate final decision report; auto-save voucher to training DB
    critic3         — review report quality; revise → writer
"""
from typing import Generator, Tuple

from langgraph.graph import StateGraph, END
from agents.state import ClaimState, create_initial_state
from agents.orchestrator import orchestrator_agent
from agents.ingestion_agent import ingestion_agent
from agents.data_agent import data_agent
from agents.calculator_agent import calculator_agent
from agents.writer import writer_agent
from agents.critic_agent1 import critic_agent1, should_revise_data
from agents.critic_agent2 import critic_agent2, should_revise_calculation
from agents.critic_agent3 import critic_agent3, should_revise_report
from agents.admin_judgment_agent import admin_judgment_agent


def build_graph():
    """Build the LangGraph workflow for claim review."""
    workflow = StateGraph(ClaimState)

    workflow.add_node("orchestrator",    orchestrator_agent)
    workflow.add_node("ingestion",       ingestion_agent)
    workflow.add_node("data",            data_agent)
    workflow.add_node("admin_judgment",  admin_judgment_agent)
    workflow.add_node("critic1",         critic_agent1)
    workflow.add_node("calculator",      calculator_agent)
    workflow.add_node("critic2",         critic_agent2)
    workflow.add_node("writer",          writer_agent)
    workflow.add_node("critic3",         critic_agent3)

    workflow.set_entry_point("orchestrator")

    workflow.add_edge("orchestrator",   "ingestion")
    workflow.add_edge("ingestion",      "data")
    workflow.add_edge("data",           "admin_judgment")
    workflow.add_edge("admin_judgment", "critic1")

    workflow.add_conditional_edges(
        "critic1",
        should_revise_data,
        {"revise": "data", "end": "calculator"},
    )

    workflow.add_edge("calculator", "critic2")

    workflow.add_conditional_edges(
        "critic2",
        should_revise_calculation,
        {"revise": "calculator", "end": "writer"},
    )

    workflow.add_edge("writer", "critic3")

    workflow.add_conditional_edges(
        "critic3",
        should_revise_report,
        {"revise": "writer", "end": END},
    )

    return workflow.compile()


# Human-readable labels shown in the streaming UI
_STEP_LABELS: dict[str, str] = {
    "orchestrator":   "Validating claim inputs",
    "ingestion":      "Scanning receipts and documents",
    "data":           "Structuring expense categories",
    "admin_judgment": "Applying admin judgment",
    "critic1":        "Validating data completeness",
    "calculator":     "Applying policy rules",
    "critic2":        "Verifying calculations",
    "writer":         "Generating decision report",
    "critic3":        "Reviewing report quality",
}


def review_claim_stream(
    claim_id:             str,
    employee_id:          str,
    employee_name:        str,
    claimed_amount:       float,
    images:               list = None,
    documents:            list = None,
    vision_data:          dict = None,
    emp_distance_km:      float = None,
    eligible_distance_km: float = None,
    unolo_distance_km:    float = None,
    claim_period_start:   str = None,
    claim_period_end:     str = None,
    claim_description:    str = "",
    test_mode:            bool = False,
) -> Generator[Tuple[str, str, ClaimState], None, None]:
    """
    Stream claim review events as each agent node completes.

    Yields (node_name, step_label, accumulated_state) after each node finishes.
    The last yielded state is the final result — no separate review_claim() call needed.
    """
    initial_state = create_initial_state(
        claim_id=claim_id,
        employee_id=employee_id,
        employee_name=employee_name,
        claimed_amount=claimed_amount,
        images=images,
        documents=documents,
        vision_data=vision_data,
        emp_distance_km=emp_distance_km,
        eligible_distance_km=eligible_distance_km,
        unolo_distance_km=unolo_distance_km,
        claim_period_start=claim_period_start,
        claim_period_end=claim_period_end,
        claim_description=claim_description,
    )
    initial_state["test_mode"] = test_mode

    graph        = build_graph()
    config       = {"recursion_limit": 75}  # 9 nodes × up to 3 revisions each
    final_state  = dict(initial_state)

    try:
        for event in graph.stream(initial_state, config=config):
            node_name     = list(event.keys())[0]
            partial_state = event[node_name]
            final_state.update(partial_state)
            label = _STEP_LABELS.get(node_name, node_name.replace("_", " ").title())
            yield node_name, label, final_state
    except Exception as exc:
        final_state["error_message"]      = f"Pipeline error in agent node: {exc}"
        final_state["processing_complete"] = True
        yield "__error__", "Pipeline error", final_state


def review_claim(
    claim_id:             str,
    employee_id:          str,
    employee_name:        str,
    claimed_amount:       float,
    images:               list = None,
    documents:            list = None,
    vision_data:          dict = None,
    emp_distance_km:      float = None,
    eligible_distance_km: float = None,
    unolo_distance_km:    float = None,
    claim_period_start:   str = None,
    claim_period_end:     str = None,
    claim_description:    str = "",
) -> dict:
    """Non-streaming entry point — runs the full pipeline and returns final state."""
    final_state = None
    for _, _, state in review_claim_stream(
        claim_id=claim_id,
        employee_id=employee_id,
        employee_name=employee_name,
        claimed_amount=claimed_amount,
        images=images,
        documents=documents,
        vision_data=vision_data,
        emp_distance_km=emp_distance_km,
        eligible_distance_km=eligible_distance_km,
        unolo_distance_km=unolo_distance_km,
        claim_period_start=claim_period_start,
        claim_period_end=claim_period_end,
        claim_description=claim_description,
    ):
        final_state = state
    return final_state or {}


def review_voucher_stream(
    claim_id:             str,
    voucher_data:         dict,
    proof_ocr_results:    list = None,
    odometer_distance_km: float = None,
    test_mode:            bool = False,
) -> Generator[Tuple[str, str, ClaimState], None, None]:
    """
    Run the full graph pipeline for a SpineHR expense voucher.

    Mirrors review_claim_stream() exactly:
      1. voucher_judgment_agent computes per-item LLM decisions (same logic as before)
      2. Initial ClaimState is built with those decisions in voucher_line_decisions
      3. Full graph runs: ingestion → data → admin_judgment (applies decisions) →
         critic1 → calculator → critic2 → writer → critic3
      4. All critic loops, policy enforcement, and report generation run as normal

    Yields (node_name, step_label, accumulated_state) after each node.
    """
    from agents.voucher_judgment_agent import review_voucher
    from agents.state import ExpenseCategory

    # ── Step 1: Per-item LLM judgment ─────────────────────────────────────────
    decisions = review_voucher(
        voucher_data=voucher_data,
        proof_ocr_results=proof_ocr_results or [],
        odometer_distance_km=odometer_distance_km,
        test_mode=test_mode,
    )

    total_claimed  = sum(d["claimed_amount"]  for d in decisions)
    total_approved = sum(d["approved_amount"] for d in decisions)

    # ── Step 2: Build employee_summary for data_agent path A ─────────────────
    # Map voucher expense heads to canonical categories
    _HEAD_MAP = {
        "2 wheeler": ExpenseCategory.TWO_WHEELER.value,
        "2_wheeler": ExpenseCategory.TWO_WHEELER.value,
        "two_wheeler": ExpenseCategory.TWO_WHEELER.value,
        "food allowance": ExpenseCategory.FOOD.value,
        "food_allowance": ExpenseCategory.FOOD.value,
        "food": ExpenseCategory.FOOD.value,
        "bus travel": ExpenseCategory.BUS_TRAVEL.value,
        "bus_travel": ExpenseCategory.BUS_TRAVEL.value,
        "fasttag": ExpenseCategory.FASTTAG.value,
        "site expenses": ExpenseCategory.SITE_EXPENSES.value,
        "site_expenses": ExpenseCategory.SITE_EXPENSES.value,
        "other expense": ExpenseCategory.OTHER.value,
        "other_expense": ExpenseCategory.OTHER.value,
        "other": ExpenseCategory.OTHER.value,
    }

    cat_summary: dict = {}
    for d in decisions:
        head_key = d.get("expense_head", "other").strip().lower()
        cat = (
            d.get("category")
            or _HEAD_MAP.get(head_key)
            or ExpenseCategory.OTHER.value
        )
        if cat not in cat_summary:
            cat_summary[cat] = {"claimed": 0.0, "approved": 0.0, "items": []}
        cat_summary[cat]["claimed"]  += d["claimed_amount"]
        cat_summary[cat]["approved"] += d["approved_amount"]
        cat_summary[cat]["items"].append({
            "expense_head": d["expense_head"],
            "amount":       d["claimed_amount"],
            "date":         d.get("date", ""),
        })

    employee_summary = {
        "is_summary":       True,
        "voucher_no":       voucher_data.get("voucher_no", ""),
        "period":           (
            f"{voucher_data.get('period_start','')} to "
            f"{voucher_data.get('period_end','')}"
        ),
        "employee_name":    voucher_data.get("employee_name", ""),
        "employee_code":    voucher_data.get("employee_code", ""),
        "summary_total":    total_claimed,
        "summary_approved": total_approved,
        "categories":       cat_summary,
        "path":             "expense_voucher",
    }

    # ── Step 3: Build vision_data for ingestion_agent fast path ──────────────
    vision_data = {
        "has_summary":          True,
        "employee_summary":     employee_summary,
        "receipts":             proof_ocr_results or [],
        "odometer_readings":    [],
        "odometer_distance_km": odometer_distance_km,
        "total_extracted":      total_claimed,
        "errors":               [],
    }

    # ── Step 4: Build initial state and run full graph ────────────────────────
    initial_state = create_initial_state(
        claim_id=claim_id,
        employee_id=voucher_data.get("employee_code", ""),
        employee_name=voucher_data.get("employee_name", ""),
        claimed_amount=total_claimed,
        vision_data=vision_data,
        unolo_distance_km=odometer_distance_km,
        claim_period_start=voucher_data.get("period_start", ""),
        claim_period_end=voucher_data.get("period_end", ""),
        claim_description=voucher_data.get("narration", ""),
    )
    initial_state["test_mode"]             = test_mode
    initial_state["voucher_line_decisions"] = decisions
    initial_state["employee_summary"]      = employee_summary

    graph        = build_graph()
    config       = {"recursion_limit": 75}
    final_state  = dict(initial_state)

    try:
        for event in graph.stream(initial_state, config=config):
            node_name     = list(event.keys())[0]
            partial_state = event[node_name]
            final_state.update(partial_state)
            label = _STEP_LABELS.get(node_name, node_name.replace("_", " ").title())
            yield node_name, label, final_state
    except Exception as exc:
        final_state["error_message"]       = f"Pipeline error: {exc}"
        final_state["processing_complete"] = True
        yield "__error__", "Pipeline error", final_state


__all__ = ["build_graph", "review_claim", "review_claim_stream", "review_voucher_stream"]
