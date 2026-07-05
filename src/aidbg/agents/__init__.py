"""Agent extension slot.

Each module registers one :class:`AgentSpec` at import time. Sub-agents must be
imported before the orchestrator so ``delegates_to`` can resolve them. Import
new agent modules here.
"""

# Register children first, then the orchestrator (which references them).
from aidbg.agents import code_reviewer, coder, log_analyst, researcher  # noqa: F401
from aidbg.agents import orchestrator  # noqa: F401

__all__ = ["code_reviewer", "coder", "log_analyst", "orchestrator", "researcher"]
