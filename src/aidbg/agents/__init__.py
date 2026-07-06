"""Agent extension slot.

Each module registers one :class:`AgentSpec` at import time. Sub-agents must be
imported before the orchestrator so ``delegates_to`` can resolve them. Import
new agent modules here.
"""

# Register children first, then the orchestrator (which references them).
from aidbg.agents import case_rag, case_recorder, code_research, log_analyst  # noqa: F401
from aidbg.agents import orchestrator  # noqa: F401

__all__ = [
    "case_rag",
    "case_recorder",
    "code_research",
    "log_analyst",
    "orchestrator",
]
