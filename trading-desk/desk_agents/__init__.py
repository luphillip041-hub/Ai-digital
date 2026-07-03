"""Native multi-agent trading desk for Flip.

Replaces the external TauricResearch/TradingAgents dependency with an
in-repo orchestrator + sub-agent engine. Every LLM call is planned,
counted, and budgeted; market data is gathered deterministically before
any agent runs so there are no unpredictable tool loops.
"""

from desk_agents.llm import ChatClient, LLMConfig, UsageMeter
from desk_agents.orchestrator import DeskOrchestrator, planned_calls
from desk_agents.subagent import SubAgent

__all__ = [
    "ChatClient",
    "LLMConfig",
    "UsageMeter",
    "SubAgent",
    "DeskOrchestrator",
    "planned_calls",
]
