"""
Orchestrator Agent

Entry point for claim processing. Initializes state and validates inputs.
"""
from typing import Dict, Any
from agents.state import ClaimState
from config.policy import GENERAL_POLICY, validate_claim_period


def orchestrator_agent(state: ClaimState) -> ClaimState:
    """
    Initialize and validate claim processing.
    
    Responsibilities:
    - Validate claim amount is within limits
    - Validate claim period
    - Check required inputs are present
    - Set up processing flags
    
    Args:
        state: Current claim state
        
    Returns:
        Updated state with validation results
    """
    state["current_agent"] = "orchestrator"
    issues = []
    
    # Validate claim amount
    claimed = state.get("claimed_amount", 0)
    
    if claimed < GENERAL_POLICY["min_claim_amount"]:
        issues.append(
            f"Claim amount ₹{claimed} is below minimum ₹{GENERAL_POLICY['min_claim_amount']}"
        )
    
    if claimed > GENERAL_POLICY["max_single_claim"]:
        issues.append(
            f"Claim amount ₹{claimed} exceeds maximum ₹{GENERAL_POLICY['max_single_claim']}"
        )
    
    # Validate claim period if provided
    period_start = state.get("claim_period_start")
    period_end = state.get("claim_period_end")
    
    if period_start and period_end:
        is_valid, message = validate_claim_period(period_start, period_end)
        if not is_valid:
            issues.append(message)
    
    # Check if any inputs are provided
    images = state.get("images", [])
    documents = state.get("documents", [])
    
    if not images and not documents and not state.get("vision_data"):
        issues.append("No supporting documents or images provided")
    
    # Check if claim requires manager approval
    if claimed > GENERAL_POLICY["require_manager_approval_above"]:
        state["decision_reasoning"] = (
            f"Note: Claim exceeds ₹{GENERAL_POLICY['require_manager_approval_above']}, "
            "will require manager approval after AI review."
        )
    
    # Set validation flags
    if issues:
        state["data_validation_issues"] = issues
        state["error_message"] = "; ".join(issues)
    
    return state
