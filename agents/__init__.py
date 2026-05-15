"""Agents package for Rite Audit System."""

# Import only state module initially - other imports happen when needed
from agents.state import ClaimState, create_initial_state, ExpenseCategory, DecisionType

__all__ = [
    "ClaimState",
    "create_initial_state",
    "ExpenseCategory",
    "DecisionType",
]

# Lazy imports for agent functions
def get_agents():
    """Get all agent functions (lazy import)."""
    from agents.orchestrator import orchestrator_agent
    from agents.ingestion_agent import ingestion_agent
    from agents.data_agent import data_agent
    from agents.calculator_agent import calculator_agent
    from agents.writer import writer_agent
    from agents.critic_agent1 import critic_agent1, should_revise_data
    from agents.critic_agent2 import critic_agent2, should_revise_calculation
    from agents.critic_agent3 import critic_agent3, should_revise_report
    
    return {
        "orchestrator_agent": orchestrator_agent,
        "ingestion_agent": ingestion_agent,
        "data_agent": data_agent,
        "calculator_agent": calculator_agent,
        "writer_agent": writer_agent,
        "critic_agent1": critic_agent1,
        "critic_agent2": critic_agent2,
        "critic_agent3": critic_agent3,
        "should_revise_data": should_revise_data,
        "should_revise_calculation": should_revise_calculation,
        "should_revise_report": should_revise_report,
    }

